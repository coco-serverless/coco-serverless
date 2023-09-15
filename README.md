# CoCo Serverless

The goal of this project is to run Knative using confidential containes instead than plain Docker containers.

## Quick Start

First, get the local `k8s` cluster ready with [`microk8s`](./docs/uk8s.md).

Second, build and install both the operator and the CC runtime. For the operator, we currently pin to version `v0.7.0` and we maintain a separate directory with the source code. TODO: don't rely on a local checkout.

```bash
inv operator.install
```
