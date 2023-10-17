from json import loads as json_loads
from subprocess import run
from time import sleep


def get_journalctl_containerd_logs():
    journalctl_cmd = 'sudo journalctl -xeu containerd --since "10 min ago" -o json'
    out = (
        run(journalctl_cmd, shell=True, capture_output=True)
        .stdout.decode("utf-8")
        .strip()
        .split("\n")
    )
    return out


def get_time_pulling_image(image_name):
    """
    Retrieve the start and end timestamp (in epoch floating seconds) for the
    PullImage event from containerd
    """
    out = get_journalctl_containerd_logs()

    pull_image_json = []
    for o in out:
        o_json = json_loads(o)
        if "PullImage" in o_json["MESSAGE"] and image_name in o_json["MESSAGE"]:
            pull_image_json.append(o_json)

    assert len(pull_image_json) >= 2

    start_ts = int(pull_image_json[-2]["__REALTIME_TIMESTAMP"]) / 1e6
    end_ts = int(pull_image_json[-1]["__REALTIME_TIMESTAMP"]) / 1e6

    return start_ts, end_ts


def get_start_end_ts_for_containerd_event(event_name, event_id, lower_bound=None):
    """
    Get the start and end timestamps (in epoch floating seconds) for a given
    event from the containerd journalctl logs
    """
    # Parsing from `journalctl` is slightly hacky, and prone to spurious
    # errors. We put a lot of assertions here to make sure that the timestamps
    # we read are the adequate ones, thus we allow some failures and retry
    num_repeats = 3
    backoff_secs = 3
    for i in range(num_repeats):
        try:
            out = get_journalctl_containerd_logs()

            event_json = []
            for o in out:
                o_json = json_loads(o)
                if event_name in o_json["MESSAGE"] and event_id in o_json["MESSAGE"]:
                    event_json.append(o_json)

            assert len(event_json) >= 2

            start_ts = int(event_json[-2]["__REALTIME_TIMESTAMP"]) / 1e6
            end_ts = int(event_json[-1]["__REALTIME_TIMESTAMP"]) / 1e6

            assert end_ts > start_ts

            if lower_bound is not None:
                assert start_ts > lower_bound

            return start_ts, end_ts
        except AssertionError:
            print(
                "WARNING: Failed getting event {} (attempt {}/{})".format(
                    event_name,
                    i + 1,
                    num_repeats,
                )
            )
            sleep(backoff_secs)
            continue
