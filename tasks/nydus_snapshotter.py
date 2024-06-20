from invoke import task
from os import makedirs
from os.path import exists, join
from tasks.util.docker import is_ctr_running
from tasks.util.env import CONF_FILES_DIR, CONTAINERD_CONFIG_FILE, PROJ_ROOT
from tasks.util.toml import update_toml
from subprocess import run, CalledProcessError

@task
def populate_host_sharing_config(ctx):
    config_path = join(COCO_ROOT, "share", "nydus-snapshotter", "config-coco-host-sharing.toml")
    
    if not exists(config_path):
        try:
            run(f"sudo mkdir -p {join(COCO_ROOT, 'share', 'nydus-snapshotter')}", shell=True, check=True)
            
            config_content = """
version = 1
root = "/var/lib/containerd-nydus"
address = "/run/containerd-nydus/containerd-nydus-grpc.sock"
daemon_mode = "none"

[system]
enable = true
address = "/run/containerd-nydus/system.sock"

[daemon]
fs_driver = "blockdev"
nydusimage_path = "/usr/local/bin/nydus-image"

[remote]
skip_ssl_verify = true

[snapshot]
enable_kata_volume = true

[experimental.tarfs]
enable_tarfs = true
mount_tarfs_on_host = false
export_mode = "image_block_with_verity"
"""
            run(f'echo "{config_content}" | sudo tee {config_path}', shell=True, check=True)
        except CalledProcessError as e:
            print(f"Error occurred: {e}")


@task
def toggle_mode(ctx, hybrid=False):
    service_path = "/etc/systemd/system/nydus-snapshotter.service"

    exec_start_host_sharing = "/opt/confidential-containers/bin/containerd-nydus-grpc-hybrid --config /opt/confidential-containers/share/nydus-snapshotter/config-coco-host-sharing.toml --log-to-stdout"
    exec_start_guest_pulling = "/opt/confidential-containers/bin/containerd-nydus-grpc --config /opt/confidential-containers/share/nydus-snapshotter/config-coco-guest-pulling.toml --log-to-stdout"

    service_template = """
[Unit]
Description=Nydus snapshotter
After=network.target local-fs.target
Before=containerd.service

[Service]
ExecStart={}

[Install]
RequiredBy=containerd.service
"""

    exec_start = exec_start_host_sharing if hybrid else exec_start_guest_pulling
    service_content = service_template.format(exec_start)

    try:
        run(f'echo "{service_content.strip()}" | sudo tee {service_path}', shell=True, check=True)
        
        # Reload systemd to apply the new service configuration
        run("sudo systemctl daemon-reload", shell=True, check=True)
        run("sudo systemctl restart nydus-snapshotter.service", shell=True, check=True)
    except CalledProcessError as e:
        print(f"Error occurred: {e}")