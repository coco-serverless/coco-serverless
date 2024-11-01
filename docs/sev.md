# AMD SEV-SNP Configuration

To run this project (and CoCo in general) on AMD SEV-SNP there is some
additional configuration to be done.

For most of the SEV-SNP management, we recommend installing [`snphost`](
https://github.com/virtee/snphost).

## Provision Certificate Chain

Once per node we need to install a full certificate chain. To do so, run:

```bash
sudo mkdir -p /opt/sev
sudo snphost export --full /opt/sev/cert_chain.cert
```

## Annotations

If you use any kata-specific annotations (like `io.katacontainers.config.pre-attestation.enabled`)
you need to add them to an allow-list in `/opt/confidential-containers/share/defaults/kata-containers/configuration-<runtime>.toml`
and maybe in the `/etc/containerd/config.toml`.
