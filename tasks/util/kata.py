from os import makedirs
from os.path import dirname, exists, join
from subprocess import run
from tasks.util.docker import is_ctr_running
from tasks.util.env import (
    KATA_CONFIG_DIR,
    KATA_IMG_DIR,
    KATA_RUNTIMES,
    KATA_WORKON_CTR_NAME,
    KATA_WORKON_IMAGE_TAG,
)
from tasks.util.toml import read_value_from_toml, remove_entry_from_toml, update_toml

# This path is hardcoded in the docker image: ./docker/kata.dockerfile
KATA_SOURCE_DIR = "/go/src/github.com/kata-containers/kata-containers"
KATA_AGENT_SOURCE_DIR = join(KATA_SOURCE_DIR, "src", "agent")


def run_kata_workon_ctr():
    """
    Start Kata workon container image if it is not running. Return `True` if
    we actually did start the container
    """
    if is_ctr_running(KATA_WORKON_CTR_NAME):
        return False

    docker_cmd = [
        "docker run",
        "-d -t",
        "--name {}".format(KATA_WORKON_CTR_NAME),
        KATA_WORKON_IMAGE_TAG,
        "bash",
    ]
    docker_cmd = " ".join(docker_cmd)
    out = run(docker_cmd, shell=True, capture_output=True)
    assert out.returncode == 0, "Error starting Kata workon ctr: {}".format(
        out.stderr.decode("utf-8")
    )

    return True


def stop_kata_workon_ctr():
    run("docker rm -f {}".format(KATA_WORKON_CTR_NAME), shell=True, check=True)


def copy_from_kata_workon_ctr(ctr_path, host_path, sudo=False):
    ctr_started = run_kata_workon_ctr()

    docker_cmd = "docker cp {}:{} {}".format(
        KATA_WORKON_CTR_NAME,
        ctr_path,
        host_path,
    )
    if sudo:
        docker_cmd = "sudo {}".format(docker_cmd)
    run(docker_cmd, shell=True, check=True)

    # If the Kata workon ctr was not running before, make sure we delete it
    if ctr_started:
        stop_kata_workon_ctr()


def replace_agent(
    dst_initrd_path=join(KATA_IMG_DIR, "kata-containers-initrd-sev-csg.img"),
    extra_files=None,
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

    # Copy the kata-agent in our docker image into `/usr/bin/kata-agent` as
    # this is the path expected by the kata initrd_builder.sh script
    agent_host_path = join(
        KATA_AGENT_SOURCE_DIR,
        "target",
        "x86_64-unknown-linux-musl",
        "release",
        "kata-agent",
    )
    agent_initrd_path = join(workdir, "usr/bin/kata-agent")
    copy_from_kata_workon_ctr(agent_host_path, agent_initrd_path, sudo=True)

    # We also need to manually copy the agent to <root_fs>/sbin/init (note that
    # <root_fs>/init is a symlink to <root_fs>/sbin/init)
    alt_agent_initrd_path = join(workdir, "sbin", "init")
    run("sudo rm {}".format(alt_agent_initrd_path), shell=True, check=True)
    copy_from_kata_workon_ctr(agent_host_path, alt_agent_initrd_path, sudo=True)

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

    # Pack the initrd again (copy the script from the container into a
    # temporarly location). Annoyingly, we also need to copy a bash script in
    # the same relative directory structure (cuz bash).
    kata_tmp_scripts = "/tmp/osbuilder"
    run(
        "rm -f {} && mkdir -p {} {}".format(
            kata_tmp_scripts,
            join(kata_tmp_scripts, "scripts"),
            join(kata_tmp_scripts, "initrd-builder"),
        ),
        shell=True,
        check=True,
    )
    ctr_initrd_builder_path = join(
        KATA_SOURCE_DIR, "tools", "osbuilder", "initrd-builder", "initrd_builder.sh"
    )
    ctr_lib_path = join(KATA_SOURCE_DIR, "tools", "osbuilder", "scripts", "lib.sh")
    initrd_builder_path = join(kata_tmp_scripts, "initrd-builder", "initrd_builder.sh")
    copy_from_kata_workon_ctr(ctr_initrd_builder_path, initrd_builder_path)
    copy_from_kata_workon_ctr(ctr_lib_path, join(kata_tmp_scripts, "scripts", "lib.sh"))
    work_env = {"AGENT_INIT": "yes"}
    initrd_pack_cmd = "sudo {} -o {} {}".format(
        initrd_builder_path,
        dst_initrd_path,
        workdir,
    )
    out = run(
        initrd_pack_cmd, shell=True, check=True, env=work_env, capture_output=True
    )
    assert out.returncode == 0, "Error packing initrd: {}".format(
        out.stderr.decode("utf-8")
    )

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
