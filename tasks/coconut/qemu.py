from invoke import task
from os.path import join
from subprocess import run
from tasks.util.env import BIN_DIR, PROJ_ROOT, KATA_ROOT
from tasks.util.docker import copy_from_container, build_image_and_run, stop_container
# refer to
# https://github.com/coconut-svsm/svsm/blob/main/Documentation/docs/installation/INSTALL.md

QEMU_IMAGE_TAG = "qemu-igvm-build"
DATA_DIR = join(KATA_ROOT, "coconut", "qemu-svsm", "share")


@task
def build(ctx):
    tmp_ctr_name = "tmp-qemu-igvm-run"
    
    build_image_and_run(QEMU_IMAGE_TAG, join(PROJ_ROOT, "docker", "coconut", "qemu.dockerfile"), tmp_ctr_name, {"QEMU_DATADIR": DATA_DIR})
    
    copy_from_container(
        tmp_ctr_name,
        "/root/bin/qemu-svsm/bin/qemu-system-x86_64",
        join(BIN_DIR, "qemu-system-x86_64-igvm"),
    )
    copy_from_container(tmp_ctr_name, f"{DATA_DIR}/.", DATA_DIR)
    
    stop_container(tmp_ctr_name)


@task
def guest(ctx, guest_img_path=join(PROJ_ROOT, "ubuntu-guest.qcow2"), detach=False, vnc=False):
    qemu_path = join(BIN_DIR, "qemu-system-x86_64-igvm")
    igvm_path = join(BIN_DIR, "coconut-qemu.igvm")

    qemu_cmd = [
        "sudo",
        qemu_path,
        "-enable-kvm",
        "-cpu EPYC-v4",
        "-machine q35,confidential-guest-support=sev0,memory-backend=ram1",
        ("-object memory-backend-memfd,id=ram1,size=8G,share=true,"
            "prealloc=false,reserve=false"),
        ("-object sev-snp-guest,id=sev0,cbitpos=51,"
            "reduced-phys-bits=1,igvm-file={}").format(igvm_path),
        "-smp 8",
        "-no-reboot",
        ("-netdev user,id=vmnic,hostfwd=tcp::2222-:22,"
            "hostfwd=tcp::8080-:80 -device e1000,netdev=vmnic,romfile="),
        "-device virtio-scsi-pci,id=scsi0,disable-legacy=on,iommu_platform=on",
        "-device scsi-hd,drive=disk0,bootindex=0",
        "-drive file={},if=none,id=disk0,format=qcow2,snapshot=off".format(
            guest_img_path
        ),
        "--serial file:tmp.log",
        "-display none",
    ]
    if detach:
        qemu_cmd.append("-daemonize")
    
    if vnc:
        qemu_cmd.append("-vnc :1")
        
    qemu_cmd = " ".join(qemu_cmd)
    print(qemu_cmd)
    run(qemu_cmd, shell=True, check=True)
