from invoke import task
from os.path import join
from os import makedirs
from shutil import copy, rmtree
from subprocess import run
from tasks.util.env import BIN_DIR, print_dotted_line
from tasks.util.network import symlink_global_bin
from tasks.util.versions import K9S_VERSION


@task
def install(ctx, debug=False):
    """
    Install the K9s CLI
    """
    print_dotted_line(f"Installing K9s (v{K9S_VERSION})")

    tar_name = "k9s_Linux_amd64.tar.gz"
    url = "https://github.com/derailed/k9s/releases/download/v{}/{}".format(
        K9S_VERSION, tar_name
    )

    workdir = "/tmp/k9s"
    makedirs(workdir, exist_ok=True)

    # Download the TAR
    cmd = "curl -LO {}".format(url)
    result = run(cmd, shell=True, capture_output=True, cwd=workdir)
    assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
    if debug:
        print(result.stdout.decode("utf-8").strip())

    # Untar
    result = run(
        "tar -xf {}".format(tar_name), shell=True, capture_output=True, cwd=workdir
    )
    assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
    if debug:
        print(result.stdout.decode("utf-8").strip())

    # Copy k9s into place
    binary_path = join(BIN_DIR, "k9s")
    copy(join(workdir, "k9s"), binary_path)

    # Remove tar
    rmtree(workdir)

    # Symlink for k9s command globally
    symlink_global_bin(binary_path, "k9s", debug=debug)

    print("Success!")
