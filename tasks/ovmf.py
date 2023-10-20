from invoke import task
from os.path import join
from tasks.util.env import BIN_DIR, KATA_CONFIG_DIR, KATA_RUNTIMES
from tasks.util.toml import update_toml


@task
def set_log_level(ctx, log_level):
    """
    Set OVMF's log level, must be one in: info, debug

    In order to toggle debug logging in OVMF, we need to update the QEMU
    command line to include a couple of OVMF flags. To change the QEMU command
    line, we use a bash wrapper with the extra flags, and point Kata to the
    wrapper script.
    """
    allowed_log_levels = ["info", "debug"]
    if log_level not in allowed_log_levels:
        print(
            "Unsupported log level '{}'. Must be one in: {}".format(
                log_level, allowed_log_levels
            )
        )
        return

    default_qemu_path = "/opt/confidential-containers/bin/qemu-system-x86_64"
    wrapper_qemu_path = join(BIN_DIR, "qemu_wrapper_ovmf_logging.sh")
    qemu_path = default_qemu_path if log_level == "info" else wrapper_qemu_path
    updated_toml_str = """
    [hypervisor.qemu]
    valid_hypervisor_paths = [ "{qemu_path}",]
    """.format(
        qemu_path=qemu_path
    )

    for runtime in KATA_RUNTIMES:
        conf_file_path = join(KATA_CONFIG_DIR, "configuration-{}.toml".format(runtime))
        update_toml(conf_file_path, updated_toml_str)
