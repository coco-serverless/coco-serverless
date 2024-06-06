import re
from datetime import datetime, timedelta
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
from tasks.util.containerd import get_start_end_ts_for_containerd_event, get_ts_for_containerd_event, get_event_from_containerd_logs
from tasks.util.k8s import get_container_id_from_pod, template_k8s_file
from tasks.util.kubeadm import get_pod_names_in_ns, run_kubectl_command
from time import sleep, time

CSG_MAGIC_BEGIN = "CSG-M4GIC: B3G1N: {}"
CSG_MAGIC_END = "CSG-M4GIC: END: {}"



blob_ids = [
    "7f56387226e70ce21a149045482d2146fba827021d8ee9d0c063cbdb1d771506",
    "5d1ffbf03dfd7abe95a301340a2ad76433606f2159eef4336311c0abc3fdd01b",
    "0c2f179fe0a1bf25f887b1a160547187f56c3eec2832ad27089af6fbf968f4ca",
    "56e8c72352c9982c4e093720e88be857bf720adb0e5b9f8281bbadd56ea38c2d",
    "09be425e109d1fdd2dbb9df95970a06ffdcbac9e6449aafea6693f9d4317198e",
    "e6afae4885123a820c042d95491276b70678a2431806d5b6c254ea5ddefa4962",
    "9eef7af31f2e72be0e1de3305ff3b85afdf6031cbc68cf68b2fadee1e1f26a9c",
    "0ed07411d8954cb951acc9f64a2ce87d4c675c87681c96b695af46a655cd9369",
    "4637b4ceed70b7e7603c8b0b288580b6b5858c1c94f91cd4e422ccee1a1d72f9",
    "0d6c7f635bfb09b3b2df91e295be099b05364412934bc4fe453329e993281dae",
    "ca24d41828ba46b5654d68bd0857564f4884725aae57f7207e2cdb2bf20ce6d1",
    "76b29cde971e3d15e582673daaee023aa4e9378101603b8ea08ca63ea4d1febf",
    "7307fdea7fb000e04c0e8a2dfeb82e7504583a4af20c4dab5424673dac99f6e6",
    "879ebf56a22543af767b1160e87be2ade87219b51205a646bd643a28c3844ebe",
    "92182a3da467585a1d95ae40f7743d7fe26ca7a90a50681ff55fb2ec6f37b00d",
  ]

def get_timestamps_for_blob(blob_id):
    
    start_ts = None
    increment = 20
    counter = 20

    try:
        pull_start_ts = get_ts_for_containerd_event(
                        CSG_MAGIC_BEGIN.format("KS (nydus) calling"), blob_id, start_ts, extra_event_id=f"counter: {counter}", timeout_mins=None,
            )

        pull_end_ts = get_ts_for_containerd_event(
                        CSG_MAGIC_END.format("KS (nydus) blob_id:"), blob_id, start_ts, extra_event_id=f"counter: {counter}", timeout_mins=None,
            )

        events_found = True
        timestamps = [(pull_start_ts, pull_end_ts)]
        counter += increment
    except Exception as e:
        print(f"Events not found for counter: {counter}, blob_id: {blob_id}")
        timestamps = []
        events_found = False

    while events_found:
        try:
            pull_start_ts = get_ts_for_containerd_event(
                            CSG_MAGIC_BEGIN.format("KS (nydus) calling"), blob_id, start_ts, extra_event_id=f"counter: {counter}", timeout_mins=None,
                )

            pull_end_ts = get_ts_for_containerd_event(
                            CSG_MAGIC_END.format("KS (nydus) blob_id:"), blob_id, start_ts, extra_event_id=f"counter: {counter}", timeout_mins=None,
                )

            events_found = True
            timestamps.append((pull_start_ts, pull_end_ts))
            counter += increment
        except Exception as e:
            print(f"Events not found for counter: {counter}, blob_id: {blob_id}")
            events_found = False

    return timestamps


@task
def get_pull_duartions(ctx, baseline=None):

    blob_ids = ["4637b4ceed70b7e7603c8b0b288580b6b5858c1c94f91cd4e422ccee1a1d72f9"
        ,"0d6c7f635bfb09b3b2df91e295be099b05364412934bc4fe453329e993281dae"
        ,"92182a3da467585a1d95ae40f7743d7fe26ca7a90a50681ff55fb2ec6f37b00d"]   

    start_ts = get_ts_for_containerd_event(
                        "KS (nydus) cache file", "CSG", None, timeout_mins=None,
            )

    print(start_ts)

    pull_duration = 0
    for blob_id in blob_ids:
        try:
            event_json = get_event_from_containerd_logs(
                CSG_MAGIC_END.format("KS (nydus) blob_id:"), blob_id, 1, timeout_mins=None,
            )[0]
        except:
            continue

        msg = str(event_json["MESSAGE"])

        print(msg)
        pattern = r"total time spent: ([\d\.]+)([a-z]+)"
        match = re.search(pattern, msg)

        print(match)
        duration = float(match.group(1))
        time_unit = match.group(2)

        if time_unit == "ms":
            duration /= 1000


        pull_duration += duration

        if blob_id == blob_ids[-1]:
            end_ts = int(event_json["__REALTIME_TIMESTAMP"]) / 1e6
        
        print(duration)

    total_duration = end_ts - start_ts

    print(f"Pull duration {pull_duration}")
    print(f"Total duration {total_duration}")
