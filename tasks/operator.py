from invoke import task
from os.path import join
from tasks.util.env import CONTAINERD_CONFIG_FILE, KATA_CONFIG_DIR, print_dotted_line
from tasks.util.kubeadm import (
    run_kubectl_command,
    wait_for_pods_in_ns,
)
from tasks.util.toml import read_value_from_toml
from tasks.util.versions import COCO_VERSION
from time import sleep

OPERATOR_GITHUB_URL = "github.com/confidential-containers/operator"
OPERATOR_NAMESPACE = "confidential-containers-system"


@task
def install(ctx, debug=False):
    """
    Install the cc-operator on the cluster
    """
    print_dotted_line(f"Installing CoCo operator (v{COCO_VERSION})")

    # Install the operator from the confidential-containers/operator
    # release tag
    operator_url = join(
        OPERATOR_GITHUB_URL, "config", "release?ref=v{}".format(COCO_VERSION)
    )
    run_kubectl_command("apply -k {}".format(operator_url), capture_output=not debug)
    wait_for_pods_in_ns(
        OPERATOR_NAMESPACE,
        expected_num_of_pods=1,
        label="control-plane=controller-manager",
        debug=debug,
    )

    print("Success!")


@task
def install_cc_runtime(ctx, debug=False):
    """
    Install the CoCo runtime through the operator
    """
    print_dotted_line("Install CoCo runtimes")

    cc_runtime_url = join(
        OPERATOR_GITHUB_URL,
        "config",
        "samples",
        "ccruntime",
        "default?ref=v{}".format(COCO_VERSION),
    )
    run_kubectl_command("create -k {}".format(cc_runtime_url), capture_output=not debug)

    for pod_label in [
        "name=cc-operator-pre-install-daemon",
        "name=cc-operator-daemon-install",
    ]:
        wait_for_pods_in_ns(
            OPERATOR_NAMESPACE, expected_num_of_pods=1, label=pod_label, debug=debug
        )

    # We check that the registered runtime classes are the same ones
    # we expect. We deliberately hardcode the following list
    expected_runtime_classes = [
        "kata",
        "kata-clh",
        "kata-qemu",
        "kata-qemu-coco-dev",
        "kata-qemu-tdx",
        "kata-qemu-sev",
        "kata-qemu-snp",
    ]
    run_class_cmd = "get runtimeclass -o jsonpath='{.items..handler}'"
    runtime_classes = run_kubectl_command(run_class_cmd, capture_output=True).split(" ")
    while len(expected_runtime_classes) != len(runtime_classes):
        if debug:
            print(
                "Not all expected runtime classes are registered ({} != {})".format(
                    len(expected_runtime_classes), len(runtime_classes)
                )
            )

        sleep(5)
        runtime_classes = run_kubectl_command(run_class_cmd, capture_output=True).split(
            " "
        )

    # We must also wait until we are done configuring the nydus snapshotter
    sleep(10)
    for runtime in expected_runtime_classes[1:]:
        runtime_no_kata = runtime[5:]
        expected_config_path = (
            f"{KATA_CONFIG_DIR}//configuration-{runtime_no_kata}.toml"
        )
        toml_path = (
            f'plugins."io.containerd.grpc.v1.cri".containerd.runtimes'
            f".{runtime}.options.ConfigPath"
        )

        while expected_config_path != read_value_from_toml(
            CONTAINERD_CONFIG_FILE, toml_path, tolerate_missing=True
        ):
            if debug:
                print(
                    (
                        f"Waiting for operator to populate containerd "
                        f"entry for runtime: {runtime}..."
                    )
                )

            sleep(2)

    print("Success!")


@task
def uninstall(ctx):
    """
    Uninstall the operator
    """
    operator_url = join(
        OPERATOR_GITHUB_URL, "config", "release?ref=v{}".format(COCO_VERSION)
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
        "default?ref=v{}".format(COCO_VERSION),
    )
    run_kubectl_command("delete -k {}".format(cc_runtime_url))
