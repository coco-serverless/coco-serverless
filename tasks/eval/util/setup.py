from os import makedirs
from os.path import basename, exists, join
from subprocess import run
from tasks.eval.util.env import BASELINES, EXPERIMENT_IMAGE_REPO
from tasks.util.coco import (
    guest_attestation,
    signature_verification,
    set_firmware,
    set_hypervisor,
)
from tasks.util.containerd import set_cri_handler
from tasks.util.kbs import clear_kbs_db, provision_launch_digest


def get_backup_file_path_from_conf_file(conf_file):
    backup_dir = "/tmp/coco-serverless-back-up"
    if not exists(backup_dir):
        makedirs(backup_dir)

    backup_file = join(backup_dir, basename(conf_file))
    return backup_file


def backup_kata_config_file(conf_file):
    backup_file = get_backup_file_path_from_conf_file(conf_file)
    run("cp {} {}".format(conf_file, backup_file), shell=True, check=True)


def restore_kata_config_file(conf_file):
    backup_file = get_backup_file_path_from_conf_file(conf_file)
    run("cp {} {}".format(backup_file, conf_file), shell=True, check=True)


def cleanup_baseline(baseline):
    """
    Clean-up the system after executing a baseline

    This method reverts the Kata configuration file to the default one after
    a baseline has executed
    """
    baseline_traits = BASELINES[baseline]
    restore_kata_config_file(baseline_traits["conf_file"])


def setup_baseline(baseline, used_images, image_repo=EXPERIMENT_IMAGE_REPO):
    """
    Configure the system for a specific baseline

    This set-up is meant to run once per baseline (so not per run) and it
    configures things like turning guest attestation on/off or signature
    verification on/off and also populating the KBS.
    """
    baseline_traits = BASELINES[baseline]

    # First, save a copy of the current config file so that we can reset it
    # after we are done
    backup_kata_config_file(baseline_traits["conf_file"])

    # Change the path to the used hypervisor
    if "hypervisor" in baseline_traits:
        set_hypervisor(baseline_traits["conf_file"], baseline_traits["hypervisor"])

    # Change the CRI handler
    if "cri_handler" in baseline_traits:
        set_cri_handler(
            baseline_traits["runtime_class"], baseline_traits["cri_handler"]
        )

    # Change the firmware
    if "firmware" in baseline_traits:
        set_firmware(baseline_traits["conf_file"], baseline_traits["firmware"])

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
