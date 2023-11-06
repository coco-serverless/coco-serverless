from invoke import task
from os.path import join
from subprocess import run
from tasks.util.env import (
    COCO_ROOT,
    KATA_CONFIG_DIR,
    KATA_RUNTIMES,
)
from tasks.util.kata import (
    KATA_AGENT_SOURCE_DIR,
    KATA_SOURCE_DIR,
    replace_agent as do_replace_agent,
)
from tasks.util.toml import update_toml

KATA_SHIM_SOURCE_DIR = join(KATA_SOURCE_DIR, "src", "runtime")


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

    for runtime in KATA_RUNTIMES:
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
def replace_agent(ctx, agent_source_dir=KATA_AGENT_SOURCE_DIR, extra_files=None):
    """
    Replace the kata-agent with a custom-built one

    Replacing the kata-agent is a bit fiddly, as the kata-agent binary lives
    inside the initrd guest image that we load to the VM. The replacement
    includes the following steps:
    1. Find the initrd file - should be pointed in the Kata config file
    2. Unpack the initrd
    3. Replace the init process by the new kata agent
    4. Re-build the initrd
    5. Update the kata config to point to the new initrd

    By using the extra_flags optional argument, you can pass a dictionary of
    host_path: guest_path pairs of files you want to be included in the initrd.
    """
    do_replace_agent(agent_source_dir=agent_source_dir, extra_files=extra_files)


@task
def replace_shim(ctx, shim_source_dir=KATA_SHIM_SOURCE_DIR, revert=False):
    """
    Replace the containerd-kata-shim with a custom one

    To replace the agent, we just need to change the soft-link from the right
    shim to our re-built one
    """
    # First, copy the binary from the source tree
    src_shim_binary = join(shim_source_dir, "containerd-shim-kata-v2")
    dst_shim_binary = join(COCO_ROOT, "bin", "containerd-shim-kata-v2-csg")
    run(
        "sudo cp {} {}".format(src_shim_binary, dst_shim_binary), shell=True, check=True
    )

    # Second, soft-link the SEV runtime to the right shim binary
    if revert:
        dst_shim_binary = join(COCO_ROOT, "bin", "containerd-shim-kata-v2")

    # This path is hardcoded in the containerd config/operator
    sev_shim_binary = "/usr/local/bin/containerd-shim-kata-qemu-sev-v2"

    run(
        "sudo ln -sf {} {}".format(dst_shim_binary, sev_shim_binary),
        shell=True,
        check=True,
    )
