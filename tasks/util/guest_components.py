from os.path import join
from subprocess import run
from tasks.util.env import COMPONENTS_DIR, PROJ_ROOT
from time import sleep

GUEST_COMPONENTS_DIR = join(COMPONENTS_DIR, "guest-components")
COCO_KEYPROVIDER_DIR = join(
    GUEST_COMPONENTS_DIR, "attestation-agent", "coco_keyprovider"
)

COCO_KEYPROVIDER_CTR_NAME = "coco-keyprovider"
COCO_KEYPROVIDER_CTR_PORT = 50000


def start_coco_keyprovider(host_key_path, guest_key_path):
    """
    Start the CoCo key-provider to encrypt a docker image using Skopeo
    """
    docker_cmd = [
        "docker run -d",
        "--net host",
        "--name {}".format(COCO_KEYPROVIDER_CTR_NAME),
        "-v {}:/usr/src/guest-components".format(GUEST_COMPONENTS_DIR),
        "-v {}:{}".format(host_key_path, guest_key_path),
        "-w /usr/src/guest-components/attestation-agent/coco-keyprovider",
        "rust:1.72",
        "bash -c 'rustup component add rustfmt && cargo run --release --bin",
        "coco_keyprovider -- --socket 127.0.0.1:{}'".format(COCO_KEYPROVIDER_CTR_PORT),
    ]
    docker_cmd = " ".join(docker_cmd)
    run(docker_cmd, shell=True, check=True)

    # Wait for the gRPC server to be ready
    poll_period = 2
    string_to_check = "listening to socket addr"
    while True:
        sleep(poll_period)
        logs_cmd = "docker logs {}".format(COCO_KEYPROVIDER_CTR_NAME)
        ctr_logs = run(logs_cmd, shell=True, capture_output=True).stderr.decode("utf-8")
        if string_to_check in ctr_logs:
            print("gRPC server ready!")
            break

        print("Waiting for keyprovider's gRPC server to be ready...")


def stop_coco_keyprovider():
    """
    Stop the CoCo key-provider
    """
    docker_cmd = "docker rm -f {}".format(COCO_KEYPROVIDER_CTR_NAME)
    run(docker_cmd, shell=True, check=True)
