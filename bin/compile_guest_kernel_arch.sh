read -p "Name of Linux Kernel: " name
make -j $(nproc) \
        && make modules_install -j $(nproc) \
        && cp -v arch/x86_64/boot/bzImage /boot/vmlinuz-$name \
        && cp /etc/mkinitcpio.d/linux.preset /etc/mkinitcpio.d/$name.preset \
        && sed -i "s/linux/$name/g" /etc/mkinitcpio.d/$name.preset \
        && mkinitcpio -p $name \
        && cp System.map /boot/System.map-$name \
        && ln -sf /boot/System.map-$name /boot/System.map \
        && grub-mkconfig -o /boot/grub/grub.cfg
