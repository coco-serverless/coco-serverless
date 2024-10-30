from invoke import task
from tasks.knative import install as knative_install
from tasks.kubeadm import create as k8s_create, destroy as k8s_destroy
from tasks.operator import (
    install as operator_install,
    install_cc_runtime as operator_install_cc_runtime,
)


@task(default=True)
def deploy(ctx, debug=False):
    """
    Deploy an SC2-enabled cluster
    """
    # First, create a single-node k8s cluster
    k8s_create(ctx, debug=debug)

    # Second, install the CoC operator as well as the CC-runtimes
    operator_install(ctx, debug=debug)
    operator_install_cc_runtime(ctx, debug=debug)

    # TODO: install sc2 runtime

    # Third, install Knative
    knative_install(debug=debug)

    # Fourth, start a local docker registry

    # TODO: apply SC2 patches to things


@task
def destroy(ctx):
    k8s_destroy(ctx)
