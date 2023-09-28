# Kata Containers

Most of the Kata development happens in our [Kata fork](
https://github.com/csegarragonz/kata-containers). The reason why we use a fork
is to pin to an older, but stable, CC release, and add patches on top when
necessary. Down the road (and particularly when CoCo uses Kata's main), we'd
get rid of the fork.

## Tweaking Kata

To get a working environment to modify Kata, clone our fork and build/exec into
the workon container. For convenience, it is recommended to clone the fork at
the same directory level that this repo lives (i.e. ../kata-containers).

```bash
git clone https://github.com/csegarragonz/kata-containers
cd kata-containers
./csg-bin/build_docker.sh
./csg-bin/cli.sh
```

## Replacing the Kata Agent

Replacing the Kata Agent is something we may do regularly, and is a fairly
automated process.

First, from our Kata fork, rebuild the `kata-agent` binary:

```bash
cd ../kata-containers
./csg-bin/cli.sh
cd src/agent
make
exit
cd -
```

Second, from this repository, bake the new agent into the `initrd` image used
by `qemu-sev` and update the config path:

```bash
inv kata.replace-agent
```

The new VMs you start should use the new `initrd` (and thus the updated
`kata-agent`).
