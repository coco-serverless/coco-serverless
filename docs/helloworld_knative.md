# Hello World! (Knative)

This application runs the same `Hello World!` sample than [`helloworld-py`](
./helloworld_py.md), but through Knative Serving.

To deploy it, you may run:

```bash
kubectl apply -f ./apps/helloworld-knative
```

then, you can test it out by reading the node port IP, and sending a `GET`
request:

```bash
# Figure out the URL using the following command
service_url=$(kubectl get ksvc helloworld-knative  --output=custom-columns=URL:.status.url --no-headers)

curl ${service_url}
# Hello World!
```

To remove the application, you can run:

```bash
kubectl delete -f ./apps/helloworld-knative
```
