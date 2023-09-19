# AMD SEV Configuration

To run this project (and CoCo in general) on AMD SEV nodes there is some
additional configuration to be done.

For most of the SEV management, we recommend installing [`sevctl`](
https://github.com/virtee/sevctl). If something is not covered here, make sure
to check the upstream [CoCo SEV guide](
https://github.com/confidential-containers/confidential-containers/tree/main/guides/sev.md).

## Provision Certificate Chain

Once per node we need to install a full certificate chain. To do so, run:

```bash
sudo mkdir -p /opt/sev
sudo sevctl export --full /opt/sev/cert_chain.cert
```

## Annotations

If you use any kata-specific annotations (like `io.katacontainers.config.pre-attestation.enabled`)
you need to add them to an allow-list in `/opt/confidential-containers/share/defaults/kata-containers/configuration-<runtime>.toml`
and maybe in the `/etc/containerd/config.toml`.
