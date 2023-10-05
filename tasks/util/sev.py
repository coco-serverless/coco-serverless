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
        # The append parameter of the launch digest corresponds to the -append
        # command passed to QEMU when launching the VM. In order to get it,
        # we must run the exact same VM once, without guest attestation and
        # record the measurement
        # TODO: method to get the right append
        append="""tsc=reliable no_timer_check rcupdate.rcu_expedited=1 i8042.direct=1 i8042.dumbkbd=1 i8042.nopnp=1 i8042.noaux=1 noreplace-smp reboot=k cryptomgr.notests net.ifnames=0 pci=lastbus=0 console=hvc0 console=hvc1 debug panic=1 nr_cpus=1 selinux=0 agent.aa_kbc_params=online_sev_kbc::10.160.40.149:44444 scsi_mod.scan=none agent.log=debug agent.debug_console agent.debug_console_vport=1026 agent.config_file=/etc/agent-config.toml agent.enable_signature_verification=true""",
        vmm_type=VMMType.QEMU,
    )

    return ld
