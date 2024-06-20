from invoke import task
from os.path import dirname, exists, join
from subprocess import run, CalledProcessError
from tasks.util.env import (
    KATA_CONFIG_DIR,
    KATA_IMG_DIR,
    KATA_RUNTIMES,
    KATA_IMG_DIR
)
from tasks.util.toml import remove_entry_from_toml, update_toml


cc_hybrid_initrd_path = join(KATA_IMG_DIR, "kata-containers-initrd-sev-verity-ks.img")
cc_hybrid_kernel_path = join(KATA_IMG_DIR, "vmlinuz-sev-verity.container")

@task
def update_configs(ctx):
    for runtime in ["qemu-sev"]:# KATA_RUNTIMES:
        conf_file_path = join(KATA_CONFIG_DIR, "configuration-{}.toml".format(runtime))
        updated_toml_str = """
        [hypervisor.qemu]
        initrd = "{new_initrd_path}"
        """.format(
            new_initrd_path=cc_hybrid_initrd_path
        )
        update_toml(conf_file_path, updated_toml_str)

        updated_toml_str = """
        [hypervisor.qemu]
        kernel = "{new_vm_path}"
        """.format(
            new_vm_path=cc_hybrid_kernel_path
        )
        update_toml(conf_file_path, updated_toml_str)

        if runtime == "qemu":
            remove_entry_from_toml(conf_file_path, "hypervisor.qemu.image")


@task
def install_cc_hybrid_deps(ctx):
    repo_url = "https://github.com/konsougiou/coco-hybrid-assets.git"
    clone_dir = "/tmp/coco-hybrid-assets"
    dest_paths = {
        "kata/kata-containers-initrd-sev-verity-ks.img": cc_hybrid_initrd_path,
        "kata/vmlinuz-sev.container": cc_hybrid_vm_path,
        "nydus-snapshotter/containerd-nydus-grpc-hybrid": "/opt/confidential-containers/bin/containerd-nydus-grpc-hybrid"
    }

    try:
        if not exists(clone_dir):
            # Clone the repository to /tmp
            run(f"git clone {repo_url} {clone_dir}", shell=True, check=True)
        else:
            # If already cloned, pull the latest changes
            run(f"git -C {clone_dir} pull", shell=True, check=True)

        # Copy the files to their respective destinations
        for src, dest in dest_paths.items():
            run(f"sudo cp {clone_dir}/{src} {dest}", shell=True, check=True)

        print("CoCo hybrid assets fetched and copied successfully.")
    except CalledProcessError as e:
        print(f"Error occurred: {e}")