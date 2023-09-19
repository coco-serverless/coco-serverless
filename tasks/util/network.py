from os.path import exists, join
from os import makedirs
from subprocess import run
from tasks.util.env import BIN_DIR, GLOBAL_BIN_DIR


def download_binary(url, binary_name):
    makedirs(BIN_DIR, exist_ok=True)
    cmd = "curl -LO {}".format(url)
    run(cmd, shell=True, check=True, cwd=BIN_DIR)
    run("chmod +x {}".format(binary_name), shell=True, check=True, cwd=BIN_DIR)

    return join(BIN_DIR, binary_name)


def symlink_global_bin(binary_path, name):
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
