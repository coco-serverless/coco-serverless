from invoke import task
from os.path import join
from tasks.util.env import CONF_FILES_DIR, LOCAL_REGISTRY_URL, print_dotted_line
from tasks.util.knative import (
    configure_self_signed_certs as do_configure_self_signed_certs,
    patch_autoscaler as do_patch_autoscaler,
    replace_sidecar as do_replace_sidecar,
)
from tasks.util.kubeadm import run_kubectl_command, wait_for_pods_in_ns
from tasks.util.registry import (
    HOST_CERT_DIR,
    HOST_CERT_PATH,
    K8S_SECRET_NAME,
)
from time import sleep

KNATIVE_VERSION = "1.15.0"

# Namespaces
KNATIVE_EVENTING_NAMESPACE = "knative-eventing"
KNATIVE_SERVING_NAMESPACE = "knative-serving"
KOURIER_NAMESPACE = "kourier-system"
ISTIO_NAMESPACE = "istio-system"

# URLs
KNATIVE_SERVING_BASE_URL = "https://github.com/knative/serving/releases/download"
KNATIVE_SERVING_BASE_URL += "/knative-v{}".format(KNATIVE_VERSION)
KNATIVE_EVENTING_BASE_URL = "https://github.com/knative/eventing/releases/download"
KNATIVE_EVENTING_BASE_URL += "/knative-v{}".format(KNATIVE_VERSION)
KOURIER_BASE_URL = "https://github.com/knative/net-kourier/releases/download"
KOURIER_BASE_URL += "/knative-v{}".format(KNATIVE_VERSION)


def install_kourier(debug=False):
    kube_cmd = "apply -f {}".format(join(KOURIER_BASE_URL, "kourier.yaml"))
    run_kubectl_command(kube_cmd, capture_output=not debug)

    # Wait for all components to be ready
    wait_for_pods_in_ns(
        KNATIVE_SERVING_NAMESPACE,
        label="app=net-kourier-controller",
        expected_num_of_pods=1,
        debug=debug,
    )
    wait_for_pods_in_ns(
        KOURIER_NAMESPACE,
        label="app=3scale-kourier-gateway",
        expected_num_of_pods=1,
        debug=debug,
    )

    # Configure Knative Serving to use Kourier
    kube_cmd = [
        "patch configmap/config-network",
        "--namespace {}".format(KNATIVE_SERVING_NAMESPACE),
        "--type merge",
        "--patch",
        '\'{"data":{"ingress-class":"kourier.ingress.networking.knative.dev"}}\'',
    ]
    kube_cmd = " ".join(kube_cmd)
    run_kubectl_command(kube_cmd, capture_output=not debug)


def install_istio(debug=False):
    istio_base_url = (
        "https://github.com/knative/net-istio/releases/download/knative-v{}".format(
            KNATIVE_VERSION
        )
    )
    istio_url = join(istio_base_url, "istio.yaml")
    kube_cmd = "apply -l knative.dev/crd-install=true -f {}".format(istio_url)
    run_kubectl_command(kube_cmd)

    run_kubectl_command("apply -f {}".format(istio_url))
    run_kubectl_command("apply -f {}".format(join(istio_base_url, "net-istio.yaml")))
    wait_for_pods_in_ns(KNATIVE_SERVING_NAMESPACE, 6)
    wait_for_pods_in_ns(ISTIO_NAMESPACE, 6)


def install_metallb(debug=False):
    """
    Install the MetalLB load balancer
    """
    # First deploy the load balancer
    metalb_version = "0.13.11"
    metalb_url = "https://raw.githubusercontent.com/metallb/metallb/"
    metalb_url += "v{}/config/manifests/metallb-native.yaml".format(metalb_version)
    kube_cmd = "apply -f {}".format(metalb_url)
    run_kubectl_command(kube_cmd, capture_output=not debug)
    wait_for_pods_in_ns(
        "metallb-system",
        label="component=controller",
        expected_num_of_pods=1,
        debug=debug,
    )
    wait_for_pods_in_ns(
        "metallb-system", label="component=speaker", expected_num_of_pods=1, debug=debug
    )

    # Second, configure the IP address pool and L2 advertisement
    metallb_conf_file = join(CONF_FILES_DIR, "metallb_config.yaml")
    run_kubectl_command(
        "apply -f {}".format(metallb_conf_file), capture_output=not debug
    )


@task
def install(ctx, skip_push=False, debug=False):
    """
    Install Knative on a running K8s cluster

    Steps here follow closely the Knative docs:
    https://knative.dev/docs/install/yaml-install/serving/install-serving-with-yaml
    """
    net_layer = "kourier"

    print_dotted_line(
        f"Installing Knative (v{KNATIVE_VERSION}) with {net_layer} as net layer"
    )

    # Knative requires a functional LoadBalancer, so we use MetaLB
    install_metallb(debug=debug)

    # -----
    # Install Knative Serving
    # -----

    # Create the knative CRDs
    kube_cmd = "apply -f {}".format(join(KNATIVE_SERVING_BASE_URL, "serving-crds.yaml"))
    run_kubectl_command(kube_cmd, capture_output=not debug)

    # Install the core serving components
    kube_cmd = "apply -f {}".format(join(KNATIVE_SERVING_BASE_URL, "serving-core.yaml"))
    run_kubectl_command(kube_cmd, capture_output=not debug)

    # Wait for the core components to be ready
    wait_for_pods_in_ns(
        KNATIVE_SERVING_NAMESPACE,
        label="app=activator",
        expected_num_of_pods=1,
        debug=debug,
    )
    wait_for_pods_in_ns(
        KNATIVE_SERVING_NAMESPACE,
        label="app=autoscaler",
        expected_num_of_pods=1,
        debug=debug,
    )
    wait_for_pods_in_ns(
        KNATIVE_SERVING_NAMESPACE,
        label="app=controller",
        expected_num_of_pods=1,
        debug=debug,
    )
    wait_for_pods_in_ns(
        KNATIVE_SERVING_NAMESPACE,
        label="app=webhook",
        expected_num_of_pods=1,
        debug=debug,
    )

    # -----
    # Install Knative Eventing
    # -----

    # Create the knative CRDs
    kube_cmd = "apply -f {}".format(
        join(KNATIVE_EVENTING_BASE_URL, "eventing-crds.yaml")
    )
    run_kubectl_command(kube_cmd, capture_output=not debug)

    # Install the core serving components
    kube_cmd = "apply -f {}".format(
        join(KNATIVE_EVENTING_BASE_URL, "eventing-core.yaml")
    )
    run_kubectl_command(kube_cmd, capture_output=not debug)

    # Wait for the core components to be ready
    wait_for_pods_in_ns(
        KNATIVE_EVENTING_NAMESPACE,
        label="app=eventing-controller",
        expected_num_of_pods=1,
        debug=debug,
    )
    wait_for_pods_in_ns(
        KNATIVE_EVENTING_NAMESPACE,
        label="app=eventing-webhook",
        expected_num_of_pods=1,
        debug=debug,
    )
    wait_for_pods_in_ns(
        KNATIVE_EVENTING_NAMESPACE,
        label="sinks.knative.dev/sink=job-sink",
        expected_num_of_pods=1,
        debug=debug,
    )

    # Install non-core eventing components
    kube_cmd = "apply -f {}".format(
        join(KNATIVE_EVENTING_BASE_URL, "in-memory-channel.yaml")
    )
    run_kubectl_command(kube_cmd, capture_output=not debug)

    kube_cmd = "apply -f {}".format(
        join(KNATIVE_EVENTING_BASE_URL, "mt-channel-broker.yaml")
    )
    run_kubectl_command(kube_cmd, capture_output=not debug)

    # Wait for non-core components to be ready
    wait_for_pods_in_ns(
        KNATIVE_EVENTING_NAMESPACE,
        label="app.kubernetes.io/component=imc-controller",
        expected_num_of_pods=1,
        debug=debug,
    )
    wait_for_pods_in_ns(
        KNATIVE_EVENTING_NAMESPACE,
        label="app.kubernetes.io/component=imc-dispatcher",
        expected_num_of_pods=1,
        debug=debug,
    )
    wait_for_pods_in_ns(
        KNATIVE_EVENTING_NAMESPACE,
        label="app.kubernetes.io/component=broker-controller",
        expected_num_of_pods=1,
        debug=debug,
    )
    wait_for_pods_in_ns(
        KNATIVE_EVENTING_NAMESPACE,
        label="app.kubernetes.io/component=broker-filter",
        expected_num_of_pods=1,
        debug=debug,
    )
    wait_for_pods_in_ns(
        KNATIVE_EVENTING_NAMESPACE,
        label="app.kubernetes.io/component=broker-ingress",
        expected_num_of_pods=1,
        debug=debug,
    )

    # -----
    # Install a networking layer
    # -----

    # Install a networking layer
    if net_layer == "istio":
        net_layer_ns = ISTIO_NAMESPACE
        net_layer_service_name = "istio-ingressgateway"
        install_istio(debug)
    elif net_layer == "kourier":
        net_layer_ns = KOURIER_NAMESPACE
        net_layer_service_name = "kourier"
        install_kourier(debug)

    # Update the Serving's ConfigMap to support running CoCo
    knative_configmap = join(CONF_FILES_DIR, "knative_config.yaml")
    run_kubectl_command(
        "apply -f {}".format(knative_configmap), capture_output=not debug
    )

    # Get Knative's external IP
    ip_cmd = [
        "--namespace {}".format(net_layer_ns),
        "get service {}".format(net_layer_service_name),
        "-o jsonpath='{.status.loadBalancer.ingress[0].ip}'",
    ]
    ip_cmd = " ".join(ip_cmd)
    expected_ip_len = 4
    actual_ip = run_kubectl_command(ip_cmd, capture_output=True)
    actual_ip_len = len(actual_ip.split("."))
    while actual_ip_len != expected_ip_len:
        if not debug:
            print("Waiting for kourier external IP to be assigned by the LB...")

        sleep(3)
        actual_ip = run_kubectl_command(ip_cmd, capture_output=True)
        actual_ip_len = len(actual_ip.split("."))

    # Deploy a DNS
    kube_cmd = "apply -f {}".format(
        join(KNATIVE_SERVING_BASE_URL, "serving-default-domain.yaml")
    )
    run_kubectl_command(kube_cmd, capture_output=not debug)
    wait_for_pods_in_ns(
        KNATIVE_SERVING_NAMESPACE,
        label="app=default-domain",
        expected_num_of_pods=1,
        debug=debug,
    )

    # -----
    # Patch Knative components
    # -----

    # Replace the sidecar to use an image we control
    do_replace_sidecar(skip_push=skip_push, quiet=not debug)

    # Patch the auto-scaler
    do_patch_autoscaler(debug=debug)

    # Create a k8s secret with the credentials to support pulling images from
    # a local registry with a self-signed certificate
    kube_cmd = (
        "-n knative-serving create secret generic {} --from-file=ca.crt={}".format(
            K8S_SECRET_NAME, HOST_CERT_PATH
        )
    )
    run_kubectl_command(kube_cmd, capture_output=not debug)

    # Patch the controller deployment to mount the certificate to avoid
    # having to specify it in every service definition
    configure_self_signed_certs(HOST_CERT_DIR, K8S_SECRET_NAME, debug=debug)

    print("Success!")


@task
def uninstall(ctx):
    """
    Uninstall a Knative Serving installation

    To un-install the components, we follow the installation instructions in
    reverse order
    """
    # Delete DNS services
    kube_cmd = "delete -f {}".format(
        join(KNATIVE_SERVING_BASE_URL, "serving-default-domain.yaml")
    )
    run_kubectl_command(kube_cmd)

    # Delete networking layer
    kube_cmd = "delete -f {}".format(join(KOURIER_BASE_URL, "kourier.yaml"))
    run_kubectl_command(kube_cmd)

    # Delete all components in the knative-serving namespace
    kube_cmd = "delete all --all -n {}".format(KNATIVE_SERVING_NAMESPACE)
    run_kubectl_command(kube_cmd)
    run_kubectl_command("delete namespace {}".format(KNATIVE_SERVING_NAMESPACE))

    # Delete CRDs
    kube_cmd = "delete -f {}".format(
        join(KNATIVE_SERVING_BASE_URL, "serving-crds.yaml")
    )
    run_kubectl_command(kube_cmd)


@task
def replace_sidecar(
    ctx, reset_default=False, image_repo=LOCAL_REGISTRY_URL, skip_push=False
):
    """
    Replace Knative's side-car image with an image we control

    In order to enable image signature and encryption, we need to have push
    access to the image repository. As a consequence, we can not use Knative's
    default side-car image. Instead, we re-tag the corresponding image, and
    update Knative's deployment ConfigMap to use our image.
    """
    do_replace_sidecar(reset_default, image_repo, skip_push=skip_push)


@task
def configure_self_signed_certs(ctx, path_to_certs_dir):
    """
    Configure Knative to like our self-signed certificates
    """
    do_configure_self_signed_certs(path_to_certs_dir)
