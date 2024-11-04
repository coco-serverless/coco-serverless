from invoke import task
from os.path import join
from subprocess import run
from tasks.util.env import BASE_IMAGE_TAG, PROJ_ROOT


@task
def build(ctx, nocache=False, push=False):
    docker_cmd = "docker build {} -t {} -f {} .".format(
        "--no-cache" if nocache else "",
        BASE_IMAGE_TAG,
        join(PROJ_ROOT, "docker", "base.dockerfile"),
    )
    run(docker_cmd, shell=True, check=True, cwd=PROJ_ROOT)

    if push:
        run(f"docker push {BASE_IMAGE_TAG}", shell=True, check=True)
