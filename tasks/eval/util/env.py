from tasks.util.env import BIN_DIR, KATA_ROOT, KATA_CONFIG_DIR, PROJ_ROOT
from os.path import join

EVAL_ROOT = join(PROJ_ROOT, "eval")

APPS_DIR = join(EVAL_ROOT, "apps")
EVAL_TEMPLATED_DIR = join(EVAL_ROOT, "templated")
PLOTS_DIR = join(EVAL_ROOT, "plots")
RESULTS_DIR = join(EVAL_ROOT, "results")

# We are running into image pull rate issues, so we want to support changing
# this easily. Note that the image, signatures, and encrypted layers _already_
# live in any container registry before we run the experiment
EXPERIMENT_IMAGE_REPO = "external-registry.coco-csg.com"

INTER_RUN_SLEEP_SECS = 10

BASELINES = {
    # This baseline uses plain Knative on docker containrs
    "docker": {
        "conf_file": "",
        "runtime_class": "",
        "image_tag": "unencrypted",
    },
    # This baseline uses plain Knative on CoCo, but without SEV-enabled VMs
    # (so all CoCo machinery, but no runtime memory encryption)
    "kata": {
        "conf_file": join(KATA_CONFIG_DIR, "configuration-qemu.toml"),
        "runtime_class": "kata",
        "cri_handler": "",
        "image_tag": "unencrypted",
        "firmware": "",
    },
    # This baseline uses plain Knative on CoCo, but without SEV-enabled VMs
    "coco-nosev": {
        "conf_file": join(KATA_CONFIG_DIR, "configuration-qemu.toml"),
        "runtime_class": "kata-qemu",
        "cri_handler": "cc",
        "image_tag": "unencrypted",
        "firmware": "",
    },
    # This baseline is the same one as before, but makes sure we use OVMF as
    # firware (Kata may use SeaBIOS by default)
    "coco-nosev-ovmf": {
        "conf_file": join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml"),
        "runtime_class": "kata-qemu-sev",
        "cri_handler": "cc",
        "image_tag": "unencrypted",
        "firmware": join(KATA_ROOT, "share", "ovmf", "OVMF_CSG.fd"),
        "hypervisor": join(BIN_DIR, "qemu_wrapper_remove_sev_blob.py"),
        "guest_attestation": "off",
        "signature_verification": "off",
    },
    # This baseline uses Knative on confidential VMs with Kata, but does not
    # have any kind of attestation feature. This is an _insecure_ baseline,
    # and only included for demonstration purposes
    "coco": {
        "conf_file": join(KATA_CONFIG_DIR, "configuration-qemu.toml"),
        "runtime_class": "kata-qemu",
        "cri_handler": "cc",
        "image_tag": "unencrypted",
        "guest_attestation": "off",
        "signature_verification": "off",
        "signature_policy": "none",
    },
    # This baseline is the same as the previous one, but the hardware is
    # attested
    "coco-fw": {
        "conf_file": join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml"),
        "runtime_class": "kata-qemu-sev",
        "cri_handler": "cc",
        "image_tag": "unencrypted",
        "guest_attestation": "on",
        "signature_verification": "on",
        "signature_policy": "none",
    },
    # This baseline is the same as the previous one, but in addition the
    # container images used are signed, and the signature is verified
    "coco-fw-sig": {
        "conf_file": join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml"),
        "runtime_class": "kata-qemu-sev",
        "cri_handler": "cc",
        "image_tag": "unencrypted",
        "guest_attestation": "on",
        "signature_verification": "on",
        "signature_policy": "verify",
    },
    # This baseline is the same as the previous one, but the container images
    # are also encrypted
    "coco-fw-sig-enc": {
        "conf_file": join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml"),
        "runtime_class": "kata-qemu-sev",
        "cri_handler": "cc",
        "image_tag": "encrypted",
        "guest_attestation": "on",
        "signature_verification": "on",
        "signature_policy": "verify",
    },
    "coco-nydus": {
        "conf_file": join(KATA_CONFIG_DIR, "configuration-qemu.toml"),
        "runtime_class": "kata-qemu",
        "cri_handler": "cc",
        "image_tag": "unencrypted-nydus",
        "guest_attestation": "off",
        "signature_verification": "off",
        "signature_policy": "none",
    },
    "coco-nydus-caching": {
        "conf_file": join(KATA_CONFIG_DIR, "configuration-qemu.toml"),
        "runtime_class": "kata-qemu",
        "cri_handler": "cc",
        "image_tag": "blob-cache",
        "guest_attestation": "off",
        "signature_verification": "off",
        "signature_policy": "none",
    },
    "coco-caching": {
        "conf_file": join(KATA_CONFIG_DIR, "configuration-qemu.toml"),
        "runtime_class": "kata-qemu",
        "cri_handler": "cc",
        "image_tag": "unencrypted",
        "guest_attestation": "off",
        "signature_verification": "off",
        "signature_policy": "none",
    },
}
BASELINE_FLAVOURS = ["warm", "cold"]

# Each image digest has a unique ID in `crictl`'s image repository. We want to
# remove it from there to avoid caching images when measuring cold starts.
# Note that this ID depends on the image digest, and will change if we change
# the image
IMAGE_TO_ID = {
    "csegarragonz/coco-helloworld-py": "e84d0530bcded",
    "csegarragonz/coco-knative-sidecar": "b7c9cff267c66",
    "fio-benchmark:unencrypted-nydus": "029220d95ecf3",
    "fio-benchmark:unencrypted": "1b1b8660a1d81",
    "helloworld-py:unencrypted": "3cd0777829030",
    "helloworld-py:unencrypted-nydus": "ec73184b3a1fc",
    "knative/serving/cmd/queue:unencrypted": "b7c9cff267c66",
    "knative/serving/cmd/queue:unencrypted-nydus": "85b099d78a8b1",
    "node-app:unencrypted": "0733336eca06f",
    "node-app:unencrypted-nydus": "ab7158860eeff",
    "tf-serving:unencrypted": "77f94702fb2fd",
    "tf-serving:unencrypted-nydus": "2c08273fe3628",
    "tf-serving-tinybert:blob-cache": "b57f04ee02ead",
    "tf-serving:blob-cache": "b232e67d1af43",
    "tf-app:unencrypted-nydus": "6b84d111f0671",
    "tf-app:blob-cache": "afdce6b12dc1b",
    "tf-app:unencrypted": "abcaa35f02d8e",
    "tf-app-tinybert:unencrypted-nydus": "a50ae3000a09d",
    "tf-app-tinybert:blob-cache": "7d68464da7617",
    "tf-app-tinybert:unencrypted": "2a0546dcabae1",
}