from datetime import datetime
from glob import glob
from invoke import task
from json import loads as json_loads
from matplotlib.pyplot import subplots
from os import makedirs
from os.path import basename, exists, join
from pandas import read_csv
from subprocess import run as sp_run
from tasks.eval.util.env import (
    APPS_DIR,
    BASELINES,
    EVAL_TEMPLATED_DIR,
    IMAGE_TO_ID,
    RESULTS_DIR,
    PLOTS_DIR,
)
from tasks.util.coco import guest_attestation, signature_verification
from tasks.util.k8s import template_k8s_file
from tasks.util.kbs import clear_kbs_db, provision_launch_digest
from tasks.util.kubeadm import get_pod_names_in_ns, run_kubectl_command
from time import sleep, time

# We are running into image pull rate issues, so we want to support changing
# this easily. Note that the image, signatures, and encrypted layers _already_
# live in any container registry before we run the experiment
EXPERIMENT_IMAGE_REPO = "ghcr.io"

BASELINE_FLAVOURS = ["warm", "cold"]


def init_csv_file(file_name, header):
    with open(file_name, "w") as fh:
        fh.write("{}\n".format(header))


def write_csv_line(file_name, *args):
    layout = ",".join(["{}" for _ in range(len(args))]) + "\n"
    with open(file_name, "a") as fh:
        fh.write(layout.format(*args))


def setup_baseline(baseline, used_images):
    """
    Configure the system for a specific baseline

    This set-up is meant to run once per baseline (so not per run) and it
    configures things like turning guest attestation on/off or signature
    verification on/off and also populating the KBS.
    """
    if baseline in ["docker", "kata"]:
        return

    baseline_traits = BASELINES[baseline]

    # Turn guest pre-attestation on/off (connect KBS to PSP)
    guest_attestation(baseline_traits["guest_attestation"])

    # Turn signature verification on/off (validate HW digest)
    signature_verification(baseline_traits["signature_verification"])

    # Manually clean the KBS but skip clearing the secrets used to decrypt
    # images. Those can remain there
    clear_kbs_db(skip_secrets=True)

    # Configure signature policy (check image signature or not). We must do
    # this at the very end as it relies on: (i) the KBS DB being clear, and
    # (ii) the configuration file populated by the previous methods
    images_to_sign = [join(EXPERIMENT_IMAGE_REPO, image) for image in used_images]
    provision_launch_digest(
        images_to_sign,
        signature_policy=baseline_traits["signature_policy"],
        clean=False,
    )


def clean_container_images(used_ctr_images):
    ids_to_remove = [IMAGE_TO_ID["csegarragonz/coco-knative-sidecar"]]
    for ctr in used_ctr_images:
        ids_to_remove.append(IMAGE_TO_ID[ctr])
    crictl_cmd = "sudo crictl rmi {}".format(" ".join(ids_to_remove))
    out = sp_run(crictl_cmd, shell=True, capture_output=True)
    assert out.returncode == 0


def cleanup_after_run(baseline, used_ctr_images):
    """
    This method is called after each experiment run
    """
    if baseline in ["docker", "kata"]:
        clean_container_images(used_ctr_images)


def do_run(result_file, num_run, service_file, warmup=False):
    start_ts = time()

    # Silently start
    run_kubectl_command("apply -f {}".format(service_file), capture_output=True)

    # Wait for pod to start
    pods = get_pod_names_in_ns("default")
    while len(pods) < 1:
        sleep(1)
        pods = get_pod_names_in_ns("default")
    assert len(pods) == 1
    pod_name = pods[0]

    # Get events
    while True:
        kube_cmd = "get pod {} -o jsonpath='{{..status.conditions}}'".format(pod_name)
        events_ts = [("Start", start_ts)]
        conditions = run_kubectl_command(kube_cmd, capture_output=True)
        cond_json = json_loads(conditions)

        is_done = all([cond["status"] == "True" for cond in cond_json])
        if is_done:
            for cond in cond_json:
                events_ts.append(
                    (
                        cond["type"],
                        datetime.fromisoformat(
                            cond["lastTransitionTime"][:-1]
                        ).timestamp(),
                    )
                )
            break

        sleep(2)

    if not warmup:
        events_ts = sorted(events_ts, key=lambda x: x[1])
        for event in events_ts:
            write_csv_line(result_file, num_run, event[0], event[1])

    # Wait for pod to finish
    run_kubectl_command("delete -f {}".format(service_file), capture_output=True)
    run_kubectl_command("delete pod {}".format(pod_name), capture_output=True)


@task
def run(ctx, baseline=None):
    """
    Calculate the end-to-end time to spin-up a pod

    This benchmark compares the time required to spin-up a pod (i.e. time for
    the pod to be in `Running` state) as reported by Kubernetes.
    """
    baselines_to_run = list(BASELINES.keys())
    if baseline is not None:
        if baseline not in baselines_to_run:
            print(
                "Unrecognised baseline {}! Must be one in: {}".format(
                    baseline, baselines_to_run
                )
            )
            raise RuntimeError("Unrecognised baseline")
        baselines_to_run = [baseline]

    service_template_file = join(APPS_DIR, "startup", "service.yaml.j2")
    image_name = "csegarragonz/coco-helloworld-py"
    used_images = ["csegarragonz/coco-knative-sidecar", image_name]
    num_runs = 3

    results_dir = join(RESULTS_DIR, "startup")
    if not exists(results_dir):
        makedirs(results_dir)

    if not exists(EVAL_TEMPLATED_DIR):
        makedirs(EVAL_TEMPLATED_DIR)

    for bline in baselines_to_run:
        baseline_traits = BASELINES[bline]

        # First, template the service file
        service_file = join(
            EVAL_TEMPLATED_DIR, "apps_startup_{}_service.yaml".format(bline)
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

        for flavour in BASELINE_FLAVOURS:
            # Prepare the result file
            result_file = join(results_dir, "{}_{}.csv".format(bline, flavour))
            init_csv_file(result_file, "Run,Event,TimeStampMs")

            if flavour == "warm":
                print("Executing baseline {} warmup run...".format(bline))
                do_run(result_file, -1, service_file, warmup=True)

            for nr in range(num_runs):
                print(
                    "Executing baseline {} ({}) run {}/{}...".format(
                        bline, flavour, nr + 1, num_runs
                    )
                )
                do_run(result_file, nr, service_file)

                if flavour == "cold":
                    cleanup_after_run(bline, used_images)


@task
def plot(ctx):
    results_dir = join(RESULTS_DIR, "startup")
    plots_dir = join(PLOTS_DIR, "startup")

    glob_str = join(results_dir, "*.csv")
    results_dict = {}
    for csv in glob(glob_str):
        baseline = basename(csv).split(".")[0].split("_")[0]
        flavour = basename(csv).split(".")[0].split("_")[1]
        if baseline == "kata":
            # TODO: kata baseline does not work
            continue

        if baseline not in results_dict:
            results_dict[baseline] = {}

        results_dict[baseline][flavour] = {}
        results = read_csv(csv)
        groupped = results.groupby("Event", as_index=False)
        events = groupped.mean()["Event"].to_list()
        for ind, event in enumerate(events):
            # TODO: these timestamps are in seconds
            results_dict[baseline][flavour][event] = {
                "mean": groupped.mean()["TimeStampMs"].to_list()[ind],
                "sem": groupped.sem()["TimeStampMs"].to_list()[ind],
            }

    fig, ax = subplots()
    xlabels = list(BASELINES.keys())
    xs = range(len(xlabels))
    num_flavours = len(BASELINE_FLAVOURS)
    space_between_baselines = 0.2
    if num_flavours % 2 == 0:
        bar_width = (1 - space_between_baselines) / num_flavours
    else:
        bar_width = (1 - space_between_baselines) / (num_flavours + 1)

    for ind, flavour in enumerate(BASELINE_FLAVOURS):
        if num_flavours % 2 == 0:
            x_offset = bar_width * (ind + 1 / 2 - num_flavours / 2)
        else:
            x_offset = bar_width * (ind - num_flavours / 2)

        this_xs = [x + x_offset for x in xs]
        print("bar width:", bar_width)
        print("x offset:", x_offset)
        print("xs:", this_xs)
        ys = []
        for b in xlabels:
            ys.append(
                results_dict[b][flavour]["Ready"]["mean"]
                - results_dict[b][flavour]["Start"]["mean"]
            )
        ax.bar(this_xs, ys, label=flavour, width=bar_width)

    # Misc
    ax.set_xticks(xs, xlabels)
    ax.set_xlabel("Baseline")
    ax.set_ylabel("Time [s]")
    ax.set_title("End-to-end latency to start a pod")
    ax.legend()

    for plot_format in ["pdf", "png"]:
        plot_file = join(plots_dir, "startup.{}".format(plot_format))
        fig.savefig(plot_file, format=plot_format, bbox_inches="tight")
