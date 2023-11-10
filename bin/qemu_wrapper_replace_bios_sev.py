#!/bin/python3
from os import environ, getcwd, posix_spawn
from sys import argv


def launch_qemu(argv):
    # Remove the SEV blob
    sev_idx = -1
    for ind, arg in enumerate(argv):
        if "sev-guest" in arg:
            sev_idx = ind - 1
    new_argv = argv[:sev_idx] + argv[sev_idx+2:]

    # Change the machine type
    m_idx = new_argv.index("-machine")
    new_argv[m_idx + 1] = "q35,accel=kvm,kernel_irqchip=split"

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
