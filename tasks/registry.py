from invoke import task
from tasks.util.containerd import restart_containerd
from tasks.util.registry import (
    start as start_registry,
    stop as stop_registry,
)


@task
def start(ctx, debug=False, clean=False):
    """
    Configure a local container registry reachable from CoCo guests in K8s
    """
    start_registry(debug=debug, clean=clean)
    restart_containerd()


@task
def stop(ctx, debug=False):
    """
    Remove the container registry in the k8s cluster

    We follow the steps in start in reverse order, paying particular interest
    to the steps that are not idempotent (e.g. creating a k8s secret).
    """
    stop_registry(debug=debug)
