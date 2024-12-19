from os import makedirs
from os.path import exists, join
from shutil import rmtree
from subprocess import run
from tasks.util.env import BIN_DIR, CONF_FILES_DIR, print_dotted_line
from tasks.util.network import download_binary, symlink_global_bin
from tasks.util.versions import K8S_VERSION, CNI_VERSION, CRICTL_VERSION


def install_cni(debug=False, clean=False):
    """
    Install CNI
    """
    cni_root = "/opt/cni"

    cni_dir = join(cni_root, "bin")

    if clean:
        run("sudo rm -rf {}".format(cni_dir), shell=True, check=True)

    if not exists(cni_dir):
        run("sudo mkdir -p {}".format(cni_dir), shell=True, check=True)

    cni_tar = "cni-plugins-linux-amd64-v{}.tgz".format(CNI_VERSION)
    cni_url = "https://github.com/containernetworking/plugins/releases/"
    cni_url += "download/v{}/{}".format(CNI_VERSION, cni_tar)

    # Download the TAR
    result = run(
        "sudo curl -LO {}".format(cni_url), shell=True, capture_output=True, cwd=cni_dir
    )
    assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
    if debug:
        print(result.stdout.decode("utf-8").strip())

    # Untar
    result = run(
        "sudo tar -xf {}".format(cni_tar), shell=True, capture_output=True, cwd=cni_dir
    )
    assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
    if debug:
        print(result.stdout.decode("utf-8").strip())

    # Remove the TAR
    run("sudo rm {}".format(join(cni_dir, cni_tar)), shell=True, check=True)


def install_crictl(debug=False):
    """
    Install the crictl container management tool
    """
    work_dir = "/tmp/crictl"

    if exists(work_dir):
        rmtree(work_dir)

    makedirs(work_dir)

    circtl_binary = "crictl"
    circtl_tar = "crictl-v{}-linux-amd64.tar.gz".format(CRICTL_VERSION)
    circtl_url = "https://github.com/kubernetes-sigs/cri-tools/releases/"
    circtl_url += "download/v{}/{}".format(CRICTL_VERSION, circtl_tar)

    # Download the TAR
    result = run(
        "curl -LO {}".format(circtl_url), shell=True, capture_output=True, cwd=work_dir
    )
    assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
    if debug:
        print(result.stdout.decode("utf-8").strip())

    # Untar
    result = run(
        "tar -xf {}".format(circtl_tar), shell=True, capture_output=True, cwd=work_dir
    )
    assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
    if debug:
        print(result.stdout.decode("utf-8").strip())

    # Copy the binary and symlink
    circtl_binary_path = join(BIN_DIR, circtl_binary)
    run(
        "cp {} {}".format(join(work_dir, circtl_binary), circtl_binary_path),
        shell=True,
        check=True,
    )
    symlink_global_bin(circtl_binary_path, circtl_binary, debug=debug)

    rmtree(work_dir)


def install_k8s(debug=False, clean=False):
    """
    Install the k8s binaries: kubectl, kubeadm, and kubelet
    """
    binaries = ["kubectl", "kubeadm", "kubelet"]
    base_url = "https://dl.k8s.io/release/v{}/bin/linux/amd64".format(K8S_VERSION)

    for binary in binaries:
        url = join(base_url, binary)
        binary_path = download_binary(url, binary, debug=debug)
        symlink_global_bin(binary_path, binary, debug=debug)

    # Also install some APT dependencies
    result = run("sudo apt install -y conntrack socat", shell=True, capture_output=True)
    assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
    if debug:
        print(result.stdout.decode("utf-8").strip())

    # Run modprobe, kubeadm does not do it for non-docker deployments
    result = run("sudo modprobe br_netfilter", shell=True, capture_output=True)
    assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
    if debug:
        print(result.stdout.decode("utf-8").strip())


def configure_kubelet_service(debug=False, clean=False):
    """
    Configure the kubelet service
    """
    kubelet_service_dir = "/etc/systemd/system/kubelet.service.d"
    run(f"sudo mkdir -p {kubelet_service_dir}", shell=True, check=True)

    # Copy conf file into place
    conf_file = join(CONF_FILES_DIR, "kubelet_service.conf")
    systemd_conf_file = join(kubelet_service_dir, "10-kubeadm.conf")
    run("sudo cp {} {}".format(conf_file, systemd_conf_file), shell=True, check=True)

    # Copy service file into place
    service_file = join(CONF_FILES_DIR, "kubelet.service")
    systemd_service_file = "/etc/systemd/system/kubelet.service"
    run(
        "sudo cp {} {}".format(service_file, systemd_service_file),
        shell=True,
        check=True,
    )

    # Enable the service
    result = run(
        "sudo systemctl enable kubelet.service", shell=True, capture_output=True
    )
    assert result.returncode == 0, print(result.stderr.decode("utf-8").strip())
    if debug:
        print(result.stdout.decode("utf-8").strip())


def install(debug=False, clean=False):
    """
    Install and configure all tools to deploy a single-node k8s cluster
    """
    print_dotted_line(f"Installing CNI (v{CNI_VERSION})")
    install_cni(debug=debug, clean=clean)
    print("Success!")

    print_dotted_line(f"Installing crictl (v{CRICTL_VERSION})")
    install_crictl(debug=debug)
    print("Success!")

    print_dotted_line(f"Installing kubectl & friends (v{K8S_VERSION})")
    install_k8s(debug=debug, clean=clean)
    print("Success!")

    # Start kubelet service
    configure_kubelet_service(debug=debug, clean=clean)
