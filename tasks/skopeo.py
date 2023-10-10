from base64 import b64encode
from invoke import task
from os.path import exists, join
from subprocess import run
from tasks.util.env import CONF_FILES_DIR, K8S_CONFIG_DIR, PROJ_ROOT
from tasks.util.guest_components import (
    start_coco_keyprovider,
    stop_coco_keyprovider,
)
from tasks.util.kbs import create_kbs_secret

SKOPEO_VERSION = "1.13.0"
SKOPEO_IMAGE = "quay.io/skopeo/stable:v{}".format(SKOPEO_VERSION)
SKOPEO_ENCRYPTION_KEY = join(K8S_CONFIG_DIR, "image_enc.key")
# SKOPEO_CTR_ENCRYPTION_KEY = "/tmp/image_enc.key"
AA_CTR_ENCRYPTION_KEY = "/tmp/image_enc.key"


def run_skopeo_cmd(cmd):
    ocicrypt_conf_host = join(CONF_FILES_DIR, "ocicrypt.conf")
    ocicrypt_conf_guest = "/ocicrypt.conf"
    skopeo_cmd = [
        "docker run --rm",
        "--net host",
        # "-v /var/run/docker.sock:/var/run/docker.sock",
        "-e OCICRYPT_KEYPROVIDER_CONFIG={}".format(ocicrypt_conf_guest),
        "-v {}:{}".format(ocicrypt_conf_host, ocicrypt_conf_guest),
        "-v ~/.docker/config.json:/config.json",
        # "-v {}:{}".format(SKOPEO_ENCRYPTION_KEY, SKOPEO_CTR_ENCRYPTION_KEY),
        SKOPEO_IMAGE,
        cmd,
    ]
    skopeo_cmd = " ".join(skopeo_cmd)
    print(skopeo_cmd)
    run(skopeo_cmd, shell=True, check=True)


def create_encryption_key():
    cmd = "head -c32 < /dev/random > {}".format(SKOPEO_ENCRYPTION_KEY)
    run(cmd, shell=True, check=True)


@task
def encrypt_container_image(ctx, image_tag):
    """
    Encrypt an OCI container image using Skopeo

    The image tag must be provided in the format: docker.io/<repo>/<name>:tag
    """
    # start_coco_keyprovider()

    # Encrypt image
    encryption_key_resource_id = "default/image-encryption-key/1"
    if not exists(SKOPEO_ENCRYPTION_KEY):
        create_encryption_key()

    encrypted_image_tag = image_tag.split(":")[0] + ":encrypted"
    skopeo_cmd = [
        "copy --insecure-policy",
        "--authfile /config.json",
        # "--debug",
        "--encryption-key provider:attestation-agent:keyid=kbs:///{}::keypath={}".format(
            encryption_key_resource_id, AA_CTR_ENCRYPTION_KEY),
        "docker://{}".format(image_tag),
        "docker://{}".format(encrypted_image_tag),
    ]
    skopeo_cmd = " ".join(skopeo_cmd)
    run_skopeo_cmd(skopeo_cmd)

    # TODO: sanity check?

    # Create a secret in KBS with the encryption key. Skopeo needs it as raw
    # bytes, whereas KBS wants it base64 encoded, so we do the conversion first
    with open(SKOPEO_ENCRYPTION_KEY, "rb") as fh:
        key_b64 = b64encode(fh.read()).decode()

    create_kbs_secret(
        encryption_key_resource_id,
        key_b64
    )

    # We probably also want to sign the image?
    # TODO
