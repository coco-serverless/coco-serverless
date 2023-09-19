from invoke import task
from os.path import join
from os import getegid, geteuid
from shutil import rmtree
from subprocess import run
from tasks.util.env import (
    BIN_DIR,
    GLOBAL_BIN_DIR,
    CRI_RUNTIME_SOCKET,
    FLANNEL_VERSION,
    K8S_ADMIN_FILE,
    KUBEADM_KUBECONFIG_FILE,
)
from time import sleep


def run_kubectl_command(cmd, capture_output=False):
    # As long as we don't copy the config file elsewhere we need to use
    # sudo to read the admin config file
    k8s_cmd = "kubectl --kubeconfig={} {}".format(KUBEADM_KUBECONFIG_FILE, cmd)

    if capture_output:
        return run(k8s_cmd, shell=True, capture_output=True).stdout.decode("utf-8").strip()

    run(k8s_cmd, shell=True, check=True)


def wait_for_pods(ns=None, expected_num_of_pods=0):
    """
    Wait for pods in a namespace to be ready
    """
    while True:
        print("Waiting for pods to be ready...")
        cmd = [
            "-n {}".format(ns) if ns else "",
            "get pods",
            "-o jsonpath='{..status.conditions[?(@.type==\"Ready\")].status}'",
        ]

        output = run_kubectl_command(
            " ".join(cmd),
            capture_output=True,
        )

        statuses = [o.strip() for o in output.split(" ") if o.strip()]
        if expected_num_of_pods > 0 and len(statuses) != expected_num_of_pods:
            print("Expecting {} pods, have {}".format(expected_num_of_pods, len(statuses)))
        elif all([s == "True" for s in statuses]):
            print("All pods ready, continuing...")
            break

        print("Pods not ready, waiting ({})".format(output))
        sleep(5)


@task
def create(ctx):
    """
    Create a single-node k8s cluster
    """
    # Start the cluster
    kubeadm_cmd = "sudo kubeadm init --config {}".format(K8S_ADMIN_FILE)
    # kubeadm_cmd = "sudo kubeadm init"
    run(kubeadm_cmd, shell=True, check=True)

    # Copy the config file locally and change permissions
    cp_cmd = "sudo cp /etc/kubernetes/admin.conf {}".format(KUBEADM_KUBECONFIG_FILE)
    run(cp_cmd, shell=True, check=True)
    chown_cmd = "sudo chown {}:{} {}".format(geteuid(), getegid(), KUBEADM_KUBECONFIG_FILE)
    run(chown_cmd, shell=True, check=True)

    # Wait for the node to be in ready state
    def get_node_state():
        # We could use a jsonpath format here, but couldn't quite work it out
        out = run_kubectl_command("get nodes --no-headers", capture_output=True).split(" ")
        out = [_ for _ in out if len(_) > 0]
        return out[1]

    expected_node_state = "Ready"
    actual_node_state = get_node_state()
    while expected_node_state != actual_node_state:
        print("Waiting for node to be ready...")
        sleep(3)
        actual_node_state = get_node_state()

    # Configure flannel
    flannel_url = "https://github.com/flannel-io/flannel/releases/download/v{}/kube-flannel.yml".format(FLANNEL_VERSION)
    run_kubectl_command("apply -f {}".format(flannel_url))
    wait_for_pods("kube-flannel", 1)


@task
def destroy(ctx):
    """
    Destroy a k8s cluster initialised with `inv k8s.create`
    """

    def remove_link(dev_name):
        """
        Remove link entries from ip tables

        We want to be able to run k8s.destroy multiple times, so we need
        to spport the link not existing (and the command failing).
        """
        ip_cmd = "sudo ip link set dev {} down".format(dev_name)
        # The command may fail?
        run(ip_cmd, shell=True)
        ip_cmd = "sudo ip link del {}".format(dev_name)
        # The command may fail?
        run(ip_cmd, shell=True)

    def remove_cni():
        rmtree("/etc/cni/net.d", ignore_errors=True)
        remove_link("cni0")

    def remove_flannel():
        remove_link("flannel.1")

    kubeadm_cmd = "sudo kubeadm reset -f --cri-socket='{}'".format(CRI_RUNTIME_SOCKET)
    run(kubeadm_cmd, shell=True, check=True)

    # Remove networking stuff
    remove_cni()
    remove_flannel()
