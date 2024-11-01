from os.path import join
from tasks.util.env import K8S_CONFIG_DIR

HOST_CERT_DIR = join(K8S_CONFIG_DIR, "local-registry")
GUEST_CERT_DIR = "/certs"
REGISTRY_KEY_FILE = "domain.key"
HOST_KEY_PATH = join(HOST_CERT_DIR, REGISTRY_KEY_FILE)
REGISTRY_CERT_FILE = "domain.crt"
HOST_CERT_PATH = join(HOST_CERT_DIR, REGISTRY_CERT_FILE)
REGISTRY_CTR_NAME = "sc2-registry"
K8S_SECRET_NAME = "sc2-registry-customca"
