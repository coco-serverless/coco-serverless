from invoke import task
from os import getegid, geteuid, makedirs
from os.path import exists
from shutil import rmtree
from subprocess import run
from tasks.util.env import (
    CRI_RUNTIME_SOCKET,
    CALICO_VERSION,
    K8S_ADMIN_FILE,
    K8S_CONFIG_DIR,
    K8S_VERSION,
    KUBEADM_KUBECONFIG_FILE,
)
from tasks.util.kubeadm import (
    get_node_name,
    run_kubectl_command,
    wait_for_pods_in_ns,
)
from time import sleep


@task
def create(ctx, debug=False):
    """
    Create a single-node k8s cluster
    """
    print(f"Creating K8s (v{K8S_VERSION}) cluster using kubeadm...")

    # Start the cluster
    kubeadm_cmd = "sudo kubeadm init --config {}".format(K8S_ADMIN_FILE)
    if debug:
        run(kubeadm_cmd, shell=True, check=True)
    else:
        out = run(kubeadm_cmd, shell=True, capture_output=True)
        assert out.returncode == 0, "Error running cmd: {} (error: {})".format(
            kubeadm_cmd, out.stderr
        )

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
        run_kubectl_command(taint_cmd, capture_output=not debug)

    # In addition, make sure the node has the worker label (required by CoCo)
    node_label = "node.kubernetes.io/worker="
    run_kubectl_command(
        "label node {} {}".format(node_name, node_label), capture_output=not debug
    )

    # Configure Calico
    calico_url = "https://raw.githubusercontent.com/projectcalico/calico"
    calico_url += f"/v{CALICO_VERSION}/manifests"
    run_kubectl_command(
        f"create -f {calico_url}/tigera-operator.yaml", capture_output=not debug
    )
    run_kubectl_command(
        f"create -f {calico_url}/custom-resources.yaml", capture_output=not debug
    )
    wait_for_pods_in_ns(
        "calico-system",
        label="app.kubernetes.io/name=csi-node-driver",
        debug=debug,
        expected_num_of_pods=1,
    )
    wait_for_pods_in_ns(
        "calico-system",
        label="app.kubernetes.io/name=calico-typha",
        debug=debug,
        expected_num_of_pods=1,
    )
    wait_for_pods_in_ns(
        "calico-system",
        label="app.kubernetes.io/name=calico-node",
        debug=debug,
        expected_num_of_pods=1,
    )
    wait_for_pods_in_ns(
        "calico-system",
        label="app.kubernetes.io/name=calico-kube-controllers",
        expected_num_of_pods=1,
        debug=debug,
    )
    wait_for_pods_in_ns(
        "calico-apiserver",
        label="app.kubernetes.io/name=calico-apiserver",
        debug=debug,
        expected_num_of_pods=2,
    )

    print("Cluster created!")


@task
def destroy(ctx, debug=False):
    """
    Destroy a k8s cluster initialised with `inv kubeadm.create`
    """

    def remove_link(dev_name):
        """
        Remove link entries from ip tables

        We want to be able to run k8s.destroy multiple times, so we need
        to spport the link not existing (and the command failing).
        """
        ip_cmd = "sudo ip link set dev {} down".format(dev_name)
        # The command may fail?
        run(ip_cmd, shell=True, capture_output=True)
        ip_cmd = "sudo ip link del {}".format(dev_name)
        # The command may fail?
        run(ip_cmd, shell=True, capture_output=True)

    def remove_cni():
        rmtree("/etc/cni/net.d", ignore_errors=True)
        remove_link("cni0")

    kubeadm_cmd = "sudo kubeadm reset -f --cri-socket='{}'".format(CRI_RUNTIME_SOCKET)
    if debug:
        run(kubeadm_cmd, shell=True, check=True)
    else:
        out = run(kubeadm_cmd, shell=True, capture_output=True)
        assert out.returncode == 0, "Error running cmd: {} (error: {})".format(
            kubeadm_cmd, out.stderr
        )

    # Remove networking stuff
    remove_cni()
