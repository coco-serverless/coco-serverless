#!/bin/bash

# This script is a wrapper to modify the QEMU command line when invoked through
# Kata. We also need to change the Kata config to point the hypervisor path
# to this script
/opt/confidential-containers/bin/qemu-system-x86_64 \
    "$@" \
    --serial file:/tmp/qemu-serial.log
