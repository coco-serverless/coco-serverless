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
from tasks.eval.util.env import (
    APPS_DIR,
    BASELINES,
    EXPERIMENT_IMAGE_REPO,
    EVAL_TEMPLATED_DIR,
    INTER_RUN_SLEEP_SECS,
    PLOTS_DIR,
    RESULTS_DIR,
)
from tasks.eval.util.pod import  get_event_ts_in_pod_logs
from tasks.eval.util.setup import setup_baseline, update_sidecar_deployment
from tasks.util.k8s import template_k8s_file
from tasks.util.kubeadm import get_pod_names_in_ns, run_kubectl_command
from time import sleep, time


def do_run(result_file, baseline, image_name ,num_run, num_par_inst, end_to_end=False, entrypoint_keyword=None):
    start_ts = time()
    service_templated_dir = join(EVAL_TEMPLATED_DIR, image_name)
    service_files = [
        "apps_xput_{}_service_{}.yaml".format(baseline, i) for i in range(num_par_inst)
    ]
    for service_file in service_files:
        # Capture output to avoid verbose Knative logging
        run_kubectl_command(
            "apply -f {}".format(join(service_templated_dir, service_file)),
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
    completed_pods = {pod: False for pod in pods}

    pods_ready_ts = {pod: None for pod in pods}
    pods_completed_ts = {pod: None for pod in pods}

    is_done = all(list(ready_pods.values()))
    while not is_done:

        def is_pod_ready(pod_name):
            # kube_cmd = "get pod {} -o jsonpath='{{..status.conditions}}'".format(
            #     pod_name
            # )
            # conditions = run_kubectl_command(kube_cmd, capture_output=True)
            # cond_json = json_loads(conditions)
            # return all([cond["status"] == "True" for cond in cond_json])

            kube_cmd = "get pod {} -o jsonpath=\"{{.status.containerStatuses[?(@.name=='user-container')]}}\"".format(
                pod_name
            )
            user_container_cond = run_kubectl_command(kube_cmd, capture_output=True)
            cond_json = json_loads(user_container_cond)
            return cond_json["ready"] == True

        def is_pod_completed(pod_name):
            kube_cmd = "get pod {} -o jsonpath='{{..status.conditions}}'".format(
                pod_name
            )
            conditions = run_kubectl_command(kube_cmd, capture_output=True)
            cond_json = json_loads(conditions)
            return any(["reason" in cond and cond["reason"] == "ContainersNotReady" for cond in cond_json])

        def pod_entrypoint_completed(pod_name):
            get_event_ts_in_pod_logs(pod_name, entrypoint_keyword)


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

        def get_pod_completed_ts(pod_name):
            kube_cmd = "get pod {} -o jsonpath='{{..status.conditions}}'".format(
                pod_name
            )
            conditions = run_kubectl_command(kube_cmd, capture_output=True)
            cond_json = json_loads(conditions)
            for cond in cond_json:
                if cond["reason"] == "ContainersNotReady":
                    return (
                        datetime.fromisoformat(
                            cond["lastTransitionTime"][:-1]
                        ).timestamp(),
                    )

        for pod in ready_pods:
            # Skip finished pods
            if ready_pods[pod]:
                if completed_pods[pod] or (not end_to_end):
                    continue
                if is_pod_completed(pod):
                    completed_pods[pod] = True
                    pods_completed_ts[pod] = get_pod_completed_ts(pod)

            if is_pod_ready(pod):
                ready_pods[pod] = True
                pods_ready_ts[pod] = get_pod_ready_ts(pod)

        is_done = all(list(completed_pods.values())) if end_to_end else all(list(ready_pods.values()))
        sleep(1)

    # Calculate the end timestamp as the maximum (latest) timestamp measured

    # if there is an entrypoint command, use its maximum completion as end_ts timestamp
    if entrypoint_keyword is not None:
        end_ts = start_ts
        for pod in ready_pods:
            entrypoint_complete = get_event_ts_in_pod_logs(pod, entrypoint_keyword)
            end_ts = max(end_ts, entrypoint_complete)

    else:
        end_ts = max(list(pods_completed_ts.values()))[0] if end_to_end or (entrypoint_keyword is not None) else max(list(pods_ready_ts.values()))[0]

    write_csv_line(result_file, num_run, start_ts, end_ts)

    # Remove the pods when we are done
    print("removing pods")
    for service_file in service_files:
        run_kubectl_command(
            "delete -f {}".format(join(service_templated_dir, service_file)),
            capture_output=True,
        )
    for pod in pods:
        run_kubectl_command("delete pod {}".format(pod), capture_output=True)

    print("waiting for pods to terminate")
    # Wait for pods to end terminating
    pods = get_pod_names_in_ns("default")
    while len(pods) != 0:
        sleep(10)
        pods = get_pod_names_in_ns("default")

    print("all pods terminated")

@task
def run(ctx, baseline=None, num_par=None):
    """
    Measure the latency-throughput of spawning new Knative service instances
    """
    baselines_to_run = list(BASELINES.keys())
    baselines_to_run = ["coco-nydus-caching"]
    if baseline is not None:
        if baseline not in baselines_to_run:
            print(
                "Unrecognised baseline {}! Must be one in: {}".format(
                    baseline, baselines_to_run
                )
            )
            raise RuntimeError("Unrecognised baseline")
        baselines_to_run = [baseline]

    num_parallel_instances = [12]
    if num_par is not None:
        num_parallel_instances = [num_par]

    results_dir = join(RESULTS_DIR, "xput")
    if not exists(results_dir):
        makedirs(results_dir)

    if not exists(EVAL_TEMPLATED_DIR):
        makedirs(EVAL_TEMPLATED_DIR)

    service_template_file = join(APPS_DIR, "xput", "service.yaml.j2")

    num_runs = 1

    image_repos = [EXPERIMENT_IMAGE_REPO]
    image_names = ["tf-app-tinybert"]

    time_end_to_end = {"node-app": False, "tf-serving": False, "tf-serving-tinybert": False, "tf-app": False, "tf-app-tinybert": False,  "fio-benchmark": False}
    entrypoint_keywords = {"node-app": "node server starting", "tf-serving": "Exporting HTTP/REST", "tf-serving-tinybert": "Exporting HTTP/REST", "tf-app": "flask server starting", "tf-app-tinybert": "flask server starting", "fio-benchmark": "FIO end timestamp"}

    used_images = ["knative/serving/cmd/queue:unencrypted", "knative/serving/cmd/queue:unencrypted-nydus", "fio-benchmark:unencrypted", "fio-benchmark:unencrypted-nydus", "tf-serving:unencrypted", "tf-serving:unencrypted-nydus", "tf-serving-tinybert:blob-cache", "tf-app:unencrypted-nydus", "tf-app:unencrypted","tf-app:blob-cache", "tf-app-tinybert:unencrypted-nydus", "tf-app-tinybert:unencrypted", "tf-app-tinybert:blob-cache"]

    sidecar_image = "knative/serving/cmd/queue"

    for image_repo in image_repos:           
        #replace_sidecar(repo=image_repo, quiet=True)

        for image_name in image_names:

            service_templated_dir = join(EVAL_TEMPLATED_DIR, image_name)
            if not exists(service_templated_dir):
                makedirs(service_templated_dir)

            results_image_dir = join(results_dir, image_name)
            if not exists(results_image_dir):
                makedirs(results_image_dir )

            end_to_end = time_end_to_end[image_name]

            entrypoint_keyword = entrypoint_keywords[image_name]

            for bline in baselines_to_run:
                baseline_traits = BASELINES[bline]

                # update the sidecar image deployment file
                sidecar_image_tag = "unencrypted-nydus" if "nydus" in bline else "unencrypted"
                update_sidecar_deployment(image_repo, sidecar_image, sidecar_image_tag)

                # Template as many service files as parallel instances
                for i in range(max(num_parallel_instances)):
                    service_file = join(
                        service_templated_dir, "apps_xput_{}_service_{}.yaml".format(bline, i)
                    )
                    template_vars = {
                        "image_repo": image_repo,
                        "image_name": image_name,
                        "image_tag": baseline_traits["image_tag"],
                        "service_num": i,
                    }
                    if len(baseline_traits["runtime_class"]) > 0:
                        template_vars["runtime_class"] = baseline_traits["runtime_class"]
                    template_k8s_file(service_template_file, service_file, template_vars)

                # Second, run any baseline-specific set-up
                # setup_baseline(bline, used_images)

                for num_par in num_parallel_instances:
                    # Prepare the result file
                    result_file = join(results_image_dir, "{}_{}.csv".format(bline, num_par))
                    init_csv_file(result_file, "Run,StartTimeStampSec,EndTimeStampSec")

                    for nr in range(num_runs):
                        print(
                            "Executing baseline {} ({} parallel srv) run {}/{}...".format(
                                bline, num_par, nr + 1, num_runs
                            )
                        )
                        do_run(result_file, bline, image_name, nr, num_par, end_to_end, entrypoint_keyword)
                        sleep(INTER_RUN_SLEEP_SECS)
                        print("starting cleanup")
                        cleanup_after_run(bline, used_images)
                        print("finished cleanup")
                        sleep(10)

@task
def plot(ctx):
    """
    Measure the latency-throughput of spawning new Knative service instances
    """

    image_name = "tf-app-tinybert"

    results_dir = join(RESULTS_DIR, "xput", image_name)

    plots_dir = join(PLOTS_DIR, "xput", image_name)
    if not exists(plots_dir):
        makedirs(plots_dir)

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
    baselines = ["coco", "coco-nydus", "coco-caching", "coco-nydus-caching"]#list(BASELINES.keys())
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
