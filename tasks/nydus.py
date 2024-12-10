from invoke import task
from os.path import join
from subprocess import run
from tasks.util.env import GHCR_URL, GITHUB_ORG, PROJ_ROOT
from tasks.util.nydus import NYDUSIFY_PATH
from tasks.util.versions import NYDUS_VERSION, NYDUS_SNAPSHOTTER_VERSION

NYDUS_CTR_NAME = "nydus-workon"
NYDUS_SNAPSHOTTER_CTR_NAME = "nydus-snapshotter-workon"
NYDUS_IMAGE_TAG = join(GHCR_URL, GITHUB_ORG, "nydus") + f":{NYDUS_VERSION}"
NYDUS_SNAPSHOTTER_IMAGE_TAG = (
    join(GHCR_URL, GITHUB_ORG, "nydus-snapshotter") + f":{NYDUS_SNAPSHOTTER_VERSION}"
)


@task
def build(ctx, nocache=False, push=False):
    """
    Build the nydusd and nydus-snapshotter images
    """
    for image_tag in [NYDUS_IMAGE_TAG, NYDUS_SNAPSHOTTER_IMAGE_TAG]:
        dockerfile = "nydus" if image_tag == NYDUS_IMAGE_TAG else "nydus_snapshotter"
        dockerfile += ".dockerfile"
        docker_cmd = "docker build {} -t {} -f {} .".format(
            "--no-cache" if nocache else "",
            image_tag,
            join(PROJ_ROOT, "docker", dockerfile),
        )
        run(docker_cmd, shell=True, check=True, cwd=PROJ_ROOT)

        if push:
            run(f"docker push {image_tag}", shell=True, check=True)


def do_install_nydus(debug=False):
    docker_cmd = "docker run -td --name {} {} bash".format(
        NYDUS_CTR_NAME, NYDUS_IMAGE_TAG
    )
    result = run(docker_cmd, shell=True, capture_output=True)
    assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
    if debug:
        print(result.stdout.decode("utf-8").strip())

    def cleanup():
        docker_cmd = "docker rm -f {}".format(NYDUS_CTR_NAME)
        result = run(docker_cmd, shell=True, capture_output=True)
        assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
        if debug:
            print(result.stdout.decode("utf-8").strip())

    base_ctr_dir = "/go/src/github.com/sc2-sys/nydus"
    binaries = [
        {
            "ctr_path": f"{base_ctr_dir}/contrib/nydusify/cmd/nydusify",
            "host_path": NYDUSIFY_PATH,
        }
    ]
    for binary in binaries:
        docker_cmd = "docker cp {}:{} {}".format(
            NYDUS_CTR_NAME, binary["ctr_path"], binary["host_path"]
        )
        result = run(docker_cmd, shell=True, capture_output=True)
        assert result.returncode == 0, (
            cleanup(),
            print(result.stderr.decode("utf-8").strip()),
        )
        if debug:
            print(result.stdout.decode("utf-8").strip())

    cleanup()


def do_install_nydus_snapshotter(debug=False, clean=False):
    docker_cmd = "docker run -td --name {} {} bash".format(
        NYDUS_SNAPSHOTTER_CTR_NAME, NYDUS_SNAPSHOTTER_IMAGE_TAG
    )
    result = run(docker_cmd, shell=True, capture_output=True)
    assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
    if debug:
        print(result.stdout.decode("utf-8").strip())

    def cleanup():
        docker_cmd = "docker rm -f {}".format(NYDUS_SNAPSHOTTER_CTR_NAME)
        result = run(docker_cmd, shell=True, capture_output=True)
        assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
        if debug:
            print(result.stdout.decode("utf-8").strip())

    binary_names = [
        "containerd-nydus-grpc",
        "nydus-overlayfs",
    ]
    ctr_base_path = "/go/src/github.com/sc2-sys/nydus-snapshotter/bin"
    host_base_path = "/opt/confidential-containers/bin"
    for binary in binary_names:
        docker_cmd = "sudo docker cp {}:{}/{} {}/{}".format(
            NYDUS_SNAPSHOTTER_CTR_NAME, ctr_base_path, binary, host_base_path, binary
        )
        result = run(docker_cmd, shell=True, capture_output=True)
        assert result.returncode == 0, (
            cleanup(),
            print(result.stderr.decode("utf-8").strip()),
        )

    cleanup()

    # Remove all nydus config for a clean start
    if clean:
        run("sudo rm -rf /var/lib/containerd-nydus", shell=True, check=True)

    # Restart the nydus service
    run("sudo service nydus-snapshotter restart", shell=True, check=True)


@task
def install(ctx, debug=False, clean=False):
    """
    Install the nydus snapshotter binaries and the nydusify CLI tool
    """
    do_install_nydus(debug=debug)
    do_install_nydus_snapshotter(debug=debug, clean=clean)
