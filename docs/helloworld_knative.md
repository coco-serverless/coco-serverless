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

## Knative on CoCo

For the time being, CoCo requires the image to _always_ be pulled on the guest.
If the image is present on the host, Knative will try to cache it (as it is
not possible to specify `imagePullPolicy: Always`), and the pod won't start
complaining about problems mounting the root file-system.

To remove the image from the host's cache, you can use `crictl`:

```bash
sudo crictl rmi <image_id>
```

note that, if _only_ using CoCo, the images are _never_ on the host, so they
should never be cached.
