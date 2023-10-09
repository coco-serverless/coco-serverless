from json import dumps as json_dumps
from os import makedirs
from os.path import join
from pymysql import connect as mysql_connect
from pymysql.cursors import DictCursor
from subprocess import run
from tasks.util.env import PROJ_ROOT

KBS_PORT = 44444
SIMPLE_KBS_DIR = join(PROJ_ROOT, "..", "simple-kbs")
# WARNING: this resource path depends on the KBS' `server` service working
# directory. The server expects the `resources` directory to be in:
# /<working_dir>/resources
SIMPLE_KBS_RESOURCE_PATH = join(SIMPLE_KBS_DIR, "resources")
SIMPLE_KBS_KEYS_RESOURCE_PATH = join(SIMPLE_KBS_RESOURCE_PATH, "keys")

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


def get_kbs_url():
    """
    Get the external KBS IP that can be reached from both host and guest

    If the KBS is deployed using docker compose with host networking and the
    port is forwarded to the host (i.e. KBS is bound to :${KBS_PORT}, then
    we can use this method to figure out the "public-facing" IP that can be
    reached both from the host and the guest
    """
    ip_cmd = "ip -o route get to 8.8.8.8"
    ip_cmd_out = (
        run(ip_cmd, shell=True, capture_output=True)
        .stdout.decode("utf-8")
        .strip()
        .split(" ")
    )
    idx = ip_cmd_out.index("src") + 1
    kbs_url = ip_cmd_out[idx]
    return kbs_url


def create_kbs_resource(resource_path, resource_contents):
    """
    Create a KBS resource for the kata-agent to consume

    KBS resources are stored in a `resources` directory in the same **working
    directory** from which we call the KBS binary. This value can be checked
    in the simple KBS' docker-compose.yml file. The `resource_path` argument is
    a relative directory from the base `resources` directory.
    """
    makedirs(SIMPLE_KBS_RESOURCE_PATH, exist_ok=True)

    with open(join(SIMPLE_KBS_RESOURCE_PATH, resource_path), "w") as fh:
        fh.write(resource_contents)


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
