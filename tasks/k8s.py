from invoke import task
from os.path import join, exists
from os import makedirs
from shutil import copy, rmtree
from subprocess import run
from tasks.util.env import (
    BIN_DIR,
    GLOBAL_BIN_DIR,
    K8S_VERSION,
    K9S_VERSION,
)


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
