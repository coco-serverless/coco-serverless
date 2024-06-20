from invoke import task
from os.path import dirname, exists, join
import os
from subprocess import run, CalledProcessError
from tasks.util.env import EXTERNAL_REGISTRY_URL
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

@task
def generate_images(ctx, image_name, workdir):

    image_repo = EXTERNAL_REGISTRY_URL
    try:
        public_dockerfile = os.path.join(workdir, "public", "Dockerfile")
        main_dockerfile = os.path.join(workdir, "Dockerfile")
        blob_cache_dir = os.path.join(workdir, "blob-cache")
        blobs_dir = os.path.join(blob_cache_dir, "blobs")

        if not os.path.exists(blob_cache_dir):
            os.makedirs(blob_cache_dir)
        if not os.path.exists(blobs_dir):
            os.makedirs(blobs_dir)

        # Step 1: Build the whole image with the tag unencrypted
        unencrypted_tag = f"{image_repo}/{image_name}:unencrypted"
        run(f"docker build -t {unencrypted_tag} -f {main_dockerfile} {workdir}", shell=True, check=True)

        # Step 2: Build the public image with the tag public and push to registry
        public_tag = f"{image_repo}/{image_name}:public"
        run(f"docker build -t {public_tag} -f {public_dockerfile} {os.path.join(workdir, 'public')}", shell=True, check=True)

        run(f"docker push {public_tag}", shell=True, check=True)
        run(f"docker push {unencrypted_tag}", shell=True, check=True)

        # Step 3: Convert to Nydus images using nydusify and push to registry
        public_nydus_tag = f"{image_repo}/{image_name}:public-nydus"
        unencrypted_nydus_tag = f"{image_repo}/{image_name}:unencrypted-nydus"

        run(f"nydusify convert --source {public_tag} --target {public_nydus_tag}", shell=True, check=True)
        run(f"nydusify convert --source {unencrypted_tag} --target {unencrypted_nydus_tag}", shell=True, check=True)

        # Step 4:  Extract blob data
        run(f"nydusify check --target {unencrypted_nydus_tag} --work-dir {output_dir}", shell=True, check=True)
        run(f"nydus-image check --bootstrap {join(output_dir, 'nydus_bootstrap')} -J {join(output_dir, 'output.json')}", shell=True, check=True)

        # Step 5:  Read extracted json 
        with open(join(output_dir, 'output.json')) as f:
            output_data = json.load(f)
            blob_ids = output_data['blobs']

        # Step 6: Pull all the blobs and store them
        for blob_id in blob_ids:
            blob_url = f"https://{image_repo}/v2/{image_name}/blobs/sha256:{blob_id}"
            blob_dest = join(blobs_dir, blob_id)
            run(f"curl -L {blob_url} -o {blob_dest}", shell=True, check=True)

        # Step 7: Create the blob-cache Dockerfile
        blob_cache_dockerfile = os.path.join(blob_cache_dir, "Dockerfile")
        with open(blob_cache_dockerfile, "w") as f:
            f.write("FROM scratch\n")
            for blob_id in blob_ids:
                f.write(f"COPY blobs/{blob_id} /cache/{blob_id}\n")

        # Step 8: Build and push the blob-cache image
        blob_cache_tag = f"{image_repo}/{image_name}:blob-cache"
        run(f"docker build -t {blob_cache_tag} -f {blob_cache_dockerfile} {blob_cache_dir}", shell=True, check=True)
        run(f"docker push {blob_cache_tag}", shell=True, check=True)

        print("Nydus private image and blob-cache image have been created and pushed successfully.")

    except CalledProcessError as e:
        print(f"Error occurred: {e}")