from invoke import task
from os.path import join
from subprocess import run
from tasks.util.env import BIN_DIR, PROJ_ROOT
from tasks.util.docker import build_image_and_run, copy_from_container, stop_container
# refer to
# https://github.com/coconut-svsm/svsm/blob/main/Documentation/docs/installation/INSTALL.md

QEMU_IMAGE_TAG = "svsm-build"


@task
def build(ctx):
    tmp_ctr_name = "tmp-svsm-run"
    
    build_image_and_run(QEMU_IMAGE_TAG, join(PROJ_ROOT, "docker", "coconut", "svsm.dockerfile"), tmp_ctr_name, {"OVMF_DIR": "bin"})

    ctr_path = "/root/svsm/bin"
    host_path = BIN_DIR
    files_to_copy = ["svsm.bin", "coconut-qemu.igvm", "../target/x86_64-unknown-none/debug/svsm"]
    for file_name in files_to_copy:
        copy_from_container(tmp_ctr_name, join(ctr_path, file_name), join(host_path, file_name))

    stop_container(tmp_ctr_name)
