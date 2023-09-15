from invoke import task
from subprocess import run
from tasks.util.env import PROJ_ROOT


@task(default=True)
def format(ctx, check=False):
    """
    Format Python code
    """
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
