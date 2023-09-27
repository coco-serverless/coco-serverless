from invoke import task
from os.path import join
from subprocess import run
from tasks.util.env import KATA_CONFIG_DIR
from toml import load as toml_load, dump as toml_dump

KATA_RUNTIMES = ["qemu", "qemu-sev"]


@task
def set_log_level(ctx, log_level):
    """
    Set kata's log level, must be one in: info, debug
    """
    allowed_log_levels = ["info", "debug"]
    if log_level not in allowed_log_levels:
        print("Unsupported log level '{}'. Must be one in: {}".format(log_level, allowed_log_levels))
        return

    enable_debug = log_level == "debug"

    for runtime in KATA_RUNTIMES:
        conf_file_path = join(KATA_CONFIG_DIR, "configuration-{}.toml".format(runtime))
        conf_file = toml_load(conf_file_path)
        conf_file["hypervisor"]["qemu"]["enable_debug"] = enable_debug
        conf_file["agent"]["kata"]["enable_debug"] = enable_debug
        conf_file["agent"]["kata"]["debug_console_enabled"] = enable_debug
        conf_file["runtime"]["enable_debug"] = enable_debug

        # Dump the TOML contents to a temporary file (can't sudo-write)
        tmp_conf = "/tmp/configuration_{}.toml".format(runtime)
        with open(tmp_conf, "w") as fh:
            toml_dump(conf_file, fh)

        # sudo-copy the TOML file in place
        run(
            "sudo cp {} {}".format(tmp_conf, conf_file_path), shell=True, check=True
        )
