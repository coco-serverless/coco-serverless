# Using a Local Registry

In order to use a local image registry we need to configure `containerd`,
`Kata`, and `containerd` to like our home-baked registry. In addition, Kata does
not seem to be able to use HTTP registries inside the guest, so we need to go an extra
step and configure HTTPS certificates for our registry too.

To this extent, we first create a self-signed certificate, and give it the
ALT name of our home-made registry. We must also include an entry in our DNS
records to match our local (reachable from within the guest) IP, to this
registry name.

Second, we need to update the docker config to include our certificates for
this registry, as well as containerd's.

Third, we need to include both the updated `/etc/hosts` file with the DNS
entries, as well as the certificate, inside the agent's `initrd`.

Finally, we need to configure Knative to accept self-signed certificates. To
do so, we need to update the `controller` deployment by applying a [patch](
./conf-files/knative_controller_custom_certs.yaml.j2).

All this process is automated when we start the local registry with the provided
task:

```bash
inv registry.start
```

and is undone when we stop it:

```bash
inv registry.stop
```
