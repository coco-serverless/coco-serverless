# CoCo Serverless

This is project is an extention of the [coco-serverless](https://github.com/coco-serverless/coco-serverless/edit/main/README.md). The project has two main goals:
* to deploy [Knative](https://knative.dev/docs/) on [CoCo](https://github.com/confidential-containers) and run some baseline benchmarks.
* Deploy and benchmark custom CoCo implementation that imporves the image pulling mechanism (CoCo-Hybrid), providing a comparison with the previous baselines. 

Our CoCo-hybrid mode makes ajustments so several of the CoCo components, all of which can be found in the following branches of our forked repositories:
* [Nydus-snapshotter](https://github.com/konsougiou/nydus-snapshotter/tree/ks-main-0.13.3)
* [kata-containers](https://github.com/coco-serverless/kata-containers/tree/ks-prod)
* [guest-components](https://github.com/coco-serverless/guest-components/tree/KS-prod)
* [nydus]()

All instructions in this repository assume that you have checked-out the source
code, and have activated the python virtual environment:

```bash
source ./bin/workon.sh

# List available tasks
inv -l
```

## Pre-Requisites

You will need CoCo's fork of containerd built and running. To this extent you
may run:

```bash
inv containerd.build
inv containerd.install
```

You also need all the kubernetes-related tooling: `kubectl`, `kubeadm`, and
`kubelet`:

```bash
inv k8s.install [--clean]
```

You may also want to install `k9s`, a kubernetes monitoring tool:

```bash
inv k9s.install-k9s
```

## Quick Start

Deploy a (single-node) kubernetes cluster using `kubeadm`:

```bash
inv kubeadm.create
```

Second, install both the operator and the CC runtime from the upstream tag.
We currently pin to version `v0.7.0` (see the [`COCO_RELEASE_VERSION` variable](
https://github.com/csegarragonz/coco-serverless/tree/main/tasks/util/env.py)).

```bash
inv operator.install
inv operator.install-cc-runtime
```

Third, update the `initrd` file to include our patched `kata-agent`:

```bash
inv kata.replace-agent
```

if it is the first time, you will have to manually build the agent following
[these instructions](./docs/kata.md#replacing-the-kata-agent).

Then, you are ready to run one of the supported apps:
* [Hello World! (Py)](./docs/helloworld_py.md) - simple HTTP server running in Python to test CoCo and Kata.
* [Hello World! (Knative)](./docs/helloworld_knative.md) - same app as before, but invoked over Knatvie.
* [Hello Attested World! (Knative + Attestation)](./docs/helloworld_knative_attestation.md) - same setting as the Knative hello world, but with varying levels of attestation configured.

If your app uses Knative, you will have to install it first:

```bash
inv knative.install
```
## Setting Up CoCo-Hybrid

In order to enable the CoCo-Hybrid mode, the following configuration steps need to be taken:

Our customised nydus-snapshotter binary, linux Kernel and VM initrd image. These can be installed using the following command:

```bash
inv hybrid.install-cc-hybrid-deps
```

The kata configs can then be adjusted to point to the nre kernel and initrd using the following command

```bash
inv hybrid.update-configs
```

Additionally, in ordert to configure the snapshotter to be in our hybrid mode the following commands can be run:

```bash
inv nydus-snapshotter.populate_host_sharing_config
inv nydus-snapshotter.toggle_mode --hybrid
```


## Evaluation

The goal of the project is to measure the performance of Knative with CoCo,
and compare it to other isolation mechanisms using standarised benchmarks. To
This extent, we provide a thorough evaluation in the [evaluation](./eval)
directory.

## Uninstall

In order to uninstall components for debugging purposes, you may un-install the CoCo runtime, and then the operator as follows:

```bash
inv operator.uninstall-cc-runtime
inv operator.uninstall
```

Lastly, you can completely remove the `k8s` cluster by running:

```bash
inv kubeadm.destroy
```

## Further Reading

For further documentation, you may want to check these other documents:
* [Attestation](./docs/attestation.md) - attestation particularities of CoCo and SEV(-ES).
* [Guest Components](./docs/guest_components.md) - patch `image-rs` or other guest components.
* [K8s](./docs/k8s.md) - documentation about configuring a single-node Kubernetes cluster.
* [Kata](./docs/kata.md) - instructions to build our custom Kata fork and `initrd` images.
* [Key Broker Service](./docs/kbs.md) - docs on using and patching the KBS.
* [Knative](./docs/knative.md) - documentation about Knative, our serverless runtime of choice.
* [Local Registry](./docs/registry.md) - configuring a local registry to store OCI images.
* [OVMF](./docs/ovmf.md) - notes on building OVMF and CoCo's OVMF boot process.
* [SEV](./docs/sev.md) - speicifc documentation to get the project working with AMD SEV machines.
* [Troubleshooting](./docs/troubleshooting.md) - tips to debug when things go sideways.