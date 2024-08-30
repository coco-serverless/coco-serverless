## Knative Chaining

We support function chaining in Knative using a combination of primitives from
both Knative Serving and Knative Eventing, together with the CloudEvents
specification.

> [!WARN]
> Knative Eventing requires hairpin traffic to be enabled in the cluster's
> CNI configuration. Flannel did not work for us so we had to move to Calico.

In particular, we use:
- Knative Services: for nodes in the DAG (i.e. functions).
- Knative JobSinks: like services, but for fan-out scenatios where we want a
  one-to-one mapping between CloudEvents and service instances.
- Knative Channels: edges in the DAG.
- Knative Subscriptions: determine the beginning and ending of an edge.

Knative uses CloudEvents to send data around the chains. We use the
CloudEvent's SDK to listen for requests from our Knative service, and
respond to them.

As part of our demos, we [implement](./apps/knative_chaining/chaining.yaml)
a fan-out/fan-in pattern (a la MapReduce), where the fan-out degree is
determined at run-time.

To run this sample first build the main service container image:

```bash
# NOTE: requires push access to ghcr.io/coco-serverless
inv apps.build --app knative-chaining
```

then, make sure that your Kata installation supports changing the pod's
memory via annotations:

```bash
inv kata.enable-annotation default_memory
```

lastly, you can run the app:

```bash
kubectl apply -f ./apps/knative_chaining/chaining.yaml
```


