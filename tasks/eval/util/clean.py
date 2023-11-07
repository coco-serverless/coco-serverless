from subprocess import run
from tasks.eval.util.env import IMAGE_TO_ID


def clean_container_images(used_ctr_images):
    ids_to_remove = [IMAGE_TO_ID["csegarragonz/coco-knative-sidecar"]]
    for ctr in used_ctr_images:
        ids_to_remove.append(IMAGE_TO_ID[ctr])
    crictl_cmd = "sudo crictl rmi {}".format(" ".join(ids_to_remove))
    out = run(crictl_cmd, shell=True, capture_output=True)
    assert out.returncode == 0


def cleanup_after_run(baseline, used_ctr_images):
    """
    This method is called after each experiment run
    """
    # The Kata baseline we use also pulls iamges directly on the host
    if baseline in ["docker", "kata"]:
        clean_container_images(used_ctr_images)
