from invoke import task
from os.path import exists
from subprocess import run
from tasks.util.kbs import (
    SIMPLE_KBS_DIR,
    SIGNATURE_POLICY_NONE,
    clear_kbs_db,
    provision_launch_digest as do_provision_launch_digest,
)


def check_kbs_dir():
    if not exists(SIMPLE_KBS_DIR):
        print("Error: could not find local KBS checkout at {}".format(SIMPLE_KBS_DIR))
        raise RuntimeError("Simple KBS local checkout not found!")


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
    )
    run("docker compose exec -it cli bash", shell=True, check=True, cwd=SIMPLE_KBS_DIR)


@task
def start(ctx):
    """
    Start the simple KBS service
    """
    check_kbs_dir()
    run("docker compose up -d server", shell=True, check=True, cwd=SIMPLE_KBS_DIR)


@task
def stop(ctx):
    """
    Stop the simple KBS service
    """
    check_kbs_dir()
    run("docker compose down", shell=True, check=True, cwd=SIMPLE_KBS_DIR)


@task
def clear_db(ctx, skip_secrets=False):
    """
    Clear the contents of the KBS DB
    """
    clear_kbs_db(skip_secrets=skip_secrets)


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
        "docker.io/csegarragonz/coco-helloworld-py",
        "docker.io/csegarragonz/coco-knative-sidecar",
        "ghcr.io/csegarragonz/coco-helloworld-py",
        "ghcr.io/csegarragonz/coco-knative-sidecar",
        "registry.coco-csg.com/csegarragonz/coco-helloworld-py",
        "registry.coco-csg.com/csegarragonz/coco-knative-sidecar",
    ]

    do_provision_launch_digest(
        images_to_sign, signature_policy=signature_policy, clean=clean
    )
