from tasks.util.env import PROJ_ROOT
from os.path import join

EVAL_ROOT = join(PROJ_ROOT, "eval")

APPS_DIR = join(EVAL_ROOT, "apps")
EVAL_TEMPLATED_DIR = join(EVAL_ROOT, "templated")
PLOTS_DIR = join(EVAL_ROOT, "plots")
RESULTS_DIR = join(EVAL_ROOT, "results")

BASELINES = {
    # This baseline uses plain Knative on docker containrs
    "docker": {
        "runtime_class": "",
        "image_tag": "unencrypted",
        "guest_attestation": "",
        "signature_verification": "",
        "signature_policy": "",
    },
    # This baseline uses plain Knative on Kata containers (i.e. VMs)
    # Unfortunately, we can't run baseline kata as we need to use the CCv0
    # fork with CoCo, and we had to patch the agent in that version to run wiht
    # image revisions
    "kata": {
        "runtime_class": "kata-qemu",
        "image_tag": "unencrypted",
        "guest_attestation": "",
        "signature_verification": "",
        "signature_policy": "",
    },
    # This baseline uses Knative on confidential VMs with Kata, but does not
    # have any kind of attestation feature. This is an _insecure_ baseline,
    # and only included for demonstration purposes
    "coco": {
        "runtime_class": "kata-qemu-sev",
        "image_tag": "unencrypted",
        "guest_attestation": "off",
        "signature_verification": "off",
        "signature_policy": "none",
    },
    # This baseline is the same as the previous one, but the hardware is
    # attested
    "coco-fw": {
        "runtime_class": "kata-qemu-sev",
        "image_tag": "unencrypted",
        "guest_attestation": "on",
        "signature_verification": "on",
        "signature_policy": "none",
    },
    # This baseline is the same as the previous one, but in addition the
    # container images used are signed, and the signature is verified
    "coco-fw-sig": {
        "runtime_class": "kata-qemu-sev",
        "image_tag": "unencrypted",
        "guest_attestation": "on",
        "signature_verification": "on",
        "signature_policy": "verify",
    },
    # This baseline is the same as the previous one, but the container images
    # are also encrypted
    "coco-fw-sig-enc": {
        "runtime_class": "kata-qemu-sev",
        "image_tag": "encrypted",
        "guest_attestation": "on",
        "signature_verification": "on",
        "signature_policy": "verify",
    },
}

# Each image digest has a unique ID in `crictl`'s image repository. We want to
# remove it from there to avoid caching images when measuring cold starts.
# Note that this ID depends on the image digest, and will change if we change
# the image
IMAGE_TO_ID = {
    "csegarragonz/coco-helloworld-py": "e84d0530bcded",
    "csegarragonz/coco-knative-sidecar": "b7c9cff267c66",
}
