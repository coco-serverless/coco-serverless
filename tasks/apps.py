from invoke import task
from os.path import join
from subprocess import run
from tasks.util.env import APPS_SOURCE_DIR

APP_LIST = {"helloworld-py": join(APPS_SOURCE_DIR, "helloworld-py")}


@task
def build(ctx, app=None, nocache=False):
    """
    Build an app for its usage with the project
    """
    if not app:
        app = list(APP_LIST.keys())
    elif app not in APP_LIST:
        print(
            "Unrecognized app name ({}) must be one in: {}".format(app, APP_LIST.keys())
        )
        raise RuntimeError("Unrecognised app name")
    else:
        app = [app]

    for app_name in app:
        app_path = APP_LIST[app_name]
        docker_tag = join("csegarragonz", "coco-{}".format(app_name))

        # First, build the image
        docker_cmd = [
            "docker build",
            "--no-cache" if nocache else "",
            "-t {} .".format(docker_tag),
        ]
        docker_cmd = " ".join(docker_cmd)
        run(docker_cmd, shell=True, check=True, cwd=app_path)

        # Second, push it
        docker_cmd = "docker push {}".format(docker_tag)
        run(docker_cmd, shell=True, check=True)
