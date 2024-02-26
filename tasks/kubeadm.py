from invoke import task
from os import getegid, geteuid, makedirs
from os.path import exists
from shutil import rmtree
from subprocess import run
from tasks.util.env import (
    CRI_RUNTIME_SOCKET,
    FLANNEL_VERSION,
    K8S_ADMIN_FILE,
    K8S_CONFIG_DIR,
    KUBEADM_KUBECONFIG_FILE,
)
from tasks.util.kubeadm import (
    get_node_name,
    run_kubectl_command,
    wait_for_pods_in_ns,
)
from time import sleep


@task
def create(ctx):
    """
    Create a single-node k8s cluster
    """
    # Start the cluster
    kubeadm_cmd = "sudo kubeadm init --config {}".format(K8S_ADMIN_FILE)
    # kubeadm_cmd = "sudo kubeadm init"
    run(kubeadm_cmd, shell=True, check=True)

    if not exists(K8S_CONFIG_DIR):
        makedirs(K8S_CONFIG_DIR)

    # Copy the config file locally and change permissions
    cp_cmd = "sudo cp /etc/kubernetes/admin.conf {}".format(KUBEADM_KUBECONFIG_FILE)
    run(cp_cmd, shell=True, check=True)
    chown_cmd = "sudo chown {}:{} {}".format(
        geteuid(), getegid(), KUBEADM_KUBECONFIG_FILE
    )
    run(chown_cmd, shell=True, check=True)

    # Wait for the node to be in ready state
    def get_node_state():
        # We could use a jsonpath format here, but couldn't quite work it out
        out = run_kubectl_command("get nodes --no-headers", capture_output=True).split(
            " "
        )
        out = [_ for _ in out if len(_) > 0]
        return out[1]

    expected_node_state = "Ready"
    actual_node_state = get_node_state()
    while expected_node_state != actual_node_state:
        print("Waiting for node to be ready...")
        sleep(3)
        actual_node_state = get_node_state()

    # Untaint the node so that pods can be scheduled on it
    node_name = get_node_name()
    for role in ["control-plane"]:
        node_label = "node-role.kubernetes.io/{}:NoSchedule-".format(role)
        taint_cmd = "taint nodes {} {}".format(node_name, node_label)
        run_kubectl_command(taint_cmd)

    # In addition, make sure the node has the worker label (required by CoCo)
    node_label = "node.kubernetes.io/worker="
    run_kubectl_command("label node {} {}".format(node_name, node_label))

    # Configure flannel
    flannel_url = "https://github.com/flannel-io/flannel/releases/download"
    flannel_url += "/v{}/kube-flannel.yml".format(FLANNEL_VERSION)
    run_kubectl_command("apply -f {}".format(flannel_url))
    wait_for_pods_in_ns("kube-flannel", 1)


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
