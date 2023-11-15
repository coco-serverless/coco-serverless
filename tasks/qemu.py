from invoke import task
from os.path import join
from subprocess import run
from tasks.util.env import COCO_ROOT, KATA_CONFIG_DIR, PROJ_ROOT
from tasks.util.toml import read_value_from_toml

QEMU_IMAGE_TAG = "qemu-build"


@task
def build(ctx, qemu_datadir=join(COCO_ROOT, "share", "kata-qemu")):
    """
    Build the QEMU work-on image

    The optional `--qemu-datadir` flag is the path where QEMU will look for
    firmware images. This path is hardcoded into the QEMU binary, and we set
    it at build time. In a system provisioned by the operator, the default
    QEMU data dir is: `/opt/confidential-containers/share/kata-qemu`
    """
    docker_cmd = "docker build --build-arg QEMU_DATADIR={} -t {} -f {} .".format(
        qemu_datadir, QEMU_IMAGE_TAG, join(PROJ_ROOT, "docker", "qemu.dockerfile")
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
    Invoke a standalone (non-)confidential VM using QEMU

    So far, only non-confidential VMs work. Note that the /init process in the
    default `initrd` is the Kata Agent, so the VM will not hang in the agent
    init. It is still useful to assert that the VM can boot.
    """
    conf_file_path = join(KATA_CONFIG_DIR, "configuration-qemu.toml")
    qemu_path = join(COCO_ROOT, "bin", "qemu-system-x86_64-csg")
    fw_path = join(COCO_ROOT, "share", "ovmf", "OVMF.fd")
    kernel_path = join(COCO_ROOT, "share", "kata-containers", "vmlinuz-5.19.2-109cc+")

    # Prepare QEMU command line
    qemu_cmd = [
        "sudo",
        qemu_path,
        "-machine q35,accel=kvm",
        "-m 2048M,slots=10,maxmem=257720M",
        "-kernel {}".format(kernel_path),
        '-append "console=ttyS0 root=/dev/sda2 debug"',
        "-initrd {}".format(
            read_value_from_toml(conf_file_path, "hypervisor.qemu.initrd")
        ),
        "-no-user-config",
        "-nodefaults",
        "-nographic",
        "--no-reboot",
        "-drive if=pflash,format=raw,readonly=on,file={}".format(fw_path),
        "--serial file:/tmp/qemu-serial-direct.log",
    ]
    qemu_cmd = " ".join(qemu_cmd)

    print(qemu_cmd)
    run(qemu_cmd, shell=True, check=True)
