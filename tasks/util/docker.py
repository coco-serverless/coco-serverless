from subprocess import run
from tasks.util.env import PROJ_ROOT

def is_ctr_running(ctr_name):
    """
    Work out whether a container is running or not
    """
    docker_cmd = ["docker container inspect", "-f '{{.State.Running}}'", ctr_name]
    docker_cmd = " ".join(docker_cmd)
    out = run(docker_cmd, shell=True, capture_output=True)
    if out.returncode == 0:
        value = out.stdout.decode("utf-8").strip()
        return value == "true"

    return False

def copy_from_container(ctr_name, ctr_path, host_path):
    docker_cmd = "docker cp {}:{} {}".format(
        ctr_name,
        ctr_path,
        host_path,
    )
    run(docker_cmd, shell=True, check=True)

def build_image(image_tag, dockerfile, build_args=None):
    build_args_cmd = ""
    if build_args:
        build_args_cmd = " ".join(["--build-arg {}={}".format(key, value) for key, value in build_args.items()])
    docker_cmd = "docker build {} -t {} -f {} .".format(build_args_cmd, image_tag, dockerfile)
    run(docker_cmd, shell=True, check=True, cwd=PROJ_ROOT)

def run_container(image_tag, ctr_name):
    docker_cmd = "docker run -td --name {} {}".format(ctr_name, image_tag)
    run(docker_cmd, shell=True, check=True)
    
def stop_container(ctr_name):
    docker_cmd = "docker rm -f {}".format(ctr_name)
    run(docker_cmd, shell=True, check=True)
    
def build_image_and_run(image_tag, dockerfile, ctr_name, build_args=None):
    build_image(image_tag, dockerfile, build_args)
    run_container(image_tag, ctr_name)
