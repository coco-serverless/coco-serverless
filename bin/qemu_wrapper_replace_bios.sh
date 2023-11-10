#!/bin/bash

# This script is a wrapper to modify the QEMU command line when invoked through
# Kata. We also need to change the Kata config to point the hypervisor path
# to this script

original_cmdline="/opt/confidential-containers/bin/qemu-system-x86_64 "$@""
# Remove the BIOS option from the command line arguments
args_no_bios=$(echo $@ | sed -r 's/-bios [^ ]+ //g')
# args_no_bios=$(echo ${args_no_bios}| sed -r 's/no_timer_check [^ ]+ //g')
echo ${original_cmdline} > /tmp/qemu_cmdline.log
/opt/confidential-containers/bin/qemu-system-x86_64 \
    ${args_no_bios[@]} \
    -drive if=pflash,format=raw,readonly=on,file=/opt/confidential-containers/share/ovmf/OVMF.fd \
    --serial file:/tmp/qemu-serial.log
# ${cmdline}
