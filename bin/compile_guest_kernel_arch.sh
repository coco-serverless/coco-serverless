#!/bin/bash

# Compile Linux Kernel for Arch Linux. 
# This script automates the the steps explained in https://wiki.archlinux.org/title/Kernel/Traditional_compilation.

if [ $# -eq 0 ]; then
  echo "Error: No arguments provided."
  echo "Usage: $0 <kernel_version>"
  exit 1
fi

make -j $(nproc) \
        && make modules_install -j $(nproc) \
        && cp -v arch/x86_64/boot/bzImage /boot/vmlinuz-$1 \
        && cp /etc/mkinitcpio.d/linux.preset /etc/mkinitcpio.d/$1.preset \
        && sed -i "s/linux/$1/g" /etc/mkinitcpio.d/$1.preset \
        && mkinitcpio -p $1 \
        && cp System.map /boot/System.map-$1 \
        && ln -sf /boot/System.map-$1 /boot/System.map \
        && grub-mkconfig -o /boot/grub/grub.cfg
