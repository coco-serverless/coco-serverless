from tasks.util.env import BIN_DIR, COCO_ROOT, KATA_CONFIG_DIR, PROJ_ROOT
from os.path import join

EVAL_ROOT = join(PROJ_ROOT, "eval")

APPS_DIR = join(EVAL_ROOT, "apps")
EVAL_TEMPLATED_DIR = join(EVAL_ROOT, "templated")
PLOTS_DIR = join(EVAL_ROOT, "plots")
RESULTS_DIR = join(EVAL_ROOT, "results")

# We are running into image pull rate issues, so we want to support changing
# this easily. Note that the image, signatures, and encrypted layers _already_
# live in any container registry before we run the experiment
EXPERIMENT_IMAGE_REPO = "ghcr.io"

INTER_RUN_SLEEP_SECS = 10

BASELINES = {
    "coco": {
        "conf_file": join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml"),
        "runtime_class": "kata-qemu-sev",
        "cri_handler": "cc",
        "image_tag": "unencrypted",
        "guest_attestation": "off",
        "signature_verification": "off",
        "signature_policy": "none",
    },
    # "coco-nydus": {
    #     "conf_file": join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml"),
    #     "runtime_class": "kata-qemu-sev",
    #     "cri_handler": "cc",
    #     "image_tag": "unencrypted",
    #     "guest_attestation": "off",
    #     "signature_verification": "off",
    # },
}
BASELINE_FLAVOURS = ["cold"]


# Each image digest has a unique ID in `crictl`'s image repository. We want to
# remove it from there to avoid caching images when measuring cold starts.
# Note that this ID depends on the image digest, and will change if we change
# the image
IMAGE_TO_ID = {
    "csegarragonz/coco-helloworld-py": "e84d0530bcded",
    "csegarragonz/coco-knative-sidecar": "b7c9cff267c66",
}
