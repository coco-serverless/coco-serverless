# Troubleshooting

In this document we include a collection of tips to help you debug the system
in case something is not working as expected.

## K8s Monitoring with K9s

Gaining visibility into the state of a Kubernetes cluster is hard. Thus we can
not stress enough how useful `k9s` is to debug what is going on.

We strongly recommend you using it, you may install it with:

```bash
inv k9s.install
export KUBECONFIG=$(pwd)/.config/kubeadm_kubeconfig
k9s
```

## Enabling debug logging in the system journal

Another good observability tool are the journal logs. Both `containerd` and
`kata-agent` send logs to the former's systemd journal log. You may inspect
the logs using:

```bash
sudo journalctl -xeu containerd
```

To enable debug logging you may run:

```bash
inv containerd.set-log-level [debug,info]
inv kata.set-log-level [debug,info]
```

naturally, run the commands again with `info` to reset the original log level.

## Nuking the whole cluster

When things really go wrong, resetting the whole cluster is usually a good way
to get a clean start:

```bash
inv kubeadm.destroy kubeadm.create
```

If you want a really clean start, you can re-install cotnainerd and all the
`k8s` tooling:

```bash
inv kubeadm.destroy
inv containerd.build containerd.install
inv k8s.install --clean
inv kubeadm.create
```

## Known Issues

### Nydus Clean-Up Issue

If you encounter a `ContainerCreating` error with an error message along the
lines of:

```
failed to extract layer sha256:1e604deea57dbda554a168861cff1238f93b8c6c69c863c43aed37d9d99c5fed: failed to get reader from content store: content digest sha256:9fa9226be034e47923c0457d916aa68474cdfb23af8d4525e9baeebc4760977a: not found
```

you need to manually fetch the image contents on the host. This is a once-per-
host fix:

```bash
ctr -n k8s.io content fetch ${IMAGE_NAME}
```

the image name is the image tag appearing right before the error message in
the pod logs.
