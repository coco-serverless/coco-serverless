from invoke import task
from os import makedirs
from os.path import join
from subprocess import CalledProcessError, run
from tasks.util.env import CONF_FILES_DIR, PROJ_ROOT
from toml import load as toml_load, dump as toml_dump

CONTAINERD_IMAGE_TAG = "containerd-build"
CONTAINERD_SOURCE_CHECKOUT = join(PROJ_ROOT, "..", "containerd")
CONTAINERD_CONFIG_FILE = "/etc/containerd/config.toml"


@task
def build(ctx):
    """
    Build the containerd fork for CoCo
    """
    docker_cmd = "docker build -t {} -f {} .".format(
        CONTAINERD_IMAGE_TAG, join(PROJ_ROOT, "docker", "containerd.dockerfile")
    )
    run(docker_cmd, shell=True, check=True, cwd=PROJ_ROOT)


@task
def cli(ctx):
    """
    Get a working environment for containerd
    """
    containerd_guest_wdir = "/go/src/github.com/containerd/containerd"
    docker_cmd = [
        "docker run",
        "--rm -it",
        "--name containerd-cli",
        "-v {}:{}".format(CONTAINERD_SOURCE_CHECKOUT, containerd_guest_wdir),
        CONTAINERD_IMAGE_TAG,
        "bash",
    ]
    docker_cmd = " ".join(docker_cmd)

    run(docker_cmd, shell=True, check=True, cwd=PROJ_ROOT)


def configure_devmapper_snapshotter():
    """
    Configure the devmapper snapshotter in containerd's config file
    """
    data_dir = "/var/lib/containerd/devmapper"
    pool_name = "containerd-pool"

    # First, remove the device if it already exists
    run("sudo dmsetup remove --force {}".format(pool_name), shell=True, check=True)

    # Create data and metadata files
    makedirs(data_dir, exist_ok=True)
    data_file = join(data_dir, "data")
    meta_file = join(data_dir, "meta")
    run("sudo touch {}".format(data_file), shell=True, check=True)
    run("sudo truncate -s 100G {}".format(data_file), shell=True, check=True)
    run("sudo touch {}".format(meta_file), shell=True, check=True)
    run("sudo truncate -s 10G {}".format(meta_file), shell=True, check=True)

    # Allocate loop devices
    data_dev = run("sudo losetup --find --show {}".format(data_file),
                   shell=True,
                   capture_output=True).stdout.decode("utf-8").strip()
    meta_dev = run("sudo losetup --find --show {}".format(meta_file),
                   shell=True,
                   capture_output=True).stdout.decode("utf-8").strip()

    # Define thin-pool parameters:
    # https://www.kernel.org/doc/Documentation/device-mapper/thin-provisioning.txt
    sector_size = 512
    data_size = int(run("sudo blockdev --getsize64 -q {}".format(data_dev),
                        shell=True,
                        capture_output=True).stdout.decode("utf-8").strip())
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

    devmapper_conf = {
        "root_path": data_dir,
        "pool_name": pool_name,
        "base_image_size": "8192MB",
        "discard_blocks": True,
    }

    conf_file = toml_load(CONTAINERD_CONFIG_FILE)
    conf_file['plugins']['io.containerd.snapshotter.v1.devmapper'] = devmapper_conf

    tmp_conf = "/tmp/containerd_config.toml"
    with open(tmp_conf, "w") as fh:
        toml_dump(conf_file, fh)

    # Finally, copy in place
    run("sudo cp {} {}".format(tmp_conf, CONTAINERD_CONFIG_FILE), shell=True, check=True)


@task
def install(ctx):
    """
    Install the built containerd
    """
    tmp_ctr_name = "tmp_containerd_build"
    docker_cmd = "docker run -td --name {} {} bash".format(
        tmp_ctr_name, CONTAINERD_IMAGE_TAG
    )
    run(docker_cmd, shell=True, check=True)

    def cleanup():
        docker_cmd = "docker rm -f {}".format(tmp_ctr_name)
        run(docker_cmd, shell=True, check=True)

    binary_names = [
        "containerd",
        "containerd-shim",
        "containerd-shim-runc-v1",
        "containerd-shim-runc-v2",
    ]
    ctr_base_path = "/go/src/github.com/containerd/containerd/bin"
    host_base_path = "/usr/bin"
    for binary in binary_names:
        docker_cmd = "sudo docker cp {}:{}/{} {}/{}".format(
            tmp_ctr_name, ctr_base_path, binary, host_base_path, binary
        )
        try:
            # TODO: we need to copy containerd to /opt/confidential-containers/bin
            run(docker_cmd, shell=True, check=True)
        except CalledProcessError as e:
            cleanup()
            raise e

    cleanup()

    # Configure the CNI (see containerd/scripts/setup/install-cni)
    cni_conf_file = "10-containerd-net.conflist"
    cni_dir = "/etc/cni/net.d"
    run("sudo mkdir -p {}".format(cni_dir), shell=True, check=True)
    cp_cmd = "sudo cp {} {}".format(
        join(CONF_FILES_DIR, cni_conf_file),
        join(cni_dir, cni_conf_file)
    )
    run(cp_cmd, shell=True, check=True)

    # Populate the default config gile
    config_cmd = "containerd config default > {}".format(CONTAINERD_CONFIG_FILE)
    config_cmd = "sudo bash -c '{}'".format(config_cmd)
    run(config_cmd, shell=True, check=True)

    # Configure the devmapper snapshotter for Knative
    configure_devmapper_snapshotter()

    # Restart containerd service
    run("sudo service containerd restart", shell=True, check=True)
