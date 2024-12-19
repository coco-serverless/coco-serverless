from os import makedirs
from os.path import dirname, exists, join
from subprocess import run
from tasks.util.docker import is_ctr_running
from tasks.util.env import (
    CONTAINERD_CONFIG_FILE,
    KATA_CONFIG_DIR,
    KATA_IMG_DIR,
    KATA_ROOT,
    KATA_RUNTIMES,
    KATA_WORKON_CTR_NAME,
    KATA_IMAGE_TAG,
    SC2_RUNTIMES,
)
from tasks.util.registry import HOST_CERT_PATH
from tasks.util.toml import remove_entry_from_toml, update_toml

# These paths are hardcoded in the docker image: ./docker/kata.dockerfile
KATA_SOURCE_DIR = "/go/src/github.com/kata-containers/kata-containers-sc2"
KATA_AGENT_SOURCE_DIR = join(KATA_SOURCE_DIR, "src", "agent")
KATA_SHIM_SOURCE_DIR = join(KATA_SOURCE_DIR, "src", "runtime")
KATA_BASELINE_SOURCE_DIR = "/go/src/github.com/kata-containers/kata-containers-baseline"
KATA_BASELINE_AGENT_SOURCE_DIR = join(KATA_BASELINE_SOURCE_DIR, "src", "agent")
KATA_BASELINE_SHIM_SOURCE_DIR = join(KATA_BASELINE_SOURCE_DIR, "src", "runtime")


def run_kata_workon_ctr(mount_path=None):
    """
    Start Kata workon container image if it is not running. Return `True` if
    we actually did start the container
    """
    if is_ctr_running(KATA_WORKON_CTR_NAME):
        return False

    docker_cmd = [
        "docker run",
        "-d -t",
        (f"-v {mount_path}:{KATA_SOURCE_DIR}" if mount_path else ""),
        "--name {}".format(KATA_WORKON_CTR_NAME),
        KATA_IMAGE_TAG,
        "bash",
    ]
    docker_cmd = " ".join(docker_cmd)
    out = run(docker_cmd, shell=True, capture_output=True)
    assert out.returncode == 0, "Error starting Kata workon ctr: {}".format(
        out.stderr.decode("utf-8")
    )

    return True


def stop_kata_workon_ctr():
    result = run(
        "docker rm -f {}".format(KATA_WORKON_CTR_NAME),
        shell=True,
        check=True,
        capture_output=True,
    )
    assert result.returncode == 0


# TODO: differentiate between a hot-replace and a regular replace
def copy_from_kata_workon_ctr(ctr_path, host_path, sudo=False, debug=False):
    ctr_started = run_kata_workon_ctr()

    if not ctr_started:
        print("Copying files from running Kata container...")

    docker_cmd = "docker cp {}:{} {}".format(
        KATA_WORKON_CTR_NAME,
        ctr_path,
        host_path,
    )
    if sudo:
        docker_cmd = "sudo {}".format(docker_cmd)
    result = run(docker_cmd, shell=True, capture_output=True)
    if debug:
        print(result.stdout.decode("utf-8").strip())

    # If the Kata workon ctr was not running before, make sure we delete it
    if ctr_started:
        stop_kata_workon_ctr()


def replace_agent(
    dst_initrd_path=join(KATA_IMG_DIR, "kata-containers-initrd-confidential-sc2.img"),
    debug=False,
    sc2=False,
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
    # This is a list of files that we want to _always_ include in our custom
    # agent builds
    extra_files = {
        "/etc/hosts": {"path": "/etc/hosts", "mode": "w"},
        HOST_CERT_PATH: {"path": "/etc/ssl/certs/ca-certificates.crt", "mode": "a"},
    }

    # Use a hardcoded path, as we want to always start from a _clean_ initrd
    initrd_path = join(KATA_IMG_DIR, "kata-containers-initrd-confidential.img")

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
        KATA_AGENT_SOURCE_DIR if sc2 else KATA_BASELINE_AGENT_SOURCE_DIR,
        "target",
        "x86_64-unknown-linux-musl",
        "release",
        "kata-agent",
    )
    agent_initrd_path = join(workdir, "usr/bin/kata-agent")
    copy_from_kata_workon_ctr(
        agent_host_path, agent_initrd_path, sudo=True, debug=debug
    )

    # We also need to manually copy the agent to <root_fs>/sbin/init (note that
    # <root_fs>/init is a symlink to <root_fs>/sbin/init)
    alt_agent_initrd_path = join(workdir, "sbin", "init")
    run("sudo rm {}".format(alt_agent_initrd_path), shell=True, check=True)
    copy_from_kata_workon_ctr(
        agent_host_path, alt_agent_initrd_path, sudo=True, debug=debug
    )

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
        "rm -rf {} && mkdir -p {} {}".format(
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
    copy_from_kata_workon_ctr(ctr_initrd_builder_path, initrd_builder_path, debug=debug)
    copy_from_kata_workon_ctr(
        ctr_lib_path, join(kata_tmp_scripts, "scripts", "lib.sh"), debug=debug
    )
    work_env = {"AGENT_INIT": "yes"}
    initrd_pack_cmd = "sudo {} -o {} {}".format(
        initrd_builder_path,
        dst_initrd_path,
        workdir,
    )
    out = run(initrd_pack_cmd, shell=True, env=work_env, capture_output=True)
    assert out.returncode == 0, "Error packing initrd: {}".format(
        out.stderr.decode("utf-8")
    )

    # Lastly, update the Kata config to point to the new initrd
    target_runtimes = SC2_RUNTIMES if sc2 else KATA_RUNTIMES
    for runtime in target_runtimes:
        # QEMU uses an optimized image file (no initrd) so we keep it that way
        # also, for the time being, the QEMU baseline requires no patches
        if runtime == "qemu":
            continue

        conf_file_path = join(KATA_CONFIG_DIR, "configuration-{}.toml".format(runtime))
        updated_toml_str = """
        [hypervisor.qemu]
        initrd = "{new_initrd_path}"
        """.format(
            new_initrd_path=dst_initrd_path
        )
        update_toml(conf_file_path, updated_toml_str)

        if runtime == "qemu-coco-dev" or "tdx" in runtime:
            remove_entry_from_toml(conf_file_path, "hypervisor.qemu.image")


def replace_shim(
    dst_shim_binary=join(KATA_ROOT, "bin", "containerd-shim-kata-sc2-v2"),
    dst_runtime_binary=join(KATA_ROOT, "bin", "kata-runtime-sc2"),
    sc2=True,
):
    """
    Replace the containerd-kata-shim with a custom one

    To replace the agent, we just need to change the soft-link from the right
    shim to our re-built one
    """
    # First, copy the binary from the source tree
    src_shim_binary = join(
        KATA_SHIM_SOURCE_DIR if sc2 else KATA_BASELINE_SHIM_SOURCE_DIR,
        "containerd-shim-kata-v2",
    )
    copy_from_kata_workon_ctr(src_shim_binary, dst_shim_binary, sudo=True)

    # Also copy the kata-runtime binary
    src_runtime_binary = join(
        KATA_SHIM_SOURCE_DIR if sc2 else KATA_BASELINE_SHIM_SOURCE_DIR,
        "kata-runtime",
    )
    copy_from_kata_workon_ctr(src_runtime_binary, dst_runtime_binary, sudo=True)

    target_runtimes = SC2_RUNTIMES if sc2 else KATA_RUNTIMES
    for runtime in target_runtimes:
        updated_toml_str = """
        [plugins."io.containerd.grpc.v1.cri".containerd.runtimes.kata-{runtime_name}]
        runtime_type = "io.containerd.kata-{runtime_name}.v2"
        runtime_path = "{ctrd_path}"
        """.format(
            runtime_name=runtime, ctrd_path=dst_shim_binary
        )
        update_toml(CONTAINERD_CONFIG_FILE, updated_toml_str)
