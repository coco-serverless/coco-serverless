from invoke import task
from os.path import exists, join
from subprocess import run
from tasks.util.env import PROJ_ROOT

SIMPLE_KBS_DIR = join(PROJ_ROOT, "..", "simple-kbs")


@task
def start(ctx):
    """
    Start the simple KBS service
    """
    if not exists(SIMPLE_KBS_DIR):
        print("Error: could not find local KBS checkout at {}".format(SIMPLE_KBS_DIR))
        raise RuntimeError("Simple KBS local checkout not found!")

    run("docker compose up -d", shell=True, check=True, cwd=SIMPLE_KBS_DIR)
