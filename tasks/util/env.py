from os.path import dirname, realpath, join

PROJ_ROOT = dirname(dirname(dirname(realpath(__file__))))

BIN_DIR = join(PROJ_ROOT, "bin")
GLOBAL_BIN_DIR = "/usr/local/bin"

# K8s Config

K8S_VERSION = "1.28.2"
K9S_VERSION = "0.27.1"
K8S_CONFIG_DIR = join(PROJ_ROOT, ".config")
# This value is hardcoded in ./.config/kubeadm.conf
CRI_RUNTIME_SOCKET = "unix:///run/containerd/containerd.sock"
