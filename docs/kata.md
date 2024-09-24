# Kata Containers

Most of the Kata development happens in our [Kata fork](
https://github.com/csegarragonz/kata-containers). The reason why we use a fork
is to pin to an older, but stable, CC release, and add patches on top when
necessary. Down the road (and particularly when CoCo uses Kata's main), we'd
get rid of the fork.

## Tweaking Kata

We provide a containerised environment to develop/patch Kata. First, build the
workon container image using:

```bash
inv kata.build
```

then you may get a shell by running:

```bash
inv kata.cli
```

> [!WARNING]
> The changes you make inside the Kata environment won't be persisted across
> container restarts. This is a deliberate design choice. You can hot-patch
> the Kata Agent by following the instructions in the following section. To
> permanently patch it, push the changes to the `sc2-main` branch and re-build
> the container: `inv kata.build --nocache`.

## Replacing the Kata Agent

Replacing the Kata Agent is something we may do regularly, and is a fairly
automated process.

The agent replacement script copies the agent binary from our Kata work-on
docker image. There are two ways in which the copying happens:

### One-off Copy

If the work-on image is not running, the script will copy the built-in binary
from the built-in image. The steps are:

```bash
inv kata.build
inv kata.replace-agent
```

### Hot-Patch

To develop on Kata, and quickly generate new `initrd`s, you may use the Kata
CLI. In this case, when the work-on image is running, the replacement script
will copy the binary from the CLI. Note that, as previously mentioned,
any changes made therein are not persisted across container restarts.

```bas
inv kata.cli [--mount-path <path_to_local_kata_checkout>]
cd src/agent
...
# Make changes
...
make
exit
inv kata.replace-agent
```

The new VMs you start should use the new `initrd` (and thus the updated
`kata-agent`). Note that we replace the `initrd` for both `qemu` and `qemu-sev`
runtime classes.

# Replacing the Kata Shim

To replace the Kata Shim for the `qemu-sev` runtime class, you can follow a
very similar approach to [replacing the agent](#replacing-the-kata-agent):

```bash
inv kata.cli
cd src/runtime
...
# Make changes
...
make
exit
inv kata.replace-shim
```

note that this changes will not affect other runtime classes.
