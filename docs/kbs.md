# Key Broker Service

The Key Broker Service is a key piece in the CoCo architecture. It behaves as
the relying-party (RP) in the remote attestation process. Among other things,
the KBS is responsible to establish a secure channel with the PSP to get the
launch measurements, as well as storing image signature/encryption policies and
keys.

The KBS runs as a separate process in a separate (trusted) location. For the
sake of experimentation, we currently run the KBS with `docker compose` in the
same node we run the experiments in. This is **not** secure, and should be
changed in a production environment. In addition, and for the time being,
we use our own fork of the [simple KBS](https://github.com/csegarragonz/simple-kbs)
which we track as a submodule in [`./components/simple-kbs`](../components/simple-kbs).

You can see the available interactions with the KBS with: `inv -l kbs`. If
you want further control over what is happening, you can `cd` into the submodule
and use regular `docker`/`docker compose` commands.
