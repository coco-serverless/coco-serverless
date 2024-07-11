# Coconut-SVSM

## Installation

For more details, please refer to [Coconut SVSM](https://github.com/coconut-svsm/svsm). The following instructions are intended to simplify the installation. 

### 1. Preparing the Host
TODO

### 2. Building QEMU
You will need a QEMU build that supports launching guests using IGVM:
```bash
inv coconut.qemu.build
```
This will create a file called `qemu-system-x86_64-igvm` in the `BIN_DIR`. 

### 3. Building the guest firmware

A special OVMF build is needed to launch a guest on top of the COCONUT-SVSM:
```
inv coconut.ovmf.build
```
A file named `ovmf-svsm.fd` will be created in the `BIN_DIR`.


### 4. Preparing the guest image
TODO

### 5. Building the COCONUT-SVSM
To build the SVSM itself using the special OVMF build from step 3, run
``` 
inv coconut.svsm.build
```
This command produces `svsm.bin` in the `BIN_DIR`.

### 6. Putting it all together
TODO


