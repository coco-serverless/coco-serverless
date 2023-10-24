#!/bin/bash

# This script is a wrapper to modify the QEMU command line when invoked through
# Kata. We also need to change the Kata config to point the valid hypervisor
# path to this script
/opt/confidential-containers/bin/qemu-system-x86_64-csg -debugcon file:/tmp/ovmf.log -global isa-debugcon.iobase=0x402 "$@" -D /tmp/qemu.log --trace 'kvm_sev_*'
