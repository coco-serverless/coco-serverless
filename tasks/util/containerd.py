from json import loads as json_loads
from subprocess import run
from time import sleep


def get_journalctl_containerd_logs():
    journalctl_cmd = 'sudo journalctl -xeu containerd --since "1 min ago" -o json'
    out = (
        run(journalctl_cmd, shell=True, capture_output=True)
        .stdout.decode("utf-8")
        .strip()
        .split("\n")
    )
    return out


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
                if (
                    o_json is None
                    or "MESSAGE" not in o_json
                    or o_json["MESSAGE"] is None
                ):
                    # Sometimes, after resetting containerd, some of the
                    # journal messages won't have a "MESSAGE" in it, so we skip
                    # them
                    continue
                try:
                    if (
                        event_name in o_json["MESSAGE"]
                        and event_id in o_json["MESSAGE"]
                    ):
                        event_json.append(o_json)
                except TypeError as e:
                    print(o_json)
                    print(e)
                    raise e

            assert len(event_json) >= 2, "Not enough events in log: {} !>= 2".format(
                len(event_json)
            )

            start_ts = int(event_json[-2]["__REALTIME_TIMESTAMP"]) / 1e6
            end_ts = int(event_json[-1]["__REALTIME_TIMESTAMP"]) / 1e6

            assert (
                end_ts > start_ts
            ), "End and start timestamp not in order: {} !> {}".format(end_ts, start_ts)

            if lower_bound is not None:
                assert (
                    start_ts > lower_bound
                ), "Provided timestamp smaller than lower bound: {} !> {}".format(
                    start_ts, lower_bound
                )

            return start_ts, end_ts
        except AssertionError as e:
            print(e)
            print(
                "WARNING: Failed getting event {} (id: {}) (attempt {}/{})".format(
                    event_name,
                    event_id,
                    i + 1,
                    num_repeats,
                )
            )
            sleep(backoff_secs)
            continue
