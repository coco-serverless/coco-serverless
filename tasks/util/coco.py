from os.path import join
from tasks.util.env import KATA_CONFIG_DIR, KBS_PORT, get_node_url
from tasks.util.toml import read_value_from_toml, update_toml


def guest_attestation(
    conf_file_path=join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml"), mode="off"
):
    """
    This method toggles the signature verification parameter in the Kata
    configration file. The guest_pre_attestation flag indicates whether the
    kata shim is going to try to ping the KBS and establish a secure channel
    between the KBS and the PSP.
    """
    # Update the pre_attestation flag
    att_val = str(mode == "on").lower()
    updated_toml_str = """
    [hypervisor.qemu]
    guest_pre_attestation = {att_val}
    """.format(
        att_val=att_val
    )
    update_toml(conf_file_path, updated_toml_str)

    # We also update the KBS URI if pre_attestation is enabled
    if mode == "on":
        # We need to set the KBS URL to something that is reachable both from
        # the host _and_ the guest
        updated_toml_str = """
        [hypervisor.qemu]
        guest_pre_attestation_kbs_uri = "{kbs_url}:{kbs_port}"
        """.format(
            kbs_url=get_node_url(), kbs_port=KBS_PORT
        )
        update_toml(conf_file_path, updated_toml_str)


def signature_verification(
    conf_file_path=join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml"), mode="off"
):
    """
    This method configures the signature verification process in the Kata
    config file. This flag is not only an on/off switch, but also
    specifies the KBS URI, which is also passed as part of the kernel
    parameters. Note that the kernel parameters are measured, so a change in
    this method will change the HW measurement.
    """
    conf_file_path = join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml")
    att_val = str(mode == "on").lower()

    # We need to update the kernel parameters, which is a string, so we are
    # particularly careful
    original_kernel_params = read_value_from_toml(
        conf_file_path, "hypervisor.qemu.kernel_params"
    )
    # Whenever I learn regex, this will be less hacky
    pattern = "enable_signature_verification="
    value_beg = original_kernel_params.find(pattern) + len(pattern)
    value_end = original_kernel_params.find(" ", value_beg)
    updated_kernel_params = (
        original_kernel_params[:value_beg]
        + att_val
        + original_kernel_params[value_end:]
    )

    updated_toml_str = """
    [hypervisor.qemu]
    kernel_params = "{updated_kernel_params}"
    """.format(
        updated_kernel_params=updated_kernel_params
    )
    update_toml(conf_file_path, updated_toml_str)
