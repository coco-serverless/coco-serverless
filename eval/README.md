# Evaluation

This directory summarizes the different evaluation efforts to measure the
performance of Knative using confidential containers, and place it in relation
to well-known serverless benchmarks.

The evaluation of the project is divided in two parts:
* [Performance Measurements](#performance-measurements) - performance (overheads) of Knative on CoCo.
* [Benchmarks](#benchmarks) - evaluating Knative + CoCo on standarised benchmarks.

In general, we compare Knative running on regular containers, on VMs (aka
Knative + Kata) and with Knative + CoCo with different levels of security: (i)
no attestaion, (ii) only guest FW attestation, (ii) image signature, and (iii)
image signature + encryption.

## Performance Measurements

In order to execute any of the performance measurement experiments, it is
expected that you have a functional system as described in the [Quick Start](
https://github.com/csegarragonz/coco-serverless#quick-start) guide.

Then, start the KBS:

```bash
inv kbs.start

# If the KBS is already running, clear the DB contents
inv kbs.clear-db
```

you must also sign and encrypt all the images used in the performance tests.
Signing and encryption is an interactive process, hence why we do it once,
in advance of the evaluation:

```bash
# First encrypt (and sign) the image
inv skopeo.encrypt-container-image "ghcr.io/csegarragonz/coco-helloworld-py:unencrypted" --sign

# Then sign the unencrypted images used
inv cosign.sign-container-image "ghcr.io/csegarragonz/coco-helloworld-py:unencrypted"
inv cosign.sign-container-image "ghcr.io/csegarragonz/coco-knative-sidecar:unencrypted"
```

Now you are ready to run one of the experiments:
* [Start-Up Costs](#start-up-costs) - time required to spin-up a Knative service.
* [Instantiation Throughput](#instantiation-throughput) - throughput-latency of service instantiation.
* [Memory Size](#memory-size) - impact on initial VM memory size on start-up time.
* [VM Start-Up](#vm-start-up) - breakdown of the cVM start-up costs

### Start-Up Costs

This benchmark compares the time required to spin-up a pod as measured from
Kubernetes. This is the higher-level (user-facing) measure we can take.

The benchmark must be run with `debug` logging disabled:

```bash
inv containerd.set-log-level info kata.set-log-level info
```

In order to run the experiment, just run:

```bash
inv eval.startup.run
```

you may then plot the results by using:

```
inv eval.startup.plot
```

which generates a plot in [`./plots/startup/startup.png`](
./plots/sartup/startup.png). You can also see the plot below:

![plot](./plots/startup/startup.png)

In addition, we also generate a breakdown pie chart for one of the runs in
[`./plots/sartup/breakdown.png`](./plots/startup/breakdown.png):

![plot](./plots/startup/breakdown.png)

### Instantiation Throughput

In this experiment we measure the time it takes to spawn a fixed number of
Knative services. Each service uses the _same_ docker image, so it is a proxy
measurement for scale-up/scale-down costs.

In more detail, we template `N` different service files, apply all of them,
and wait for all associated service pods to be in `Ready` state. We report the
time between we apply all files, and the last service pod is `Ready`.

To run the benchmark, you may run:

```bash
inv eval.xput.run
```

which generates a plot in [`./plots/xput/xput.png`](
./plots/xput/xput.png). You can also see the plot below:

![plot](./plots/xput/xput.png)

### Memory Size

This experiment explores the impact of the initial VM memory size on the
Knative service start-up time.

By initial VM memory size we mean the memory size passed to QEMU with the `-m`
flag. This size can be configured through the Kata configuration file.

To run the experiment you may run:

```bash
inv eval.mem-size.run
```

which generates a plot in [`./plots/mem-size/mem_size.png`](
./plots/mem-size/mem_size.png). You can also see the plot below:

![plot](./plots/mem-size/mem_size.png)

### VM Start-Up

This experiment further analyzes the costs associated to spinning up just the
confidential VM (as part of the Knative service instantiation).

To run this test, we want to enable `debug` logging on `containerd`, `kata`,
and `ovmf`:

```bash
inv containerd.set-log-level debug kata.set-log-level debug ovmf.set-log-level debug
```

In very brief summary, the events when booting a confidential VM (for CoCo) are
the following:
1. `containerd` calls the `RunPodSandbox` API
2. The `kata-shim` translates this call into a QEMU command to start a VM
3. In the process of starting a VM, pre-attestation happens and secrets are
  injected from the KBS
4. The VM is officially started, and OVMF boots into the kernel from the `initrd`
5. The Kernel calls the `/init` process, which in our case is the `kata-agent`
6. Once the `kata-agent` has started, it concludes the API `RunPodSandbox` call

To generate a flame graph-like plot with the detailed costs, you may run:

```bash
inv eval.vm-detail.run
```

which generates a plot in [`./plots/vm-detail/vm_detail.png`](
./plots/vm-detail/vm_detail.png). You can also see the plot below:

![plot](./plots/vm-detail/vm_detail.png)

## Benchmarks

TODO
