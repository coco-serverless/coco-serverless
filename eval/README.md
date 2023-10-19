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

## Benchmarks

TODO
