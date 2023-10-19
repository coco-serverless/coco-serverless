# Attestation for Knative on CoCo

## SEV(-ES) Attestation

In SEV-ES the attestation (or pre-attestation) is driven by the **host**, and
happens before guest boot.

The host also facilitates the establishment of a secure channel between the
guest owner and the PSP.

As part of the pre-attestation, the host generates a launch measurement which
contains:
- Platform Information
- Launch Digest:
  - Hash of VM firmware
  - Initial vCPU State (only for SEV-ES)

The contents of the initial launch measurement are provisioned by the host and
measured by the PSP. Thus, they cannot contain any secrets.

Once the launch measurement is finished, the PSP uses the secure channel to
communicate the measurement to the guest owner, which will decide whether to
accept the measurement or not.

If the measurement is accepted, the guest owner can provision some unique
secrets and the VM can be booted.

## SEV-ES Direct Boot Process

To boot an SEV VM with CoCo we use a special VM firmware. In particular, we
take advantage of specific SEV support in OVMF.

The [AMD SEV package in OVMF](https://github.com/tianocore/edk2/blob/master/OvmfPkg/AmdSev/AmdSevX64.dsc)
sets aside some space in the firmware binary for storing the hashes of the
`initrd`, the kernel, and the kernel command line. When QEMU boots an SEV VM,
it hashes each of these components and injects the hashes into the firmware
bianry.

This means that when the host is provisioning the initial VM state, and the
PSP is measuring it, the measurement will be tied to a specific `initrd`,
kernel, and kernel command line, hash.

Then, we boot the VM directly from the `initrd` which contains the Kata Agent
as the `/sbin/init` process. In the `initrd` we also have other
[`guest-components`](https://github.com/confidential-containers/guest-components)
which include the `attestation-agent`, that will talk to the guest owner
to continue provisioning secrets to the guest after boot.
