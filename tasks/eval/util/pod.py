from datetime import datetime
from json import loads as json_loads
from re import search as re_search
from tasks.util.containerd import get_event_from_containerd_logs
from tasks.util.kubeadm import run_kubectl_command
from time import sleep


def is_pod_ready(pod_name):
    """
    Return true if a pod has been succesfully initialised (i.e. is in `Ready`
    state)
    """
    kube_cmd = "get pod {} -o jsonpath='{{..status.conditions}}'".format(pod_name)
    conditions = run_kubectl_command(kube_cmd, capture_output=True)
    cond_json = json_loads(conditions)
    return all([cond["status"] == "True" for cond in cond_json])


def get_pod_ready_ts(pod_name):
    """
    Get the timestamp at which the pod turned to a 'Ready' state as reported
    in the Kubernetes event log
    """
    kube_cmd = "get pod {} -o jsonpath='{{..status.conditions}}'".format(pod_name)
    conditions = run_kubectl_command(kube_cmd, capture_output=True)
    cond_json = json_loads(conditions)
    for cond in cond_json:
        if cond["type"] == "Ready":
            return datetime.fromisoformat(cond["lastTransitionTime"][:-1]).timestamp()


def wait_for_pod_ready_and_get_ts(pod_name):
    """
    Utility method to wait for a pod to be in 'Ready' state and get the
    timestamp at which it became ready, as reported in the Kuberenetes event
    logs
    """
    pod_ready = is_pod_ready(pod_name)
    while not pod_ready:
        sleep(1)
        pod_ready = is_pod_ready(pod_name)

    return get_pod_ready_ts(pod_name)


def get_sandbox_id_from_pod_name(pod_name, timeout_mins=1):
    """
    Get the sandbox ID from a pod name
    """
    # The sandbox ID is in the ending pair of the RunPodSandbox event
    event_json = get_event_from_containerd_logs("RunPodSandbox", pod_name, 1, timeout_mins=timeout_mins)[0]
    sbox_id = re_search(
        r'returns sandbox id \\"([a-zA-Z0-9]*)\\"', event_json["MESSAGE"]
    ).groups(1)[0]
    return sbox_id
