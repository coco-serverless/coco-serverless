from invoke import task
from os.path import join, exists
from os import makedirs
from shutil import copy, rmtree
from subprocess import run
from tasks.util.env import (
    BIN_DIR,
    GLOBAL_BIN_DIR,
    CRI_RUNTIME_SOCKET,
    FLANNEL_INSTALL_DIR,
    K8S_VERSION,
    K8S_ADMIN_FILE,
    K8S_CONFIG_FILE,
    K9S_VERSION,
)
from time import sleep


def _download_binary(url, binary_name):
    makedirs(BIN_DIR, exist_ok=True)
    cmd = "curl -LO {}".format(url)
    run(cmd, shell=True, check=True, cwd=BIN_DIR)
    run("chmod +x {}".format(binary_name), shell=True, check=True, cwd=BIN_DIR)

    return join(BIN_DIR, binary_name)


def _symlink_global_bin(binary_path, name):
    global_path = join(GLOBAL_BIN_DIR, name)
    if exists(global_path):
        print("Removing existing binary at {}".format(global_path))
        run(
            "sudo rm -f {}".format(global_path),
            shell=True,
            check=True,
        )

    print("Symlinking {} -> {}".format(global_path, binary_path))
    run(
        "sudo ln -s {} {}".format(binary_path, name),
        shell=True,
        check=True,
        cwd=GLOBAL_BIN_DIR,
    )


@task
def install_kubectl(ctx, system=False):
    """
    Install the k8s CLI (kubectl)
    """
    url = "https://dl.k8s.io/release/v{}/bin/linux/amd64/kubectl".format(
        K8S_VERSION
    )

    binary_path = _download_binary(url, "kubectl")

    # Symlink for kubectl globally
    if system:
        _symlink_global_bin(binary_path, "kubectl")


@task
def install_k9s(ctx, system=False):
    """
    Install the K9s CLI
    """
    tar_name = "k9s_Linux_amd64.tar.gz"
    url = "https://github.com/derailed/k9s/releases/download/v{}/{}".format(
        K9S_VERSION, tar_name
    )

    # Download the TAR
    workdir = "/tmp/k9s"
    makedirs(workdir, exist_ok=True)

    cmd = "curl -LO {}".format(url)
    run(cmd, shell=True, check=True, cwd=workdir)

    # Untar
    run("tar -xf {}".format(tar_name), shell=True, check=True, cwd=workdir)

    # Copy k9s into place
    binary_path = join(BIN_DIR, "k9s")
    copy(join(workdir, "k9s"), binary_path)

    # Remove tar
    rmtree(workdir)

    # Symlink for k9s command globally
    if system:
        _symlink_global_bin(binary_path, "k9s")


def run_kubectl_command(cmd, capture_output=False):
    # As long as we don't copy the config file elsewhere we need to use
    # sudo to read the admin config file
    k8s_cmd = "sudo kubectl --kubeconfig={} {}".format(K8S_CONFIG_FILE, cmd)

    if capture_output:
        return run(cmd, shell=True, capture_output=True).stdout.decode("utf-8").strip()

    run(k8s_cmd, shell=True, check=True)


def wait_for_pods(ns=None):
    while True:
        print("Waiting for pods to be ready...")
        cmd = [
            "-n {}".format(ns) if ns else "",
            "get pods",
            "-o jsonpath='{..status.conditions[?(@.type==\"Ready\")].status}'",
        ]

        output = run_kubectl_command(
            " ".join(cmd),
            capture_output=True,
        )

        statuses = [o.strip() for o in output.split(" ") if o.strip()]
        if all([s == "True" for s in statuses]):
            print("All pods ready, continuing...")
            break

        print("Pods not ready, waiting ({})".format(output))
        sleep(5)


@task
def create(ctx):
    """
    Create a single-node k8s cluster
    """
    # Start the cluster
    kubeadm_cmd = "sudo kubeadm init --config {}".format(K8S_ADMIN_FILE)
    run(kubeadm_cmd, shell=True, check=True)

    # Wait for pods to be ready
    # TODO

    # Configure flannel
    run_kubectl_command("apply -f {}".format(join(FLANNEL_INSTALL_DIR, "kube-flannel.yml")))
    wait_for_pods("kube-flannel")


@task
def destroy(ctx):
    """
    Destroy a k8s cluster initialised with `inv k8s.create`
    """
    def remove_link(dev_name):
        """
        Remove link entries from ip tables

        We want to be able to run k8s.destroy multiple times, so we need
        to spport the link not existing (and the command failing).
        """
        ip_cmd = "sudo ip link set dev {} down".format(dev_name)
        # The command may fail?
        run(ip_cmd, shell=True)
        ip_cmd = "sudo ip link del {}".format(dev_name)
        # The command may fail?
        run(ip_cmd, shell=True)

    def remove_cni():
        rmtree("/etc/cni/net.d", ignore_errors=True)
        remove_link("cni0")

    def remove_flannel():
        remove_link("flannel.1")

    kubeadm_cmd = "sudo kubeadm reset -f --cri-socket='{}'".format(CRI_RUNTIME_SOCKET)
    run(kubeadm_cmd, shell=True, check=True)

    # Remove networking stuff
    remove_cni()
    remove_flannel()
