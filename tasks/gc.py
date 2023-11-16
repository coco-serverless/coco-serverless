from invoke import task
from os.path import join
from subprocess import run
from tasks.util.docker import is_ctr_running
from tasks.util.env import PROJ_ROOT

GC_CTR_NAME = "guest-components-workon"
GC_IMAGE_TAG = "guest-components-build"


@task
def build(ctx):
    """
    Build the guest-components work-on image
    """
    docker_cmd = "docker build -t {} -f {} .".format(
        GC_IMAGE_TAG, join(PROJ_ROOT, "docker", "guest_components.dockerfile")
    )
    run(docker_cmd, shell=True, check=True, cwd=PROJ_ROOT)


@task
def cli(ctx):
    """
    Get a working environment for guest components
    """
    if not is_ctr_running(GC_CTR_NAME):
        docker_cmd = [
            "docker run",
            "-d -it",
            "--name {}".format(GC_CTR_NAME),
            GC_IMAGE_TAG,
            "bash",
        ]
        docker_cmd = " ".join(docker_cmd)
        run(docker_cmd, shell=True, check=True, cwd=PROJ_ROOT)

    run("docker exec -it {} bash".format(GC_CTR_NAME), shell=True, check=True)


@task
def stop(ctx):
    """
    Stop the GC work-on container
    """
    run("docker rm -f {}".format(GC_CTR_NAME), shell=True, check=True)
