from invoke import task
from os.path import join
from subprocess import CalledProcessError, run
from tasks.util.env import PROJ_ROOT

NYDUS_CTR_NAME = "nydus-workon"
NYDUS_IMAGE_TAG = "nydus-build"


@task
def build(ctx):
    """
    Build the nydus snapshotter
    """
    docker_cmd = "docker build -t {} -f {} .".format(
        NYDUS_IMAGE_TAG, join(PROJ_ROOT, "docker", "nydus.dockerfile")
    )

    run(docker_cmd, shell=True, check=True, cwd=PROJ_ROOT)


@task
def install(ctx, clean=False):
    """
    Install the nydus snapshotter
    """
    docker_cmd = "docker run -td --name {} {} bash".format(
        NYDUS_CTR_NAME, NYDUS_IMAGE_TAG
    )
    run(docker_cmd, shell=True, check=True)

    def cleanup():
        docker_cmd = "docker rm -f {}".format(NYDUS_CTR_NAME)
        run(docker_cmd, shell=True, check=True)

    binary_names = [
        "containerd-nydus-grpc",
        "nydus-overlayfs",
    ]
    ctr_base_path = "/go/src/github.com/containerd/nydus-snapshotter/bin"
    host_base_path = "/opt/confidential-containers/bin"
    for binary in binary_names:
        docker_cmd = "sudo docker cp {}:{}/{} {}/{}".format(
            NYDUS_CTR_NAME, ctr_base_path, binary, host_base_path, binary
        )
        try:
            run(docker_cmd, shell=True, check=True)
        except CalledProcessError as e:
            cleanup()
            raise e

    cleanup()

    # Remove all nydus config for a clean start
    if clean:
        run("sudo rm -rf /var/lib/containerd-nydus", shell=True, check=True)

    # Restart the nydus service
    run("sudo service nydus-snapshotter restart", shell=True, check=True)
