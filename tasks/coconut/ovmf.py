from invoke import task
from os.path import join
from subprocess import run
from tasks.util.env import BIN_DIR, PROJ_ROOT

# refer to
# https://github.com/coconut-svsm/svsm/blob/main/Documentation/docs/installation/INSTALL.md

OVMF_IMAGE_TAG = "ovmf-svsm-build"


@task
def build(ctx):
    docker_cmd = "docker build -t {} -f {} .".format(
        OVMF_IMAGE_TAG, join(PROJ_ROOT, "docker", "coconut", "ovmf.dockerfile")
    )
    run(docker_cmd, shell=True, check=True, cwd=PROJ_ROOT)

    tmp_ctr_name = "tmp-ovmf-svsm-run"
    docker_cmd = "docker run -td --name {} {}".format(tmp_ctr_name, OVMF_IMAGE_TAG)
    run(docker_cmd, shell=True, check=True)
    ctr_path = "/root/edk2/Build/OvmfX64/DEBUG_GCC5/FV/OVMF.fd"
    host_path = join(BIN_DIR, "ovmf-svsm.fd")
    docker_cmd = "docker cp {}:{} {}".format(
        tmp_ctr_name,
        ctr_path,
        host_path,
    )
    run(docker_cmd, shell=True, check=True)

    run("docker rm -f {}".format(tmp_ctr_name), shell=True, check=True)
