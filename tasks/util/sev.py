from json import loads as json_loads
from os.path import join
from sevsnpmeasure import guest
from sevsnpmeasure.sev_mode import SevMode
from sevsnpmeasure.vmm_types import VMMType
from sevsnpmeasure.vcpu_types import cpu_sig as sev_snp_cpu_sig
from subprocess import run
from tasks.util.env import KATA_CONFIG_DIR
from tasks.util.toml import read_value_from_toml


def get_launch_digest(mode):
    """
    Calculate the SEV launch digest from configuration files
    """
    # Get CPU information
    cpu_json_str = (
        run("lscpu --json", shell=True, check=True, capture_output=True)
        .stdout.decode("utf-8")
        .strip()
    )
    cpu_json = json_loads(cpu_json_str)
    cpu_fields = {"CPU family:": None, "Model:": None, "Stepping:": None}
    for field in cpu_fields:
        data = next(
            filter(
                lambda _dict: _dict["field"] == field,
                [entry for entry in cpu_json["lscpu"]],
            ),
            None,
        )["data"]
        cpu_fields[field] = data
    cpu_sig = sev_snp_cpu_sig(
        int(cpu_fields["CPU family:"]),
        int(cpu_fields["Model:"]),
        int(cpu_fields["Stepping:"]),
    )

    # Pick the right configuration file
    toml_path = join(KATA_CONFIG_DIR, "configuration-qemu-{}.toml".format(mode))

    # Finally, calculate the launch digest
    ld = guest.calc_launch_digest(
        mode=SevMode.SEV,
        vcpus=read_value_from_toml(toml_path, "hypervisor.qemu.default_vcpus"),
        vcpu_sig=cpu_sig,
        ovmf_file=read_value_from_toml(toml_path, "hypervisor.qemu.firmware"),
        kernel=read_value_from_toml(toml_path, "hypervisor.qemu.kernel"),
        initrd=read_value_from_toml(toml_path, "hypervisor.qemu.initrd"),
        append=read_value_from_toml(toml_path, "hypervisor.qemu.kernel_params"),
        vmm_type=VMMType.QEMU,
    )

    return ld
