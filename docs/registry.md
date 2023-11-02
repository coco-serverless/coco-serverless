# Using a Local Registry

In order to use a local image registry we need to configure both `containerd`
and `Kata` to like our home-baked registry. In addition, Kata does not seem to
be able to use HTTP registries inside the guest, so we need to go an extra
step and configure HTTPS certificates for our registry too.
