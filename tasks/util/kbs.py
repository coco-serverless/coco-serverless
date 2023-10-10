from base64 import b64encode
from json import dumps as json_dumps
from os import makedirs
from os.path import join
from pymysql import connect as mysql_connect
from pymysql.cursors import DictCursor
from subprocess import run
from tasks.util.env import PROJ_ROOT
from tasks.util.sev import get_launch_digest

SIMPLE_KBS_DIR = join(PROJ_ROOT, "..", "simple-kbs")
# WARNING: this resource path depends on the KBS' `server` service working
# directory. The server expects the `resources` directory to be in:
# /<working_dir>/resources
SIMPLE_KBS_RESOURCE_PATH = join(SIMPLE_KBS_DIR, "resources")
SIMPLE_KBS_KEYS_RESOURCE_PATH = join(SIMPLE_KBS_RESOURCE_PATH, "keys")

DEFAULT_LAUNCH_POLICY_ID = 10

# --------
# Signature Verification Policy
# --------

NO_SIGNATURE_POLICY = "no-signature-policy"
SIGNATURE_POLICY_NONE = "none"
SIGNATURE_POLICY_VERIFY = "verify"
ALLOWED_SIGNATURE_POLICIES = [SIGNATURE_POLICY_NONE, SIGNATURE_POLICY_VERIFY]
SIGNATURE_POLICY_NONE_JSON = """{
    "default": [{"type": "insecureAcceptAnything"}],
    "transports": {}
}
"""
SIGNATURE_POLICY_VERIFY_JSON = {
    "default": [{"type": "reject"}],
    "transports": {"docker": {}},
}


def connect_to_kbs_db():
    """
    Get a working MySQL connection to the KBS DB
    """
    # Get the database IP
    docker_cmd = "docker network inspect simple-kbs_default | jq -r "
    docker_cmd += (
        "'.[].Containers[] | select(.Name | test(\"simple-kbs[_-]db.*\")).IPv4Address'"
    )
    db_ip = (
        run(docker_cmd, shell=True, capture_output=True)
        .stdout.decode("utf-8")
        .strip()[:-3]
    )

    # Connect to the database
    connection = mysql_connect(
        host=db_ip,
        user="kbsuser",
        password="kbspassword",
        database="simple_kbs",
        cursorclass=DictCursor,
    )

    return connection


def set_launch_measurement_policy():
    """
    This method configures and sets the launch measurement policy
    """
    # Get the launch measurement
    ld = get_launch_digest("sev")
    ld_b64 = b64encode(ld).decode()

    # Create a policy associated to this measurement in the KBS DB
    connection = connect_to_kbs_db()
    with connection:
        with connection.cursor() as cursor:
            sql = "INSERT INTO policy VALUES ({}, ".format(DEFAULT_LAUNCH_POLICY_ID)
            sql += "'[\"{}\"]', '[]', 0, 0, '[]', now(), NULL, 1)".format(ld_b64)
            cursor.execute(sql)

        connection.commit()


def create_kbs_resource(resource_id, resource_kbs_path, resource_contents, resource_launch_policy_id=DEFAULT_LAUNCH_POLICY_ID):
    """
    Create a KBS resource for the kata-agent to consume

    Each KBS resource is identified by a resource ID. Each KBS resource has
    a resource path, where the actual resource lives. In addition, each
    each resource is associated to a launch policy, that checks that the FW
    digest is as expected.

    KBS resources are stored in a `resources` directory in the same **working
    directory** from which we call the KBS binary. This value can be checked
    in the simple KBS' docker-compose.yml file. The `resource_path` argument is
    a relative directory from the base `resources` directory.
    """
    makedirs(SIMPLE_KBS_RESOURCE_PATH, exist_ok=True)

    # First, insert the resource in the SQL database
    connection = connect_to_kbs_db()
    with connection:
        with connection.cursor() as cursor:
            sql = "INSERT INTO resources VALUES(NULL, NULL, "
            sql += "'{}', '{}', {})".format(
                resource_id, resource_kbs_path, resource_launch_policy_id
            )
            cursor.execute(sql)

        connection.commit()

    # Second, dump the resource contents in the specified resource path
    with open(join(SIMPLE_KBS_RESOURCE_PATH, resource_kbs_path), "w") as fh:
        fh.write(resource_contents)


def create_kbs_secret(secret_id, secret_contents, resource_launch_policy_id=DEFAULT_LAUNCH_POLICY_ID):
    """
    Create a KBS secret for the kata-agent to consume
    """
    # First, insert the resource in the SQL database
    connection = connect_to_kbs_db()
    with connection:
        with connection.cursor() as cursor:
            sql = "INSERT INTO secrets VALUES(NULL, "
            sql += "'{}', '{}', {})".format(
                secret_id, secret_contents, resource_launch_policy_id
            )
            cursor.execute(sql)

        connection.commit()


def validate_signature_verification_policy(signature_policy):
    """
    Validate that a given signature policy is supported
    """
    if signature_policy not in ALLOWED_SIGNATURE_POLICIES:
        print(
            "--signature-policy must be one in: {}".format(ALLOWED_SIGNATURE_POLICIES)
        )
        raise RuntimeError("Disallowed signature policy: {}".format(signature_policy))


def populate_signature_verification_policy(signature_policy, policy_details=None):
    """
    Given a list of tuples containing an image name, and the resource id of the
    key used to sign it, return the JSON string containing the signature
    verification policy
    """
    if signature_policy == SIGNATURE_POLICY_NONE:
        return SIGNATURE_POLICY_NONE_JSON

    policy = SIGNATURE_POLICY_VERIFY_JSON
    for image_name, signing_key_resource_id in policy_details:
        policy["transports"]["docker"][image_name] = [
            {
                "type": "sigstoreSigned",
                "keyPath": "kbs:///{}".format(signing_key_resource_id),
            }
        ]

    return json_dumps(policy)
