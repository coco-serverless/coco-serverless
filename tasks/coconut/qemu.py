from invoke import task
from os.path import join
from subprocess import run
from tasks.util.env import BIN_DIR, PROJ_ROOT

# refer to 
# https://github.com/coconut-svsm/svsm/blob/main/Documentation/docs/installation/INSTALL.md

QEMU_IMAGE_TAG = "qemu-igvm-build"

@task
def build(ctx):
    docker_cmd = "docker build -t {} -f {} .".format(
        QEMU_IMAGE_TAG, join(PROJ_ROOT, "docker", "coconut", "qemu.dockerfile")
    )
    run(docker_cmd, shell=True, check=True, cwd=PROJ_ROOT)
    
    tmp_ctr_name = "tmp-qemu-igvm-run"
    docker_cmd = "docker run -td --name {} {}".format(tmp_ctr_name, QEMU_IMAGE_TAG)
    run(docker_cmd, shell=True, check=True)
    copy_from_container(tmp_ctr_name, "/root/bin/qemu-svsm/bin/qemu-system-x86_64", join(BIN_DIR, "qemu-system-x86_64-igvm"))
    copy_from_container(tmp_ctr_name, "/root/bin/qemu-svsm/share/qemu/bios-256k.bin", join(BIN_DIR, "bios-256k.bin"))
    
    run("docker rm -f {}".format(tmp_ctr_name), shell=True, check=True)

def copy_from_container(ctr_name, ctr_path, host_path):
    docker_cmd = "docker cp {}:{} {}".format(
        ctr_name,
        ctr_path,
        host_path,
    )
    run(docker_cmd, shell=True, check=True)
    
# TODO --qemu-datadir flag nessary?

@task
def standalone(ctx):
    # TODO
    raise NotImplementedError
