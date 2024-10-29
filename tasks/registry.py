from invoke import task
from os import makedirs
from os.path import exists, join
from subprocess import run
from tasks.util.docker import is_ctr_running
from tasks.util.env import (
    CONTAINERD_CONFIG_FILE,
    CONTAINERD_CONFIG_ROOT,
    K8S_CONFIG_DIR,
    LOCAL_REGISTRY_URL,
    get_node_url,
)
from tasks.util.kata import replace_agent
from tasks.util.knative import configure_self_signed_certs
from tasks.util.kubeadm import run_kubectl_command
from tasks.util.toml import update_toml

HOST_CERT_DIR = join(K8S_CONFIG_DIR, "local-registry")
GUEST_CERT_DIR = "/certs"
REGISTRY_KEY_FILE = "domain.key"
HOST_KEY_PATH = join(HOST_CERT_DIR, REGISTRY_KEY_FILE)
REGISTRY_CERT_FILE = "domain.crt"
HOST_CERT_PATH = join(HOST_CERT_DIR, REGISTRY_CERT_FILE)
REGISTRY_CTR_NAME = "csg-coco-registry"

REGISTRY_IMAGE_TAG = "registry:2.7"

K8S_SECRET_NAME = "csg-coco-registry-customca"


@task
def start(ctx):
    """
    Configure a local container registry reachable from CoCo guests in K8s
    """
    this_ip = get_node_url()

    # ----------
    # DNS Config
    # ----------

    # Add DNS entry (careful to be able to sudo-edit the file)
    dns_file = "/etc/hosts"
    dns_contents = (
        run("sudo cat {}".format(dns_file), shell=True, capture_output=True)
        .stdout.decode("utf-8")
        .strip()
        .split("\n")
    )

    # Only write the DNS entry if it is not there yet
    dns_line = "{} {}".format(this_ip, LOCAL_REGISTRY_URL)
    must_write = not any([dns_line in line for line in dns_contents])

    if must_write:
        actual_dns_line = "\n# CSG: DNS entry for local registry\n{}".format(dns_line)
        write_cmd = "sudo sh -c \"echo '{}' >> {}\"".format(actual_dns_line, dns_file)
        run(write_cmd, shell=True, check=True)

        # If creating a new registry, also update the local SSL certificates
        system_cert_path = "/usr/share/ca-certificates/coco_csg_registry.crt"
        run(
            "sudo cp {} {}".format(HOST_CERT_PATH, system_cert_path),
            shell=True,
            check=True,
        )
        run("sudo dpkg-reconfigure ca-certificates")

    # ----------
    # Docker Registry Config
    # ----------

    # Create certificates for registry
    if not exists(HOST_CERT_DIR):
        makedirs(HOST_CERT_DIR)

    openssl_cmd = [
        "openssl req",
        "-newkey rsa:4096",
        "-nodes -sha256",
        "-keyout {}".format(HOST_KEY_PATH),
        '-addext "subjectAltName = DNS:{}"'.format(LOCAL_REGISTRY_URL),
        "-x509 -days 365",
        "-out {}".format(HOST_CERT_PATH),
    ]
    openssl_cmd = " ".join(openssl_cmd)
    if not exists(HOST_CERT_PATH):
        print(f"running: {openssl_cmd}")
        run(openssl_cmd, shell=True, check=True)

    # Start self-hosted local registry with HTTPS
    docker_cmd = [
        "docker run -d",
        "--restart=always",
        "--name {}".format(REGISTRY_CTR_NAME),
        "-v {}:{}".format(HOST_CERT_DIR, GUEST_CERT_DIR),
        "-e REGISTRY_HTTP_ADDR=0.0.0.0:443",
        "-e REGISTRY_HTTP_TLS_CERTIFICATE={}".format(
            join(GUEST_CERT_DIR, REGISTRY_CERT_FILE)
        ),
        "-e REGISTRY_HTTP_TLS_KEY={}".format(join(GUEST_CERT_DIR, REGISTRY_KEY_FILE)),
        "-p 443:443",
        REGISTRY_IMAGE_TAG,
    ]
    docker_cmd = " ".join(docker_cmd)
    if not is_ctr_running(REGISTRY_CTR_NAME):
        out = run(docker_cmd, shell=True, capture_output=True)
        assert out.returncode == 0, "Failed starting docker container: {}".format(
            out.stderr
        )
    else:
        print("WARNING: skipping starting container as it is already running...")

    # Configure docker to be able to push to this registry
    docker_certs_dir = join("/etc/docker/certs.d", LOCAL_REGISTRY_URL)
    if not exists(docker_certs_dir):
        run("sudo mkdir -p {}".format(docker_certs_dir), shell=True, check=True)

    docker_ca_cert_file = join(docker_certs_dir, "ca.crt")
    cp_cmd = "sudo cp {} {}".format(HOST_CERT_PATH, docker_ca_cert_file)
    run(cp_cmd, shell=True, check=True)

    # ----------
    # containerd config
    # ----------

    containerd_base_certs_dir = join(CONTAINERD_CONFIG_ROOT, "certs.d")
    updated_toml_str = """
    [plugins."io.containerd.grpc.v1.cri".registry]
    config_path = "{containerd_base_certs_dir}"
    """.format(
        containerd_base_certs_dir=containerd_base_certs_dir
    )
    update_toml(CONTAINERD_CONFIG_FILE, updated_toml_str)

    # Add the correspnding configuration to containerd
    containerd_certs_dir = join(containerd_base_certs_dir, LOCAL_REGISTRY_URL)
    if not exists(containerd_certs_dir):
        run("sudo mkdir -p {}".format(containerd_certs_dir), shell=True, check=True)

    containerd_certs_file = """
server = "https://{registry_url}"

[host."https://{registry_url}"]
  skip_verify = true
    """.format(
        registry_url=LOCAL_REGISTRY_URL
    )
    run(
        "sudo sh -c \"echo '{}' > {}\"".format(
            containerd_certs_file, join(containerd_certs_dir, "hosts.toml")
        ),
        shell=True,
        check=True,
    )

    # Restart containerd to pick up the changes (?)
    run("sudo service containerd restart", shell=True, check=True)

    # ----------
    # Kata config
    # ----------

    # Populate the right DNS config and certificate files in the agent
    extra_files = {
        dns_file: {"path": "/etc/hosts", "mode": "w"},
        HOST_CERT_PATH: {"path": "/etc/ssl/certs/ca-certificates.crt", "mode": "a"},
    }
    replace_agent(extra_files=extra_files)

    # ----------
    # Knative config
    # ----------

    # First, create a k8s secret with the credentials
    kube_cmd = (
        "-n knative-serving create secret generic {} --from-file=ca.crt={}".format(
            K8S_SECRET_NAME, HOST_CERT_PATH
        )
    )
    run_kubectl_command(kube_cmd)

    # Second, patch the controller deployment
    configure_self_signed_certs(HOST_CERT_PATH, K8S_SECRET_NAME)


@task
def stop(ctx):
    """
    Remove the container registry in the k8s cluster

    We follow the steps in start in reverse order, paying particular interest
    to the steps that are not idempotent (e.g. creating a k8s secret).
    """
    # For Knative, we only need to delete the secret, as the other bit is a
    # patch to the controller deployment that can be applied again
    kube_cmd = "-n knative-serving delete secret {}".format(K8S_SECRET_NAME)
    run_kubectl_command(kube_cmd)

    # For Kata and containerd, all configuration is reversible, so we only
    # need to sop the container image
    docker_cmd = "docker run --rm -f {}".format(REGISTRY_CTR_NAME)
    run(docker_cmd, shell=True, check=True)
