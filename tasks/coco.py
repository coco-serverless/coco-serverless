from invoke import task
from os.path import join
from tasks.util.env import KATA_CONFIG_DIR
from tasks.util.kbs import KBS_PORT, get_kbs_url
from tasks.util.toml import read_value_from_toml, update_toml


@task
def guest_attestation(ctx, mode="off"):
    """
    Toggle guest attestation for CoCo: -attestation --mode=[on,off]
    """
    conf_file_path = join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml")

    # Update the pre_attestation flag
    att_val = str(mode == "on").lower()
    updated_toml_str = """
    [hypervisor.qemu]
    guest_pre_attestation = {att_val}
    """.format(att_val=att_val)
    update_toml(conf_file_path, updated_toml_str)

    # We also update the KBS URI if pre_attestation is enabled
    if mode == "on":
        # We need to set the KBS URL to something that is reachable both from
        # the host _and_ the guest
        updated_toml_str = """
        [hypervisor.qemu]
        guest_pre_attestation_kbs_uri = "{kbs_url}:{kbs_port}"
        """.format(kbs_url=get_kbs_url(), kbs_port=KBS_PORT)
        update_toml(conf_file_path, updated_toml_str)


@task
def signature_verification(ctx, mode="off"):
    """
    Toggle signature verification for CoCo's agent: --mode=[on,off]
    """
    conf_file_path = join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml")
    att_val = str(mode == "on").lower()

    # We need to update the kernel parameters, which is a string, so we are
    # particularly careful
    original_kernel_params = read_value_from_toml(conf_file_path, "hypervisor.qemu.kernel_params")
    # Whenever I learn regex, this will be less hacky
    pattern = "enable_signature_verification="
    value_beg = original_kernel_params.find(pattern) + len(pattern)
    value_end = original_kernel_params.find(" ", value_beg)
    updated_kernel_params = (original_kernel_params[:value_beg]
                             + att_val
                             + original_kernel_params[value_end:])

    updated_toml_str = """
    [hypervisor.qemu]
    kernel_params = "{updated_kernel_params}"
    """.format(updated_kernel_params=updated_kernel_params)
    update_toml(conf_file_path, updated_toml_str)
