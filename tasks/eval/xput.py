from datetime import datetime
from glob import glob
from invoke import task
from json import loads as json_loads
from matplotlib.pyplot import subplots
from numpy import array as np_array, mean as np_mean, std as np_std
from os import makedirs
from os.path import basename, exists, join
from pandas import read_csv
from tasks.eval.util.clean import cleanup_after_run
from tasks.eval.util.csv import init_csv_file, write_csv_line
from tasks.eval.util.env_ccv8 import (
    APPS_DIR,
    BASELINES,
    EXPERIMENT_IMAGE_REPO,
    EVAL_TEMPLATED_DIR,
    INTER_RUN_SLEEP_SECS,
    PLOTS_DIR,
    RESULTS_DIR,
)
from tasks.eval.util.setup import setup_baseline
from tasks.util.k8s import template_k8s_file
from tasks.util.kubeadm import get_pod_names_in_ns, run_kubectl_command
from time import sleep, time


def do_run(result_file, baseline, num_run, num_par_inst):
    start_ts = time()

    service_files = [
        "apps_xput_{}_service_{}.yaml".format(baseline, i) for i in range(num_par_inst)
    ]
    for service_file in service_files:
        # Capture output to avoid verbose Knative logging
        run_kubectl_command(
            "apply -f {}".format(join(EVAL_TEMPLATED_DIR, service_file)),
            capture_output=True,
        )

    # Get all pod names
    pods = get_pod_names_in_ns("default")
    while len(pods) != num_par_inst:
        sleep(1)
        pods = get_pod_names_in_ns("default")

    # Once we have all pod names, wait for all of them to be ready. We poll the
    # pods in round-robin fashion, but we report the "Ready" timestamp as
    # logged in Kubernetes, so it doesn't matter that much if we take a while
    # to notice that we are done
    ready_pods = {pod: False for pod in pods}
    pods_ready_ts = {pod: None for pod in pods}
    is_done = all(list(ready_pods.values()))
    while not is_done:

        def is_pod_done(pod_name):
            kube_cmd = "get pod {} -o jsonpath='{{..status.conditions}}'".format(
                pod_name
            )
            conditions = run_kubectl_command(kube_cmd, capture_output=True)
            cond_json = json_loads(conditions)
            return all([cond["status"] == "True" for cond in cond_json])

        def get_pod_ready_ts(pod_name):
            kube_cmd = "get pod {} -o jsonpath='{{..status.conditions}}'".format(
                pod_name
            )
            conditions = run_kubectl_command(kube_cmd, capture_output=True)
            cond_json = json_loads(conditions)
            for cond in cond_json:
                if cond["type"] == "Ready":
                    return (
                        datetime.fromisoformat(
                            cond["lastTransitionTime"][:-1]
                        ).timestamp(),
                    )

        for pod in ready_pods:
            # Skip finished pods
            if ready_pods[pod]:
                continue

            if is_pod_done(pod):
                ready_pods[pod] = True
                pods_ready_ts[pod] = get_pod_ready_ts(pod)

        is_done = all(list(ready_pods.values()))
        sleep(1)

    # Calculate the end timestamp as the maximum (latest) timestamp measured
    end_ts = max(list(pods_ready_ts.values()))[0]
    write_csv_line(result_file, num_run, start_ts, end_ts)

    # Remove the pods when we are done
    for service_file in service_files:
        run_kubectl_command(
            "delete -f {}".format(join(EVAL_TEMPLATED_DIR, service_file)),
            capture_output=True,
        )
    for pod in pods:
        run_kubectl_command("delete pod {}".format(pod), capture_output=True)


@task
def run(ctx, baseline=None, num_par=None):
    """
    Measure the latency-throughput of spawning new Knative service instances
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

    num_parallel_instances = [1, 2, 4, 8, 16]
    if num_par is not None:
        num_parallel_instances = [num_par]

    results_dir = join(RESULTS_DIR, "xput")
    if not exists(results_dir):
        makedirs(results_dir)

    if not exists(EVAL_TEMPLATED_DIR):
        makedirs(EVAL_TEMPLATED_DIR)

    service_template_file = join(APPS_DIR, "xput", "service-ccv8.yaml.j2")
    image_name = "csegarragonz/coco-helloworld-py"
    used_images = ["csegarragonz/coco-knative-sidecar", image_name]
    num_runs = 3

    for bline in baselines_to_run:
        baseline_traits = BASELINES[bline]

        # Template as many service files as parallel instances
        for i in range(max(num_parallel_instances)):
            service_file = join(
                EVAL_TEMPLATED_DIR, "apps_xput_{}_service_{}.yaml".format(bline, i)
            )
            template_vars = {
                "image_repo": EXPERIMENT_IMAGE_REPO,
                "image_name": image_name,
                "image_tag": baseline_traits["image_tag"],
                "service_num": i,
            }
            if len(baseline_traits["runtime_class"]) > 0:
                template_vars["runtime_class"] = baseline_traits["runtime_class"]
            template_k8s_file(service_template_file, service_file, template_vars)

        # Second, run any baseline-specific set-up
        setup_baseline(bline, used_images)

        for num_par in num_parallel_instances:
            # Prepare the result file
            result_file = join(results_dir, "{}_{}.csv".format(bline, num_par))
            init_csv_file(result_file, "Run,StartTimeStampSec,EndTimeStampSec")

            for nr in range(num_runs):
                print(
                    "Executing baseline {} ({} parallel srv) run {}/{}...".format(
                        bline, num_par, nr + 1, num_runs
                    )
                )
                do_run(result_file, bline, nr, num_par)
                sleep(INTER_RUN_SLEEP_SECS)
                cleanup_after_run(bline, used_images)


@task
def plot(ctx):
    """
    Measure the latency-throughput of spawning new Knative service instances
    """
    results_dir = join(RESULTS_DIR, "xput")
    plots_dir = join(PLOTS_DIR, "xput")

    # Collect results
    glob_str = join(results_dir, "*.csv")
    results_dict = {}
    for csv in glob(glob_str):
        baseline = basename(csv).split(".")[0].split("_")[0]
        num_par = basename(csv).split(".")[0].split("_")[1]

        if baseline not in results_dict:
            results_dict[baseline] = {}

        results = read_csv(csv)
        results_dict[baseline][num_par] = {
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
    ax.set_xlabel("# concurrent Knative services")
    ax.set_ylabel("Time [s]")
    ax.set_ylim(bottom=0)
    ax.set_title("Throughput-Latency of Knative Servce Instantiation")
    ax.legend()

    for plot_format in ["pdf", "png"]:
        plot_file = join(plots_dir, "xput.{}".format(plot_format))
        fig.savefig(plot_file, format=plot_format, bbox_inches="tight")
