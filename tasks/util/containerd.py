from json import loads as json_loads
from subprocess import run


def get_time_pulling_image(image_name):
    """
    Retrieve the start and end timestamp (in epoch floating seconds) for the
    PullImage event from containerd
    """
    journalctl_cmd = "sudo journalctl -xeu containerd --since \"10 min ago\" -o json"
    out = run(journalctl_cmd, shell=True, capture_output=True).stdout.decode("utf-8").strip().split("\n")
    pull_image_json = []
    for o in out:
        o_json = json_loads(o)
        image_name = "coco-helloworld-py"
        if "PullImage" in o_json["MESSAGE"] and image_name in o_json["MESSAGE"]:
            pull_image_json.append(o_json)

    assert len(pull_image_json) >= 2

    start_ts = int(pull_image_json[-2]["__REALTIME_TIMESTAMP"]) / 1e6
    end_ts = int(pull_image_json[-1]["__REALTIME_TIMESTAMP"]) / 1e6

    return start_ts, end_ts
