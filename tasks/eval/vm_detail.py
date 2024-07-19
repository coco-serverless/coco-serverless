from glob import glob
from invoke import task
from matplotlib.patches import Patch
from matplotlib.pyplot import subplots
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
    GITHUB_USER,
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
from tasks.util.kata import get_default_vm_mem_size, update_vm_mem_size
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

    # Capture QEMU PID as soon as possible
    # NOTE: uncomment to generate a flame graph of the QEMU process
    # qemu_pid = get_qemu_pid(0.05)
    # flame_path = "/tmp/qemu.svg"
    # print("Generating QEMU flame graph... (PID: {})".format(qemu_pid))
    # generate_flame_graph(qemu_pid, 20, flame_path)
    # print("Done generating QEMU flame graph. Saved file at: {}".format(flame_path))

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
        if is_sev:
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
    Detailed break-down of the start-up latency of the cVM in the service

    This benchmark digs deeper into the costs associated with just spinning up
    the confidnetial VM (and kata agent) as part of the bootstrap of a Knative
    service on CoCo
    """
    baselines_to_run = ["coco-fw-sig-enc", "coco-nosev", "coco-nosev-ovmf"]
    if baseline is not None:
        if baseline not in baselines_to_run:
            raise RuntimeError(
                "Unrecognised baseline ({}) must be one in: {}".format(
                    baseline, baselines_to_run
                )
            )
        baselines_to_run = [baseline]

    mem_size_mult = [1, 64]
    service_template_file = join(APPS_DIR, "vm-detail", "service.yaml.j2")
    image_name = f"{GITHUB_USER}/coco-helloworld-py"
    used_images = [f"{GITHUB_USER}/coco-knative-sidecar", image_name]
    num_runs = 1

    results_dir = join(RESULTS_DIR, "vm-detail")
    if not exists(results_dir):
        makedirs(results_dir)

    if not exists(EVAL_TEMPLATED_DIR):
        makedirs(EVAL_TEMPLATED_DIR)

    for bline in baselines_to_run:
        baseline_traits = BASELINES[bline]

        # First, template the service file
        service_file = join(
            EVAL_TEMPLATED_DIR, "apps_vm-detail_{}_service.yaml".format(bline)
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

        # Third, get the default VM memory size to be able to reset it later
        default_vm_mem_size = get_default_vm_mem_size(baseline_traits["conf_file"])

        for mem_size in mem_size_mult:
            update_vm_mem_size(
                baseline_traits["conf_file"], mem_size * default_vm_mem_size
            )

            for flavour in ["cold"]:
                # Prepare the result file
                result_file = join(
                    results_dir, "{}_{}_{}.csv".format(bline, mem_size, flavour)
                )
                init_csv_file(result_file, "Run,Event,TimeStampMs")

                if flavour == "warm":
                    print("Executing baseline {} warmup run...".format(bline))
                    try:
                        do_run(result_file, -1, service_file, flavour, warmup=True)
                    except TypeError:
                        cleanup_after_run(bline, used_images)
                        cleanup_baseline(bline)
                        raise RuntimeError(
                            "Error executing {} warmup run!".format(bline)
                        )

                    sleep(INTER_RUN_SLEEP_SECS)

                if flavour == "cold":
                    # `cold` happens after `warm`, so we want to clean-up after
                    # all the `warm` runs
                    cleanup_after_run(bline, used_images)

                for nr in range(num_runs):
                    print(
                        "Executing baseline {} ({}, {} GB mem) run {}/{}...".format(
                            bline, flavour, mem_size, nr + 1, num_runs
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


# ---------
# Useful maps to plot the experiments
# ---------

ordered_events = {
    "make-pod-sandbox": ("StartRunPodSandbox", "EndRunPodSandbox"),
    "host-setup": ("StartVMPreparation", "EndVMStarted"),
    "start-vm": ("StartVMStarted", "EndVMStarted"),
    "pre-attestation": ("StartPreAtt", "EndPreAtt"),
    "guest-setup": ("EndVMStarted", "AgentStarted"),
    "ovmf-booting": ("StartOVMFBoot", "EndOVMFBoot"),
    "ovmf-dxe": ("StartOVMFDxeMain", "EndOVMFDxeMain"),
    "ovmf-measure-verify": ("StartOVMFVerify", "EndOVMFVerify"),
    "guest-kernel": ("StartGuestKernelBoot", "EndGuestKernelBoot"),
    "kata-agent": ("EndGuestKernelBoot", "AgentStarted"),
}
height_for_event = {
    "make-pod-sandbox": 0,
    "host-setup": 1,
    "start-vm": 2,
    "pre-attestation": 3,
    "guest-setup": 1,
    "ovmf-booting": 2,
    "ovmf-dxe": 3,
    "ovmf-measure-verify": 4,
    "guest-kernel": 2,
    "kata-agent": 2,
}
color_for_event = {
    "make-pod-sandbox": "red",
    "host-setup": "purple",
    "start-vm": "orange",
    "pre-attestation": "green",
    "guest-setup": "yellow",
    "ovmf-booting": "gray",
    "ovmf-dxe": "brown",
    "ovmf-measure-verify": "olive",
    "guest-kernel": "blue",
    "kata-agent": "pink",
}


def do_flame_plot(ax, results_dict, legend_on_bars=False, nosev=False):
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

    # Helper list to know which labels don't fit in their bar. Alas, I have not
    # found a way to programatically place them well, so the (x, y) coordinates
    # for this labels will have to be hard-coded
    short_bars = {
        "pre-attestation": (1, bar_height * 3.5),
        "kata-agent": (5.5, bar_height * 3.1),
        "ovmf-measure-verify": (4.5, bar_height * 4.5),
        "guest-kernel": (5.2, bar_height * 2.5),
    }
    nosev_skip_events = [
        "pre-attestation",
        "ovmf-booting",
        "ovmf-dxe",
        "ovmf-measure-verify",
    ]

    x_rlim = 0
    x_origin = results_dict["StartRunPodSandbox"]["mean"]
    for event in ordered_events:
        # Skip events that don't happen in a non-SEV boot
        if nosev and event in nosev_skip_events:
            continue

        start_ev = ordered_events[event][0]
        end_ev = ordered_events[event][1]
        x_left = results_dict[start_ev]["mean"]
        x_right = results_dict[end_ev]["mean"]
        widths.append(x_right - x_left)
        xs.append(x_left - x_origin)
        ys.append(height_for_event[event] * bar_height)
        labels.append(event)
        colors.append(color_for_event[event])

        if event == "make-pod-sandbox":
            x_rlim = x_right - x_left

        # Print the label inside the bar
        if legend_on_bars:
            if event in list(short_bars.keys()):
                x_text = short_bars[event][0]
                y_text = short_bars[event][1]
            else:
                x_text = x_left - x_origin + (x_right - x_left) / 4
                y_text = (height_for_event[event] + 0.4) * bar_height

            ax.text(x_text, y_text, event)

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
    Plot a flame-graph of the VM start-up process
    """
    results_dir = join(RESULTS_DIR, "vm-detail")
    plots_dir = join(PLOTS_DIR, "vm-detail")
    # baseline = "coco-fw-sig-enc"
    # results_file = join(results_dir, "{}_cold.csv".format(baseline))
    glob_str = join(results_dir, "*_cold.csv")

    # Collect results
    results_dict = {}
    for result_file in glob(glob_str):
        baseline = basename(result_file).split("_")[0]
        mem_mult = basename(result_file).split("_")[1]

        if baseline not in results_dict:
            results_dict[baseline] = {}
        if mem_mult not in results_dict[baseline]:
            results_dict[baseline][mem_mult] = {}

        results = read_csv(result_file)
        groupped = results.groupby("Event", as_index=False)
        events = groupped.mean()["Event"].to_list()
        for ind, event in enumerate(events):
            # NOTE: these timestamps are in seconds
            results_dict[baseline][mem_mult][event] = {
                "mean": groupped.mean()["TimeStampMs"].to_list()[ind],
                "sem": groupped.sem()["TimeStampMs"].to_list()[ind],
                "list": groupped.get_group(event)["TimeStampMs"].to_list(),
            }

    # -----------------------
    # First, one single flame graph of the default config in one file
    # -----------------------

    # (baseline = "coco-fw-sig-enc" and mem_mult=1)
    fig, ax = subplots()
    do_flame_plot(ax, results_dict["coco-fw-sig-enc"]["1"], legend_on_bars=True)
    ax.set_xlabel("Time [s]")
    ax.tick_params(axis="y", which="both", left=False, right=False, labelbottom=False)
    ax.set_yticklabels([])
    title_str = "Breakdown of the time to start a CoCo sandbox\n"
    title_str += "(baseline: {}, mem_size: {} GB)".format(
        baseline,
        int(get_default_vm_mem_size() / 1024),
    )
    ax.set_title(title_str)
    for plot_format in ["pdf", "png"]:
        plot_file = join(plots_dir, "vm_detail.{}".format(plot_format))
        fig.savefig(plot_file, format=plot_format, bbox_inches="tight")

    # -----------------------
    # Second, two flame graphs on top of each other with the two different mem
    # -----------------------

    # mults and shared y
    fig, axes = subplots(ncols=1, nrows=2)
    x_rlim = 0
    for ax, mem_mult in zip(axes, ["1", "64"]):
        this_x_rlim = do_flame_plot(
            ax, results_dict["coco-fw-sig-enc"][mem_mult], legend_on_bars=False
        )
        x_rlim = max(x_rlim, this_x_rlim)
        ax.set_xlabel("Time [s]")
        ax.tick_params(
            axis="y", which="both", left=False, right=False, labelbottom=False
        )
        ax.set_yticklabels([])
        ax.set_title(
            "Memory size: {} GB".format(
                int(int(mem_mult) * get_default_vm_mem_size() / 1024)
            )
        )

    # Update the x limit
    for ax in axes:
        ax.set_xlim(left=0, right=x_rlim)

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
    axes[0].legend(handles=legend_handles, ncols=2)

    fig.suptitle("VM Start-Up with different guest memory sizes")
    fig.subplots_adjust(hspace=0.5)

    for plot_format in ["pdf", "png"]:
        plot_file = join(plots_dir, "vm_detail_multimem.{}".format(plot_format))
        fig.savefig(plot_file, format=plot_format, bbox_inches="tight")

    # -----------------------
    # Third, two flame graphs on top of each other with SEV/no-SEV (w/ out OVMF)
    # -----------------------

    fig, axes = subplots(ncols=1, nrows=2)
    x_rlim = 0
    for ax, bline in zip(axes, ["coco-fw-sig-enc", "coco-nosev"]):
        this_x_rlim = do_flame_plot(
            ax, results_dict[bline]["1"], legend_on_bars=False, nosev="nosev" in bline
        )
        x_rlim = max(x_rlim, this_x_rlim)
        ax.set_xlabel("Time [s]")
        ax.tick_params(
            axis="y", which="both", left=False, right=False, labelbottom=False
        )
        ax.set_yticklabels([])
        ax.set_title("Baseline: {}".format(bline))

    # Update the x limit
    for ax in axes:
        ax.set_xlim(left=0, right=x_rlim)

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
    axes[1].legend(handles=legend_handles, ncols=2)

    fig.suptitle("VM Start-Up with different SEV configurations")
    fig.subplots_adjust(hspace=0.5)

    for plot_format in ["pdf", "png"]:
        plot_file = join(plots_dir, "vm_detail_multisev.{}".format(plot_format))
        fig.savefig(plot_file, format=plot_format, bbox_inches="tight")

    # -----------------------
    # Fourth, two flame graphs on top of each other with SEV/no-SEV (w/ OVMF)
    # -----------------------

    fig, axes = subplots(ncols=1, nrows=2)
    x_rlim = 0
    for ax, bline in zip(axes, ["coco-fw-sig-enc", "coco-nosev-ovmf"]):
        this_x_rlim = do_flame_plot(
            ax, results_dict[bline]["1"], legend_on_bars=False, nosev="nosev" in bline
        )
        x_rlim = max(x_rlim, this_x_rlim)
        ax.set_xlabel("Time [s]")
        ax.tick_params(
            axis="y", which="both", left=False, right=False, labelbottom=False
        )
        ax.set_yticklabels([])
        ax.set_title("Baseline: {}".format(bline))

    # Update the x limit
    for ax in axes:
        ax.set_xlim(left=0, right=x_rlim)

    fig.suptitle("VM Start-Up with different SEV configurations")
    fig.subplots_adjust(hspace=0.5)

    for plot_format in ["pdf", "png"]:
        plot_file = join(plots_dir, "vm_detail_multisev_ovmf.{}".format(plot_format))
        fig.savefig(plot_file, format=plot_format, bbox_inches="tight")
