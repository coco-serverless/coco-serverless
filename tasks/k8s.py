from invoke import task
from os import makedirs
from os.path import exists, join
from subprocess import run
from tasks.util.env import BIN_DIR, CONF_FILES_DIR, K8S_VERSION
from tasks.util.kubeadm import (
    get_pod_names_in_ns,
    wait_for_pods_in_ns,
    run_kubectl_command,
)
from tasks.util.network import download_binary, symlink_global_bin
from tasks.util.pid import get_pid


def install_cni(clean=False):
    """
    Install CNI
    """
    cni_root = "/opt/cni"
    cni_version = "1.3.0"

    cni_dir = join(cni_root, "bin")

    if clean:
        run("sudo rm -rf {}".format(cni_dir), shell=True, check=True)

    if not exists(cni_dir):
        run("sudo mkdir -p {}".format(cni_dir), shell=True, check=True)

    cni_tar = "cni-plugins-linux-amd64-v{}.tgz".format(cni_version)
    cni_url = "https://github.com/containernetworking/plugins/releases/"
    cni_url += "download/v{}/{}".format(cni_version, cni_tar)

    # Download the TAR
    run("sudo curl -LO {}".format(cni_url), shell=True, check=True, cwd=cni_dir)

    # Untar
    run("sudo tar -xf {}".format(cni_tar), shell=True, check=True, cwd=cni_dir)

    # Remote the TAR
    run("sudo rm {}".format(join(cni_dir, cni_tar)), shell=True, check=True)


def install_crictl():
    """
    Install the crictl container management tool
    """
    work_dir = "/tmp/crictl"
    makedirs(work_dir, exist_ok=True)

    circtl_binary = "crictl"
    circtl_version = "1.28.0"
    circtl_tar = "crictl-v{}-linux-amd64.tar.gz".format(circtl_version)
    circtl_url = "https://github.com/kubernetes-sigs/cri-tools/releases/"
    circtl_url += "download/v{}/{}".format(circtl_version, circtl_tar)

    # Download the TAR
    run("curl -LO {}".format(circtl_url), shell=True, check=True, cwd=work_dir)

    # Untar
    run("tar -xf {}".format(circtl_tar), shell=True, check=True, cwd=work_dir)

    # Copy the binary and symlink
    circtl_binary_path = join(BIN_DIR, circtl_binary)
    run(
        "cp {} {}".format(join(work_dir, circtl_binary), circtl_binary_path),
        shell=True,
        check=True,
    )
    symlink_global_bin(circtl_binary_path, circtl_binary)


def install_k8s(clean=False):
    """
    Install the k8s binaries: kubectl, kubeadm, and kubelet
    """
    binaries = ["kubectl", "kubeadm", "kubelet"]
    base_url = "https://dl.k8s.io/release/v{}/bin/linux/amd64".format(K8S_VERSION)

    for binary in binaries:
        url = join(base_url, binary)
        binary_path = download_binary(url, binary)
        symlink_global_bin(binary_path, binary)


def configure_kubelet_service(clean=False):
    """
    Configure the kubelet service
    """
    kubelet_service_dir = "/etc/systemd/system/kubelet.service.d"
    makedirs(kubelet_service_dir, exist_ok=True)

    # Copy conf file into place
    conf_file = join(CONF_FILES_DIR, "kubelet_service.conf")
    systemd_conf_file = join(kubelet_service_dir, "10-kubeadm.conf")
    run("sudo cp {} {}".format(conf_file, systemd_conf_file), shell=True, check=True)

    # Copy service file into place
    service_file = join(CONF_FILES_DIR, "kubelet.service")
    systemd_service_file = "/etc/systemd/system/kubelet.service"
    run(
        "sudo cp {} {}".format(service_file, systemd_service_file),
        shell=True,
        check=True,
    )


@task
def install(ctx, clean=False):
    """
    Install and configure all tools to deploy a single-node k8s cluster
    """
    install_cni(clean)
    install_crictl()
    install_k8s()

    # Start kubelet service
    configure_kubelet_service(clean)
