from datetime import datetime
from glob import glob
from invoke import task
from json import loads as json_loads
from matplotlib.patches import Patch
from matplotlib.pyplot import subplots
from numpy import array as np_array, mean as np_mean
from os import makedirs
from os.path import basename, exists, join
from pandas import read_csv
from tasks.eval.util.clean import cleanup_after_run
from tasks.eval.util.csv import init_csv_file, write_csv_line
from tasks.eval.util.env import (
    APPS_DIR,
    BASELINE_FLAVOURS,
    BASELINES,
    EXPERIMENT_IMAGE_REPO,
    EVAL_TEMPLATED_DIR,
    INTER_RUN_SLEEP_SECS,
    RESULTS_DIR,
    PLOTS_DIR,
)
from tasks.eval.util.pod import get_event_ts_in_pod_logs, wait_for_pod_ready_and_get_ts
from tasks.eval.util.setup import setup_baseline, update_sidecar_deployment
from tasks.util.containerd import get_start_end_ts_for_containerd_event, get_ts_for_containerd_event
from tasks.util.k8s import get_container_id_from_pod, template_k8s_file
from tasks.util.kubeadm import get_pod_names_in_ns, run_kubectl_command
from time import sleep, time


CSG_MAGIC_BEGIN = "CSG-M4GIC: B3G1N: {}"
CSG_MAGIC_END = "CSG-M4GIC: END: {}"

def do_run(result_file, image_name, num_run, service_file, flavour, end_to_end, entrypoint_keyword, warmup=False):
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

    wait_for_pod_ready_and_get_ts(pod_name)
    print(f"pod {pod_name} ready")
    # Get events
    while True:
        kube_cmd = "get pod {} -o jsonpath='{{..status.conditions}}'".format(pod_name)
        events_ts = [("Start", start_ts)]
        conditions = run_kubectl_command(kube_cmd, capture_output=True)
        cond_json = json_loads(conditions)

        is_ready = all([cond["status"] == "True" for cond in cond_json])
        print(f"pod ready: {is_ready}")
        if is_ready:
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
        # Work-out the time spent creating the pod sandbox
        start_ts_ps, end_ts_ps = get_start_end_ts_for_containerd_event(
            "RunPodSandbox",
            pod_name,
            # lower_bound=start_ts,
            timeout_mins=None,
        )
        events_ts.append(("StartRunPodSandbox", start_ts_ps))
        events_ts.append(("EndRunPodSandbox", end_ts_ps))

        # Work-out the time spent pulling container images
        skip_image_pull = (
            ("docker" in service_file or "kata" in service_file or "coco-nydus-caching" in service_file or "coco-caching" in service_file)
        ) and flavour == "warm"

        if skip_image_pull:
            start_ts_pi_srv = end_ts_ps
            end_ts_pi_srv = end_ts_ps
            start_ts_pi_sc = end_ts_ps
            end_ts_pi_sc = end_ts_ps
        else:
            if "docker" in service_file or "kata" in service_file or "coco-caching" in service_file:
                start_ts_pi_srv, end_ts_pi_srv = get_start_end_ts_for_containerd_event(
                    "PullImage",
                    image_name,
                    lower_bound=end_ts_ps,
                )
            elif "coco-nydus-caching" in service_file:
                # start_ts_pi_srv, _ = get_start_end_ts_for_containerd_event(
                #     "PullImage",
                #     image_name,
                #     lower_bound=end_ts_ps,
                # )
                start_ts_pi_srv = end_ts_ps
                end_ts_pi_srv = get_ts_for_containerd_event(
                    CSG_MAGIC_END.format("(KS-agent) GC Image Pull"), "CSG", start_ts, timeout_mins=None,
                )
            else:
                start_ts_pi_srv = get_ts_for_containerd_event(
                    CSG_MAGIC_BEGIN.format("(KS-agent) GC Image Pull"), "CSG", start_ts, timeout_mins=None,
                )

                end_ts_pi_srv = get_ts_for_containerd_event(
                    CSG_MAGIC_END.format("(KS-agent) GC Image Pull"), "CSG", start_ts, timeout_mins=None,
                )
            
        events_ts.append(("StartImagePull_Service", start_ts_pi_srv))
        events_ts.append(("EndImagePull_Service", end_ts_pi_srv))

        # Work-out time to create each container
        start_ts_cc_srv, end_ts_cc_srv = get_start_end_ts_for_containerd_event(
            "CreateContainer",
            "helloworld-py",
            lower_bound=start_ts,#end_ts_pi_srv,
            timeout_mins=None,
        )
        events_ts.append(("StartCreateContainer_Service", start_ts_cc_srv))
        events_ts.append(("EndCreateContainer_Service", end_ts_cc_srv))


        # Work-out time to start each container
        start_ts_sc_srv, end_ts_sc_srv = get_start_end_ts_for_containerd_event(
            "StartContainer",
            " ",#get_container_id_from_pod(pod_name, "user-container"),
            lower_bound=start_ts, #end_ts_cc_srv,
            timeout_mins=None,
        )
        events_ts.append(("StartStartContainer_Service", start_ts_sc_srv))
        events_ts.append(("EndStartContainer_Service", end_ts_sc_srv))



        if end_to_end:
            print("End to end found")
            while True:
                kube_cmd = "get pod {} -o jsonpath='{{..status.conditions}}'".format(pod_name)
                conditions = run_kubectl_command(kube_cmd, capture_output=True)
                cond_json = json_loads(conditions)
                completed = [datetime.fromisoformat(cond["lastTransitionTime"][:-1]).timestamp() 
                                    for cond in cond_json if "reason" in cond and cond["reason"] == "PodCompleted"]

                if completed:
                    events_ts.append(("StartEntrypoint", end_ts_sc_srv))
                    events_ts.append(("EndEntrypoint", sorted(completed)[-1]))
                    break
                else:
                    sleep(2)

        elif entrypoint_keyword is not None:
            entrypoint_complete = get_event_ts_in_pod_logs(pod_name, entrypoint_keyword)
            events_ts.append(("StartEntrypoint", end_ts_sc_srv))
            events_ts.append(("EndEntrypoint", entrypoint_complete))

        else:
            events_ts.append(("StartEntrypoint", end_ts_sc_srv))
            events_ts.append(("EndEntrypoint", end_ts_sc_srv))

        # Sort the events by timestamp and write them to a file
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

    baselines_to_run = ["docker"]
    if baseline is not None:
        if baseline not in baselines_to_run:
            print(
                "Unrecognised baseline {}! Must be one in: {}".format(
                    baseline, baselines_to_run
                )
            )
            raise RuntimeError("Unrecognised baseline")
        baselines_to_run = [baseline]

    service_template_file = join(APPS_DIR, "startup-ccv8", "deployment.yaml.j2")
    image_names = ["tf-app-tinybert"]

    entrypoint_keywords = {"node-app": "node server starting", "tf-serving": "Exporting HTTP/REST", "tf-serving-tinybert": "Exporting HTTP/REST", "tf-app": "flask server starting", "tf-app-tinybert": "flask server starting", "fio-benchmark": , "tf-app-tinibert": "flask server starting"}

    used_images = ["fio-benchmark:unencrypted", "fio-benchmark:unencrypted-nydus", "tf-serving:unencrypted", "tf-serving:unencrypted-nydus", "tf-serving-tinybert:blob-cache", "tf-app:unencrypted-nydus", "tf-app:unencrypted","tf-app:blob-cache", "tf-app-tinybert:unencrypted-nydus", "tf-app-tinybert:unencrypted" ,"tf-app-tinybert:blob-cache", "tf-app-tinibert:unencrypted-nydus", "tf-app-tinibert:unencrypted" ,"tf-app-tinibert:blob-cache"]
    num_runs = 1

    results_dir = join(RESULTS_DIR, "startup-ccv8")
    if not exists(results_dir):
        makedirs(results_dir)

    if not exists(EVAL_TEMPLATED_DIR):
        makedirs(EVAL_TEMPLATED_DIR)


    for image_name in image_names:

        # Use different results dir for each image name
        results_image_dir = join(results_dir, image_name)
        if not exists(results_image_dir):
            makedirs(results_image_dir)

        end_to_end = is_benchmark[image_name]

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
            template_vars["runtime_class"] = baseline_traits["runtime_class"]
            template_k8s_file(service_template_file, service_file, template_vars)

            # Second, run any baseline-specific set-up
            #setup_baseline(bline, used_images)

            for flavour in BASELINE_FLAVOURS:
                # Prepare the result file
                result_file = join(results_image_dir, "{}_{}.csv".format(bline, flavour))
                init_csv_file(result_file, "Run,Event,TimeStampMs")

                if flavour == "warm":
                    print("Executing baseline {} warmup run...".format(bline))
                    do_run(result_file, image_name, -1, service_file, flavour, end_to_end, entrypoint_keywords[image_name], warmup=True)
                    #sleep(INTER_RUN_SLEEP_SECS)

                if flavour == "cold":
                    # `cold` happens after `warm`, so we want to clean-up after
                    # all the `warm` runs
                    print("deleting images")
                    cleanup_after_run(bline, used_images)

                for nr in range(num_runs):
                    print(
                        "Executing baseline {} ({}) run {}/{}...".format(
                            bline, flavour, nr + 1, num_runs
                        )
                    )
                    do_run(result_file, image_name, nr, service_file, flavour, end_to_end, entrypoint_keywords[image_name])
                    sleep(INTER_RUN_SLEEP_SECS)

                    if flavour == "cold":
                        cleanup_after_run(bline, used_images)
                
                print("finished run")
                sleep(15)

@task
def plot(ctx):

    image_name = "tf-app-tinybert"
    results_dir = join(RESULTS_DIR, "startup-ccv8", image_name)

    if not exists(results_dir):
        makedirs(results_dir)


    plots_dir = join(PLOTS_DIR, "startup-ccv8", image_name)
    if not exists(plots_dir):
        makedirs(plots_dir)

    glob_str = join(results_dir, "*.csv")
    results_dict = {}
    for csv in glob(glob_str):
        baseline = basename(csv).split(".")[0].split("_")[0]
        flavour = basename(csv).split(".")[0].split("_")[1]

        if baseline not in results_dict:
            results_dict[baseline] = {}


        results_dict[baseline][flavour] = {}
        results = read_csv(csv)
        groupped = results.groupby("Event", as_index=False)
        events = groupped.mean()["Event"].to_list()
        for ind, event in enumerate(events):
            # NOTE: these timestamps are in seconds
            results_dict[baseline][flavour][event] = {
                "mean": groupped.mean()["TimeStampMs"].to_list()[ind],
                "sem": groupped.sem()["TimeStampMs"].to_list()[ind],
                "list": groupped.get_group(event)["TimeStampMs"].to_list(),
            }

    # Useful maps to plot the experiments

    del results_dict["coco-nydus-caching"]

    pattern_for_flavour = {"warm": "//", "cold": "."}
    ordered_events = {
        "pod-scheduling": ("Start", "StartRunPodSandbox"),
        "make-pod-sandbox": ("StartRunPodSandbox", "EndRunPodSandbox"),
        "image-pull": ("StartImagePull", "EndImagePull"),
        "create-container": ("StartCreateContainer", "EndCreateContainer"),
        "start-container": ("StartCreateContainer", "EndCreateContainer"),
        #"execute-job": ("StartContainerJob", "EndContainerJob"),
        "execute-entrypoint": ("StartEntrypoint", "EndEntrypoint"),
    }
    color_for_event = {
        "pod-scheduling": "green",
        "make-pod-sandbox": "blue",
        "image-pull": "orange",
        "create-container": "yellow",
        "start-container": "red",
        #"execute-job": "purple",
        "execute-entrypoint": "aquamarine"
    }
    assert list(color_for_event.keys()) == list(ordered_events.keys())

    # --------------------------
    # Stacked bar chart comparing different baselines
    # --------------------------

    fig, ax = subplots()
    xlabels = list(results_dict.keys())

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
        stacked_ys = []
        for ev in ordered_events:
            start_ev = ordered_events[ev][0]
            end_ev = ordered_events[ev][1]
            ys = []
            for b in xlabels:
                # We calculate the event duration as the mean of the
                # differences, not the difference of the mean (eventually
                # consider if something like the median is more significant)
                if ev in ["pod-scheduling", "make-pod-sandbox", "execute-job", "execute-entrypoint"]:
                    # For the pod-scheduling, make-pod-sandbox, execute-job and 
                    # execute-job and execute-entrypoint event we
                    # only have one start/end timestamp pair
                    event_duration = np_mean(
                        np_array(results_dict[b][flavour][end_ev]["list"])
                        - np_array(results_dict[b][flavour][start_ev]["list"])
                    )
                else:
                    # For all other events, (i.e. all events related to
                    # containers) we have two timestamp pairs: one for the
                    # service container, and one for the sidecar
                    event_duration = 0
                    for i in ["Service"]:
                        event_duration += np_mean(
                            np_array(
                                results_dict[b][flavour]["{}_{}".format(end_ev, i)][
                                    "list"
                                ]
                            )
                            - np_array(
                                results_dict[b][flavour]["{}_{}".format(start_ev, i)][
                                    "list"
                                ]
                            )
                        )

                # Some events we read from the Kubernetes events (e.g. the
                # 'Ready' event) only have second resolution, whereas the
                # containerd logs have higher resolution, so sometimes we may
                # have event with negative durations in the [-1, 0) range
                # due to resolution issues
                if event_duration < 0 and event_duration > -1:
                    event_duration = 0
                assert event_duration >= 0
                ys.append(event_duration)

            stacked_ys.append(ys)

        for num, ys in enumerate(stacked_ys):
            label = list(ordered_events.keys())[num]
            if num == 0:
                ax.bar(
                    this_xs,
                    ys,
                    width=bar_width,
                    color=color_for_event[label],
                    edgecolor="black",
                    hatch=pattern_for_flavour[flavour],
                )
                acc_ys = ys
            else:
                ax.bar(
                    this_xs,
                    ys,
                    bottom=acc_ys,
                    width=bar_width,
                    color=color_for_event[label],
                    edgecolor="black",
                    hatch=pattern_for_flavour[flavour],
                )
                for i in range(len(acc_ys)):
                    acc_ys[i] += ys[i]

    # Misc
    ax.set_xticks(xs, xlabels, rotation=45)
    ax.set_xlabel("Baseline")
    ax.set_ylabel("Time [s]")
    ax.set_title(
        "End-to-end latency to start a pod\n(cold start='{}' - warm start='{}')".format(
            pattern_for_flavour["cold"], 0
        )
    )

    # Manually craft the legend
    legend_handles = []
    for ev in color_for_event:
        legend_handles.append(Patch(color=color_for_event[ev], label=ev))
    ax.legend(handles=legend_handles)

    for plot_format in ["pdf", "png"]:
        plot_file = join(plots_dir, "startup.{}".format(plot_format))
        fig.savefig(plot_file, format=plot_format, bbox_inches="tight")

    # --------------------------
    # Pie chart breaking down the execution time of one baseline
    # --------------------------

    baseline = "coco"
    flavour = "cold"
    fig, ax = subplots()

    labels = list(color_for_event.keys())
    event_durations = []
    event_labels = []
    for ev in labels:
        start_ev = ordered_events[ev][0]
        end_ev = ordered_events[ev][1]
        if ev in ["pod-scheduling", "make-pod-sandbox", "execute-job", "execute-entrypoint"]:
            event_durations.append(
                np_mean(
                    np_array(results_dict[baseline][flavour][end_ev]["list"])
                    - np_array(results_dict[baseline][flavour][start_ev]["mean"])
                )
            )
            event_labels.append(ev)
        else:
            for i in ["Service"]:
                event_durations.append(
                    np_mean(
                        np_array(
                            results_dict[baseline][flavour]["{}_{}".format(end_ev, i)][
                                "list"
                            ]
                        )
                        - np_array(
                            results_dict[baseline][flavour][
                                "{}_{}".format(start_ev, i)
                            ]["mean"]
                        )
                    )
                )
                event_labels.append("{}_{}".format(end_ev.removeprefix("End"), i))

    ax.pie(
        event_durations,
        labels=event_labels,
        colors=list(color_for_event.values()),
        wedgeprops={"edgecolor": "black"}
        # edgecolor="black",
    )

    title_str = "Breakdown of the time to start a Knative Service on CoCo\n"
    title_str += "(baseline: {} - total time: {:.2f} s)".format(
        baseline, sum(event_durations)
    )
    ax.set_title(title_str)

    for plot_format in ["pdf", "png"]:
        plot_file = join(plots_dir, "breakdown.{}".format(plot_format))
        fig.savefig(plot_file, format=plot_format, bbox_inches="tight")