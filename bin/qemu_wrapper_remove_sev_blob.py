#!/bin/python3
from os import environ, posix_spawn
from sys import argv

# ------------------------------
# This script is meant to be used as a replacement for the hypervisor path
# in the Kata config file. It takes the QEMU command prepared to boot an SEV
# guest, and it removes the `sev-guest` blob.
#
# We use this script to boot a non-SEV guest with OVMF.
# ------------------------------


def launch_qemu(argv):
    # Remove the SEV blob
    sev_idx = -1
    for ind, arg in enumerate(argv):
        if "sev-guest" in arg:
            sev_idx = ind - 1
    new_argv = argv[:sev_idx] + argv[sev_idx + 2 :]

    # Change the machine type
    m_idx = new_argv.index("-machine")
    new_argv[m_idx + 1] = "q35,accel=kvm,kernel_irqchip=split"

    qemu_binary = "/opt/confidential-containers/bin/qemu-system-x86_64"
    qemu_cmdline = (
        [qemu_binary]
        + new_argv
        + [
            "--serial",
            "file:/tmp/qemu-serial.log",
        ]
    )
    # Use posix_spawn instead of the higher-level run, as the latter does
    # some `fd` re-direction that breaks the underlying QEMU command
    posix_spawn(qemu_binary, qemu_cmdline, environ)


if __name__ == "__main__":
    launch_qemu(argv)
