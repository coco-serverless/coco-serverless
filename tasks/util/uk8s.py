from subprocess import run
from tasks.util.env import UK8S_KUBECONFIG_FILE
from time import sleep

UK8S_LOCAL_REGISTRY_PREFIX = "localhost:32000"


def get_uk8s_kubectl_cmd():
    return "kubectl --kubeconfig={}".format(UK8S_KUBECONFIG_FILE)


def run_uk8s_kubectl_cmd(cmd, capture_output=False):
    if capture_output:
        return (
            run(
                "{} {}".format(get_uk8s_kubectl_cmd(), cmd),
                shell=True,
                capture_output=True,
            )
            .stdout.decode("utf-8")
            .strip()
        )

    run("{} {}".format(get_uk8s_kubectl_cmd(), cmd), shell=True, check=True)


def wait_for_pods_in_ns(ns=None):
    while True:
        print("Waiting for pods to be ready...")
        cmd = [
            "-n {}".format(ns) if ns else "",
            "get pods",
            "-o jsonpath='{..status.conditions[?(@.type==\"Ready\")].status}'",
        ]

        output = run_uk8s_kubectl_cmd(
            " ".join(cmd),
            capture_output=True,
        )

        statuses = [o.strip() for o in output.split(" ") if o.strip()]
        if all([s == "True" for s in statuses]):
            print("All pods ready, continuing...")
            break

        print("Pods not ready, waiting ({})".format(output))
        sleep(5)


def wait_for_pod(ns, pod_name):
    while True:
        print("Waiting for pod {} (ns: {})...".format(pod_name, ns))
        cmd = [
            "-n {}".format(ns) if ns else "",
            "get pods",
            "-o jsonpath='{..status.conditions[?(@.type==\"Ready\")].status}'",
        ]

        output = run_uk8s_kubectl_cmd(
            " ".join(cmd),
            capture_output=True,
        )

        statuses = [o.strip() for o in output.split(" ") if o.strip()]
        if all([s == "True" for s in statuses]):
            print("All pods ready, continuing...")
            break

        print("Pods not ready, waiting ({})".format(output))
        sleep(5)
