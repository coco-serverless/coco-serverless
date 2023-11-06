from os.path import join
from subprocess import run
from tasks.util.cosign import sign_container_image
from tasks.util.env import LOCAL_REGISTRY_URL
from tasks.util.skopeo import encrypt_container_image

ALL_USED_IMAGES = {
    "csegarragonz/coco-knative-sidecar": {"unencrypted"},
    "csegarragonz/coco-helloworld-py": {"unencrypted", "encrypted"},
}

ALL_CTR_REGISTRIES = ["ghcr.io", LOCAL_REGISTRY_URL]


def copy_images_to_registry(src_repo, dst_repo):
    """
    Copy all images from one repo to another
    """
    for image in ALL_USED_IMAGES:
        for tag in ALL_USED_IMAGES[image]:
            if tag == "unencrypted":
                src_path = "{}:{}".format(join(src_repo, image), tag)
                dst_path = "{}:{}".format(join(dst_repo, image), tag)

                # Push regular images
                run("docker pull {}".format(src_path), shell=True, check=True)
                run(
                    "docker tag {} {}".format(src_path, dst_path),
                    shell=True,
                    check=True,
                )
                run("docker push {}".format(dst_path), shell=True, check=True)
                # Tolerate rmi failing, as images should not be there to start off with
                run(
                    "docker rmi {} {}".format(src_path, dst_path),
                    shell=True,
                    capture_output=True,
                )

                # Push signature for the image too
                sign_container_image(dst_path)
            elif tag == "encrypted":
                # Note that it is the skopeo method that makes the tag encrypted
                dst_path = "{}:unencrypted".format(join(dst_repo, image))
                encrypt_container_image(dst_path, sign=True)
            else:
                raise RuntimeError("Unrecognised image tag: {}".format(tag))
