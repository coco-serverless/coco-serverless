from os.path import dirname, realpath, join

PROJ_ROOT = dirname(dirname(dirname(realpath(__file__))))

BIN_DIR = join(PROJ_ROOT, "bin")
GLOBAL_BIN_DIR = "/usr/local/bin"
# See csegarragonz/coco-serverless#3
GLOBAL_INSTALL_DIR = "/opt"
CONF_FILES_DIR = join(PROJ_ROOT, "conf-files")
TEMPLATED_FILES_DIR = join(PROJ_ROOT, "templated")

# K8s Config

K8S_VERSION = "1.28.2"
K9S_VERSION = "0.27.1"
K8S_CONFIG_DIR = join(PROJ_ROOT, ".config")
K8S_ADMIN_FILE = join(CONF_FILES_DIR, "kubeadm.conf")
# TODO: consider copying this file elsewhere
K8S_CONFIG_FILE = "/etc/kubernetes/admin.conf"
# This value is hardcoded in ./.config/kubeadm.conf
CRI_RUNTIME_SOCKET = "unix:///run/containerd/containerd.sock"
FLANNEL_INSTALL_DIR = join(GLOBAL_INSTALL_DIR, "flannel")

# MicroK8s config

UK8S_KUBECONFIG_FILE = join(K8S_CONFIG_DIR, "uk8s_kubeconfig")

# Kubeadm config

FLANNEL_VERSION = "0.22.3"
KUBEADM_KUBECONFIG_FILE = join(K8S_CONFIG_DIR, "kubeadm_kubeconfig")

# CoCo config

COCO_RELEASE_VERSION = "0.7.0"
COCO_ROOT = join("/opt", "confidential-containers")

# Kata config
KATA_CONFIG_DIR = join(COCO_ROOT, "share", "defaults", "kata-containers")
KATA_IMG_DIR = join(COCO_ROOT, "share", "kata-containers")

# Apps config

APPS_SOURCE_DIR = join(PROJ_ROOT, "apps")
