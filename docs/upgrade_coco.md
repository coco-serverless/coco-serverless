## CoCo Upgrade List

CoCo cuts out new releases often. Here is what you need to do when a new
release comes out.

### Clean-Up Previous Versions

CoCo does not like in-place upgrades. To ensure a smooth upgrade make sure
you first clean-up the previous install:

```bash
inv kuebadm.destroy
sudo rm -rf /opt/kata
sudo rm -rf /opt/confidential-containers
```

### Upgrade Host Kernel

CoCo relies on specific patches for the host kernel. Make sure you upgrade
to the version they point to.

### Upgrade CoCo Version Tag

First, bump the `COCO_RELEASE_VERSION` in `tasks/util/env.py`. Then work-out
what Kata version is being used, and `cd` into your `kata-containers` source
tree.

### Update Kata and Guest Components

The source tree should point to `sc2-main`. We need to rebase it on the latest
Kata:

```bash
git fetch upstream

# You may try to first rebase and re-build on a test branch
git checkout -b sc2-main-test
git rebase <TAG>
git push origin sc2-main-test
```

If you have any changes on top of guest components, you should rebase them
on top of `0.10.0`, re-build, and push the tag. Note that you Kata fork should
point to a guest components version with the `sc2-main` branch.

Now, if you have used a test branch, update the branch name in the kata
dockerfile in `./docker/kata.dockerfile`, and try to re-build Kata:

```bash
inv kata.build
inv kata.replace-agent
```

### Dry Run

The only thing remaining is to test a fresh install:

```bash
inv kubeadm.create operator.install operator.install-cc-runtime knative.install
```

and run some demo functions.
