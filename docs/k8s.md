# Setting up a Kubernetes cluster

This project is, essentially, Kubernetes native. For most of the development and
deployment we need a running, and well-configured, single-node k8s cluster. In
this document we include instructions to set-it up and a troubleshooting guide.

In our kubernetes stack we need:
* A modified `containerd` - required to run confidential containers
* A working CNI plugin - required for pod-to-pod networking, we use Flannel.
* A working service mesh - required for Knative's network programming, we use Kourier.

## Setting up containerd

To compile our custom `containerd`, we can use the utility script:

```bash
inv containerd.build
```

and we can install it with:

```bash
inv containerd.install
```

## Setting up the node

We use `kubeadm` to bootstrap the single-node cluster. To install all required
binaries you may run:

```bash
inv k8s.install
```

All configuration files live under `../conf-files`. There are a couple of things
to bear in mind:
* The Pod CIDR needs to be the same in the: `containerd`, `flannel`, and `kubeadm` config.
