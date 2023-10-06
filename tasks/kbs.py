from base64 import b64encode
from invoke import task
from os.path import exists
from subprocess import run
from tasks.util.kbs import SIMPLE_KBS_DIR, create_kbs_resource, connect_to_kbs_db
from tasks.util.sev import get_launch_digest

SIMPLE_KBS_DEFAULT_POLICY = "/usr/local/bin/default_policy.json"

SIGNATURE_POLICY_STRING_ID = "default/security-policy/test"
SIGNATURE_POLICY_NONE = "none"
ALLOWED_SIGNATURE_POLICIES = [SIGNATURE_POLICY_NONE]
SIGNATURE_POLICY_NONE_JSON = """{
    "default": [{"type": "insecureAcceptAnything"}],
    "transports": {}
}
"""


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
def provision_launch_digest(ctx, signature_policy):
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

    For signature verification, we have the NONE policy, that accepts all
    images.

    For launch digest, we manually generate the measure digest, and include it
    in the policy. If the FW digest is not exactly the one in the policy, boot
    fails.
    """
    if signature_policy not in ALLOWED_SIGNATURE_POLICIES:
        print(
            "--signature-policy must be one in: {}".format(ALLOWED_SIGNATURE_POLICIES)
        )
        raise RuntimeError("Disallowed signature policy: {}".format(signature_policy))

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
            if signature_policy == SIGNATURE_POLICY_NONE:
                # If we set a `none` signature policy, it means that we don't
                # check any signatures on the pulled container images
                resource_path = "signature_policy_{}.json".format(signature_policy)
                create_kbs_resource(resource_path, SIGNATURE_POLICY_NONE_JSON)

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
