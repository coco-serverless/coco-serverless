from invoke import task
from os.path import join
from subprocess import CalledProcessError, run
from tasks.util.docker import is_ctr_running
from tasks.util.env import (
    CONF_FILES_DIR,
    CONTAINERD_CONFIG_FILE,
    GHCR_URL,
    GITHUB_ORG,
    PROJ_ROOT,
    print_dotted_line,
)
from tasks.util.toml import update_toml
from tasks.util.versions import CONTAINERD_VERSION

CONTAINERD_CTR_NAME = "containerd-workon"
CONTAINERD_IMAGE_TAG = join(GHCR_URL, GITHUB_ORG, "containerd") + f":{CONTAINERD_VERSION}"


def restart_containerd():
    """
    Utility function to gracefully restart the containerd service
    """
    run("sudo service containerd restart", shell=True, check=True)


def do_build(debug=False):
    docker_cmd = "docker build -t {} -f {} .".format(
        CONTAINERD_IMAGE_TAG,
        join(PROJ_ROOT, "docker", "containerd.dockerfile"),
    )
    result = run(docker_cmd, shell=True, capture_output=True, cwd=PROJ_ROOT)
    assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
    if debug:
        print(result.stdout.decode("utf-8").strip())


@task
def build(ctx):
    """
    Build the containerd fork for CoCo
    """
    do_build(debug=True)


@task
def cli(ctx):
    """
    Get a working environment for containerd
    """
    if not is_ctr_running(CONTAINERD_CTR_NAME):
        docker_cmd = [
            "docker run",
            "-d -it",
            "--name {}".format(CONTAINERD_CTR_NAME),
            CONTAINERD_IMAGE_TAG,
            "bash",
        ]
        docker_cmd = " ".join(docker_cmd)
        run(docker_cmd, shell=True, check=True, cwd=PROJ_ROOT)

    run("docker exec -it {} bash".format(CONTAINERD_CTR_NAME), shell=True, check=True)


@task
def set_log_level(ctx, log_level):
    """
    Set containerd's log level, must be one in: info, debug
    """
    allowed_log_levels = ["info", "debug"]
    if log_level not in allowed_log_levels:
        print(
            "Unsupported log level '{}'. Must be one in: {}".format(
                log_level, allowed_log_levels
            )
        )
        return

    updated_toml_str = """
    [debug]
    level = "{log_level}"
    """.format(
        log_level=log_level
    )
    update_toml(CONTAINERD_CONFIG_FILE, updated_toml_str)

    restart_containerd()


@task
def install(ctx, debug=False, clean=False):
    """
    Install (and build) containerd from source
    """
    print_dotted_line(f"Installing containerd (v{CONTAINERD_VERSION})")
    do_build(debug=debug)

    tmp_ctr_name = "tmp_containerd_build"
    docker_cmd = "docker run -td --name {} {} bash".format(
        tmp_ctr_name, CONTAINERD_IMAGE_TAG
    )
    result = run(docker_cmd, capture_output=True, shell=True)
    assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
    if debug:
        print(result.stdout.decode("utf-8").strip())

    def cleanup():
        docker_cmd = "docker rm -f {}".format(tmp_ctr_name)
        result = run(docker_cmd, shell=True, capture_output=True)
        assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
        if debug:
            print(result.stdout.decode("utf-8").strip())

    binary_names = [
        "containerd",
        "containerd-shim",
        "containerd-shim-runc-v1",
        "containerd-shim-runc-v2",
    ]
    ctr_base_path = "/go/src/github.com/sc2-sys/containerd/bin"
    host_base_path = "/usr/bin"
    for binary in binary_names:
        if clean:
            run(
                "sudo rm -f {}".format(join(host_base_path, binary)),
                shell=True,
                check=True,
            )

        docker_cmd = "sudo docker cp {}:{}/{} {}/{}".format(
            tmp_ctr_name, ctr_base_path, binary, host_base_path, binary
        )
        try:
            result = run(docker_cmd, shell=True, capture_output=True)
            assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
            if debug:
                print(result.stdout.decode("utf-8").strip())
        except CalledProcessError as e:
            cleanup()
            raise e

    cleanup()

    # Clean-up all runtime files for a clean start
    if clean:
        run("sudo rm -rf /var/lib/containerd", shell=True, check=True)

    # Configure the CNI (see containerd/scripts/setup/install-cni)
    if clean:
        cni_conf_file = "10-containerd-net.conflist"
        cni_dir = "/etc/cni/net.d"
        run("sudo mkdir -p {}".format(cni_dir), shell=True, check=True)
        cp_cmd = "sudo cp {} {}".format(
            join(CONF_FILES_DIR, cni_conf_file), join(cni_dir, cni_conf_file)
        )
        run(cp_cmd, shell=True, check=True)

    # Populate the default config file for a clean start
    if clean:
        config_cmd = "containerd config default > {}".format(CONTAINERD_CONFIG_FILE)
        config_cmd = "sudo bash -c '{}'".format(config_cmd)
        run(config_cmd, shell=True, check=True)

    # Restart containerd service
    restart_containerd()
    print("Success!")
