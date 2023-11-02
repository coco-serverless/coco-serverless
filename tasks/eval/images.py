from invoke import task
from tasks.eval.util.images import (
    ALL_CTR_REGISTRIES,
    copy_images_to_registry,
)


@task
def upload(ctx, origin_repo="ghcr.io"):
    """
    Upload all necessary docker images to run all the tests

    This method uploads images, signatures, and encrypted images for all
    different services required in the evaluation, in all the different
    container registries that we will use.
    """
    for repo in ALL_CTR_REGISTRIES:
        copy_images_to_registry(origin_repo, repo)
