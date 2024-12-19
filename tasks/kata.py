from invoke import task
from os.path import abspath, join
from subprocess import run
from tasks.util.containerd import restart_containerd
from tasks.util.env import (
    KATA_CONFIG_DIR,
    KATA_IMAGE_TAG,
    KATA_IMG_DIR,
    KATA_ROOT,
    KATA_RUNTIMES,
    KATA_WORKON_CTR_NAME,
    PROJ_ROOT,
    SC2_RUNTIMES,
)
from tasks.util.kata import (
    replace_agent as replace_kata_agent,
    replace_shim as replace_kata_shim,
    run_kata_workon_ctr,
    stop_kata_workon_ctr,
)
from tasks.util.toml import read_value_from_toml, update_toml
from tasks.util.versions import RUST_VERSION


@task
def build(ctx, nocache=False, push=False):
    """
    Build the Kata Containers workon docker image
    """
    build_args = {
        "RUST_VERSION": RUST_VERSION,
    }
    build_args_str = [
        "--build-arg {}={}".format(key, build_args[key]) for key in build_args
    ]
    build_args_str = " ".join(build_args_str)

    docker_cmd = "docker build {} {} -t {} -f {} .".format(
        "--no-cache" if nocache else "",
        build_args_str,
        KATA_IMAGE_TAG,
        join(PROJ_ROOT, "docker", "kata.dockerfile"),
    )
    run(docker_cmd, shell=True, check=True, cwd=PROJ_ROOT)

    if push:
        run(f"docker push {KATA_IMAGE_TAG}", shell=True, check=True)


@task
def cli(ctx, mount_path=join(PROJ_ROOT, "..", "kata-containers")):
    """
    Get a working environemnt to develop Kata
    """
    if mount_path is not None:
        mount_path = abspath(mount_path)

    run_kata_workon_ctr(mount_path=mount_path)
    run("docker exec -it {} bash".format(KATA_WORKON_CTR_NAME), shell=True, check=True)


@task
def stop(ctx):
    """
    Remove the Kata developement environment
    """
    stop_kata_workon_ctr()


@task
def set_log_level(ctx, log_level):
    """
    Set kata's log level, must be one in: info, debug
    """
    allowed_log_levels = ["info", "debug"]
    if log_level not in allowed_log_levels:
        print(
            "Unsupported log level '{}'. Must be one in: {}".format(
                log_level, allowed_log_levels
            )
        )
        return

    enable_debug = str(log_level == "debug").lower()

    for runtime in KATA_RUNTIMES + SC2_RUNTIMES:
        conf_file_path = join(KATA_CONFIG_DIR, "configuration-{}.toml".format(runtime))
        updated_toml_str = """
        [hypervisor.qemu]
        enable_debug = {enable_debug}

        [agent.kata]
        enable_debug = {enable_debug}
        debug_console_enabled = {enable_debug}

        [runtime]
        enable_debug = {enable_debug}
        """.format(
            enable_debug=enable_debug
        )
        update_toml(conf_file_path, updated_toml_str)


@task
def enable_annotation(ctx, annotation, runtime="qemu-snp-sc2"):
    conf_file_path = join(KATA_CONFIG_DIR, "configuration-{}.toml".format(runtime))
    enabled_annotations = read_value_from_toml(
        conf_file_path, "hypervisor.qemu.enable_annotations"
    )

    if annotation in enabled_annotations:
        return

    enabled_annotations.append(annotation)
    updated_toml_str = """
    [hypervisor.qemu]
    enable_annotations = [ {ann} ]
    """.format(
        ann=",".join([f'"{a}"' for a in enabled_annotations])
    )
    update_toml(conf_file_path, updated_toml_str)


@task
def replace_agent(ctx, debug=False, runtime="qemu-snp-sc2"):
    replace_kata_agent(
        dst_initrd_path=join(
            KATA_IMG_DIR, "kata-containers-initrd-confidential-sc2.img"
        ),
        debug=debug,
        sc2=runtime in SC2_RUNTIMES,
    )


@task
def replace_shim(ctx, runtime="qemu-snp-sc2"):
    replace_kata_shim(
        dst_shim_binary=join(
            KATA_ROOT,
            "bin",
            (
                "containerd-shim-kata-sc2-v2"
                if runtime in SC2_RUNTIMES
                else "containerd-shim-kata-v2"
            ),
        ),
        sc2=runtime in SC2_RUNTIMES,
    )

    restart_containerd()
