from os.path import join
from subprocess import run
from tasks.util.env import COCO_ROOT, PROJ_ROOT

NYDUS_CONFIG_FILE = join(COCO_ROOT, "share", "nydus-snapshotter", "config-coco-guest-pulling.toml")
NYDUSIFY_PATH = join(PROJ_ROOT, "bin", "nydusify")


def nydusify(src_tag, dst_tag):
    # Note that nydusify automatically pushes the image
    result = run(
        f"{NYDUSIFY_PATH} convert --source {src_tag} --target {dst_tag}",
        shell=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8").strip()
