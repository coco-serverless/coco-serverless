from os.path import join
from subprocess import run
from tasks.util.env import PROJ_ROOT

GUEST_COMPONENTS_DIR = join(PROJ_ROOT, "..", "guest-components")
COCO_KEYPROVIDER_DIR = join(GUEST_COMPONENTS_DIR, "attestation-agent", "coco_keyprovider")

COCO_KEYPROVIDER_CTR_NAME = "coco-keyprovider"
COCO_KEYPROVIDER_CTR_PORT = 50000


def start_coco_keyprovider():
    """
    Start the CoCo key-provider to encrypt a docker image using Skopeo
    """
    docker_cmd = [
        "docker run -d",
        "--name {}".format(COCO_KEYPROVIDER_CTR_NAME),
        "-p {port}:{port}".format(port=COCO_KEYPROVIDER_CTR_PORT),
        "-v {}:/usr/src/guest-components".format(GUEST_COMPONENTS_DIR),
        "-w /usr/src/guest-components/attestation-agent/coco-keyprovider",
        "rust:1.72",
        "bash -c 'rustup component add rustfmt && cargo run --release -- --socket 127.0.0.1:{}'".format(COCO_KEYPROVIDER_CTR_PORT),
    ]
    docker_cmd = " ".join(docker_cmd)
    run(docker_cmd, shell=True, check=True)


def stop_coco_keyprovider():
    """
    Stop the CoCo key-provider
    """
    docker_cmd = "docker rm -f {}".format(COCO_KEYPROVIDER_CTR_NAME)
    run(docker_cmd, shell=True, check=True)
