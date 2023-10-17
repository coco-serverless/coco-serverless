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

### Start-Up Costs

This benchmark compares the time required to spin-up a pod as measured from
Kubernetes. This is the higher-level (user-facing) measure we can take.

In order to run the experiment, just run:

```
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

## Benchmarks

TODO
