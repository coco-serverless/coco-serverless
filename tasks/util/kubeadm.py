from subprocess import run
from tasks.util.env import KUBEADM_KUBECONFIG_FILE
from time import sleep


def run_kubectl_command(cmd, capture_output=False):
    k8s_cmd = "kubectl --kubeconfig={} {}".format(KUBEADM_KUBECONFIG_FILE, cmd)

    if capture_output:
        return (
            run(k8s_cmd, shell=True, capture_output=True).stdout.decode("utf-8").strip()
        )

    run(k8s_cmd, shell=True, check=True)


def wait_for_pods_in_ns(ns=None, expected_num_of_pods=0, label=None):
    """
    Wait for pods in a namespace to be ready
    """
    while True:
        print("Waiting for pods to be ready...")
        cmd = [
            "-n {}".format(ns) if ns else "",
            "get pods",
            "-l {}".format(label) if label else "",
            "-o jsonpath='{..status.conditions[?(@.type==\"Ready\")].status}'",
        ]

        output = run_kubectl_command(
            " ".join(cmd),
            capture_output=True,
        )

        statuses = [o.strip() for o in output.split(" ") if o.strip()]
        if expected_num_of_pods > 0 and len(statuses) != expected_num_of_pods:
            print(
                "Expecting {} pods, have {}".format(expected_num_of_pods, len(statuses))
            )
        elif all([s == "True" for s in statuses]):
            print("All pods ready, continuing...")
            break

        print("Pods not ready, waiting ({})".format(output))
        sleep(5)


def get_node_name():
    cmd = "get nodes -o jsonpath="
    cmd += "'{.items..status..addresses[?(@.type==\"Hostname\")].address}'"
    return run_kubectl_command(cmd, capture_output=True)
