from glob import glob
from invoke import task
from matplotlib.pyplot import subplots
from numpy import array as np_array, mean as np_mean, std as np_std
from os import makedirs
from os.path import basename, exists, join
from pandas import read_csv
from tasks.eval.util.clean import cleanup_after_run
from tasks.eval.util.csv import init_csv_file, write_csv_line
from tasks.eval.util.env import (
    APPS_DIR,
    BASELINES,
    EXPERIMENT_IMAGE_REPO,
    EVAL_TEMPLATED_DIR,
    INTER_RUN_SLEEP_SECS,
    PLOTS_DIR,
    RESULTS_DIR,
)
from tasks.eval.util.pod import wait_for_pod_ready_and_get_ts
from tasks.eval.util.setup import setup_baseline
from tasks.util.env import KATA_CONFIG_DIR
from tasks.util.k8s import template_k8s_file
from tasks.util.kubeadm import get_pod_names_in_ns, run_kubectl_command
from tasks.util.toml import read_value_from_toml, update_toml
from time import sleep, time


def get_default_vm_mem_size():
    """
    Get the default memory assigned to each new VM from the Kata config file.
    This value is expressed in MB. We also take by default, accross baselines,
    the value used for the qemu-sev runtime class.
    """
    toml_path = join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml")
    mem = int(read_value_from_toml(toml_path, "hypervisor.qemu.default_memory"))
    assert mem > 0, "Read non-positive default memory size: {}".format(mem)
    return mem


def update_vm_mem_size(baseline, new_mem_size):
    """
    Update the default VM memory size in the Kata config file
    """
    if baseline == "kata":
        toml_path = join(KATA_CONFIG_DIR, "configuration-qemu.toml")
    else:
        toml_path = join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml")

    updated_toml_str = """
    [hypervisor.qemu]
    default_memory = {mem_size}
    """.format(
        mem_size=new_mem_size
    )
    update_toml(toml_path, updated_toml_str)


def do_run(result_file, baseline, num_run, num_par_inst):
    start_ts = time()

    service_file = join(EVAL_TEMPLATED_DIR, "apps_mem-size_{}_service.yaml".format(baseline))
    # Capture output to avoid verbose Knative logging
    run_kubectl_command("apply -f {}".format(service_file), capture_output=True)

    # Get all pod names
    pods = get_pod_names_in_ns("default")
    while len(pods) != 1:
        sleep(1)
        pods = get_pod_names_in_ns("default")
    pod_name = pods[0]

    # Wait for the pod to be ready, and get ready timestamp
    end_ts = wait_for_pod_ready_and_get_ts(pod_name)

    # Write result to file
    write_csv_line(result_file, num_run, start_ts, end_ts)

    # Remove the pod when we are done
    run_kubectl_command("delete -f {}".format(service_file), capture_output=True)
    run_kubectl_command("delete pod {}".format(pod_name), capture_output=True)


@task
def run(ctx, baseline=None, mem_size_mult=None):
    """
    Measure the impact of the VM memory size in the startup time
    """
    baselines_to_run = list(BASELINES.keys())
    # This experiment is only relevant for VMs, so we don't run the 'docker'
    # baseline
    baselines_to_run.remove("docker")
    if baseline is not None:
        if baseline not in baselines_to_run:
            print(
                "Unrecognised baseline {}! Must be one in: {}".format(
                    baseline, baselines_to_run
                )
            )
            raise RuntimeError("Unrecognised baseline")
        baselines_to_run = [baseline]

    mem_size_multiplier = [1, 2, 4, 8, 16]
    if mem_size_mult is not None:
        mem_size_multiplier = [mem_size_mult]

    results_dir = join(RESULTS_DIR, "mem-size")
    if not exists(results_dir):
        makedirs(results_dir)

    if not exists(EVAL_TEMPLATED_DIR):
        makedirs(EVAL_TEMPLATED_DIR)

    service_template_file = join(APPS_DIR, "mem-size", "service.yaml.j2")
    image_name = "csegarragonz/coco-helloworld-py"
    used_images = ["csegarragonz/coco-knative-sidecar", image_name]
    num_runs = 1

    # Get the default memory size
    default_vm_mem_size = get_default_vm_mem_size()

    for bline in baselines_to_run:
        baseline_traits = BASELINES[bline]

        # Template the service file
        service_file = join(
            EVAL_TEMPLATED_DIR, "apps_mem-size_{}_service.yaml".format(bline)
        )
        template_vars = {
            "image_repo": EXPERIMENT_IMAGE_REPO,
            "image_name": image_name,
            "image_tag": baseline_traits["image_tag"],
        }
        if len(baseline_traits["runtime_class"]) > 0:
            template_vars["runtime_class"] = baseline_traits["runtime_class"]
        template_k8s_file(service_template_file, service_file, template_vars)

        # Second, run any baseline-specific set-up
        setup_baseline(bline, used_images)

        for mem_size_mult in mem_size_multiplier:
            # Prepare the result file
            result_file = join(results_dir, "{}_{}.csv".format(bline, mem_size_mult))
            init_csv_file(result_file, "Run,StartTimeStampSec,EndTimeStampSec")

            # Update the configuration file to start VMs with more memory
            update_vm_mem_size(bline, mem_size_mult * default_vm_mem_size)

            for nr in range(num_runs):
                print(
                    "Executing baseline {} ({} * {} mem) run {}/{}...".format(
                        bline, mem_size_mult, default_vm_mem_size, nr + 1, num_runs
                    )
                )
                do_run(result_file, bline, nr, mem_size_mult)
                sleep(INTER_RUN_SLEEP_SECS)
                cleanup_after_run(bline, used_images)

        # Reset the VM memory size to the default value (different baselines
        # may use different Kata config files)
        update_vm_mem_size(bline, default_vm_mem_size)


@task
def plot(ctx):
    """
    Measure the impact of the VM memory size in the startup time
    """
    results_dir = join(RESULTS_DIR, "mem-size")
    plots_dir = join(PLOTS_DIR, "mem-size")

    # Collect results
    glob_str = join(results_dir, "*.csv")
    results_dict = {}
    for csv in glob(glob_str):
        baseline = basename(csv).split(".")[0].split("_")[0]
        mem_mult = basename(csv).split(".")[0].split("_")[1]

        if baseline not in results_dict:
            results_dict[baseline] = {}

        results = read_csv(csv)
        results_dict[baseline][mem_mult] = {
            "mean": np_mean(
                np_array(results["EndTimeStampSec"].to_list())
                - np_array(results["StartTimeStampSec"].to_list())
            ),
            "sem": np_std(
                np_array(results["EndTimeStampSec"].to_list())
                - np_array(results["StartTimeStampSec"].to_list())
            ),
        }

    # Plot throughput-latency
    fig, ax = subplots()
    baselines = list(BASELINES.keys())
    baselines.remove("docker")
    for bline in baselines:
        xs = sorted([int(k) for k in results_dict[bline].keys()])
        ys = [results_dict[bline][str(x)]["mean"] for x in xs]
        ys_err = [results_dict[bline][str(x)]["sem"] for x in xs]
        ax.errorbar(
            xs,
            ys,
            yerr=ys_err,
            fmt="o-",
            label=bline,
        )

    # Misc
    xlabels = ["{} * {}".format(x, get_default_vm_mem_size()) for x in xs]
    ax.set_xticks(xs, xlabels, rotation=30)
    ax.set_xlabel("Initial VM memory size")
    ax.set_ylabel("Time [s]")
    ax.set_ylim(bottom=0)
    ax.set_title("Impact of initial VM memory size on start-up time")
    ax.legend()

    for plot_format in ["pdf", "png"]:
        plot_file = join(plots_dir, "mem_size.{}".format(plot_format))
        fig.savefig(plot_file, format=plot_format, bbox_inches="tight")
