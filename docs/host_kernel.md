## Host Kernel Set-Up

Frequently, until the SNP patches are upstreamed, we need to bump the host
kernel.

After re-building the right kernel from SNP, we need to pick it for our host.
We can do so doing the following:

```bash
grep -E "menuentry '.*'" /boot/grub/grub.cfg | cut -d"'" -f2

# Will output something like:
# Ubuntu
# Advanced options for Ubuntu
# Ubuntu, with Linux 5.15.0-50-generic
# Ubuntu, with Linux 5.15.0-50-generic (recovery mode)
# Ubuntu, with Linux 5.13.0-48-generic
# Ubuntu, with Linux 5.13.0-48-generic (recovery mode)

# Now, pick the default kernel by setting the GRUB boot index to "1"
# (for Advanced options), and then pick your kernel as 0-indexed.
sudo vi /etc/default/grub

# For "Ubuntu, with Linux 5.13.0-48-generic"
GRUB_DEFAULT="1>2"
```
