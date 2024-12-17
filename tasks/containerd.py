from invoke import task
from os import makedirs, stat
from os.path import exists, join
from subprocess import CalledProcessError, run
from tasks.util.docker import is_ctr_running
from tasks.util.env import (
    CONF_FILES_DIR,
    CONTAINERD_CONFIG_FILE,
    CONTAINERD_CONFIG_ROOT,
    PROJ_ROOT,
    print_dotted_line,
)
from tasks.util.toml import update_toml
from tasks.util.versions import CONTAINERD_VERSION

CONTAINERD_CTR_NAME = "containerd-workon"
CONTAINERD_IMAGE_TAG = "containerd-build"


def restart_containerd():
    """
    Utility function to gracefully restart the containerd service
    """
    run("sudo service containerd restart", shell=True, check=True)


def do_build(debug=False):
    docker_cmd = "docker build -t {} --build-arg CONTAINERD_VERSION={} -f {} .".format(
        CONTAINERD_IMAGE_TAG,
        CONTAINERD_VERSION,
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


def configure_devmapper_snapshotter():
    """
    Configure the devmapper snapshotter in containerd's config file

    This method was included at the begining, when we thought that we needed
    the devmapper snapshotter to get containerd to work. In the end it turned
    out that we did not, but we keep this method here for completeness.
    """
    data_dir = "/var/lib/containerd/devmapper"
    pool_name = "containerd-pool"

    # --------------------------
    # Thin Pool device configuration
    # --------------------------

    # First, remove the device if it already exists
    try:
        run("sudo dmsetup remove --force {}".format(pool_name), shell=True, check=True)
    except CalledProcessError:
        print("Ignoring errors when removing device if it doesn't exist...")

    # Create data and metadata files
    makedirs(data_dir, exist_ok=True)
    data_file = join(data_dir, "data")
    meta_file = join(data_dir, "meta")
    run("sudo touch {}".format(data_file), shell=True, check=True)
    run("sudo truncate -s 100G {}".format(data_file), shell=True, check=True)
    run("sudo touch {}".format(meta_file), shell=True, check=True)
    run("sudo truncate -s 10G {}".format(meta_file), shell=True, check=True)

    # Allocate loop devices
    data_dev = (
        run(
            "sudo losetup --find --show {}".format(data_file),
            shell=True,
            capture_output=True,
        )
        .stdout.decode("utf-8")
        .strip()
    )
    meta_dev = (
        run(
            "sudo losetup --find --show {}".format(meta_file),
            shell=True,
            capture_output=True,
        )
        .stdout.decode("utf-8")
        .strip()
    )

    # Define thin-pool parameters:
    # https://www.kernel.org/doc/Documentation/device-mapper/thin-provisioning.txt
    sector_size = 512
    data_size = int(
        run(
            "sudo blockdev --getsize64 -q {}".format(data_dev),
            shell=True,
            capture_output=True,
        )
        .stdout.decode("utf-8")
        .strip()
    )
    data_block_size = 128
    low_water_mark = 32768

    # Create a thin-pool device
    dmsetup_cmd = [
        "sudo dmsetup",
        "create {}".format(pool_name),
        "--table",
        "'0 {} thin-pool {} {} {} {}'".format(
            int(data_size / sector_size),
            meta_dev,
            data_dev,
            data_block_size,
            low_water_mark,
        ),
    ]
    dmsetup_cmd = " ".join(dmsetup_cmd)
    run(dmsetup_cmd, shell=True, check=True)

    # --------------------------
    # Update containerd's config file to use the devmapper snapshotter
    # --------------------------

    # Note: we currently don't use the devmapper snapshot, so this just
    # _configures_ it (but doesn't select it as snapshotter)
    updated_toml_str = """
    [plugins."io.containerd.snapshotter.v1.devmapper"]
    root_path = "{root_path}"
    pool_name = "{pool_name}"
    base_image_size = "8192MB"
    discard_blocks = true
    """.format(
        root_path=data_dir, pool_name=pool_name
    )
    update_toml(CONTAINERD_CONFIG_FILE, updated_toml_str)


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
    ctr_base_path = "/go/src/github.com/containerd/containerd/bin"
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
    cni_conf_file = "10-containerd-net.conflist"
    cni_dir = "/etc/cni/net.d"
    run("sudo mkdir -p {}".format(cni_dir), shell=True, check=True)
    cp_cmd = "sudo cp {} {}".format(
        join(CONF_FILES_DIR, cni_conf_file), join(cni_dir, cni_conf_file)
    )
    run(cp_cmd, shell=True, check=True)

    # Populate the default config gile
    run("sudo mkdir -p {CONTAINERD_CONFIG_ROOT}", shell=True, check=True)
    config_cmd = "containerd config default > {}".format(CONTAINERD_CONFIG_FILE)
    config_cmd = "sudo bash -c '{}'".format(config_cmd)
    run(config_cmd, shell=True, check=True)

    # Restart containerd service
    restart_containerd()

    # Sanity check
    if stat(CONTAINERD_CONFIG_FILE).st_size == 0:
        raise RuntimeError("containerd config file is empty!")

    print("Success!")
