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
$ ssh-copy-id -i ~/.ssh/YOUR_SSH_KEY -p 2222 user@localhost
$ ssh -i ~/.ssh/YOUR_SSH_KEY -p 2222 user@localhost"
```

## Experiments 

### Communicate with the SVSM

To communicate between the Secure VM Service Module (SVSM) and the guest, we can define and use our own protocol. Refer to Section 5 of AMD's [Secure VM Service Module for SEV-SNP Guests](https://www.amd.com/content/dam/amd/en/documents/epyc-technical-docs/specifications/58019.pdf) documentation for more details.

On the guest side, are using a new system call to invoke the protocol from the guest user space (see [GitHub coco-serverless Linux fork](https://github.com/coco-serverless/linux/blob/svsm/arch/x86/entry/syscalls/syscall_64.tbl#L432)). 

```C
syscall(svsm, REQUEST_NUMBER);
```

The guest kernel then executes the protocol call.

On the SVSM side, requests to our new protocol are handled by `request_loop_once` in `svsm/kernel/src/requests.rs` (see [GitHub coco-serverless SVSM fork](https://github.com/coco-serverless/svsm/blob/main/kernel/src/requests.rs#L115)).



### Restore the memory of the guest to a well-known state

In serverless computing, using confidential VMs (cVMs) introduces performance challenges, as discussed in the workshop paper [Serverless Confidential Containers: Challenges and Opportunities](https://dl.acm.org/doi/10.1145/3642977.3652097). One approach to mitigate the overhead of starting new cVMs for each request is to preboot cVMs and reuse them across users and requests. Ensuring confidentiality and integrity in this scenario requires, among other things, restoring the cVM's memory to a well-known state between uses.

Leveraging AMD's SEV-SNP extension, we employ a Secure Virtual Machine Service Module (SVSM) running at a higher privilege level (VMPL 1) than the guest VM (VMPL > 1). SEV-SNP provides integrity protection through a Reverse Map Table (RMP), which maintains a one-to-one mapping between system physical addresses and guest physical addresses, including security attributes for each page. Before a private memory page is used, the cVM must validate it using the PVALIDATE instruction, which sets the Validated flag in the corresponding RMP entry.

We explored two approaches to restoring the guest memory to a well-known state:

1. Full Backup Approach: Upon receiving a signal from the guest via a custom protocol after the boot process, the SVSM backs up all validated guest memory pages, capturing a well-known state. 
Upon receiving a second signal, the SVSM attempts to restore these pages. This is similar to a hot swap of the memory from the guest's point of view. However, restoration the pages currently results in a termination of the guest, therefore requiring further work.

1. Trap-on-Write Approach: After receiving a ping from the guest, we clear the WRITE bits in the RMP of all validated pages. Subsequent writes trigger a #VMEXIT(NPF), as outlined in section "15.36.10 RMP and VMPL Access Checks" of the [AMD64 Architecture Programmer’s Manual Volume 2](https://dl.acm.org/doi/10.1145/3642977.3652097). Now, the SVSM should intercept to back up the modified page before restoring the WRITE bit. Then, after receiving a second ping to restore the well-known state, the SVSM restores modified pages and clears the WRITE bits again to maintain control. 
Next steps include tracing the #VMEXIT(NPF) code path in the Linux kernel and delegating the control to the SVSM if the #VMEXIT(NPF) was triggered due to our Trap-on-Write mechanism.
