from invoke import task
from os.path import exists, join
from subprocess import run
from tasks.util.env import GHCR_URL, GITHUB_ORG
from tasks.util.kbs import (
    SIMPLE_KBS_DIR,
    SIGNATURE_POLICY_NONE,
    clear_kbs_db,
    get_kbs_db_ip,
    provision_launch_digest as do_provision_launch_digest,
)

SIMPLE_KBS_SERVER_IMAGE_NAME = join(GHCR_URL, GITHUB_ORG, "simple-kbs-server:latest")
COMPOSE_ENV = {"SIMPLE_KBS_IMAGE": SIMPLE_KBS_SERVER_IMAGE_NAME}


def check_kbs_dir():
    if not exists(SIMPLE_KBS_DIR):
        print("Error: could not find local KBS checkout at {}".format(SIMPLE_KBS_DIR))
        print(
            "Have you initialized the git submodules?"
            "Run: git submodule update --init"
        )
        raise RuntimeError("Simple KBS local checkout not found!")

    target_dir = join(SIMPLE_KBS_DIR, "target")
    if not exists(target_dir):
        print("Populating {} with the pre-compiled binaries...".format(target_dir))
        tmp_ctr_name = "simple-kbs-workon"
        docker_cmd = "docker run -d --entrypoint bash --name {} {}".format(
            tmp_ctr_name, SIMPLE_KBS_SERVER_IMAGE_NAME
        )
        run(docker_cmd, shell=True, check=True)

        cp_cmd = "docker cp {}:/usr/src/simple-kbs/target {}".format(
            tmp_ctr_name, target_dir
        )
        run(cp_cmd, shell=True, check=True)

        run("docker rm -f {}".format(tmp_ctr_name), shell=True, check=True)


@task
def build(ctx, push=False):
    """
    Build the simple-kbs image
    """
    docker_cmd = "docker build -t {} -f {} {}".format(
        SIMPLE_KBS_SERVER_IMAGE_NAME,
        join(SIMPLE_KBS_DIR, "Dockerfile.simple-kbs"),
        SIMPLE_KBS_DIR,
    )

    run(docker_cmd, shell=True, check=True)

    if push:
        run(
            "docker push {}".format(SIMPLE_KBS_SERVER_IMAGE_NAME),
            shell=True,
            check=True,
        )


@task
def cli(ctx):
    """
    Get a development CLI in the simple KBS server
    """
    # Make sure the KBS is running
    check_kbs_dir()
    run(
        "docker compose up -d --no-recreate cli",
        shell=True,
        check=True,
        cwd=SIMPLE_KBS_DIR,
        env=COMPOSE_ENV,
    )
    run(
        "docker compose exec -it cli bash",
        shell=True,
        check=True,
        cwd=SIMPLE_KBS_DIR,
        env=COMPOSE_ENV,
    )


@task
def restart(ctx):
    """
    Start the simple KBS service
    """
    check_kbs_dir()
    run(
        "docker compose restart server",
        shell=True,
        check=True,
        cwd=SIMPLE_KBS_DIR,
        env=COMPOSE_ENV,
    )


@task
def start(ctx):
    """
    Start the simple KBS service
    """
    check_kbs_dir()
    run(
        "docker compose up -d server",
        shell=True,
        check=True,
        cwd=SIMPLE_KBS_DIR,
        env=COMPOSE_ENV,
    )


@task
def stop(ctx):
    """
    Stop the simple KBS service
    """
    check_kbs_dir()
    run(
        "docker compose down",
        shell=True,
        check=True,
        cwd=SIMPLE_KBS_DIR,
        env=COMPOSE_ENV,
    )


@task
def clear_db(ctx, skip_secrets=False):
    """
    Clear the contents of the KBS DB
    """
    clear_kbs_db(skip_secrets=skip_secrets)


@task
def get_db_ip(ctx):
    print(get_kbs_db_ip())


@task
def provision_launch_digest(ctx, signature_policy=SIGNATURE_POLICY_NONE, clean=False):
    """
    Provision the KBS with the launch digest for the current node

    In order to make the Kata Agent validate the FW launch digest measurement
    we need to enable signature verification. Signature verification has an
    associated resource that contains the verification policy. By associating
    this resource to a launch digest policy (beware of the `policy` term
    overloading, but these are KBS terms), we force the Kata Agent to also
    enforce the launch digest policy.

    We support different kinds of signature verification policies, and only
    one kind of launch digest policy.

    For signature verification, we have:
    - the NONE policy, that accepts all images
    - the VERIFY policy, that verifies all (unencrypted) images

    For launch digest, we manually generate the measure digest, and include it
    in the policy. If the FW digest is not exactly the one in the policy, boot
    fails.
    """
    # For the purposes of the demo, we hardcode the images we include in the
    # policy to be included in the signature policy
    images_to_sign = [
        f"docker.io/{GITHUB_ORG}/coco-helloworld-py",
        f"docker.io/{GITHUB_ORG}/coco-knative-sidecar",
        f"ghcr.io/{GITHUB_ORG}/coco-helloworld-py",
        f"ghcr.io/{GITHUB_ORG}/coco-knative-sidecar",
        f"registry.coco-csg.com/{GITHUB_ORG}/coco-helloworld-py",
        f"registry.coco-csg.com/{GITHUB_ORG}/coco-knative-sidecar",
    ]

    do_provision_launch_digest(
        images_to_sign, signature_policy=signature_policy, clean=clean
    )
