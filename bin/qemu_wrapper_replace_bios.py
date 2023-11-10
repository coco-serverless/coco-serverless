#!/bin/python3
from os import environ, getcwd, posix_spawn
from sys import argv


def launch_qemu(argv):
    ind = argv.index("-bios")
    new_argv = argv[1:ind] + argv[ind+2:]

    other_ind = new_argv.index("virtio-scsi-pci,id=scsi0,disable-modern=false")
    new_argv = new_argv[:other_ind+1] + [
        "-drive",
        "if=pflash,format=raw,readonly=on,file=/opt/confidential-containers/share/ovmf/OVMF_CSG.fd",
    ] + new_argv[other_ind+1:]

    qemu_binary = "/opt/confidential-containers/bin/qemu-system-x86_64"
    qemu_cmdline = [qemu_binary] + new_argv + [
        # "-drive",
        # "if=pflash,format=raw,readonly=on,file=/opt/confidential-containers/share/ovmf/OVMF.fd",
        "--serial",
        "file:/tmp/qemu-serial.log",
    ]
    posix_spawn(qemu_binary, qemu_cmdline, environ)


if __name__ == "__main__":
    launch_qemu(argv)
