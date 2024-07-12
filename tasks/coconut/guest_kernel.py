from invoke import task
from os.path import join
from subprocess import run
from tasks.util.env import BIN_DIR, PROJ_ROOT

# refer to 
# https://github.com/coconut-svsm/svsm/blob/main/Documentation/docs/installation/INSTALL.md

KERNEL_IMAGE_TAG = "guest-kernel-build"

@task
def build(ctx):
    docker_cmd = "docker build -t {} -f {} .".format(
        KERNEL_IMAGE_TAG, join(PROJ_ROOT, "docker", "coconut", "guest-kernel.dockerfile")
    )
    run(docker_cmd, shell=True, check=True, cwd=PROJ_ROOT)
    
    tmp_ctr_name = "tmp-guest-kernel-run"
    docker_cmd = "docker run -td --name {} {}".format(tmp_ctr_name, KERNEL_IMAGE_TAG)
    run(docker_cmd, shell=True, check=True)
    ctr_path = "/root/linux/arch/x86/boot/bzImage"
    host_path = join(BIN_DIR, "bzImage")
    docker_cmd = "docker cp {}:{} {}".format(
        tmp_ctr_name,
        ctr_path,
        host_path,
    )
    run(docker_cmd, shell=True, check=True)

    run("docker rm -f {}".format(tmp_ctr_name), shell=True, check=True)
