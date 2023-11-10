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
    conf_file_path = join(KATA_CONFIG_DIR, "configuration-qemu.toml")
    # qemu_path = read_value_from_toml(conf_file_path, "hypervisor.qemu.path")
    qemu_path = join(COCO_ROOT, "bin", "qemu-system-x86_64-csg")
    fw_path = join(COCO_ROOT, "share", "ovmf", "OVMF.fd")
    # fw_path = join(COCO_ROOT, "share", "ovmf", "AMDSEV_CSG.fd")
    # fw_path = read_value_from_toml(conf_file_path, "hypervisor.qemu.firmware")
    kernel_path = join(
        COCO_ROOT, "share", "kata-containers", "vmlinuz-5.19.2-109cc+"
    )
    # kernel_path = read_value_from_toml(conf_file_path, "hypervisor.qemu.kernel")

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


"""
/opt/confidential-containers/bin/qemu-system-x86_64
        -name sandbox-52649472ee6114df956c8fdfc5e048548969a656322aaaebb851804135c1babc
        -uuid 5e940a3e-8909-4b8e-8e7b-8c1371b84be4
        -machine q35,accel=kvm -cpu host,pmu=off
        -qmp unix:fd=3,server=on,wait=off
        -monitor unix:path=/run/vc/vm/52649472ee6114df956c8fdfc5e048548969a656322aaaebb851804135c1babc/hmp.sock,server=on,wait=off
        -m 2048M,slots=10,maxmem=257720M
        -device pci-bridge,bus=pcie.0,id=pci-bridge-0,chassis_nr=1,shpc=off,addr=2,io-reserve=4k,mem-reserve=1m,pref64-reserve=1m
        -device virtio-serial-pci,disable-modern=false,id=serial0
        -device virtconsole,chardev=charconsole0,id=console0
        -chardev socket,id=charconsole0,path=/run/vc/vm/52649472ee6114df956c8fdfc5e048548969a656322aaaebb851804135c1babc/console.sock,server=on,wait=off
        -device virtio-scsi-pci,id=scsi0,disable-modern=false
        -drive if=pflash,format=raw,readonly=on,file=/opt/confidential-containers/share/ovmf/OVMF.fd
        -object rng-random,id=rng0,filename=/dev/urandom -device virtio-rng-pci,rng=rng0
        -device vhost-vsock-pci,disable-modern=false,vhostfd=4,id=vsock-945887153,guest-cid=945887153 -chardev socket,id=char-c11119393a6423d5,path=/run/vc/vm/52649472ee6114df956c8fdfc5e048548969a656322aaaebb851804135c1babc/vhost-fs.sock -device vhost-user-fs-pci,chardev=char-c11119393a6423d5,tag=kataShared,queue-size=1024 -netdev tap,id=network-0,vhost=on,vhostfds=5,fds=6 -device driver=virtio-net-pci,netdev=network-0,mac=ba:3e:8f:45:14:aa,disable-modern=false,mq=on,vectors=4 -rtc base=utc,driftfix=slew,clock=host -global kvm-pit.lost_tick_policy=discard -vga none -no-user-config -nodefaults -nographic --no-reboot -object memory-backend-file,id=dimm1,size=2048M,mem-path=/dev/shm,share=on -numa node,memdev=dimm1 -kernel /opt/confidential-containers/share/kata-containers/vmlinux-5.19.2-109cc+ -initrd /opt/confidential-containers/share/kata-containers/kata-containers-initrd-sev-csg.img -append tsc=reliable no_timer_check rcupdate.rcu_expedited=1 i8042.direct=1 i8042.dumbkbd=1 i8042.nopnp=1 i8042.noaux=1 noreplace-smp reboot=k cryptomgr.notests net.ifnames=0 pci=lastbus=0 console=hvc0 console=hvc1 debug panic=1 nr_cpus=128 selinux=0 scsi_mod.scan=none agent.log=debug agent.debug_console agent.debug_console_vport=1026 cc_rootfs_verity.scheme=dm-verity cc_rootfs_verity.hash=1347cec76b46ab1d93d2422aaff669e41d81677729b80f0519357377c2a5d46b agent.enable_signature_verification=false -pidfile /run/vc/vm/52649472ee6114df956c8fdfc5e048548969a656322aaaebb851804135c1babc/pid -smp 1,cores=1,threads=1,sockets=128,maxcpus=128 --serial file:/tmp/qemu-serial.log
"""
