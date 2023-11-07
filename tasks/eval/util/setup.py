from os.path import join
from tasks.eval.util.env import BASELINES, EXPERIMENT_IMAGE_REPO
from tasks.util.coco import guest_attestation, signature_verification
from tasks.util.containerd import set_cri_handler
from tasks.util.kbs import clear_kbs_db, provision_launch_digest


def setup_baseline(baseline, used_images, image_repo=EXPERIMENT_IMAGE_REPO):
    """
    Configure the system for a specific baseline

    This set-up is meant to run once per baseline (so not per run) and it
    configures things like turning guest attestation on/off or signature
    verification on/off and also populating the KBS.
    """
    baseline_traits = BASELINES[baseline]

    # Change the CRI handler
    if "cri_handler" in baseline_traits:
        set_cri_handler(
            baseline_traits["runtime_class"], baseline_traits["cri_handler"]
        )

    # Turn guest pre-attestation on/off (connect KBS to PSP)
    if "guest_attestation" in baseline_traits:
        guest_attestation(
            baseline_traits["conf_file"], baseline_traits["guest_attestation"]
        )

    # Turn signature verification on/off (validate HW digest)
    if "signature_verification" in baseline_traits:
        signature_verification(
            baseline_traits["conf_file"], baseline_traits["signature_verification"]
        )

    # Manually clean the KBS but skip clearing the secrets used to decrypt
    # images. Those can remain there
    clear_kbs_db(skip_secrets=True)

    # Configure signature policy (check image signature or not). We must do
    # this at the very end as it relies on: (i) the KBS DB being clear, and
    # (ii) the configuration file populated by the previous methods
    if "signature_policy" in baseline_traits:
        images_to_sign = [join(image_repo, image) for image in used_images]
        provision_launch_digest(
            images_to_sign,
            signature_policy=baseline_traits["signature_policy"],
            clean=False,
        )
