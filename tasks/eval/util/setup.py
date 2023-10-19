from os.path import join
from tasks.eval.util.env import BASELINES, EXPERIMENT_IMAGE_REPO
from tasks.util.coco import guest_attestation, signature_verification
from tasks.util.kbs import clear_kbs_db, provision_launch_digest


def setup_baseline(baseline, used_images):
    """
    Configure the system for a specific baseline

    This set-up is meant to run once per baseline (so not per run) and it
    configures things like turning guest attestation on/off or signature
    verification on/off and also populating the KBS.
    """
    if baseline in ["docker", "kata"]:
        return

    baseline_traits = BASELINES[baseline]

    # Turn guest pre-attestation on/off (connect KBS to PSP)
    guest_attestation(baseline_traits["guest_attestation"])

    # Turn signature verification on/off (validate HW digest)
    signature_verification(baseline_traits["signature_verification"])

    # Manually clean the KBS but skip clearing the secrets used to decrypt
    # images. Those can remain there
    clear_kbs_db(skip_secrets=True)

    # Configure signature policy (check image signature or not). We must do
    # this at the very end as it relies on: (i) the KBS DB being clear, and
    # (ii) the configuration file populated by the previous methods
    images_to_sign = [join(EXPERIMENT_IMAGE_REPO, image) for image in used_images]
    provision_launch_digest(
        images_to_sign,
        signature_policy=baseline_traits["signature_policy"],
        clean=False,
    )
