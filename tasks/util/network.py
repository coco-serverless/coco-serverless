from os.path import exists, join
from os import makedirs
from subprocess import run
from tasks.util.env import BIN_DIR, GLOBAL_BIN_DIR


def download_binary(url, binary_name, debug=False):
    makedirs(BIN_DIR, exist_ok=True)

    cmd = "curl -LO {}".format(url)
    result = run(cmd, shell=True, capture_output=True, cwd=BIN_DIR)
    assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
    if debug:
        print(result.stdout.decode("utf-8").strip())

    run("chmod +x {}".format(binary_name), shell=True, check=True, cwd=BIN_DIR)

    return join(BIN_DIR, binary_name)


def symlink_global_bin(binary_path, name, debug=False):
    global_path = join(GLOBAL_BIN_DIR, name)
    if exists(global_path):
        if debug:
            print("Removing existing binary at {}".format(global_path))
        run(
            "sudo rm -f {}".format(global_path),
            shell=True,
            check=True,
        )

    if debug:
        print("Symlinking {} -> {}".format(global_path, binary_path))
    run(
        "sudo ln -sf {} {}".format(binary_path, name),
        shell=True,
        check=True,
        cwd=GLOBAL_BIN_DIR,
    )
