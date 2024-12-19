from invoke import task
from os.path import join
from tasks.util.env import BIN_DIR
from tasks.util.docker import copy_from_ctr_image

# refer to
# https://github.com/coconut-svsm/svsm/blob/main/Documentation/docs/installation/INSTALL.md

OVMF_IMAGE_TAG = "ovmf-svsm-build"


@task
def build(ctx):
    ctr_path = "/root/edk2/Build/OvmfX64/DEBUG_GCC5/FV/OVMF.fd"
    host_path = join(BIN_DIR, "ovmf-svsm.fd")
    copy_from_ctr_image(OVMF_IMAGE_TAG, ctr_path, host_path)
