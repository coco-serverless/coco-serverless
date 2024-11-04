from os.path import exists, join
from subprocess import run
from tasks.util.env import K8S_CONFIG_DIR

COSIGN_BINARY = "cosign"

COSIGN_PRIV_KEY = join(K8S_CONFIG_DIR, "cosign.key")
COSIGN_PUB_KEY = join(K8S_CONFIG_DIR, "cosign.pub")


def generate_cosign_keypair():
    """
    Generate the keypair used to sign container images
    """
    run("cosign generate-key-pair", shell=True, check=True, cwd=K8S_CONFIG_DIR)


def sign_container_image(image_tag):
    if not exists(COSIGN_PUB_KEY):
        generate_cosign_keypair()

    # Copy the public key to KBS storage
    # cosign_key_kbs_path = join(SIMPLE_KBS_RESOURCE_PATH, "cosign.pub")
    # run("cp {} {}".format(COSIGN_PUB_KEY, cosign_key_kbs_path))

    # Actually sign the image
    sign_cmd = "cosign sign --key {} {}".format(COSIGN_PRIV_KEY, image_tag)
    run(sign_cmd, shell=True, check=True)
