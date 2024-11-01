from invoke import task
from subprocess import run
from tasks.k8s import install as k8s_tooling_install
from tasks.k9s import install as k9s_install
from tasks.knative import install as knative_install
from tasks.kubeadm import create as k8s_create, destroy as k8s_destroy
from tasks.operator import (
    install as operator_install,
    install_cc_runtime as operator_install_cc_runtime,
)
from tasks.registry import (
    start as start_local_registry,
    stop as stop_local_registry,
)
from tasks.util.env import COCO_ROOT, KATA_ROOT


@task(default=True)
def deploy(ctx, debug=False, clean=False):
    """
    Deploy an SC2-enabled bare-metal Kubernetes cluster
    """
    if clean:
        for nuked_dir in [COCO_ROOT, KATA_ROOT]:
            if debug:
                print(f"WARNING: nuking {nuked_dir}")
            run(f"sudo rm -rf {nuked_dir}", shell=True, check=True)

    # Disable swap
    run("sudo swapoff -a", shell=True, check=True)

    # Install k8s tooling (including k9s)
    k8s_tooling_install(ctx, debug=debug, clean=clean)
    k9s_install(ctx, debug=debug)

    # Create a single-node k8s cluster
    k8s_create(ctx, debug=debug)

    # Install the CoCo operator as well as the CC-runtimes
    operator_install(ctx, debug=debug)
    operator_install_cc_runtime(ctx, debug=debug)

    # Start a local docker registry (must happen before the local registry,
    # as we rely on it to host our sidecar image)
    start_local_registry(ctx, debug=debug, clean=clean)

    # TODO: install sc2 runtime

    # Install Knative
    knative_install(ctx, debug=debug)

    # TODO: apply SC2 patches to things


@task
def destroy(ctx, debug=False):
    """
    Destroy an SC2 cluster
    """
    # Destroy k8s cluster
    k8s_destroy(ctx, debug=debug)

    # Stop docker registry
    stop_local_registry(ctx, debug=debug)
