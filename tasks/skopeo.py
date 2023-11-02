from invoke import task
from tasks.util.skopeo import encrypt_container_image as do_encrypt_container_image


@task
def encrypt_container_image(ctx, image_tag, sign=False):
    """
    Encrypt an OCI container image using Skopeo

    The image tag must be provided in the format: <registry>/<repo>/<name>:<tag>
    """
    do_encrypt_container_image(image_tag, sign=sign)
