# Hello World! (Python)

This application is a simple HTTP server written in Python that returns
`Hello World!` when receives a request.

To deploy it, you may run:

```bash
kubectl apply -f ./apps/helloworld-py
```

then, you can test it out by reading the node port IP, and sending a `GET`
request:

```bash
# Figure out the IP
service_ip=$(kubectl get services -o jsonpath='{.items[?(@.metadata.name=="coco-helloworld-py-node-port")].spec.clusterIP}')

curl -X GET ${service_ip}:8080
# Hello World!
```

To remove the application, you can run:

```bash
kubectl delete -f ./apps/helloworld-py
```
