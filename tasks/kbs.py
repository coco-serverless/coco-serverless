from base64 import b64encode
from invoke import task
from os.path import exists, join
from subprocess import run
from tasks.util.cosign import COSIGN_PUB_KEY
from tasks.util.kbs import (
    NO_SIGNATURE_POLICY,
    SIMPLE_KBS_DIR,
    SIMPLE_KBS_RESOURCE_PATH,
    SIGNATURE_POLICY_NONE,
    create_kbs_resource,
    connect_to_kbs_db,
    populate_signature_verification_policy,
    validate_signature_verification_policy,
)
from tasks.util.sev import get_launch_digest

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
def provision_launch_digest(ctx, signature_policy=NO_SIGNATURE_POLICY, clean=False):
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

    # First, add our launch digest to the KBS policy
    ld = get_launch_digest("sev")
    ld_b64 = b64encode(ld).decode()

    # Create a new record
    connection = connect_to_kbs_db()
    with connection:
        with connection.cursor() as cursor:
            policy_id = 10

            # When enabling signature verification, we need to provide a
            # signature policy. This policy has a constant string identifier
            # that the kata agent will ask for (default/security-policy/test),
            # which points to a config file that specifies how to validate
            # signatures
            if signature_policy != NO_SIGNATURE_POLICY:
                resource_path = "signature_policy_{}.json".format(signature_policy)

                if signature_policy == SIGNATURE_POLICY_NONE:
                    # If we set a `none` signature policy, it means that we don't
                    # check any signatures on the pulled container images
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
                    signing_key_kbs_path = "cosign.pub"
                    signing_key_resource_path = join(
                        SIMPLE_KBS_RESOURCE_PATH, signing_key_kbs_path
                    )
                    sql = "INSERT INTO resources VALUES(NULL, NULL, "
                    sql += "'{}', '{}', {})".format(
                        signing_key_resource_id, signing_key_kbs_path, policy_id
                    )
                    cursor.execute(sql)

                    # Lastly, we copy the public signing key to the resource
                    # path annotated in the policy
                    cp_cmd = "cp {} {}".format(
                        COSIGN_PUB_KEY, signing_key_resource_path
                    )
                    run(cp_cmd, shell=True, check=True)

                create_kbs_resource(resource_path, policy_json_str)

            # Create the resource (containing the signature policy) in the KBS
            sql = "INSERT INTO resources VALUES(NULL, NULL, "
            sql += "'{}', '{}', {})".format(
                SIGNATURE_POLICY_STRING_ID, resource_path, policy_id
            )
            cursor.execute(sql)

            # We associate the signature policy to a digest policy, meaning
            # that irrespective of what signature policy are we using (even if
            # we are not checking any signatures) we will always check the FW
            # digest against the measured one
            sql = "INSERT INTO policy VALUES ({}, ".format(policy_id)
            sql += "'[\"{}\"]', '[]', 0, 0, '[]', now(), NULL, 1)".format(ld_b64)
            cursor.execute(sql)

        connection.commit()
