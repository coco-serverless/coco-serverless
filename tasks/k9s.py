from invoke import task
from os.path import join
from os import makedirs
from shutil import copy, rmtree
from subprocess import run
from tasks.util.env import BIN_DIR, K9S_VERSION
from tasks.util.network import symlink_global_bin


@task
def install_k9s(ctx):
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
    symlink_global_bin(binary_path, "k9s")
