from invoke import task
from tasks.util.coco import (
    guest_attestation as do_guest_attestation,
    signature_verification as do_signature_verification,
)


@task
def guest_attestation(ctx, mode="off"):
    """
    Toggle guest attestation for CoCo: -attestation --mode=[on,off]
    """
    do_guest_attestation(mode=mode)


@task
def signature_verification(ctx, mode="off"):
    """
    Toggle signature verification for CoCo's agent: --mode=[on,off]
    """
    do_signature_verification(mode)
