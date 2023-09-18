# CoCo Serverless

The goal of this project is to deploy Knative on CoCo and run some baseline benchmarks.

## Quick Start

First, get the local `k8s` cluster ready with [`microk8s`](./docs/uk8s.md).

```bash
inv uk8s.install
```

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
