from invoke import task
from os.path import join
from subprocess import CalledProcessError
from tasks.util.kubeadm import run_kubectl_command, wait_for_pods_in_ns

KNATIVE_VERSION = "1.11.0"

# Namespaces
KNATIVE_NAMESPACE = "knative-serving"
KOURIER_NAMESPACE = "kourier-system"

# URLs
KNATIVE_BASE_URL = "https://github.com/knative/serving/releases/download"
KNATIVE_BASE_URL += "/knative-v{}".format(KNATIVE_VERSION)
KOURIER_BASE_URL = "https://github.com/knative/net-kourier/releases/download"
KOURIER_BASE_URL += "/knative-v{}".format(KNATIVE_VERSION)


def install_metalb():


@task
def install(ctx):
    """
    Install Knative Serving on a running K8s cluster

    Steps here follow closely the Knative docs:
    https://knative.dev/docs/install/yaml-install/serving/install-serving-with-yaml
    """
    # Knative requires a functional LoadBalancer, so we use MetaLB
    install_metalb()

    # Create the knative CRDs
    kube_cmd = "apply -f {}".format(join(KNATIVE_BASE_URL, "serving-crds.yaml"))
    run_kubectl_command(kube_cmd)

    # Install the core serving components
    kube_cmd = "apply -f {}".format(join(KNATIVE_BASE_URL, "serving-core.yaml"))
    run_kubectl_command(kube_cmd)

    # Wait for the core components to be ready
    wait_for_pods_in_ns(KNATIVE_NAMESPACE, 4)

    # Install a networking layer (we pick the default, Kourier)
    kube_cmd = "apply -f {}".format(join(KOURIER_BASE_URL, "kourier.yaml"))
    run_kubectl_command(kube_cmd)

    # Configure Knative Serving to use Kourier
    kube_cmd = [
        "patch configmap/config-network",
        "--namespace {}".format(KNATIVE_NAMESPACE),
        "--type merge",
        "--patch '{\"data\":{\"ingress-class\":\"kourier.ingress.networking.knative.dev\"}}'",
    ]
    kube_cmd = " ".join(kube_cmd)
    run_kubectl_command(kube_cmd)

    # Wait for all components to be ready
    wait_for_pods_in_ns(KNATIVE_NAMESPACE, 5)
    wait_for_pods_in_ns(KOURIER_NAMESPACE, 1)

    # Deploy a DNS
    kube_cmd = "apply -f {}".format(join(KNATIVE_BASE_URL, "serving-default-domain.yaml"))
    run_kubectl_command(kube_cmd)

    # TODO: kourier deploys a load-balancer, but this probably doesn't work
    # for our single-node setting?


@task
def uninstall(ctx):
    """
    Uninstall a Knative Serving installation

    To un-install the components, we follow the installation instructions in
    reverse order
    """
    # Delete DNS services
    kube_cmd = "delete -f {}".format(join(KNATIVE_BASE_URL, "serving-default-domain.yaml"))
    run_kubectl_command(kube_cmd)

    # Delete networking layer
    kube_cmd = "delete -f {}".format(join(KOURIER_BASE_URL, "kourier.yaml"))
    run_kubectl_command(kube_cmd)

    # Delete serving components
    kube_cmd = "delete -f {}".format(join(KNATIVE_BASE_URL, "serving-core.yaml"))
    try:
        # This deletion is a bit flaky, so survive a death
        run_kubectl_command(kube_cmd)
    except CalledProcessError:
        print("WARNING: failed at removing some of the core serving components")

    # Delete CRDs
    kube_cmd = "delete -f {}".format(join(KNATIVE_BASE_URL, "serving-crds.yaml"))
    run_kubectl_command(kube_cmd)

    # Finally wait until the namespace is not there anymore
