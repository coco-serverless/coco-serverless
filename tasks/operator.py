from invoke import task
from os.path import join
from tasks.util.env import COCO_RELEASE_VERSION
from tasks.util.kubeadm import (
    run_kubectl_command,
    wait_for_pods_in_ns,
)
from time import sleep

OPERATOR_GITHUB_URL = "github.com/confidential-containers/operator"
OPERATOR_NAMESPACE = "confidential-containers-system"


@task
def install(ctx):
    """
    Install the cc-operator on the cluster
    """
    # Install the operator from the confidential-containers/operator
    # release tag
    operator_url = join(
        OPERATOR_GITHUB_URL, "config", "release?ref=v{}".format(COCO_RELEASE_VERSION)
    )
    run_kubectl_command("apply -k {}".format(operator_url))
    wait_for_pods_in_ns(
        OPERATOR_NAMESPACE,
        expected_num_of_pods=1,
        label="control-plane=controller-manager",
    )


@task
def install_cc_runtime(ctx, runtime_class="kata-qemu"):
    """
    Install the CoCo runtime through the operator
    """
    cc_runtime_url = join(
        OPERATOR_GITHUB_URL,
        "config",
        "samples",
        "ccruntime",
        "default?ref=v{}".format(COCO_RELEASE_VERSION),
    )
    run_kubectl_command("create -k {}".format(cc_runtime_url))

    for pod_label in [
        "name=cc-operator-pre-install-daemon",
        "name=cc-operator-daemon-install",
    ]:
        wait_for_pods_in_ns(OPERATOR_NAMESPACE, expected_num_of_pods=1, label=pod_label)

    # We check that the registered runtime classes are the same ones
    # we expect. We deliberately hardcode the following list
    expected_runtime_classes = [
        "kata",
        "kata-clh",
        "kata-clh-tdx",
        "kata-quemu",
        "kata-qemu-tdx",
        "kata-qemu-sev",
        "kata-qemu-snp",
    ]
    run_class_cmd = "get runtimeclass -o jsonpath='{.items..handler}'"
    runtime_classes = run_kubectl_command(run_class_cmd, capture_output=True).split(" ")
    while len(expected_runtime_classes) != len(runtime_classes):
        print(
            "Not all expected runtime classes are registered ({} != {})".format(
                len(expected_runtime_classes), len(runtime_classes)
            )
        )
        sleep(5)
        runtime_classes = run_kubectl_command(run_class_cmd, capture_output=True).split(
            " "
        )


@task
def uninstall(ctx):
    """
    Uninstall the operator
    """
    operator_url = join(
        OPERATOR_GITHUB_URL, "config", "release?ref=v{}".format(COCO_RELEASE_VERSION)
    )
    run_kubectl_command("delete -k {}".format(operator_url))


@task
def uninstall_cc_runtime(ctx):
    """
    Un-install the CoCo runtimes from the k8s cluster
    """
    cc_runtime_url = join(
        OPERATOR_GITHUB_URL,
        "config",
        "samples",
        "ccruntime",
        "default?ref=v{}".format(COCO_RELEASE_VERSION),
    )
    run_kubectl_command("delete -k {}".format(cc_runtime_url))
