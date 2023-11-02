from subprocess import run


def is_ctr_running(ctr_name):
    """
    Work out whether a container is running or not
    """
    docker_cmd = [
        "docker container inspect",
        "-f '{{.State.Running}}'",
        ctr_name
    ]
    docker_cmd = " ".join(docker_cmd)
    out = run(docker_cmd, shell=True, capture_output=True)
    if out.returncode == 0:
        value = out.stdout.decode("utf-8").strip()
        return value == "true"

    return False
