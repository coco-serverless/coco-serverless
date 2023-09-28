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
