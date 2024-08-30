from invoke import task
from os.path import join
from subprocess import run
from tasks.util.env import APPS_SOURCE_DIR, PROJ_ROOT


@task(default=True)
def format(ctx, check=False):
    """
    Format code
    """

    # -----
    # Python formatting
    # -----

    files_to_check = (
        run(
            'git ls-files -- "*.py"',
            shell=True,
            check=True,
            cwd=PROJ_ROOT,
            capture_output=True,
        )
        .stdout.decode("utf-8")
        .split("\n")[:-1]
    )
    black_cmd = [
        "python3 -m black",
        "{}".format("--check" if check else ""),
        " ".join(files_to_check),
    ]
    black_cmd = " ".join(black_cmd)
    run(black_cmd, shell=True, check=True, cwd=PROJ_ROOT)

    flake8_cmd = [
        "python3 -m flake8",
        " ".join(files_to_check),
    ]
    flake8_cmd = " ".join(flake8_cmd)
    run(flake8_cmd, shell=True, check=True, cwd=PROJ_ROOT)

    # -----
    # Rust formatting
    # -----

    dirs_to_check = [join(APPS_SOURCE_DIR, "knative-chaining")]
    for dir_to_check in dirs_to_check:
        run(
            "cargo fmt {}".format("--check" if check else ""),
            shell=True,
            check=True,
            cwd=dir_to_check,
        )
