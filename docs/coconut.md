# Coconut-SVSM

## Installation

For more details, please refer to [Coconut SVSM](https://github.com/coconut-svsm/svsm). The following instructions are intended to simplify the installation, especially for our usecase.

### 1. Preparing the Host

The host kernel needs support for SVSM.
Install necessary dependencies:

```bash
$ sudo apt install git fakeroot build-essential ncurses-dev xz-utils libssl-dev bc flex libelf-dev bison
```

Clone the linux kernel:

```bash
$ git clone https://github.com/coconut-svsm/linux 
$ cd linux
$ git checkout svsm 
```

To use your current kernel configuration, execute:

```bash 
$ cp /boot/config-$(uname -r) .config
```

Use `menuconfig` and ensure that `CONFIG_KVM_AMD_SEV` is enabled.

Next, compile and install the kernel:

```bash
$ make -j $(nproc)
$ sudo make modules_install
$ sudo make install
```

### 2. Building QEMU

You will need a QEMU build that supports launching guests using IGVM:

```bash
$ inv coconut.qemu.build
```

This will create a file called `qemu-system-x86_64-igvm` in the `BIN_DIR`. 

### 3. Building the guest firmware

A special OVMF build is needed to launch a guest on top of the COCONUT-SVSM:

```bash
$ inv coconut.ovmf.build
```

A file named `ovmf-svsm.fd` will be created in the `BIN_DIR`.


### 4. Preparing the guest image

In our case, we are creating a Ubuntu guest image.

Possible instructions:

```bash
$ wget http://releases.ubuntu.com/jammy/ubuntu-22.04.4-live-server-amd64.iso
$ qemu-img create -f qcow2 ubuntu.qcow2 40G
$ qemu-system-x86_64 \
    -cdrom ubuntu-22.04.4-live-server-amd64.iso \
    -drive "file=ubuntu.qcow2,format=qcow2" \
    -bios /usr/share/ovmf/OVMF.fd \
    -enable-kvm \
    -m 4G \
    -smp 4
```

Follow the instructions to install Ubuntu.
After the installation, start the VM. We are going to use a shared directory to copy the kernel configuration (see step 1, `CONFIG_KVM_AMD_SEV` has to be enabled) into the VM.

```bash
$ mkdir -p /path/to/shared/directory 
$ cp /path/to/kernel-config /path/to/shared/directory/
$ qemu-system-x86_64 \
    -drive "file=ubuntu-snapshot.qcow2,format=qcow2" \
    -enable-kvm -m 2G -smp 2 \
    -virtfs local,path=/path/to/shared/directory,mount_tag=hostshare,security_model=passthrough,id=hostshare
``` 

Within the VM, execute:

```bash
$ sudo apt-get install git fakeroot build-essential ncurses-dev xz-utils libssl-dev bc flex libelf-dev bison
$ git clone https://github.com/coconut-svsm/linux 
$ cd linux
$ git checkout svsm 
```

Next, mount the shared directory and copy the kernel configuration file:

```bash
$ sudo mount -t 9p -o trans=virtio hostshare /mnt
$ cp /mnt/kernel-config ./.config
```

Then, install the kernel:

```bash
$ make -j $(nproc)
$ sudo make modules_install
$ sudo make install
```

To compile the kernel on Arch Linux, you can use and adapt the `bin/compile_guest_kernel_arch.sh` script.

### 5. Building the COCONUT-SVSM

To build the SVSM itself using the special OVMF built in step 3, run

``` bash
$ inv coconut.svsm.build
```

This command creates the file `coconut-qemu.igvm` in the `BIN_DIR`.

### 6. Putting it all together

To start the guest VM, execute

```bash
$ inv coconut.qemu.guest
```

Modify the QEMU command in this file according to your needs.
`-d`/ `--detach` starts qemu in detached mode.

If you are executing QEMU on a remote server, 
you can use TigerVNC:

```bash
$ inv coconut.qemu.guest -v
$ ssh -L 5901:localhost:5901 user@server
$ vncviewer localhost:5901
```

If you want to connect to the VM using ssh, you can use the following commands:

```bash
$ ssh-copy-id -i ~/.ssh/YOUR_SSH_KEY -p 2222 USERNAME@localhost
$ ssh -i ~/.ssh/YOUR_SSH_KEY -p 2222 USERNAME@localhost"
```
