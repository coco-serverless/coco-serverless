# cVM Cache

This feature of SC2 implements a VM cache for confidential VMs. It leverages
Kata's (broken) VM cache and tweaks it for its use in a confidential context.

## Resurrecting Kata's VM Cache

There are two main sets of fixes to get VM Cache to work with CoCo. First, we
need to fix VM Cache for non-CoCo pods, and then do some extra work in CoCo.

In a non-CoCo setting (`qemu-coco-dev` is the recommended runtime), we just
need to apply a few patches that are lost in open PRs in Kata. VM Cache seems
to like running with `shared_fs = "none"`, which already works for our use case.

> [!WARNING]
> Using `shared_fs = "none"` requires setting `nydus` as the snapshotter!

The main issue when porting VM Cache to CoCo is not the TEE itself, but hot-
plugging the `veth` device when using OVMF. We need to make sure that we
hot-plug the device to one of the PCIe root ports, and configure Kata to
allocate extra root ports, even if it cannot auto-detect them.

Our patches to the kata runtime, together with the following changes in the
config get the job done:

```toml
[factory]
vm_cache_number = 3

[hypervisor.qemu]
# The only way to hot-plug devices with OVMF is via the PCIe root port. Even
# though we are  hot-plugging a veth device (not a VFIO one), we need to set
# this variable as, otherwise, Kata will not configure the right PCIe topology
# for the guest.
# See: src/runtime/virtcontainers/qemu.go -> createPCIeTopology
hot_plug_vfio = "root-port"

# Kata will try to auto-detect how many root ports we need. However, we do not
# know this at VM creation (in the factory) so we need to hard-code it here
pcie_root_port = 2
```

## Running the VM Cache

The VM cache is a long-running component that contains a number of `paused`
QEMU VMs. You can start it  by running:

```bash
sudo /opt/kata/bin/kata-runtime-sc2 \
  --config /opt/kata/share/... \
  --log /tmp/kata_factory.log \
  factory init
```

and from another directory, check that the VMs are created:

```bash
sudo /opt/kata/bin/kata-runtime-sc2 factory status
```

you may also inspect the logs of the container by running:

```bash
sudo tail -f /tmp/kata_factory.log
```
