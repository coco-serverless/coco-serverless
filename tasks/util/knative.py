from os import makedirs
from os.path import exists, join
from subprocess import run
from tasks.util.env import CONF_FILES_DIR, LOCAL_REGISTRY_URL, TEMPLATED_FILES_DIR
from tasks.util.k8s import template_k8s_file
from tasks.util.kubeadm import run_kubectl_command
from tasks.util.registry import K8S_SECRET_NAME
from time import sleep

# Knative Serving Side-Car Tag
KNATIVE_SIDECAR_IMAGE_TAG = "gcr.io/knative-releases/knative.dev/serving/cmd/"
KNATIVE_SIDECAR_IMAGE_TAG += (
    "queue@sha256:987f53e3ead58627e3022c8ccbb199ed71b965f10c59485bab8015ecf18b44af"
)


def replace_sidecar(
    reset_default=False, image_repo=LOCAL_REGISTRY_URL, quiet=False, skip_push=False
):
    def do_run(cmd, quiet):
        if quiet:
            out = run(cmd, shell=True, capture_output=True)
            assert out.returncode == 0, "Error running cmd: {} (error: {})".format(
                cmd, out.stderr
            )
        else:
            out = run(cmd, shell=True, check=True)

    k8s_filename = "knative_replace_sidecar.yaml"

    if reset_default:
        in_k8s_file = join(CONF_FILES_DIR, "{}.j2".format(k8s_filename))
        out_k8s_file = join(TEMPLATED_FILES_DIR, k8s_filename)
        template_k8s_file(
            in_k8s_file,
            out_k8s_file,
            {"knative_sidecar_image_url": KNATIVE_SIDECAR_IMAGE_TAG},
        )
        run_kubectl_command("apply -f {}".format(out_k8s_file), capture_output=quiet)
        return

    # Pull the right Knative Serving side-car image tag
    docker_cmd = "docker pull {}".format(KNATIVE_SIDECAR_IMAGE_TAG)
    do_run(docker_cmd, quiet)

    # Re-tag it, and push it to our controlled registry
    image_name = "system/knative-sidecar"
    image_tag = "unencrypted"
    new_image_url = "{}/{}:{}".format(image_repo, image_name, image_tag)
    docker_cmd = "docker tag {} {}".format(KNATIVE_SIDECAR_IMAGE_TAG, new_image_url)
    do_run(docker_cmd, quiet)

    if not skip_push:
        docker_cmd = "docker push {}".format(new_image_url)

        # Retry a few times, as the registry may be booting up
        num_retries = 3
        for i in range(num_retries):
            try:
                do_run(docker_cmd, quiet)
                break
            except AssertionError:
                sleep(3)
                continue

    # Get the digest for the recently pulled image, and use it to update
    # Knative's deployment configmap
    docker_cmd = 'docker images {} --digests --format "{{{{.Digest}}}}"'.format(
        join(image_repo, image_name),
    )
    image_digest = (
        run(docker_cmd, shell=True, capture_output=True).stdout.decode("utf-8").strip()
    )
    assert len(image_digest) > 0

    if not exists(TEMPLATED_FILES_DIR):
        makedirs(TEMPLATED_FILES_DIR)

    in_k8s_file = join(CONF_FILES_DIR, "{}.j2".format(k8s_filename))
    out_k8s_file = join(TEMPLATED_FILES_DIR, k8s_filename)
    new_image_url_digest = "{}/{}@{}".format(image_repo, image_name, image_digest)
    template_k8s_file(
        in_k8s_file, out_k8s_file, {"knative_sidecar_image_url": new_image_url_digest}
    )
    run_kubectl_command("apply -f {}".format(out_k8s_file), capture_output=quiet)

    # FIXME: to prevent an issue with nydus, we need to manually fetch the
    # contents of the image
    result = run(
        f"sudo ctr -n k8s.io content fetch -k {new_image_url}",
        shell=True,
        capture_output=True,
    )
    assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
    if not quiet:
        print(result.stdout.decode("utf-8").strip())

    # Finally, make sure to remove all pulled container images to avoid
    # unintended caching issues with CoCo
    docker_cmd = "docker rmi {}".format(KNATIVE_SIDECAR_IMAGE_TAG)
    do_run(docker_cmd, quiet)
    docker_cmd = "docker rmi {}".format(new_image_url)
    do_run(docker_cmd, quiet)


def configure_self_signed_certs(
    path_to_certs_dir, secret_name=K8S_SECRET_NAME, debug=False
):
    """
    Configure Knative to like our self-signed certificates
    """
    k8s_filename = "knative_controller_custom_certs.yaml"
    in_k8s_file = join(CONF_FILES_DIR, "{}.j2".format(k8s_filename))
    out_k8s_file = join(TEMPLATED_FILES_DIR, k8s_filename)
    template_k8s_file(
        in_k8s_file,
        out_k8s_file,
        {"path_to_certs": path_to_certs_dir, "secret_name": secret_name},
    )
    run_kubectl_command(
        "-n knative-serving patch deployment controller --patch-file {}".format(
            out_k8s_file
        ),
        capture_output=not debug,
    )


def patch_autoscaler(debug=False):
    """
    Patch Knative's auto-scaler so that our services are initially scaled-down
    to zero. They will scale-up the first time we send an HTTP request.
    """
    k8s_filename = "knative_autoscaler_patch.yaml"
    run_kubectl_command(
        "-n knative-serving patch configmap config-autoscaler --patch-file {}".format(
            join(CONF_FILES_DIR, k8s_filename)
        ),
        capture_output=not debug,
    )
