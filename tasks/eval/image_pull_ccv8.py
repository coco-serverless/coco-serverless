from invoke import task
from matplotlib.patches import Patch
from matplotlib.pyplot import subplots
from os import makedirs
from os.path import exists, join
from pandas import read_csv
from re import search as re_search
from tasks.eval.util.clean import cleanup_after_run
from tasks.eval.util.csv import init_csv_file, write_csv_line
from tasks.eval.util.env import (
    APPS_DIR,
    BASELINES,
    EVAL_TEMPLATED_DIR,
    INTER_RUN_SLEEP_SECS,
    RESULTS_DIR,
    PLOTS_DIR,
)
from tasks.eval.util.pod import wait_for_pod_ready_and_get_ts
from tasks.eval.util.setup import setup_baseline
from tasks.util.containerd import (
    get_all_events_in_between,
    get_ts_for_containerd_event,
)
from tasks.util.env import COCO_RELEASE_VERSION
from tasks.util.k8s import template_k8s_file
from tasks.util.kubeadm import get_pod_names_in_ns, run_kubectl_command
from time import sleep, time

IS_NYDUS_IMAGE = True
USED_IMAGES = ["hello-world-flask-nydus"]
CSG_MAGIC_BEGIN = "CSG-M4GIC: B3G1N: {}"
CSG_MAGIC_END = "CSG-M4GIC: END: {}"
EXPERIMENT_IMAGE_REPO = "registry.coco-csg.com"

def aggregate_layered_events(layered_events, event):
    """
    Given a sequence of BEGIN/END events, return the overall duration time
    (not real time, as some may happen in parallel)
    """
    sorted_events = sorted(layered_events, key=lambda x: int(x["__REALTIME_TIMESTAMP"]))

    actual_csg_magic_begin = CSG_MAGIC_BEGIN.format(event)
    actual_csg_magic_end = CSG_MAGIC_END.format(event)

    def get_ts_from_json(ev_json):
        return int(ev_json["__REALTIME_TIMESTAMP"]) / 1e6

    def get_digest_from_json(ev_json):
        return re_search(r"sha256:([a-z0-9]*)", ev_json["MESSAGE"]).groups(1)[0]

    def find_end_ts(ev_json):
        digest = get_digest_from_json(ev_json)
        for ev in sorted_events:
            if actual_csg_magic_end in ev["MESSAGE"] and digest in ev["MESSAGE"]:
                return get_ts_from_json(ev)

    overall_duration = 0

    for ev in sorted_events:
        # Make sure event is either begingin or end
        is_begin = actual_csg_magic_begin in ev["MESSAGE"]
        is_end = actual_csg_magic_end in ev["MESSAGE"]
        assert is_begin != is_end, "BEGIN/END XOR failed! (msg: {})".format(
            ev["MESSAGE"]
        )

        if is_end:
            continue

        start_ts = get_ts_from_json(ev)
        end_ts = find_end_ts(ev)
        assert end_ts >= start_ts, "End and start duration swapped!"

        overall_duration += end_ts - start_ts

    return overall_duration


def do_run(result_file, num_run, service_file, flavour, warmup=False):
    global_start_ts = time()

    # Silently start
    run_kubectl_command("apply -f {}".format(service_file), capture_output=True)

    # Wait for pod to start
    pods = get_pod_names_in_ns("default")
    while len(pods) < 1:
        sleep(1)
        pods = get_pod_names_in_ns("default")
    assert len(pods) == 1
    pod_name = pods[0]

    # Wait for pod to be ready (we can ignore the return value)
    wait_for_pod_ready_and_get_ts(pod_name)

    if not warmup:
        if IS_NYDUS_IMAGE:
            ordered_events = [
                "(KS-agent) GC Image Pull",
                "(KS-image-rs) Pull Manifest",
                "(KS-image-rs) Nydus Image Pull",
                "(KS-image-rs) Nydus Bootstrap Pull",
                ]
        else:
            ordered_events = [
                "(KS-agent) GC Image Pull",
                "(KS-image-rs) Pull Manifest",
                "Pull Layers",
                ]

        for image in USED_IMAGES:
            events_ts = []

            for event in ordered_events:
                start_ts = get_ts_for_containerd_event(
                    CSG_MAGIC_BEGIN.format(event), "CSG", global_start_ts
                )

                end_ts = get_ts_for_containerd_event(
                    CSG_MAGIC_END.format(event), "CSG", global_start_ts
                )

                events_ts.append(("Start{}".format(event.replace(" ", "")), start_ts))
                events_ts.append(("End{}".format(event.replace(" ", "")), end_ts))

            # Also aggregate all events associated to pulling and handling
            # singlye layers into one blob
            # NOTE: pulling and handling happens serially _per layer_ but
            # layers can be downloaded concurrently depending on an `image-rs`
            # config flag. Thus, to report the time spent pulling and the
            # time spent handling, we measure the ratios, and assume they
            # occupy all the time


            ##TODO##

            # pull_bootstrap_event = get_all_events_in_between(
            #     CSG_MAGIC_BEGIN.format("Pull Layers"),
            #     image,
            #     CSG_MAGIC_END.format("Pull Layers"),
            #     image,
            #     "Pull Single Layer",
            # )
            # pull_duration = aggregate_layered_events(
            #     pull_layer_events, "Pull Single Layer"
            # )

            # handle_layer_events = get_all_events_in_between(
            #     CSG_MAGIC_BEGIN.format(event),
            #     image,
            #     CSG_MAGIC_END.format(event),
            #     image,
            #     "Handle Single Layer",
            # )
            # handle_duration = aggregate_layered_events(
            #     handle_layer_events, "Handle Single Layer"
            # )
            if not IS_NYDUS_IMAGE:
                pull_layer_events = get_all_events_in_between(
                        CSG_MAGIC_BEGIN.format("Pull Layers"),
                        "CSG",
                        CSG_MAGIC_END.format("Pull Layers"),
                        "CSG",
                        "Pull Single Layer",
                    )
                pull_duration = aggregate_layered_events(
                pull_layer_events, "Pull Single Layer"
                )

                handle_layer_events = get_all_events_in_between(
                    CSG_MAGIC_BEGIN.format(event),
                    "CSG",
                    CSG_MAGIC_END.format(event),
                    "CSG",
                    "Handle Single Layer",
                )
                handle_duration = aggregate_layered_events(
                    handle_layer_events, "Handle Single Layer"
                )
               
                # Express durations as ratios from the parent "Pull Layers" event
                pull_start_ts = get_ts_for_containerd_event(
                    CSG_MAGIC_BEGIN.format("Pull Layers"), "CSG", global_start_ts
                )
                pull_end_ts = get_ts_for_containerd_event(
                    CSG_MAGIC_END.format("Pull Layers"), "CSG", global_start_ts
                )
                overall_duration = pull_end_ts - pull_start_ts
                pull_ratio = pull_duration / (pull_duration + handle_duration)
                events_ts.append(("StartPullSingleLayer", pull_start_ts))
                events_ts.append(
                    ("EndPullSingleLayer", pull_start_ts + pull_ratio * overall_duration)
                )
                events_ts.append(
                    (
                        "StartHandleSingleLayer",
                        pull_start_ts + pull_ratio * overall_duration,
                    )
                )
                events_ts.append(("EndHandleSingleLayer", pull_end_ts))

            # Sort the events by timestamp and write them to a file
            image_name = "sidecar" if "sidecar" in image else "app"
            events_ts = sorted(events_ts, key=lambda x: x[1])
            for event in events_ts:
                write_csv_line(result_file, num_run, image_name, event[0], event[1])

    # Wait for pod to finish
    run_kubectl_command("delete -f {}".format(service_file), capture_output=True)
    run_kubectl_command("delete pod {}".format(pod_name), capture_output=True)


@task
def run(ctx):
    """
    Detailed break-down of the guest-side image pulling latency

    This benchmark digs deeper into the costs associated with just spinning up
    the confidnetial VM (and kata agent) as part of the bootstrap of a Knative
    service on CoCo
    """
    baselines_to_run = [f"coco-nydus"]
    service_template_file = join(APPS_DIR, "image-pull-ccv8", "deployment.yaml.j2")
    num_runs = 1

    results_dir = join(RESULTS_DIR, "image-pull-ccv8")
    if not exists(results_dir):
        makedirs(results_dir)

    if not exists(EVAL_TEMPLATED_DIR):
        makedirs(EVAL_TEMPLATED_DIR)

    for bline in baselines_to_run:
        baseline_traits = BASELINES[bline]

        # First, template the service file
        service_file = join(
            EVAL_TEMPLATED_DIR, "apps_image-pull_{}_service.yaml".format(bline)
        )
        template_vars = {
            "image_repo": EXPERIMENT_IMAGE_REPO,
            "image_name": USED_IMAGES[0],
            "image_tag": baseline_traits["image_tag"],
        }
        if len(baseline_traits["runtime_class"]) > 0:
            template_vars["runtime_class"] = baseline_traits["runtime_class"]
        template_k8s_file(service_template_file, service_file, template_vars)

        # Second, run any baseline-specific set-up
        #setup_baseline(bline, USED_IMAGES)

        for flavour in ["cold"]:
            # Prepare the result file
            result_file = join(results_dir, "{}_{}.csv".format(bline, flavour))
            init_csv_file(result_file, "Run,ImageName,Event,TimeStampMs")

            if flavour == "warm":
                print("Executing baseline {} warmup run...".format(bline))
                do_run(result_file, -1, service_file, flavour, warmup=True)
                sleep(INTER_RUN_SLEEP_SECS)

            if flavour == "cold":
                # `cold` happens after `warm`, so we want to clean-up after
                # all the `warm` runs
                cleanup_after_run(bline, USED_IMAGES)

            for nr in range(num_runs):
                print(
                    "Executing baseline {} ({}) run {}/{}...".format(
                        bline, flavour, nr + 1, num_runs
                    )
                )
                do_run(result_file, nr, service_file, flavour)
                sleep(INTER_RUN_SLEEP_SECS)

                if flavour == "cold":
                    cleanup_after_run(bline, USED_IMAGES)


@task
def plot(ctx):
    """
    Plot a flame-graph of the guest-side image pulling process
    """
    results_dir = join(RESULTS_DIR, "image-pull-ccv8")
    plots_dir = join(PLOTS_DIR, "image-pull-ccv8")
    baseline = "coco-nydus"
    results_file = join(results_dir, "{}_cold.csv".format(baseline))

    results_dict = {}
    results = read_csv(results_file)
    image_names = set(results["ImageName"].to_list())
    for image_name in image_names:
        results_dict[image_name] = {}
        image_results = results[results.ImageName == image_name]
        groupped = image_results.groupby("Event", as_index=False)
        events = list(groupped.groups.keys())
        for event in events:
            # NOTE: these timestamps are in seconds
            results_dict[image_name][event] = {
                "mean": image_results[image_results.Event == event][
                    "TimeStampMs"
                ].mean(),
                "sem": image_results[image_results.Event == event]["TimeStampMs"].sem(),
            }

    # Useful maps to plot the experiments
    pattern_for_image = {"app": "//", "sidecar": "."}
    if IS_NYDUS_IMAGE:
        ordered_events = {
            "image-pull": ("Start(KS-agent)GCImagePull", "End(KS-agent)GCImagePull"),
            "pull-manifest": ("Start(KS-image-rs)PullManifest", "End(KS-image-rs)PullManifest"),
            "pull-nydus-image": ("Start(KS-image-rs)NydusImagePull", "End(KS-image-rs)NydusImagePull"),
            "pull-nydus-bootstrap": ("Start(KS-image-rs)NydusBootstrapPull", "End(KS-image-rs)NydusBootstrapPull"),
        }
        height_for_event = {
            "image-pull": 0,
            "pull-manifest": 1,
            "pull-nydus-image": 1,
            "pull-nydus-bootstrap": 2,
        }
        color_for_event = {
            "image-pull": "red",
            "pull-manifest": "purple",
            "pull-nydus-image": "green",
            "pull-nydus-bootstrap": "blue",
        }
    else:
        ordered_events = {
                "image-pull": ("Start(KS-agent)GCImagePull", "End(KS-agent)GCImagePull"),
                "pull-manifest": ("Start(KS-image-rs)PullManifest", "End(KS-image-rs)PullManifest"),
                "pull-layers": ("StartPullLayers", "EndPullLayers"),
                "pull-single-layer": ("StartPullSingleLayer", "EndPullSingleLayer"),
                "handle-single-layer": ("StartHandleSingleLayer", "EndHandleSingleLayer"),
            }
        height_for_event = {
            "image-pull": 0,
            "pull-manifest": 1,
            "pull-layers": 1,
            "pull-single-layer": 2,
            "handle-single-layer": 2,
        }
        color_for_event = {
            "image-pull": "red",
            "pull-manifest": "purple",
            "pull-layers": "green",
            "pull-single-layer": "blue",
            "handle-single-layer": "brown",
        }
    assert list(ordered_events.keys()) == list(height_for_event.keys())
    assert list(color_for_event.keys()) == list(height_for_event.keys())

    # --------------------------
    # Flame-like Graph of the CoCo sandbox start-up time
    # --------------------------

    fig, ax = subplots()
    bar_height = 0.5
    # Y coordinate of the bar
    ys = []
    # Width of each bar
    widths = []
    # x-axis offset of each bar
    xs = []
    labels = []
    colors = []
    hatches = []

    # Helper list to know which labels don't fit in their bar. Alas, I have not
    # found a way to programatically place them well, so the (x, y) coordinates
    # for this labels will have to be hard-coded
    events_to_rotate = [
        "pull-manifest",
        "signature-validation",
        "pull-nydus-image",
        "handle-single-layer",
    ]

    x_origin = min(
        [results_dict["app"]["Start(KS-agent)GCImagePull"]["mean"]]
        #results_dict["sidecar"]["Start(KS-agent)GCImagePull"]["mean"],
    )
    for image in ["app"]:
        for event in ordered_events:
            start_ev = ordered_events[event][0]
            end_ev = ordered_events[event][1]
            x_left = results_dict[image][start_ev]["mean"]
            x_right = results_dict[image][end_ev]["mean"]
            widths.append(x_right - x_left)
            xs.append(x_left - x_origin)
            ys.append(height_for_event[event] * bar_height)
            labels.append(event)
            colors.append(color_for_event[event])
            hatches.append(pattern_for_image[image])

            # Print the label inside the bar
            x_text = x_left - x_origin + (x_right - x_left) / 4
            y_text = (height_for_event[event] + 0.2) * bar_height

            ax.text(
                x_text,
                y_text,
                event,
                rotation=90 if event in events_to_rotate else 0,
                bbox={
                    "facecolor": "white",
                    "edgecolor": "black",
                },
            )

    ax.barh(
        ys,
        widths,
        height=bar_height,
        left=xs,
        align="edge",
        label=labels,
        color=colors,
        hatch=hatches,
    )

    # Misc
    ax.set_xlabel("Time [s]")
    ax.set_ylim(bottom=0)
    ax.tick_params(axis="y", which="both", left=False, right=False, labelbottom=False)
    ax.set_yticklabels([])
    title_str = "Breakdown of the time pulling OCI images\n"
    title_str += "(baseline: {})\n".format(
        baseline,
    )
    ax.set_title(title_str)

    # Manually craft the legend
    legend_handles = []
    for image in pattern_for_image:
        legend_handles.append(
            Patch(
                hatch=pattern_for_image[image],
                facecolor="white",
                edgecolor="black",
                label=image,
            )
        )
    ax.legend(handles=legend_handles, bbox_to_anchor=(1.05, 1.05))

    for plot_format in ["pdf", "png"]:
        plot_file = join(plots_dir, "image_pull_{}.{}".format(baseline, plot_format))
        fig.savefig(plot_file, format=plot_format, bbox_inches="tight")


@task
def foo(ctx):
    pull_layer_events = get_all_events_in_between(
        CSG_MAGIC_BEGIN.format("Pull Layers"),
        "sidecar",
        CSG_MAGIC_END.format("Pull Layers"),
        "sidecar",
        "Pull Single Layer",
    )
    start_ts, end_ts = aggregate_layered_events(pull_layer_events, "Pull Single Layer")