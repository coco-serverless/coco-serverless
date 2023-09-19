from invoke import task
from os.path import join
from tasks.util.env import K8S_VERSION
from tasks.util.network import download_binary, symlink_global_bin


@task
def install(ctx):
    """
    Install the k8s binaries: kubectl, kubeadm, and kubelet
    """
    binaries = ["kubectl", "kubeadm", "kubelet"]
    base_url = "https://dl.k8s.io/release/v{}/bin/linux/amd64".format(K8S_VERSION)

    for binary in binaries:
        url = join(base_url, binary)
        binary_path = download_binary(url, binary)
        symlink_global_bin(binary_path, binary)
