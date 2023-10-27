# OVMF

To enable OVMF logging, we neeed to re-build OVMF from source with some patches
to make logging to QEMU's serial port possible. Note that we do not want to just
build a `DEBUG` OVMF, as that introduces too much overhead to the VM start-up
process. So we build a `RELEASE` version of OVMF with some extra patches to
allow some basic logging.

To do so, you may run:

```bash
inv ovmf.set-log-level debug
```

which will build OVMF from source, and configure Kata to use our version of
OVMF.

You may directly re-build OVMF by running:

```bash
inv ovmf.build [--target DEBUG,RELEASE]
```

## OVMF Boot Process

OVMF is the piece of virtual firmware responsible of booting up the confidential
VM. OVMF is exposed to the guest VM by QEMU as a flash device, and is the only
component measured by the PSP when initially provisioning memory pages for the
VM.

In order to maintain the trust model, when booting a confidential SEV guest,
the (measured) OVMF firmware comes with hardcoded measurements for the guest
kernel, the guest kernel command line, and the initrd measurement. Once
QEMU injects these components using the `fw_cfg` API, OVMF will check them
against the pre-recorded measure, and will only boot if the measurements match.

In more detail, the OVMF boot process in CoCo begins in a very similar way
than the [Platform Initialization (PI) Boot Phases described here](
https://raw.githubusercontent.com/tianocore/tianocore.github.io/master/images/PI_Boot_Phases.JPG).
First comes the SEC phase that prepares an environment that can execute some
C code, then the PEI phase further prepares the environment to handle control
to the device execution environment phase. This is where we spend the most time
(as depicted in [this figure](../eval/plots/vm-detial/vm_detail.png)), and
where we measure the components for integrity.

CoCo, however, does not use a boot loader (e.g. GRUB). Instead, the Kata Agent
runs as the `/init` process in the `initrd`. So once we load and start the
guest kernel in the `initrd` we never come back to OVMF.
