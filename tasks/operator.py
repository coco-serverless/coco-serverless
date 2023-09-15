from invoke import task
from os.path import join
from subprocess import run
from tasks.util.env import PROJ_ROOT
from tasks.util.uk8s import run_uk8s_kubectl_cmd, wait_for_pod, wait_for_pods_in_ns

OPERATOR_NAMESPACE = "confidential-containers-system"
OPERATOR_SOURCE_CHECKOUT = join(PROJ_ROOT, "..", "operator")


@task
def build(ctx):
    pass


@task
def install(ctx):
    """
    Install the cc-operator on the cluster
    """
    config_dir = join(OPERATOR_SOURCE_CHECKOUT, "config", "default")
    run_uk8s_kubectl_cmd("apply -k {}".format(config_dir))
    wait_for_pod(OPERATOR_NAMESPACE, "cc-operator-controller-manager")


@task
def install_cc_runtime(ctx, runtime_class="kata-qemu"):
    cc_runtime_dir = join(OPERATOR_SOURCE_CHECKOUT, "config", "samples", "ccruntime", "default")
    run_uk8s_kubectl_cmd("create -k {}".format(cc_runtime_dir))

    for pod in ["cc-operator-daemon-install", "cc-operator-pre-install-daemon"]:
        wait_for_pod(OPERATOR_NAMESPACE, pod)


@task
def uninstall_cc_runtime(ctx):
    cc_runtime_dir = join(OPERATOR_SOURCE_CHECKOUT, "config", "samples", "ccruntime", "default")
    run_uk8s_kubectl_cmd("delete -k {}".format(cc_runtime_dir))
