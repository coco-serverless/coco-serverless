from invoke import task
from tasks.eval.util.env import EVAL_TEMPLATED_DIR
from tasks.util.kubeadm import run_kubectl_command


@task
def pods(ctx):
    """
    Prune all running pods
    """
    kube_cmd = "delete -f {}".format(EVAL_TEMPLATED_DIR)
    run_kubectl_command(kube_cmd, capture_output=True)
