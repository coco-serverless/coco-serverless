from glob import glob
from invoke import task
from matplotlib.pyplot import figure
from os import makedirs
from os.path import basename, exists, join
from pandas import read_csv
from re import search as re_search
from tasks.eval.util.clean import cleanup_after_run
from tasks.eval.util.csv import init_csv_file, write_csv_line
from tasks.eval.util.env import (
    APPS_DIR,
    BASELINES,
    EXPERIMENT_IMAGE_REPO,
    EVAL_TEMPLATED_DIR,
    INTER_RUN_SLEEP_SECS,
    RESULTS_DIR,
    PLOTS_DIR,
)
from tasks.eval.util.pod import (
    get_sandbox_id_from_pod_name,
    wait_for_pod_ready_and_get_ts,
)
from tasks.eval.util.setup import cleanup_baseline, setup_baseline
from tasks.util.containerd import (
    get_event_from_containerd_logs,
    get_start_end_ts_for_containerd_event,
    get_ts_for_containerd_event,
)
from tasks.util.k8s import template_k8s_file
from tasks.util.kubeadm import get_pod_names_in_ns, run_kubectl_command
from tasks.util.ovmf import get_ovmf_boot_events
from time import sleep, time


def get_guest_kernel_start_ts(lower_bound=None):
    """
    Get the timestamp of the guest-kernel start-up time, in the journalctl
    clock reference.

    This method greps for one of the kernel boot log messages (`dmesg` style)
    and works out the origin timestamp as the difference from the kernel
    timestamp and the journalctl one (in the host)
    """
    start_kernel_string = "random: crng init done"
    event_json = get_event_from_containerd_logs(
        start_kernel_string, start_kernel_string, 1
    )[0]

    guest_kernel_ts = float(
        re_search(r'vmconsole="\[ *([\.0-9]*)\]', event_json["MESSAGE"]).groups(1)[0]
    )
    journalctl_ts = int(event_json["__REALTIME_TIMESTAMP"]) / 1e6
    ts = journalctl_ts - guest_kernel_ts

    if lower_bound is not None:
        assert (
            ts > lower_bound
        ), "Provided timestamp smaller than lower bound: {} !> {}".format(
            ts, lower_bound
        )

    return ts


def do_run(result_file, num_run, service_file, flavour, warmup=False):
    # Work out if it is an SEV-enabled run
    is_sev = "nosev" not in service_file

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

    # Wait for pod to be ready (we can ignore the return value)
    wait_for_pod_ready_and_get_ts(pod_name)

    if not warmup:
        events_ts = []

        # First, get the total time to create the pod sandbox (aka cVM), and
        # also get the sandbox id from the logs
        start_ts_ps, end_ts_ps = get_start_end_ts_for_containerd_event(
            "RunPodSandbox",
            pod_name,
            lower_bound=start_ts,
            timeout_mins=3,
        )
        events_ts.append(("StartRunPodSandbox", start_ts_ps))
        events_ts.append(("EndRunPodSandbox", end_ts_ps))

        sandbox_id = get_sandbox_id_from_pod_name(pod_name)

        # Starting VM happens briefly after the beginning of RunPodSandbox.
        # To get the start timestamp for starting the VM, we grep for one of
        # the first log messages from the Kata runtime (not containerd)
        start_ts_vmp = get_ts_for_containerd_event(
            "IOMMUPlatform is disabled by default.", sandbox_id, lower_bound=start_ts_ps
        )
        events_ts.append(("StartVMPreparation", start_ts_vmp))
        start_ts_vms = get_ts_for_containerd_event(
            "Starting VM", sandbox_id, lower_bound=start_ts_vmp
        )
        events_ts.append(("StartVMStarted", start_ts_vms))

        # Pre-attestation
        if is_sev:
            start_ts_preatt = get_ts_for_containerd_event(
                "Processing prelaunch attestation", sandbox_id, lower_bound=start_ts_vms
            )
            end_ts_preatt = get_ts_for_containerd_event(
                "Launch secrets injected", sandbox_id, lower_bound=start_ts_preatt
            )
        else:
            start_ts_preatt = start_ts_vms
            end_ts_preatt = start_ts_vms
        events_ts.append(("StartPreAtt", start_ts_preatt))
        events_ts.append(("EndPreAtt", end_ts_preatt))

        # Get the VM started event
        end_ts_vms = get_ts_for_containerd_event(
            "VM started", sandbox_id, lower_bound=end_ts_preatt
        )
        events_ts.append(("EndVMStarted", end_ts_vms))

        # Guest kernel start-end events
        start_ts_gk = get_guest_kernel_start_ts()
        end_guest_kernel_string = "Run /init as init process"
        end_ts_gk = get_ts_for_containerd_event(
            end_guest_kernel_string,
            end_guest_kernel_string,
            lower_bound=start_ts_gk,
        )
        events_ts.append(("StartGuestKernelBoot", start_ts_gk))
        events_ts.append(("EndGuestKernelBoot", end_ts_gk))

        # Get all the events for OVMF
        # Note that we can only get OVMF logs through the serial port, which
        # we redirect to a file. In addition, we don't have a clock in OVMF,
        # so we can only use relative timestamps based on one performance
        # counter and the CPU frequency. Thus, we ARBITRARILY anchor the end
        # of OVMF execution to the start of the guest kernel
        events_ts = get_ovmf_boot_events(events_ts, start_ts_gk)

        # Get the agent started event
        ts_as = get_ts_for_containerd_event(
            "Agent started", sandbox_id, lower_bound=end_ts_vms
        )
        events_ts.append(("AgentStarted", ts_as))

        # Once the agent has started, the sandbox is essentially almost ready
        # to go, so we don't really need to print many more things

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
    Run a comparison of SEV/non-SEV OVMF execution
    """
    baselines_to_run = ["coco-fw-sig-enc", "coco-nosev-ovmf"]
    if baseline is not None:
        if baseline not in baselines_to_run:
            raise RuntimeError(
                "Unrecognised baseline ({}) must be one in: {}".format(
                    baseline, baselines_to_run
                )
            )
        baselines_to_run = [baseline]

    service_template_file = join(APPS_DIR, "ovmf-detail", "service.yaml.j2")
    image_name = "csegarragonz/coco-helloworld-py"
    used_images = ["csegarragonz/coco-knative-sidecar", image_name]
    num_runs = 1

    results_dir = join(RESULTS_DIR, "ovmf-detail")
    if not exists(results_dir):
        makedirs(results_dir)

    if not exists(EVAL_TEMPLATED_DIR):
        makedirs(EVAL_TEMPLATED_DIR)

    for bline in baselines_to_run:
        baseline_traits = BASELINES[bline]

        # First, template the service file
        service_file = join(
            EVAL_TEMPLATED_DIR, "apps_ovmf-detail_{}_service.yaml".format(bline)
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

        for flavour in ["cold"]:
            # Prepare the result file
            result_file = join(results_dir, "{}_{}.csv".format(bline, flavour))
            init_csv_file(result_file, "Run,Event,TimeStampMs")

            if flavour == "warm":
                print("Executing baseline {} warmup run...".format(bline))
                try:
                    do_run(result_file, -1, service_file, flavour, warmup=True)
                except TypeError:
                    cleanup_after_run(bline, used_images)
                    cleanup_baseline(bline)
                    raise RuntimeError("Error executing {} warmup run!".format(bline))

                sleep(INTER_RUN_SLEEP_SECS)

            if flavour == "cold":
                # `cold` happens after `warm`, so we want to clean-up after
                # all the `warm` runs
                cleanup_after_run(bline, used_images)

            for nr in range(num_runs):
                print(
                    "Executing baseline {} ({}) run {}/{}...".format(
                        bline, flavour, nr + 1, num_runs
                    )
                )
                try:
                    do_run(result_file, nr, service_file, flavour)
                except TypeError:
                    cleanup_after_run(bline, used_images)
                    cleanup_baseline(bline)
                    raise RuntimeError("Error executing {}!".format(bline))

                sleep(INTER_RUN_SLEEP_SECS)

                if flavour == "cold":
                    cleanup_after_run(bline, used_images)

        cleanup_baseline(bline)


@task
def process_logs(ctx, baseline="coco-fw-sig-enc"):
    # Fake the guest kernel start ts by reading it from a file
    with open("./eval/results/ovmf-detail/{}_cold.csv".format(baseline), "r") as fh:
        for line in fh:
            if "StartGuestKernelBoot" in line:
                start_guest_kernel_ts = float(line.split(",")[-1])
    ovmf_events = get_ovmf_boot_events([], start_guest_kernel_ts)
    ovmf_events = sorted(ovmf_events, key=lambda x: x[1])

    zero_ts = ovmf_events[0][1]
    for ev, ts in ovmf_events:
        print("{}: {} s".format(ev, ts - zero_ts))
    # print(ovmf_events)


# ---------
# Useful maps to plot the experiments
# ---------

ordered_events = {
    "ovmf-boot": ("StartOVMFBoot", "EndOVMFBoot"),
    "pei": ("StartOVMFPeiCore", "EndOVMFPeiCore"),
    "load-dxe": ("StartOVMFDxeLoadCore", "EndOVMFDxeLoadCore"),
    "dxe": ("StartOVMFDxeMain", "EndOVMFDxeMain"),
    # TODO: better labels for this events
    "dxe-ctors": ("TEMPP-23", "TEMPP-3"),
    "dxe-dispatch": ("StartOVMFCoreDispatcher", "EndOVMFCoreDispatcher"),
    "bds": ("StartOVMFBdsEntry", "EndOVMFBdsEntry"),
}
height_for_event = {
    "ovmf-boot": 0,
    "pei": 1,
    "load-dxe": 1,
    "dxe": 1,
    "dxe-ctors": 2,
    "dxe-dispatch": 2,
    "bds": 1,
}
color_for_event = {
    "ovmf-boot": "red",
    "pei": "purple",
    "load-dxe": "orange",
    "dxe": "green",
    "dxe-ctors": "yellow",
    "dxe-dispatch": "gray",
    "bds": "brown",
}


def do_flame_plot(ax, results_dict):
    assert list(ordered_events.keys()) == list(height_for_event.keys())
    assert list(color_for_event.keys()) == list(height_for_event.keys())

    bar_height = 0.5
    # Y coordinate of the bar
    ys = []
    # Width of each bar
    widths = []
    # x-axis offset of each bar
    xs = []
    labels = []
    colors = []

    x_rlim = 0
    x_origin = results_dict["StartOVMFBoot"]["mean"]
    for event in ordered_events:
        start_ev = ordered_events[event][0]
        end_ev = ordered_events[event][1]
        x_left = results_dict[start_ev]["mean"]
        x_right = results_dict[end_ev]["mean"]
        widths.append(x_right - x_left)
        xs.append(x_left - x_origin)
        ys.append(height_for_event[event] * bar_height)
        labels.append(event)
        colors.append(color_for_event[event])

        if event == "ovmf-boot":
            x_rlim = x_right - x_left

    ax.barh(
        ys,
        widths,
        height=bar_height,
        left=xs,
        align="edge",
        label=labels,
        color=colors,
    )

    return x_rlim


@task
def plot(ctx):
    """
    Plot a detailed comparison of sev and non-sev OVMF flame graphs

    We plot two graphs side-by-side. On the left, a detailed flame graph
    corresponding _only_ to OVMF execution for `coco-nosev-ovmf` and
    `coco-fw-sig-enc`. It is important that, in this plot, we print the same
    events for both flame graphs. On the right then, we print the slowdown
    for each of the aforementioned events calculated as time_sev / time_nosev.
    """
    results_dir = join(RESULTS_DIR, "ovmf-detail")
    plots_dir = join(PLOTS_DIR, "ovmf-detail")
    glob_str = join(results_dir, "*_cold.csv")

    # Collect results
    results_dict = {}
    for result_file in glob(glob_str):
        baseline = basename(result_file).split("_")[0]

        if baseline not in results_dict:
            results_dict[baseline] = {}

        results = read_csv(result_file)
        groupped = results.groupby("Event", as_index=False)
        events = groupped.mean()["Event"].to_list()
        for ind, event in enumerate(events):
            # NOTE: these timestamps are in seconds
            results_dict[baseline][event] = {
                "mean": groupped.mean()["TimeStampMs"].to_list()[ind],
                "sem": groupped.sem()["TimeStampMs"].to_list()[ind],
                "list": groupped.get_group(event)["TimeStampMs"].to_list(),
            }

    fig = figure(figsize=(8, 6))
    ax1 = fig.add_subplot(2, 2, 1)
    ax2 = fig.add_subplot(2, 2, 3)
    ax3 = fig.add_subplot(2, 2, 2)
    ax4 = fig.add_subplot(2, 2, 4)

    # -------------------------
    # LHS: two flame-graphs one on top of the other
    # -------------------------

    x_rlim = 0
    flame_axes = [ax1, ax2]
    for ax, bline in zip(flame_axes, ["coco-fw-sig-enc", "coco-nosev-ovmf"]):
        this_x_rlim = do_flame_plot(ax, results_dict[bline])
        x_rlim = max(x_rlim, this_x_rlim)
        ax.set_xlabel("Time [s]")
        ax.tick_params(
            axis="y", which="both", left=False, right=False, labelbottom=False
        )
        ax.set_yticklabels([])
        ax.set_title("Baseline: {}".format(bline))

    # Update the x limit
    for ax in flame_axes:
        ax.set_xlim(left=0, right=x_rlim)

    ax1.spines.bottom.set_visible(False)
    ax1.tick_params(bottom=False, labelbottom=False)
    ax1.set_xlabel("")

    # -------------------------
    # RHS: slowdown per event
    # -------------------------

    slowdown = {}
    for ev in ordered_events:
        start_ev = ordered_events[ev][0]
        end_ev = ordered_events[ev][1]

        duration_nosev = (
            results_dict["coco-nosev-ovmf"][end_ev]["mean"]
            - results_dict["coco-nosev-ovmf"][start_ev]["mean"]
        )
        duration_sev = (
            results_dict["coco-fw-sig-enc"][end_ev]["mean"]
            - results_dict["coco-fw-sig-enc"][start_ev]["mean"]
        )
        slowdown[ev] = duration_sev / duration_nosev

    xlabels = list(slowdown.keys())
    xs = range(1, len(xlabels) + 1)
    ys = [slowdown[x] for x in xlabels]
    color = [color_for_event[x] for x in xlabels]

    # Make the effect of a broken axis to plot the outlier
    ax3.bar(xs, ys, color=color)
    ax4.bar(xs, ys, color=color)
    ax3.set_ylim(18, 20)
    ax3.set_yticks([19, 20])
    ax4.set_ylim(0, 7.5)
    # hide the spines between ax and ax2
    ax3.spines.bottom.set_visible(False)
    ax4.spines.top.set_visible(False)
    ax4.xaxis.tick_top()
    ax3.tick_params(labeltop=False, bottom=False, labelbottom=False)
    ax4.xaxis.tick_bottom()
    # Diagonal lines in the axes
    d = 0.5  # proportion of vertical to horizontal extent of the slanted line
    kwargs = dict(
        marker=[(-1, -d), (1, d)],
        markersize=12,
        linestyle="none",
        color="k",
        mec="k",
        mew=1,
        clip_on=False,
    )
    ax3.plot([0, 1], [0, 0], transform=ax3.transAxes, **kwargs)
    ax4.plot([0, 1], [1, 1], transform=ax4.transAxes, **kwargs)
    fig.subplots_adjust(hspace=0.05)  # adjust space between axes
    ax4.axhline(y=1, color="black", linestyle="--")
    ax3.set_title("OVMF Boot Event Slowdown")
    ax4.set_ylabel("Slowdon [fw-sig-enc/nosev-ovmf]")
    ax4.yaxis.set_label_coords(-0.1, 1)

    # Set the labels
    ax4.set_xticks(xs)
    ax4.set_xticklabels(xlabels, rotation=45)

    # fig.suptitle("VM Start-Up with different guest memory sizes")
    # fig.subplots_adjust(hspace=0.5)

    for plot_format in ["pdf", "png"]:
        plot_file = join(plots_dir, "ovmf_detail.{}".format(plot_format))
        fig.savefig(plot_file, format=plot_format, bbox_inches="tight")
