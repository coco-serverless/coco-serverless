from datetime import datetime
from collections import defaultdict
from invoke import task
from json import loads as json_loads
from matplotlib.patches import Patch
from matplotlib.pyplot import subplots
from os import makedirs
from os.path import exists, join
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
from tasks.util.containerd import get_ts_for_containerd_event
from tasks.util.env import CONF_FILES_DIR, EXTERNAL_REGISTRY_URL, LOCAL_REGISTRY_URL, TEMPLATED_FILES_DIR
from tasks.util.k8s import template_k8s_file
from tasks.util.knative import replace_sidecar
from tasks.util.kubeadm import get_pod_names_in_ns, run_kubectl_command
from time import sleep

CSG_MAGIC_BEGIN = "CSG-M4GIC: B3G1N: {}"
CSG_MAGIC_END = "CSG-M4GIC: END: {}"


def do_run(result_file, baseline, image_name, num_run, num_par_inst, end_to_end=False, entrypoint_keyword=None):
    service_templated_dir = join(EVAL_TEMPLATED_DIR, image_name)
    service_files = [
        "apps_xput-detail_{}_service_{}.yaml".format(baseline, i)
        for i in range(num_par_inst)
    ]
    for service_file in service_files:
        # Capture output to avoid verbose Knative logging
        sleep(0.1)
        run_kubectl_command(
            "apply -f {}".format(join(service_templated_dir, service_file)),
            capture_output=True,
        )
    # Get all pod names
    pods = get_pod_names_in_ns("default")
    print("waiting to get pods")
    while len(pods) != num_par_inst:
        sleep(1)
        pods = get_pod_names_in_ns("default")

    print("all pods here")
    # Once we have all pod names, wait for all of them to be ready. We poll the
    # pods in round-robin fashion, but we report the "Ready" timestamp as
    # logged in Kubernetes, so it doesn't matter that much if we take a while
    # to notice that we are done
    ready_pods = {pod: False for pod in pods}
    pods_ready_ts = {pod: None for pod in pods}
    pods_completed_ts = {pod: None for pod in pods}
    completed_pods = {pod: False for pod in pods}
    is_done = all(list(completed_pods.values()))

    events_ts_per_pod = defaultdict(lambda: [])

    while not is_done:
        def is_pod_ready(pod_name):
            # kube_cmd = "get pod {} -o jsonpath='{{..status.conditions}}'".format(
            #      pod_name
            #  )
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


        # Once all pods are ready, query for the relevant events for each pod
        def get_events_for_pod(pod_id, pod_name):
            events_ts = []

            kube_cmd = "get pod {} -o jsonpath='{{..status.conditions}}'".format(
                pod_name
            )
            
            conditions = run_kubectl_command(kube_cmd, capture_output=True)
            cond_json = json_loads(conditions)

            # assert all(
            #     [cond["status"] == "True" for cond in cond_json]
            # ), "Pod {} is not ready".format(pod_name)

            for cond in cond_json:
                events_ts.append(
                    (
                        cond["type"],
                        datetime.fromisoformat(
                            cond["lastTransitionTime"][:-1]
                        ).timestamp(),
                    )
                )

            # Temporary solution to get "ContainerReady" for 
            # user-container only

            kube_cmd = "get pod {} -o jsonpath=\"{{.status.containerStatuses[?(@.name=='user-container')]}}\"".format(
                pod_name
            )
            user_container_cond = run_kubectl_command(kube_cmd, capture_output=True)
            cond_json = json_loads(user_container_cond)

            for i, (event, ts) in enumerate(events_ts):
                if event == "ContainersReady":
                    ts = datetime.fromisoformat(cond_json["state"]["running"]["startedAt"].replace("Z", "").replace("T", " ")).timestamp()
                    events_ts[i] = (event, ts)
                    break

            # Also get one event from containerd that indicates that the
            # sandbox is ready
            vm_ready_ts = get_ts_for_containerd_event(
                "RunPodSandbox",
                pod_name,
                timeout_mins=None,
                extra_event_id="returns sandbox id"
            )
            events_ts.append(("SandboxReady", vm_ready_ts))

            return events_ts


        for pod_id, pod_name in enumerate(pods):
            # Skip finished pods
            if ready_pods[pod_name]:

                if completed_pods[pod_name] or (not end_to_end):
                    continue
                if is_pod_completed(pod_name):
                    completed_pods[pod_name] = True
                    pods_completed_ts[pod_name] = get_pod_completed_ts(pod_name)

            if is_pod_ready(pod_name):
                ready_pods[pod_name] = True
                pods_ready_ts[pod_name] = get_pod_ready_ts(pod_name)

                # As soon as one pod is ready, we process the events from it
                # to avoid containerd trimming the logs
                print("Getting events for pod {}".format(pod_name))
                events_ts_per_pod[pod_id] = get_events_for_pod(pod_id, pod_name)

        is_done = all(list(completed_pods.values())) if end_to_end else all(list(ready_pods.values()))
        sleep(1)


    # Measure entrypoint duration and write events to csv file
    for pod_id, pod_name in enumerate(pods):
        events_ts = events_ts_per_pod[pod_id]

        events_ts = sorted(events_ts, key=lambda x: x[1])

        end_ts_sc_srv =  events_ts[-1][1]
        if entrypoint_keyword is not None:
            entrypoint_complete = get_event_ts_in_pod_logs(pod_name, entrypoint_keyword)
            events_ts.append(("StartEntrypoint", end_ts_sc_srv))
            events_ts.append(("EndEntrypoint", entrypoint_complete))
        else:
            events_ts.append(("StartEntrypoint", end_ts_sc_srv))
            events_ts.append(("EndEntrypoint", end_ts_sc_srv))

        # Sort the events by timestamp and write them to a file
        events_ts = sorted(events_ts, key=lambda x: x[1])
        for event in events_ts:
            write_csv_line(result_file, pod_id, event[0], event[1])


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
        sleep(20)
        num_pods = get_pod_names_in_ns("default")

    print("all pods terminated")


@task
def run(ctx, repo=None):
    """
    Measure the costs associated with starting a fixed number of concurrent
    services
    """
    baselines_to_run = ["coco-nydus-caching"]#, "coco-nydus", "coco-nydus-caching"]
    sidecar_image = "gcr.io/knative-releases/knative.dev/serving/cmd/queue@sha256:987f53e3ead58627e3022c8ccbb199ed71b965f10c59485bab8015ecf18b44af"
    num_parallel_instances = [1, 2, 4, 8, 12]
    num_runs = 1

    if repo is not None:
        if repo in image_repos:
            image_repos = [repo]
        else:
            raise RuntimeError("Unrecognised image repository: {}".format(repo))

    results_dir = join(RESULTS_DIR, "xput-detail")
    if not exists(results_dir):
        makedirs(results_dir)

    if not exists(EVAL_TEMPLATED_DIR):
        makedirs(EVAL_TEMPLATED_DIR)

    service_template_file = join(APPS_DIR, "xput-detail", "service.yaml.j2")

    image_repos = [EXPERIMENT_IMAGE_REPO]
    image_names = ["tf-app-tinybert"]

    time_end_to_end = {"node-app": False, "tf-serving": False, "tf-serving-tinybert": False, "tf-app": False, "tf-app-tinybert": False, "tf-app-tinibert": False, "fio-benchmark": True}
    entrypoint_keywords = {"node-app": "node server starting", "tf-serving": "Exporting HTTP/REST", "tf-serving-tinybert": "Exporting HTTP/REST", "tf-app": "flask server starting", "tf-app-tinybert": "flask server starting", "tf-app-tinibert": "flask server starting", "fio-benchmark": None}

    used_images = ["knative/serving/cmd/queue:unencrypted", "knative/serving/cmd/queue:unencrypted-nydus", "fio-benchmark:unencrypted", "fio-benchmark:unencrypted-nydus", "tf-serving:unencrypted", "tf-serving:unencrypted-nydus", "tf-serving-tinybert:blob-cache", "tf-app:unencrypted-nydus", "tf-app:unencrypted","tf-app:blob-cache", "tf-app-tinybert:unencrypted-nydus", "tf-app-tinybert:unencrypted", "tf-app-tinybert:blob-cache",  "tf-app-tinibert:unencrypted-nydus", "tf-app-tinibert:unencrypted", "tf-app-tinibert:blob-cache"]

    sidecar_image = "knative/serving/cmd/queue"

    for image_repo in image_repos:           
        #replace_sidecar(repo=image_repo, quiet=True)

        for image_name in image_names:

            service_templated_dir = join(EVAL_TEMPLATED_DIR, image_name)
            if not exists(service_templated_dir):
                makedirs(service_templated_dir)

            results_image_dir = join(results_dir, image_name)
            if not exists(results_image_dir):
                makedirs(results_image_dir)

            end_to_end = time_end_to_end[image_name]

            entrypoint_keyword = entrypoint_keywords[image_name]

            for bline in baselines_to_run:
                baseline_traits = BASELINES[bline]

                # update the sidecar image deployment file
                sidecar_image_tag = "unencrypted-nydus" if "nydus" in bline else "unencrypted"
                sidecar_image_repo = "external-registry.coco-csg.com"
                update_sidecar_deployment(sidecar_image_repo, sidecar_image, sidecar_image_tag)

                # Template as many service files as parallel instances
                for i in range(max(num_parallel_instances)):

                    service_file = join(
                        service_templated_dir,
                        "apps_xput-detail_{}_service_{}.yaml".format(
                            #image_repo, bline, i
                            bline, i
                        ),
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
                # setup_baseline(bline, used_images, image_repo)

                for num_par in num_parallel_instances:
                    # Prepare the result file
                    result_file = join(
                        #results_dir, "{}_{}_{}.csv".format(image_repo, bline, num_par)
                        results_image_dir, "{}_{}.csv".format(bline, num_par)
                    )
                    init_csv_file(result_file, "ServiceId,Event,TimeStampSecs")

                    for nr in range(num_runs):
                        print(
                            "Executing baseline {} ({} par srv, {}) run {}/{}...".format(
                                bline, num_par, image_repo, nr + 1, num_runs
                            )
                        )
                        do_run(result_file, bline, image_name, nr, num_par, end_to_end, entrypoint_keyword)
                        sleep(INTER_RUN_SLEEP_SECS)
                        print("starting cleanup")
                        #cleanup_after_run(bline, used_images)
                        print("finished cleanup")
                        sleep(10)


@task
def plot(ctx):
    """
    Plot the costs associated with starting a fixed number of concurrent
    services
    """

    baselines = ["coco", "coco-nydus", "coco-nydus-caching"]
    num_par_instances = 12
    image_repos = [EXPERIMENT_IMAGE_REPO, EXTERNAL_REGISTRY_URL]
    image_name = "tf-app-tinybert"

    results_dir = join(RESULTS_DIR, "xput-detail", image_name)

    plots_dir = join(PLOTS_DIR, "xput-detail", image_name)
    if not exists(plots_dir):
        makedirs(plots_dir)

    #results_file = join(results_dir, "{}_{}.csv".format(baseline, num_par_instances))

    # Collect results
    results_dict = {}
    for bline in baselines:
        results_file = join(
            results_dir, "{}_{}.csv".format(bline, num_par_instances)
        )
        results_dict[bline] = {}
        results = read_csv(results_file)
        service_ids = set(results["ServiceId"].to_list())
        for service_id in service_ids:
            results_dict[bline][service_id] = {}
            service_results = results[results.ServiceId == service_id]
            groupped = service_results.groupby("Event", as_index=False)
            events = list(groupped.groups.keys())
            for event in events:
                results_dict[bline][service_id][event] = {
                    "mean": service_results[service_results.Event == event][
                        "TimeStampSecs"
                    ].mean(),
                    "sem": service_results[service_results.Event == event][
                        "TimeStampSecs"
                    ].sem(),
                }

    ordered_events = {
        "schedule + make-pod-sandbox": ("PodScheduled", "SandboxReady"),
        "pull-images + start-containrs": ("SandboxReady", "ContainersReady"),
        "execute entrypoint": ("ContainersReady", "EndEntrypoint"),
    }
    color_for_event = {
        "schedule + make-pod-sandbox": "blue",
        "pull-images + start-containrs": "yellow",
        "execute entrypoint": "aquamarine",
    }
    pattern_for_repo = {EXPERIMENT_IMAGE_REPO: "x", EXTERNAL_REGISTRY_URL: "|"}
    name_for_repo = {EXPERIMENT_IMAGE_REPO: "ghcr", EXTERNAL_REGISTRY_URL: "local"}

    pattern_for_bline = {baselines[0]: "x", baselines[1]: "|", baselines[2]: "o"}

    assert list(color_for_event.keys()) == list(ordered_events.keys())
    assert list(pattern_for_repo.keys()) == list(name_for_repo.keys())

    # --------------------------
    # Time-series of the different services instantiation
    # --------------------------

    fig, ax = subplots()

    bar_height = 0.33

    for ind, bline in enumerate(baselines):
        # Y coordinate of the bar
        ys = []
        # Width of each bar
        widths = []
        # x-axis offset of each bar
        xs = []
        # labels = []
        colors = []

        x_origin = min(
            [results_dict[bline][s_id]["PodScheduled"]["mean"] for s_id in service_ids]
        )

        service_ids = sorted(
            service_ids,
            key=lambda x: results_dict[bline][x]["ContainersReady"]["mean"]
            - results_dict[bline][x]["PodScheduled"]["mean"],
        )

        for num, service_id in enumerate(service_ids):
            for event in ordered_events:
                start_ev = ordered_events[event][0]
                end_ev = ordered_events[event][1]
                x_left = results_dict[bline][service_id][start_ev]["mean"]
                x_right = results_dict[bline][service_id][end_ev]["mean"]
                widths.append(x_right - x_left)
                xs.append(x_left - x_origin)
                ys.append(num * (bar_height * 3) + bar_height * ind)
                colors.append(color_for_event[event])

        ax.barh(
            ys,
            widths,
            height=bar_height,
            left=xs,
            align="edge",
            edgecolor="black",
            color=colors,
            hatch=pattern_for_bline[bline],
            alpha=1 - 0.33 * ind,
        )

    # Misc
    ax.set_xlabel("Time [s]")
    ax.set_ylim(bottom=0, top=(len(service_ids)) * (bar_height * 2))
    ax.set_ylabel("Knative Service Id")
    yticks = [i * (bar_height * 3) for i in range(len(service_ids) + 1)]
    yticks_minor = [(i + 0.5) * (bar_height * 3) for i in range(len(service_ids))]
    ytick_labels = ["S{}".format(i) for i in range(len(service_ids))]
    ax.set_yticks(yticks)
    ax.set_yticks(yticks_minor, minor=True)
    ax.set_yticklabels(ytick_labels, minor=True)
    ax.set_yticklabels([])
    title_str = f"Breakdown of the time spent starting {num_par_instances} services in parallel\n"
    title_str += "(baseline: {})\n".format(
        bline,
    )
    ax.set_title(title_str)

    # Manually craft the legend
    legend_handles = []
    for event in ordered_events:
        legend_handles.append(
            Patch(
                facecolor=color_for_event[event],
                edgecolor="black",
                label=event,
            )
        )
    for ind, bline in enumerate(baselines):
        legend_handles.append(
            Patch(
                hatch=pattern_for_bline[bline],
                facecolor="white",
                edgecolor="black",
                label="Baseline: {}".format(bline),
            )
        )
    ax.legend(handles=legend_handles, bbox_to_anchor=(1.05, 1.05))


    for plot_format in ["pdf", "png"]:
        plot_file = join(plots_dir, "xput_detail_{}.{}".format(num_par_instances,plot_format))
        fig.savefig(plot_file, format=plot_format, bbox_inches="tight")
