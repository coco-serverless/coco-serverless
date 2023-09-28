from invoke import task
from os.path import join
from tasks.util.env import KATA_CONFIG_DIR
from tasks.util.toml import update_toml


@task
def disable_attestation(ctx):
    """
    Disable attestation for CoCo
    """
    conf_file_path = join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml")
    updated_toml_str = """
    [hypervisor.qemu]
    guest_pre_attestation = false
    """
    update_toml(conf_file_path, updated_toml_str)
