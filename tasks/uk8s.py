from invoke import task
from tasks.util.env import (
    K8S_VERSION,
    UK8S_KUBECONFIG_FILE,
)
from tasks.util.uk8s import get_uk8s_kubectl_cmd
from subprocess import run


@task
def install(ctx):
    """
    Install uk8s (requires sudo)
    """
    k8s_major = K8S_VERSION[0:4]
    install_cmd = "sudo snap install microk8s --classic --channel={}/stable".format(
        k8s_major
    )
    print(install_cmd)
    run(install_cmd, shell=True, check=True)

    addons = ["dns", "hostpath-storage", "rbac", "registry"]
    for addon in addons:
        addon_cmd = "sudo microk8s enable {}".format(addon)
        print(addon_cmd)
        run(addon_cmd, shell=True, check=True)

    # Set credentials
    credentials(ctx)


@task
def uninstall(ctx):
    """
    Uninstall uk8s (requires sudo)
    """
    rm_cmd = "sudo snap remove --purge microk8s"
    print(rm_cmd)
    run(rm_cmd, shell=True, check=True)

    # This patches the issue discussed here:
    # https://github.com/canonical/microk8s/issues/3092
    clean_iptables(ctx)


@task
def clean_iptables(ctx):
    """
    Clean leftover iptables rules
    """
    iptables_cmd = "sudo iptables-legacy-save | grep k8s"
    result = (
        run(iptables_cmd, shell=True, capture_output=True)
        .stdout.decode("utf-8")
        .split("\n")[:-1]
    )

    for rule in result:
        iptables_rm_cmd = "sudo iptables-legacy -t nat -D {}".format(rule[2:])
        print(iptables_rm_cmd)
        run(iptables_rm_cmd, shell=True, check=True)

    # Check that there are no leftover rules
    result = (
        run(iptables_cmd, shell=True, capture_output=True)
        .stdout.decode("utf-8")
        .split("\n")[:-1]
    )
    if result:
        print("Error cleaning uk8s iptables, there are still rules: {}".format(result))
        raise RuntimeError("Error cleaning uk8s iptables")


@task
def reset(ctx):
    """
    Reset the uk8s cluster from scratch
    """
    # Uninstall the existing
    uninstall(ctx)

    # Install
    install(ctx)

    # Update credentials
    credentials(ctx)


@task
def credentials(ctx):
    """
    Set credentials for the uk8s cluster
    """
    # Load the local config
    config_cmd = "microk8s config > {}".format(UK8S_KUBECONFIG_FILE)
    print(config_cmd)
    run(config_cmd, shell=True, check=True)

    # Check we can access the cluster
    cmd = "{} get nodes".format(get_uk8s_kubectl_cmd())
    print(cmd)
    run(cmd, shell=True, check=True)
