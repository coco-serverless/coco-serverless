from invoke import task
from os import makedirs
from os.path import dirname, join
from subprocess import run
from tasks.util.env import KATA_CONFIG_DIR, KATA_IMG_DIR, PROJ_ROOT
from tasks.util.toml import read_value_from_toml, update_toml

KATA_RUNTIMES = ["qemu", "qemu-sev"]
KATA_SOURCE_DIR = join(PROJ_ROOT, "..", "kata-containers")
KATA_AGENT_SOURCE_DIR = join(KATA_SOURCE_DIR, "src", "agent")


@task
def set_log_level(ctx, log_level):
    """
    Set kata's log level, must be one in: info, debug
    """
    allowed_log_levels = ["info", "debug"]
    if log_level not in allowed_log_levels:
        print("Unsupported log level '{}'. Must be one in: {}".format(log_level, allowed_log_levels))
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
        """.format(enable_debug=enable_debug)
        update_toml(conf_file_path, updated_toml_str)


@task
def replace_agent(ctx, agent_source_dir=KATA_AGENT_SOURCE_DIR):
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
    """
    conf_file_path = join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml")
    # Use a hardcoded path, as we want to always start from a _clean_ initrd
    initrd_path = join(KATA_IMG_DIR, "kata-containers-initrd-sev.img")

    # Make empty temporary dir to expand the initrd filesystem
    workdir = "/tmp/qemu-sev-initrd"
    run("sudo rm -rf {}".format(workdir), shell=True, check=True)
    makedirs(workdir)

    # sudo unpack the initrd filesystem
    zcat_cmd = "sudo bash -c 'zcat {} | cpio -idmv'".format(initrd_path)
    run(zcat_cmd, shell=True, check=True, cwd=workdir)

    # Copy our newly built kata-agent into `/usr/bin/kata-agent` as this is the
    # path expected by the kata initrd_builder.sh script
    agent_host_path = join(
        KATA_AGENT_SOURCE_DIR,
        "target",
        "x86_64-unknown-linux-musl",
        "release",
        "kata-agent",
    )
    agent_initrd_path = join(workdir, "usr/bin/kata-agent")
    cp_cmd = "sudo cp {} {}".format(agent_host_path, agent_initrd_path)
    run(cp_cmd, shell=True, check=True)

    # For debugging purposes, try to manually copy the agent to /init too
    alt_agent_initrd_path = join(workdir, "sbin", "init")
    run("sudo rm {}".format(alt_agent_initrd_path), shell=True, check=True)
    cp_cmd = "sudo cp {} {}".format(agent_host_path, alt_agent_initrd_path)
    run(cp_cmd, shell=True, check=True)

    # Pack the initrd again
    initrd_builder_path = join(
        KATA_SOURCE_DIR,
        "tools",
        "osbuilder",
        "initrd-builder",
        "initrd_builder.sh"
    )
    new_initrd_path = join(
        dirname(initrd_path),
        "kata-containers-initrd-sev-csg.img"
    )
    work_env = {"AGENT_INIT": "yes"}
    initrd_pack_cmd = "env && sudo {} -o {} {}".format(
        initrd_builder_path,
        new_initrd_path,
        workdir,
    )
    run(initrd_pack_cmd, shell=True, check=True, env=work_env)

    # Lastly, update the Kata config to point to the new initrd
    updated_toml_str = """
    [hypervisor.qemu]
    initrd = "{new_initrd_path}"
    """.format(new_initrd_path=new_initrd_path)
    update_toml(conf_file_path, updated_toml_str)


@task
def clean_guest_images(ctx):
    """
    Clean the docker images uses in the guest from k8s cache
    """
    pass
