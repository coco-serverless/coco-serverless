# Knative

This project uses [Knative serving](https://knative.dev/docs/serving/) as our
serverless frontend of choice.

To install it, you may run:

```bash
inv knative.install
```

the installation process also instals [MetalLB](https://metallb.universe.tf/),
a bare-metal load balancer to provide external IPs required for Knative's
networking.

To un-install Knative, you may run:

```bash
inv knative.uninstall
```

note that Knative un-installation process is a bit flaky and likely to fail or
leave orphaned resources. If you want a secure fresh Knative restart, we
recommend tearing down the cluster and starting it again:

```bash
inv kubeadm.destroy
inv kubeadm.create
inv knative.install
```
