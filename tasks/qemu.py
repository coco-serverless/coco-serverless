from invoke import task
from os.path import join
from subprocess import run
from tasks.util.env import COCO_ROOT, KATA_CONFIG_DIR, PROJ_ROOT
from tasks.util.toml import read_value_from_toml

QEMU_IMAGE_TAG = "qemu-build"


@task
def build(ctx):
    """
    Build the QEMU work-on image
    """
    docker_cmd = "docker build -t {} -f {} .".format(
        QEMU_IMAGE_TAG, join(PROJ_ROOT, "docker", "qemu.dockerfile")
    )
    run(docker_cmd, shell=True, check=True, cwd=PROJ_ROOT)

    # Start the just-built docker image
    tmp_ctr_name = "tmp-qemu-run"
    docker_cmd = "docker run -td --name {} {}".format(tmp_ctr_name, QEMU_IMAGE_TAG)
    run(docker_cmd, shell=True, check=True)

    ctr_path = "/usr/src/qemu/build/qemu-system-x86_64"
    host_path = join(COCO_ROOT, "bin", "qemu-system-x86_64-csg")
    docker_cmd = "docker cp {}:{} {}".format(
        tmp_ctr_name,
        ctr_path,
        host_path,
    )
    run(docker_cmd, shell=True, check=True)

    run("docker rm -f {}".format(tmp_ctr_name), shell=True, check=True)


@task
def standalone(ctx):
    """
    Invoke a standalone confidential VM using QEMU

    By default, we read the relevant paths from the QEMU SEV command line.
    """
    conf_file_path = join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml")

    # Prepare QEMU command line
    qemu_cmd = [
        "sudo",
        "/opt/confidential-containers/bin/qemu-system-x86_64-csg",
        "-debugcon file:/dev/stdout -global isa-debugcon.iobase=0x402",
        "-D /tmp/qemu-log",
        # "-machine q35,accel=kvm,kernel_irqchip=split,confidential-guest-support=sev",
        "-enable-kvm -cpu host -machine q35 -smp 1 -m 2G",
        "-machine memory-encryption=sev0",
        "-object sev-guest,id=sev0,cbitpos=51,reduced-phys-bits=1,policy=0x0",
        "-drive if=pflash,format=raw,readonly=on,file={}".format(
            read_value_from_toml(conf_file_path, "hypervisor.qemu.firmware")),
        "-kernel {}".format(
            read_value_from_toml(conf_file_path, "hypervisor.qemu.kernel")),
        "-append \"console=ttyS0 earlyprintk=serial root=/dev/sda2\"",
        "-initrd {}".format(
            read_value_from_toml(conf_file_path, "hypervisor.qemu.initrd")),
        "-nographic",
        "-nodefaults",
        "--trace 'kvm_sev_*'",
    ]
    qemu_cmd = " ".join(qemu_cmd)

    print(qemu_cmd)
    run(qemu_cmd, shell=True, check=True)
