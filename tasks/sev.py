from invoke import task
from tasks.util.sev import get_launch_digest as do_get_launch_digest


@task
def get_launch_digest(ctx, mode="sev"):
    """
    Calculate the SEV launch digest from the CoCo configuration file

    To calculate the launch digest we use the sev-snp-measure tool:
    https://github.com/virtee/sev-snp-measure
    """
    ld = do_get_launch_digest(mode)
    print("Calculated measurement:", ld.hex())
