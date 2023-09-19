from invoke import task
from os.path import join
from subprocess import CalledProcessError, run
from tasks.util.env import PROJ_ROOT

CONTAINERD_IMAGE_TAG = "containerd-build"


@task
def build(ctx):
    """
    Build the containerd fork for CoCo
    """
    docker_cmd = "docker build -t {} -f {} .".format(CONTAINERD_IMAGE_TAG, join(PROJ_ROOT, "docker", "containerd.dockerfile"))
    run(docker_cmd, shell=True, check=True, cwd=PROJ_ROOT)


@task
def install(ctx):
    """
    Install the built containerd
    """
    tmp_ctr_name = "tmp_containerd_build"
    docker_cmd = "docker run -td --name {} {} bash".format(tmp_ctr_name, CONTAINERD_IMAGE_TAG)
    run(docker_cmd, shell=True, check=True)

    def cleanup():
        docker_cmd = "docker rm -f {}".format(tmp_ctr_name)
        run(docker_cmd, shell=True, check=True)

    binary_names = ["containerd", "containerd-shim", "containerd-shim-runc-v1", "containerd-shim-runc-v2"]
    ctr_base_path = "/go/src/github.com/containerd/containerd/bin"
    host_base_path = "/usr/bin"
    for binary in binary_names:
        docker_cmd = "sudo docker cp {}:{}/{} {}/{}".format(
            tmp_ctr_name,
            ctr_base_path,
            binary,
            host_base_path,
            binary
        )
        try:
            #TODO: we need to copy containerd to /opt/confidential-containers/bin
            run(docker_cmd, shell=True, check=True)
        except CalledProcessError as e:
            cleanup()
            raise e

    cleanup()
    # run("sudo service containerd restart")
