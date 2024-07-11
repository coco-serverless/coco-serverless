from invoke import task
from os.path import join
from subprocess import run
from tasks.util.env import BIN_DIR, PROJ_ROOT

# refer to 
# https://github.com/coconut-svsm/svsm/blob/main/Documentation/docs/installation/INSTALL.md

QEMU_IMAGE_TAG = "svsm-build"

@task
def build(ctx):
    docker_cmd = "docker build -t {} -f {} --build-arg OVMF_DIR={} .".format(
        QEMU_IMAGE_TAG, join(PROJ_ROOT, "docker", "coconut", "svsm.dockerfile"), BIN_DIR
    )
    run(docker_cmd, shell=True, check=True, cwd=PROJ_ROOT)
    
    tmp_ctr_name = "tmp-svsm-run"
    docker_cmd = "docker run -td --name {} {}".format(tmp_ctr_name, QEMU_IMAGE_TAG)
    run(docker_cmd, shell=True, check=True)
    ctr_path = "/root/svsm/svsm.bin"
    host_path = join(BIN_DIR, "svsm.bin")
    docker_cmd = "docker cp {}:{} {}".format(
        tmp_ctr_name,
        ctr_path,
        host_path,
    )
    run(docker_cmd, shell=True, check=True)

    run("docker rm -f {}".format(tmp_ctr_name), shell=True, check=True)
