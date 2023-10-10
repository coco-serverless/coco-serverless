from invoke import task
from os.path import exists
from subprocess import run
from tasks.util.cosign import COSIGN_PUB_KEY
from tasks.util.kbs import (
    SIMPLE_KBS_DIR,
    SIGNATURE_POLICY_NONE,
    create_kbs_resource,
    connect_to_kbs_db,
    populate_signature_verification_policy,
    set_launch_measurement_policy,
    validate_signature_verification_policy,
)

SIGNATURE_POLICY_STRING_ID = "default/security-policy/test"


def check_kbs_dir():
    if not exists(SIMPLE_KBS_DIR):
        print("Error: could not find local KBS checkout at {}".format(SIMPLE_KBS_DIR))
        raise RuntimeError("Simple KBS local checkout not found!")


@task
def cli(ctx):
    """
    Get a development CLI in the simple KBS server
    """
    # Make sure the KBS is running
    check_kbs_dir()
    run(
        "docker compose up -d --no-recreate cli",
        shell=True,
        check=True,
        cwd=SIMPLE_KBS_DIR,
    )
    run("docker compose exec -it cli bash", shell=True, check=True, cwd=SIMPLE_KBS_DIR)


@task
def start(ctx):
    """
    Start the simple KBS service
    """
    check_kbs_dir()
    run("docker compose up -d server", shell=True, check=True, cwd=SIMPLE_KBS_DIR)


@task
def stop(ctx):
    """
    Stop the simple KBS service
    """
    check_kbs_dir()
    run("docker compose down", shell=True, check=True, cwd=SIMPLE_KBS_DIR)


@task
def clear_db(ctx):
    """
    Clear the contents of the KBS DB
    """
    connection = connect_to_kbs_db()
    with connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE from policy")
            cursor.execute("DELETE from resources")
            cursor.execute("DELETE from secrets")

        connection.commit()


@task
def provision_launch_digest(ctx, signature_policy=SIGNATURE_POLICY_NONE, clean=False):
    """
    Provision the KBS with the launch digest for the current node

    In order to make the Kata Agent validate the FW launch digest measurement
    we need to enable signature verification. Signature verification has an
    associated resource that contains the verification policy. By associating
    this resource to a launch digest policy (beware of the `policy` term
    overloading, but these are KBS terms), we force the Kata Agent to also
    enforce the launch digest policy.

    We support different kinds of signature verification policies, and only
    one kind of launch digest policy.

    For signature verification, we have:
    - the NONE policy, that accepts all images
    - the VERIFY policy, that verifies all (unencrypted) images

    For launch digest, we manually generate the measure digest, and include it
    in the policy. If the FW digest is not exactly the one in the policy, boot
    fails.
    """
    validate_signature_verification_policy(signature_policy)

    if clean:
        clear_db(ctx)

    # First, we provision a launch digest policy that only allows to
    # boot confidential VMs with the launch measurement that we have
    # just calculated. We will associate signature verification and
    # image encryption policies to this launch digest policy.
    set_launch_measurement_policy()

    # To make sure the launch policy is enforced, we must enable
    # signature verification. This means that we also need to provide a
    # signature policy. This policy has a constant string identifier
    # that the kata agent will ask for (default/security-policy/test),
    # which points to a config file that specifies how to validate
    # signatures
    resource_path = "signature_policy_{}.json".format(signature_policy)

    if signature_policy == SIGNATURE_POLICY_NONE:
        # If we set a `none` signature policy, it means that we don't
        # check any signatures on the pulled container images (still
        # necessary to set the policy to check the launch measurment)
        policy_json_str = populate_signature_verification_policy(
            signature_policy
        )
    else:
        # The verify policy, checks that the image has been signed
        # with a given key. As everything in the KBS, the key
        # we give in the policy is an ID for another resource.
        # Note that the following resource prefix is NOT required
        # (i.e. we could change it to keys/cosign/1 as long as the
        # corresponding resource exists)
        signing_key_resource_id = "default/cosign-key/1"
        policy_json_str = populate_signature_verification_policy(
            signature_policy,
            [
                [
                    "docker.io/csegarragonz/coco-helloworld-py",
                    signing_key_resource_id,
                ],
                [
                    "docker.io/csegarragonz/coco-knative-sidecar",
                    signing_key_resource_id,
                ],
            ],
        )

        # Create a resource for the signing key
        with open(COSIGN_PUB_KEY) as fh:
            create_kbs_resource(
                signing_key_resource_id,
                "cosign.pub",
                fh.read()
            )

    # Finally, create a resource for the image signing policy. Note that the
    # resource ID for the image signing policy is hardcoded in the kata agent
    # (particularly in the attestation agent)
    create_kbs_resource(
        SIGNATURE_POLICY_STRING_ID,
        resource_path,
        policy_json_str
    )
