# CoCo Serverless

The goal of this project is to deploy Knative on CoCo and run some baseline benchmarks.

All instructions in this repository assume that you have checked-out the source code, and have activated the python virtual environment:

```bash
source ./bin/workon.sh

# List available tasks
inv -l
```

## Quick Start

First, install the kubernetes-related tooling: `kubectl`, `kubeadm`, and `kubelet`:

```bash
inv k8s.install
```

Then, deploy a (single-node) kubernetes cluster using one of the supported
methods:
* [Kubeadm](./docs/kubeadm)
* [Microk8s](./docs/uk8s) (TODO, doesn't work)

Second, install both the operator and the CC runtime from the upstream tag.
We currently pin to version `v0.7.0` (see the [`COCO_RELEASE_VERSION` variable](https://github.com/csegarragonz/coco-serverless/tree/main/tasks/util/env.py)).

```bash
inv operator.install
inv operator.install-cc-runtime
```

## Uninstall

In order to uninstall components for debugging purposes, you may un-install the CoCo runtime, and then the operator as follows:

```bash
inv operator.uninstall-cc-runtime
inv operator.uninstall
```
