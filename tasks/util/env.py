from os.path import dirname, realpath, join
from subprocess import run

PROJ_ROOT = dirname(dirname(dirname(realpath(__file__))))

BIN_DIR = join(PROJ_ROOT, "bin")
GLOBAL_BIN_DIR = "/usr/local/bin"
# See csegarragonz/coco-serverless#3
GLOBAL_INSTALL_DIR = "/opt"
COMPONENTS_DIR = join(PROJ_ROOT, "components")
CONF_FILES_DIR = join(PROJ_ROOT, "conf-files")
TEMPLATED_FILES_DIR = join(PROJ_ROOT, "templated")

# K8s Config

K8S_VERSION = "1.28.2"
K9S_VERSION = "0.32.5"
K8S_CONFIG_DIR = join(PROJ_ROOT, ".config")
K8S_ADMIN_FILE = join(CONF_FILES_DIR, "kubeadm.conf")
# TODO: consider copying this file elsewhere
K8S_CONFIG_FILE = "/etc/kubernetes/admin.conf"
# This value is hardcoded in ./.config/kubeadm.conf
CRI_RUNTIME_SOCKET = "unix:///run/containerd/containerd.sock"
FLANNEL_INSTALL_DIR = join(GLOBAL_INSTALL_DIR, "flannel")

# Containerd

CONTAINERD_CONFIG_ROOT = "/etc/containerd"
CONTAINERD_CONFIG_FILE = join(CONTAINERD_CONFIG_ROOT, "config.toml")

# Image Registry config

LOCAL_REGISTRY_URL = "registry.coco-csg.com"
GHCR_URL = "ghcr.io"
GITHUB_USER = "coco-serverless"
# MicroK8s config

UK8S_KUBECONFIG_FILE = join(K8S_CONFIG_DIR, "uk8s_kubeconfig")

# Kubeadm config

FLANNEL_VERSION = "0.22.3"
KUBEADM_KUBECONFIG_FILE = join(K8S_CONFIG_DIR, "kubeadm_kubeconfig")

# CoCo config

COCO_RELEASE_VERSION = "0.9.0"
KATA_ROOT = join("/opt", "kata")

# Kata config
KATA_CONFIG_DIR = join(KATA_ROOT, "share", "defaults", "kata-containers")
KATA_IMG_DIR = join(KATA_ROOT, "share", "kata-containers")
KATA_WORKON_CTR_NAME = "kata-workon"
KATA_WORKON_IMAGE_TAG = "kata-build"
KATA_RUNTIMES = ["qemu", "qemu-sev", "qemu-snp"]

# Apps config

APPS_SOURCE_DIR = join(PROJ_ROOT, "apps")

# KBS Config

KBS_PORT = 44444


def get_node_url():
    """
    Get the external node IP that can be reached from both host and guest

    This IP is both used for the KBS, and for deploying a local docker registry.

    If the KBS is deployed using docker compose with host networking and the
    port is forwarded to the host (i.e. KBS is bound to :${KBS_PORT}, then
    we can use this method to figure out the "public-facing" IP that can be
    reached both from the host and the guest
    """
    ip_cmd = "ip -o route get to 8.8.8.8"
    ip_cmd_out = (
        run(ip_cmd, shell=True, capture_output=True)
        .stdout.decode("utf-8")
        .strip()
        .split(" ")
    )
    idx = ip_cmd_out.index("src") + 1
    kbs_url = ip_cmd_out[idx]
    return kbs_url
