from invoke import task
from os import makedirs
from os.path import exists, join
from subprocess import run
from tasks.util.docker import is_ctr_running
from tasks.util.env import (
    CONTAINERD_CONFIG_FILE,
    CONTAINERD_CONFIG_ROOT,
    LOCAL_REGISTRY_URL,
    print_dotted_line,
    get_node_url,
)
from tasks.util.knative import configure_self_signed_certs
from tasks.util.kubeadm import run_kubectl_command
from tasks.util.registry import (
    HOST_CERT_DIR,
    GUEST_CERT_DIR,
    REGISTRY_KEY_FILE,
    HOST_KEY_PATH,
    REGISTRY_CERT_FILE,
    HOST_CERT_PATH,
    K8S_SECRET_NAME,
    REGISTRY_CTR_NAME,
)
from tasks.util.toml import update_toml

REGISTRY_VERSION = "2.8"
REGISTRY_IMAGE_TAG = f"registry:{REGISTRY_VERSION}"


@task
def start(ctx, debug=False, clean=False):
    """
    Configure a local container registry reachable from CoCo guests in K8s
    """
    this_ip = get_node_url()
    print_dotted_line(
        "Configuring local docker registry (v{}) at IP: {} (name: {})".format(
            REGISTRY_VERSION, this_ip, LOCAL_REGISTRY_URL
        )
    )

    # ----------
    # Docker Registry Config
    # ----------

    if clean and is_ctr_running(REGISTRY_CTR_NAME):
        if debug:
            print(f"WARNING: stopping registry container: {REGISTRY_CTR_NAME}")

        result = run(
            f"docker rm -f {REGISTRY_CTR_NAME}", shell=True, capture_output=True
        )
        assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
        if debug:
            print(result.stdout.decode("utf-8").strip())

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
        result = run(openssl_cmd, shell=True, capture_output=True)
        assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
        if debug:
            print(result.stdout.decode("utf-8").strip())

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
        if debug:
            print(out.stdout.decode("utf-8").strip())
    else:
        if debug:
            print("WARNING: skipping starting container as it is already running...")

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
        system_cert_path = "/usr/share/ca-certificates/sc2_registry.crt"
        run(
            "sudo cp {} {}".format(HOST_CERT_PATH, system_cert_path),
            shell=True,
            check=True,
        )
        result = run(
            "sudo dpkg-reconfigure ca-certificates", shell=True, capture_output=True
        )
        assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
        if debug:
            print(result.stdout.decode("utf-8").strip())

    # ----------
    # dockerd config
    # ----------

    # Configure docker to be able to push to this registry
    docker_certs_dir = join("/etc/docker/certs.d", LOCAL_REGISTRY_URL)
    if not exists(docker_certs_dir):
        run("sudo mkdir -p {}".format(docker_certs_dir), shell=True, check=True)

    docker_ca_cert_file = join(docker_certs_dir, "ca.crt")
    cp_cmd = "sudo cp {} {}".format(HOST_CERT_PATH, docker_ca_cert_file)
    run(cp_cmd, shell=True, check=True)

    # Re-start docker to pick up the new certificates
    run("sudo service docker restart", shell=True, check=True)

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

    containerd_cert_path = join(containerd_certs_dir, "sc2_registry.crt")
    containerd_certs_file = """
server = "https://{registry_url}"

[host."https://{registry_url}"]
  capabilities = ["pull", "resolve"]
  ca = "{containerd_cert_path}"
    """.format(
        registry_url=LOCAL_REGISTRY_URL, containerd_cert_path=containerd_cert_path
    )
    run(
        "sudo sh -c \"echo '{}' > {}\"".format(
            containerd_certs_file, join(containerd_certs_dir, "hosts.toml")
        ),
        shell=True,
        check=True,
    )

    # Copy the certificate to the corresponding containerd directory
    run(f"sudo cp {HOST_CERT_PATH} {containerd_cert_path}", shell=True, check=True)

    # Restart containerd to pick up the changes
    run("sudo service containerd restart", shell=True, check=True)

    # ----------
    # Kata config
    #
    # We need to do two things to get the Kata Agent to pull an image from our
    # local registry with a self-signed certificate:
    # 1. Include our self-signed ceritifcate, and DNS entry, into the agent
    # 2. Re-build the agent with native-tls (instead of rusttls) so that we
    #    read the certificates (rusttls deliberately does not read from files
    #    in the filesystem)
    #
    # We concentrate all modifications to the agent in a single call to
    # do_replace_agent, part of our deployment.
    # ----------

    # ----------
    # Knative config
    # ----------

    # First, create a k8s secret with the credentials
    kube_cmd = (
        "-n knative-serving create secret generic {} --from-file=ca.crt={}".format(
            K8S_SECRET_NAME, HOST_CERT_PATH
        )
    )
    run_kubectl_command(kube_cmd, capture_output=not debug)

    # Second, patch the controller deployment
    configure_self_signed_certs(HOST_CERT_DIR, K8S_SECRET_NAME, debug=debug)

    print("Success!")


@task
def stop(ctx, debug=False):
    """
    Remove the container registry in the k8s cluster

    We follow the steps in start in reverse order, paying particular interest
    to the steps that are not idempotent (e.g. creating a k8s secret).
    """
    # For Knative, we only need to delete the secret, as the other bit is a
    # patch to the controller deployment that can be applied again
    kube_cmd = "-n knative-serving delete secret {}".format(K8S_SECRET_NAME)
    run_kubectl_command(kube_cmd, capture_output=not debug)

    # For Kata and containerd, all configuration is reversible, so we only
    # need to sop the container image
    docker_cmd = "docker rm -f {}".format(REGISTRY_CTR_NAME)
    result = run(docker_cmd, shell=True, capture_output=True)
    assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
    if debug:
        print(result.stdout.decode("utf-8").strip())
