from glob import glob
from invoke import task
from matplotlib.patches import Patch
from matplotlib.pyplot import subplots
from numpy import array as np_array, mean as np_mean
from os import makedirs
from os.path import basename, exists, join
from pandas import read_csv
from re import search as re_search
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
from tasks.eval.util.pod import (
    get_sandbox_id_from_pod_name,
    wait_for_pod_ready_and_get_ts,
)
from tasks.eval.util.setup import setup_baseline
from tasks.util.containerd import (
    get_event_from_containerd_logs,
    get_start_end_ts_for_containerd_event,
    get_ts_for_containerd_event,
)
from tasks.util.flame import generate_flame_graph
from tasks.util.k8s import get_container_id_from_pod, template_k8s_file
from tasks.util.kubeadm import get_pod_names_in_ns, run_kubectl_command
from tasks.util.qemu import get_qemu_pid
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

    # print(event_json["MESSAGE"])
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
    start_ts = time()

    # Silently start
    run_kubectl_command("apply -f {}".format(service_file), capture_output=True)

    # Capture QEMU PID as soon as possible
    qemu_pid = get_qemu_pid(0.05)
    flame_path = "/tmp/qemu.svg"
    print("Generating QEMU flame graph... (PID: {})".format(qemu_pid))
    generate_flame_graph(qemu_pid, 20, flame_path)
    print("Done generating QEMU flame graph. Saved file at: {}".format(flame_path))

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
        # What to do with this event? It is just a set-up step I think
        # start_ts_preatt = get_ts_for_containerd_event("Set up prelaunch attestation", sandbox_id, lower_bound=start_ts_vms)
        start_ts_preatt = get_ts_for_containerd_event(
            "Processing prelaunch attestation", sandbox_id, lower_bound=start_ts_vms
        )
        end_ts_preatt = get_ts_for_containerd_event(
            "Launch secrets injected", sandbox_id, lower_bound=start_ts_preatt
        )
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
def run(ctx):
    """
    Detailed break-down of the start-up latency of the cVM in the service

    This benchmark digs deeper into the costs associated with just spinning up
    the confidnetial VM (and kata agent) as part of the bootstrap of a Knative
    service on CoCo
    """
    baselines_to_run = ["coco-fw-sig-enc"]
    service_template_file = join(APPS_DIR, "vm-detail", "service.yaml.j2")
    image_name = "csegarragonz/coco-helloworld-py"
    used_images = ["csegarragonz/coco-knative-sidecar", image_name]
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

        for flavour in ["cold"]:  # BASELINE_FLAVOURS:
            # Prepare the result file
            result_file = join(results_dir, "{}_{}.csv".format(bline, flavour))
            init_csv_file(result_file, "Run,Event,TimeStampMs")

            if flavour == "warm":
                print("Executing baseline {} warmup run...".format(bline))
                do_run(result_file, -1, service_file, flavour, warmup=True)
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
                do_run(result_file, nr, service_file, flavour)
                sleep(INTER_RUN_SLEEP_SECS)

                if flavour == "cold":
                    cleanup_after_run(bline, used_images)


@task
def plot(ctx):
    """
    Plot a flame-graph of the VM start-up process
    """
    results_dir = join(RESULTS_DIR, "vm-detail")
    plots_dir = join(PLOTS_DIR, "vm-detail")
    baseline = "coco-fw-sig-enc"
    results_file = join(results_dir, "{}_cold.csv".format(baseline))

    results_dict = {}
    results = read_csv(results_file)
    groupped = results.groupby("Event", as_index=False)
    events = groupped.mean()["Event"].to_list()
    for ind, event in enumerate(events):
        # NOTE: these timestamps are in seconds
        results_dict[event] = {
            "mean": groupped.mean()["TimeStampMs"].to_list()[ind],
            "sem": groupped.sem()["TimeStampMs"].to_list()[ind],
            "list": groupped.get_group(event)["TimeStampMs"].to_list(),
        }

    # Useful maps to plot the experiments
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

    # Helper list to know which labels don't fit in their bar. Alas, I have not
    # found a way to programatically place them well, so the (x, y) coordinates
    # for this labels will have to be hard-coded
    short_bars = {
        "pre-attestation": (1, bar_height * 3.5),
        "kata-agent": (5.5, bar_height * 3.1),
        "ovmf-measure-verify": (4.5, bar_height * 4.5),
        "guest-kernel": (5.2, bar_height * 2.5),
    }

    x_origin = results_dict["StartRunPodSandbox"]["mean"]
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

        # Print the label inside the bar
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

    # Misc
    ax.set_xlabel("Time [s]")
    ax.tick_params(axis="y", which="both", left=False, right=False, labelbottom=False)
    ax.set_yticklabels([])
    title_str = "Breakdown of the time to start a CoCo sandbox\n"
    title_str += "(baseline: {})".format(
        baseline,
    )
    ax.set_title(title_str)

    for plot_format in ["pdf", "png"]:
        plot_file = join(plots_dir, "vm_detail.{}".format(plot_format))
        fig.savefig(plot_file, format=plot_format, bbox_inches="tight")
