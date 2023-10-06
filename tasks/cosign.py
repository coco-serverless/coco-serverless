from invoke import task
from os.path import join
from subprocess import run
from tasks.util.cosign import (
    COSIGN_BINARY,
    COSIGN_VERSION,
    sign_container_image as do_sign_container_image,
)
from tasks.util.env import BIN_DIR


@task
def install(ctx):
    """
    Install the cosign tool to sign container images
    """
    cosign_url = "https://github.com/sigstore/cosign/releases/download/"
    cosign_url += "v{}/cosign-linux-amd64".format(COSIGN_VERSION)
    cosign_path = join(BIN_DIR, COSIGN_BINARY)
    run("wget {} -O {}".format(cosign_url, cosign_path), shell=True, check=True)
    run("chmod +x {}".format(cosign_path), shell=True, check=True)


@task
def sign_container_image(ctx, image_tag):
    """
    Sign a container image
    """
    do_sign_container_image(image_tag)
