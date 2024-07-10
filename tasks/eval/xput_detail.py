from datetime import datetime
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
    GITHUB_USER,
)
from tasks.eval.util.setup import setup_baseline
from tasks.util.containerd import get_ts_for_containerd_event
from tasks.util.env import LOCAL_REGISTRY_URL
from tasks.util.k8s import template_k8s_file
from tasks.util.knative import replace_sidecar
from tasks.util.kubeadm import get_pod_names_in_ns, run_kubectl_command
from time import sleep


def do_run(result_file, baseline, image_repo, num_run, num_par_inst):
    service_files = [
        "apps_xput-detail_{}_{}_service_{}.yaml".format(image_repo, baseline, i)
        for i in range(num_par_inst)
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

        # Once all pods are ready, query for the relevant events for each pod
        def get_events_for_pod(pod_id, pod_name):
            events_ts = []

            kube_cmd = "get pod {} -o jsonpath='{{..status.conditions}}'".format(
                pod_name
            )
            conditions = run_kubectl_command(kube_cmd, capture_output=True)
            cond_json = json_loads(conditions)

            assert all(
                [cond["status"] == "True" for cond in cond_json]
            ), "Pod {} is not ready".format(pod_name)

            for cond in cond_json:
                events_ts.append(
                    (
                        cond["type"],
                        datetime.fromisoformat(
                            cond["lastTransitionTime"][:-1]
                        ).timestamp(),
                    )
                )

            # Also get one event from containerd that indicates that the
            # sandbox is ready
            timeout_mins = 5
            vm_ready_ts = get_ts_for_containerd_event(
                "RunPodSandbox",
                pod_name,
                timeout_mins=timeout_mins,
            )
            events_ts.append(("SandboxReady", vm_ready_ts))

            # Sort the events by timestamp and write them to a file
            events_ts = sorted(events_ts, key=lambda x: x[1])
            for event in events_ts:
                write_csv_line(result_file, pod_id, event[0], event[1])

        for pod_id, pod_name in enumerate(pods):
            # Skip finished pods
            if ready_pods[pod_name]:
                continue

            if is_pod_done(pod_name):
                ready_pods[pod_name] = True
                pods_ready_ts[pod_name] = get_pod_ready_ts(pod_name)

                # As soon as one pod is ready, we process the events from it
                # to avoid containerd trimming the logs
                print("Getting events for pod {}".format(pod_name))
                get_events_for_pod(pod_id, pod_name)

        is_done = all(list(ready_pods.values()))
        sleep(1)

    # Remove the pods when we are done
    for service_file in service_files:
        run_kubectl_command(
            "delete -f {}".format(join(EVAL_TEMPLATED_DIR, service_file)),
            capture_output=True,
        )
    for pod in pods:
        run_kubectl_command("delete pod {}".format(pod), capture_output=True)


@task
def run(ctx, repo=None):
    """
    Measure the costs associated with starting a fixed number of concurrent
    services
    """
    baselines_to_run = ["coco-fw-sig-enc"]
    image_repos = [EXPERIMENT_IMAGE_REPO, LOCAL_REGISTRY_URL]
    num_parallel_instances = [16]
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
    image_name = f"{GITHUB_USER}/coco-helloworld-py"
    used_images = [f"{GITHUB_USER}/coco-knative-sidecar", image_name]

    for image_repo in image_repos:
        replace_sidecar(image_repo=image_repo, quiet=True)

        for bline in baselines_to_run:
            baseline_traits = BASELINES[bline]

            # Template as many service files as parallel instances
            for i in range(max(num_parallel_instances)):
                service_file = join(
                    EVAL_TEMPLATED_DIR,
                    "apps_xput-detail_{}_{}_service_{}.yaml".format(
                        image_repo, bline, i
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
            setup_baseline(bline, used_images, image_repo)

            for num_par in num_parallel_instances:
                # Prepare the result file
                result_file = join(
                    results_dir, "{}_{}_{}.csv".format(image_repo, bline, num_par)
                )
                init_csv_file(result_file, "ServiceId,Event,TimeStampSecs")

                for nr in range(num_runs):
                    print(
                        "Executing baseline {} ({} par srv, {}) run {}/{}...".format(
                            bline, num_par, image_repo, nr + 1, num_runs
                        )
                    )
                    do_run(result_file, bline, image_repo, nr, num_par)
                    sleep(INTER_RUN_SLEEP_SECS)
                    cleanup_after_run(bline, used_images)


@task
def plot(ctx):
    """
    Plot the costs associated with starting a fixed number of concurrent
    services
    """
    results_dir = join(RESULTS_DIR, "xput-detail")
    plots_dir = join(PLOTS_DIR, "xput-detail")
    baseline = "coco-fw-sig-enc"
    num_par_instances = 16
    image_repos = [EXPERIMENT_IMAGE_REPO, LOCAL_REGISTRY_URL]

    results_file = join(results_dir, "{}_{}.csv".format(baseline, num_par_instances))

    # Collect results
    results_dict = {}
    for image_repo in image_repos:
        results_file = join(
            results_dir, "{}_{}_{}.csv".format(image_repo, baseline, num_par_instances)
        )
        results_dict[image_repo] = {}
        results = read_csv(results_file)
        service_ids = set(results["ServiceId"].to_list())
        for service_id in service_ids:
            results_dict[image_repo][service_id] = {}
            service_results = results[results.ServiceId == service_id]
            groupped = service_results.groupby("Event", as_index=False)
            events = list(groupped.groups.keys())
            for event in events:
                results_dict[image_repo][service_id][event] = {
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
    }
    color_for_event = {
        "schedule + make-pod-sandbox": "blue",
        "pull-images + start-containrs": "yellow",
    }
    pattern_for_repo = {EXPERIMENT_IMAGE_REPO: "x", LOCAL_REGISTRY_URL: "|"}
    name_for_repo = {EXPERIMENT_IMAGE_REPO: "ghcr", LOCAL_REGISTRY_URL: "local"}

    assert list(color_for_event.keys()) == list(ordered_events.keys())
    assert list(pattern_for_repo.keys()) == list(name_for_repo.keys())

    # --------------------------
    # Time-series of the different services instantiation
    # --------------------------

    fig, ax = subplots()

    bar_height = 0.5

    for ind, repo in enumerate(image_repos):
        # Y coordinate of the bar
        ys = []
        # Width of each bar
        widths = []
        # x-axis offset of each bar
        xs = []
        # labels = []
        colors = []

        x_origin = min(
            [results_dict[repo][s_id]["PodScheduled"]["mean"] for s_id in service_ids]
        )

        service_ids = sorted(
            service_ids,
            key=lambda x: results_dict[repo][x]["ContainersReady"]["mean"]
            - results_dict[repo][x]["PodScheduled"]["mean"],
        )

        for num, service_id in enumerate(service_ids):
            for event in ordered_events:
                start_ev = ordered_events[event][0]
                end_ev = ordered_events[event][1]
                x_left = results_dict[repo][service_id][start_ev]["mean"]
                x_right = results_dict[repo][service_id][end_ev]["mean"]
                widths.append(x_right - x_left)
                xs.append(x_left - x_origin)
                ys.append(num * (bar_height * 2) + bar_height * ind)
                colors.append(color_for_event[event])

        ax.barh(
            ys,
            widths,
            height=bar_height,
            left=xs,
            align="edge",
            edgecolor="black",
            color=colors,
            hatch=pattern_for_repo[repo],
            alpha=1 - 0.7 * ind,
        )

    # Misc
    ax.set_xlabel("Time [s]")
    ax.set_ylim(bottom=0, top=(len(service_ids)) * (bar_height * 2))
    ax.set_ylabel("Knative Service Id")
    yticks = [i * (bar_height * 2) for i in range(len(service_ids) + 1)]
    yticks_minor = [(i + 0.5) * (bar_height * 2) for i in range(len(service_ids))]
    ytick_labels = ["S{}".format(i) for i in range(len(service_ids))]
    ax.set_yticks(yticks)
    ax.set_yticks(yticks_minor, minor=True)
    ax.set_yticklabels(ytick_labels, minor=True)
    ax.set_yticklabels([])
    title_str = "Breakdown of the time spent starting 16 services in parallel\n"
    title_str += "(baseline: {})\n".format(
        baseline,
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
    for ind, repo in enumerate(image_repos):
        legend_handles.append(
            Patch(
                hatch=pattern_for_repo[repo],
                facecolor="white",
                edgecolor="black",
                label="Image registry: {}".format(name_for_repo[repo]),
            )
        )
    ax.legend(handles=legend_handles, bbox_to_anchor=(1.05, 1.05))

    for plot_format in ["pdf", "png"]:
        plot_file = join(plots_dir, "xput_detail.{}".format(plot_format))
        fig.savefig(plot_file, format=plot_format, bbox_inches="tight")
