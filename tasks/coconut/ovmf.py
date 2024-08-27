from invoke import task
from os.path import join
from tasks.util.env import BIN_DIR, PROJ_ROOT
from tasks.util.docker import copy_from_container, build_image_and_run, stop_container

# refer to
# https://github.com/coconut-svsm/svsm/blob/main/Documentation/docs/installation/INSTALL.md

OVMF_IMAGE_TAG = "ovmf-svsm-build"


@task
def build(ctx):
    tmp_ctr_name = "tmp-ovmf-svsm-run"

    build_image_and_run(
        OVMF_IMAGE_TAG,
        join(PROJ_ROOT, "docker", "coconut", "ovmf.dockerfile"),
        tmp_ctr_name,
    )

    ctr_path = "/root/edk2/Build/OvmfX64/DEBUG_GCC5/FV/OVMF.fd"
    host_path = join(BIN_DIR, "ovmf-svsm.fd")
    copy_from_container(tmp_ctr_name, ctr_path, host_path)

    stop_container(tmp_ctr_name)
