from os import makedirs
from os.path import dirname, exists, join
from subprocess import run
from tasks.util.env import KATA_CONFIG_DIR, KATA_IMG_DIR, KATA_RUNTIMES, PROJ_ROOT
from tasks.util.toml import read_value_from_toml, remove_entry_from_toml, update_toml

KATA_SOURCE_DIR = join(PROJ_ROOT, "..", "kata-containers")
KATA_AGENT_SOURCE_DIR = join(KATA_SOURCE_DIR, "src", "agent")


def replace_agent(
    dst_initrd_path=join(KATA_IMG_DIR, "kata-containers-initrd-sev-csg.img"),
    agent_source_dir=KATA_AGENT_SOURCE_DIR,
    extra_files=None
):
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

    # Use a hardcoded path, as we want to always start from a _clean_ initrd
    initrd_path = join(KATA_IMG_DIR, "kata-containers-initrd-sev.img")

    # Make empty temporary dir to expand the initrd filesystem
    workdir = "/tmp/qemu-sev-initrd"
    run("sudo rm -rf {}".format(workdir), shell=True, check=True)
    makedirs(workdir)

    # sudo unpack the initrd filesystem
    zcat_cmd = "sudo bash -c 'zcat {} | cpio -idmv'".format(initrd_path)
    out = run(zcat_cmd, shell=True, capture_output=True, cwd=workdir)
    assert out.returncode == 0, "Error unpacking initrd: {}".format(out.stderr)

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

    # We also need to manually copy the agent to <root_fs>/sbin/init (note that
    # <root_fs>/init is a symlink to <root_fs>/sbin/init)
    alt_agent_initrd_path = join(workdir, "sbin", "init")
    run("sudo rm {}".format(alt_agent_initrd_path), shell=True, check=True)
    cp_cmd = "sudo cp {} {}".format(agent_host_path, alt_agent_initrd_path)
    run(cp_cmd, shell=True, check=True)

    # Include any extra files that the caller may have provided
    if extra_files is not None:
        for host_path in extra_files:
            # Trim any absolute paths expressed as "guest" paths to be able to
            # append the rootfs
            rel_guest_path = extra_files[host_path]["path"]
            if rel_guest_path.startswith("/"):
                rel_guest_path = rel_guest_path[1:]

            guest_path = join(workdir, rel_guest_path)
            if not exists(dirname(guest_path)):
                run(
                    "sudo mkdir -p {}".format(dirname(guest_path)),
                    shell=True,
                    check=True,
                )

            if exists(guest_path) and extra_files[host_path]["mode"] == "a":
                run(
                    'sudo sh -c "cat {} >> {}"'.format(host_path, guest_path),
                    shell=True,
                    check=True,
                )
            else:
                run(
                    "sudo cp {} {}".format(host_path, guest_path),
                    shell=True,
                    check=True,
                )

    # Pack the initrd again
    initrd_builder_path = join(
        KATA_SOURCE_DIR, "tools", "osbuilder", "initrd-builder", "initrd_builder.sh"
    )
    work_env = {"AGENT_INIT": "yes"}
    initrd_pack_cmd = "env && sudo {} -o {} {}".format(
        initrd_builder_path,
        dst_initrd_path,
        workdir,
    )
    out = run(initrd_pack_cmd, shell=True, check=True, env=work_env, capture_output=True)
    assert out.returncode == 0, "Error packing initrd: {}".format(out.stderr.decode("utf-8"))

    # Lastly, update the Kata config to point to the new initrd
    for runtime in KATA_RUNTIMES:
        conf_file_path = join(KATA_CONFIG_DIR, "configuration-{}.toml".format(runtime))
        updated_toml_str = """
        [hypervisor.qemu]
        initrd = "{new_initrd_path}"
        """.format(
            new_initrd_path=dst_initrd_path
        )
        update_toml(conf_file_path, updated_toml_str)

        if runtime == "qemu":
            remove_entry_from_toml(conf_file_path, "hypervisor.qemu.image")


def get_default_vm_mem_size(
    toml_path=join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml")
):
    """
    Get the default memory assigned to each new VM from the Kata config file.
    This value is expressed in MB. We also take by default, accross baselines,
    the value used for the qemu-sev runtime class.
    """
    mem = int(read_value_from_toml(toml_path, "hypervisor.qemu.default_memory"))
    assert mem > 0, "Read non-positive default memory size: {}".format(mem)
    return mem


def update_vm_mem_size(toml_path, new_mem_size):
    """
    Update the default VM memory size in the Kata config file
    """
    updated_toml_str = """
    [hypervisor.qemu]
    default_memory = {mem_size}
    """.format(
        mem_size=new_mem_size
    )
    update_toml(toml_path, updated_toml_str)
