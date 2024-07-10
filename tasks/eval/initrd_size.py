from glob import glob
from invoke import task
from matplotlib.pyplot import subplots
from numpy import array as np_array, mean as np_mean, std as np_std
from os import makedirs
from os.path import basename, exists, getsize, join
from pandas import read_csv
from subprocess import run as sp_run
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
    GITHUB_USER,
)
from tasks.eval.util.pod import wait_for_pod_ready_and_get_ts
from tasks.eval.util.setup import cleanup_baseline, setup_baseline
from tasks.util.coco import set_initrd
from tasks.util.env import KATA_CONFIG_DIR, KATA_IMG_DIR
from tasks.util.k8s import template_k8s_file
from tasks.util.kata import replace_agent
from tasks.util.kubeadm import get_pod_names_in_ns, run_kubectl_command
from tasks.util.toml import read_value_from_toml
from time import sleep, time


def get_initrd_size_mb(initrd_path):
    initrd_size = int(getsize(initrd_path) / 1024 / 1024)
    assert initrd_size > 0
    return initrd_size


def get_default_initrd_size_mb():
    conf_file = join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml")
    initrd_path = read_value_from_toml(conf_file, "hypervisor.qemu.initrd")
    return get_initrd_size_mb(initrd_path)


def get_initrd_path(size_mult):
    initrd_dir = "/tmp/coco-serverless-initrds"
    if not exists(initrd_dir):
        makedirs(initrd_dir)

    base_name = "kata-initrd-csg-{}-mult.initrd"
    initrd_path = join(initrd_dir, base_name.format(size_mult))
    return initrd_path


def create_bloat_file(file_path, file_size_mb):
    cmd = "head -c {}MB </dev/urandom > {}".format(file_size_mb, file_path)
    sp_run(cmd, shell=True, check=True)


def inflate_initrd(dst_initrd_path, initial_size_mb, size_mult):
    print("Inflating initird ({} * {})...".format(initial_size_mb, size_mult))
    if size_mult == 0:
        sp_run(
            "sudo cp {} {}".format(
                join(KATA_IMG_DIR, "kata-containers-initrd-sev-csg.img"),
                dst_initrd_path,
            ),
            shell=True,
            check=True,
        )
        return

    target_size_mb = initial_size_mb * size_mult
    host_path = "/tmp/bloat_file"
    guest_path = host_path
    create_bloat_file(host_path, target_size_mb)
    replace_agent(
        dst_initrd_path=dst_initrd_path,
        extra_files={host_path: {"path": guest_path, "mode": "w"}},
    )
    print("Done inflating!")


def do_run(result_file, baseline, num_run, num_par_inst):
    start_ts = time()

    service_file = join(
        EVAL_TEMPLATED_DIR, "apps_initrd-size_{}_service.yaml".format(baseline)
    )
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
def run(ctx, baseline=None, initrd_size_mult=None):
    """
    Measure the impact of the initrd size in the startup time
    """
    baselines_to_run = ["coco-nosev", "coco-fw-sig-enc"]
    if baseline is not None:
        if baseline not in baselines_to_run:
            print(
                "Unrecognised baseline {}! Must be one in: {}".format(
                    baseline, baselines_to_run
                )
            )
            raise RuntimeError("Unrecognised baseline")
        baselines_to_run = [baseline]

    initrd_size_multiplier = [0, 1, 2, 3, 4, 5, 6, 7, 8]
    if initrd_size_mult is not None:
        initrd_size_multiplier = [int(initrd_size_mult)]

    results_dir = join(RESULTS_DIR, "initrd-size")
    if not exists(results_dir):
        makedirs(results_dir)

    if not exists(EVAL_TEMPLATED_DIR):
        makedirs(EVAL_TEMPLATED_DIR)

    service_template_file = join(APPS_DIR, "initrd-size", "service.yaml.j2")
    image_name = f"{GITHUB_USER}/coco-helloworld-py"
    used_images = [f"{GITHUB_USER}/coco-knative-sidecar", image_name]
    num_runs = 1

    # Get the default memory size (we always read it from the SEV initrd)
    conf_file = join(KATA_CONFIG_DIR, "configuration-qemu-sev.toml")
    initrd_path = read_value_from_toml(conf_file, "hypervisor.qemu.initrd")
    orig_initrd_size_mb = get_initrd_size_mb(initrd_path)

    # Pre-gerenate all the `initrd`s if they do not exist
    for initrd_size_mult in initrd_size_multiplier:
        initrd_path = get_initrd_path(initrd_size_mult)
        if not exists(initrd_path):
            inflate_initrd(initrd_path, orig_initrd_size_mb, initrd_size_mult)

    for bline in baselines_to_run:
        for initrd_size_mult in initrd_size_multiplier:
            baseline_traits = BASELINES[bline]

            # Template the service file
            service_file = join(
                EVAL_TEMPLATED_DIR, "apps_initrd-size_{}_service.yaml".format(bline)
            )
            template_vars = {
                "image_repo": EXPERIMENT_IMAGE_REPO,
                "image_name": image_name,
                "image_tag": baseline_traits["image_tag"],
            }
            if len(baseline_traits["runtime_class"]) > 0:
                template_vars["runtime_class"] = baseline_traits["runtime_class"]
            template_k8s_file(service_template_file, service_file, template_vars)

            # First, update the config file to point to the new initrd so that
            orig_initrd_path = read_value_from_toml(
                baseline_traits["conf_file"],
                "hypervisor.qemu.initrd",
            )
            set_initrd(baseline_traits["conf_file"], get_initrd_path(initrd_size_mult))

            # Second, run any baseline-specific set-up
            setup_baseline(bline, used_images)

            # Prepare the result file
            result_file = join(results_dir, "{}_{}.csv".format(bline, initrd_size_mult))
            init_csv_file(result_file, "Run,StartTimeStampSec,EndTimeStampSec")

            for nr in range(num_runs):
                print(
                    "Executing baseline {} ({} * {} MB initrd) run {}/{}...".format(
                        bline, initrd_size_mult, orig_initrd_size_mb, nr + 1, num_runs
                    )
                )
                do_run(result_file, bline, nr, initrd_size_mult)
                sleep(INTER_RUN_SLEEP_SECS)
                cleanup_after_run(bline, used_images)

        # Cleanup after baseline
        cleanup_baseline(bline)

        # Reset the initrd to the original one
        set_initrd(
            baseline_traits["conf_file"],
            orig_initrd_path,
        )


@task
def plot(ctx):
    """
    Measure the impact of the VM memory size in the startup time
    """
    results_dir = join(RESULTS_DIR, "initrd-size")
    plots_dir = join(PLOTS_DIR, "initrd-size")

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

    # Plot start-up latency as we increase the `initrd` size
    fig, ax = subplots()
    baselines = list(results_dict.keys())
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
    xlabels = ["{}".format(x + 1) for x in xs]
    ax.set_xticks(xs, xlabels)
    ax.set_xlabel(
        "Multiples of default initrd size ({} MB)".format(get_default_initrd_size_mb())
    )
    ax.set_ylabel("Time [s]")
    ax.set_ylim(bottom=0)
    ax.set_title("Impact of initrd size on start-up time")
    ax.legend()

    for plot_format in ["pdf", "png"]:
        plot_file = join(plots_dir, "initrd_size.{}".format(plot_format))
        fig.savefig(plot_file, format=plot_format, bbox_inches="tight")
