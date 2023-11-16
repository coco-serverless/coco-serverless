# Guest Components

When tweaking components like the KBC or `image-rs`, we need to modify the guest
component binaries that get included in the Kata Agent. This is a two step
process.

First, you can use our work-on container images to patch and build new versions
of the guest components. See `inv -l gc` for more details.

Second, push the changes to a git branch or repo. Then you can reference it
inside the `Cargo` file for the Kata Agent [here](
https://github.com/csegarragonz/kata-containers/blob/csg-main/src/agent/Cargo.toml#L74).
