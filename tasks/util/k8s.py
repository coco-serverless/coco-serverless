from jinja2 import Environment, FileSystemLoader
from os.path import basename, dirname
from tasks.util.kubeadm import run_kubectl_command


def template_k8s_file(template_file_path, output_file_path, template_vars):
    # Load and render the template using jinja
    env = Environment(
        loader=FileSystemLoader(dirname(template_file_path)),
        trim_blocks=True,
        lstrip_blocks=True,
        extensions=["jinja2_ansible_filters.AnsibleCoreFiltersExtension"],
        autoescape=True,
    )
    template = env.get_template(basename(template_file_path))
    output_data = template.render(template_vars)

    # Write to output file
    with open(output_file_path, "w") as fh:
        fh.write(output_data)


def get_container_id_from_pod(pod_name, container_name):
    """
    Get the container ID from a pod. The container name must be something in the
    style of 'user-container'
    """
    kubectl_cmd = "kubectl get pod {} -o jsonpath='{{..status.contain".format(pod_name)
    kubectl_cmd += 'erStatuses[?@(.name=="{}")].containerID}}'.format(container_name)
    out = run_kubectl_command(kubectl_cmd, capture_output=True)
    return out.removeprefix("containerd://")
