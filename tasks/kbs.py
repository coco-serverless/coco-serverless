from base64 import b64encode
from invoke import task
from json import loads as json_loads
from os.path import exists, join
from subprocess import run
from tasks.util.env import PROJ_ROOT
from tasks.util.kbs import connect_to_kbs_db
from tasks.util.sev import get_launch_digest

SIMPLE_KBS_DIR = join(PROJ_ROOT, "..", "simple-kbs")
SIMPLE_KBS_DEFAULT_POLICY = "/usr/local/bin/default_policy.json"


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
    run("docker compose up -d --no-recreate cli", shell=True, check=True, cwd=SIMPLE_KBS_DIR)
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


def get_policy_json():
    check_kbs_dir()
    compose_cmd = "docker compose exec server bash -c 'cat {}'".format(SIMPLE_KBS_DEFAULT_POLICY)
    json_str = run(compose_cmd, shell=True, capture_output=True, cwd=SIMPLE_KBS_DIR).stdout.decode("utf-8").strip()
    return json_loads(json_str)


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
def provision_launch_digest(ctx):
    """
    Provision the KBS with the launch digest for the current node
    """
    # First, add our launch digest to the KBS policy
    ld = get_launch_digest("sev")
    ld_b64 = b64encode(ld).decode()

    # Create a new record
    connection = connect_to_kbs_db()
    with connection:
        with connection.cursor() as cursor:
            # Annoyingly, the only way we can force the kata-agent to check
            # the launch measurement against our measured value is to create
            # a placeholder secret that has an associated policy that only
            # allows our launch digest (and no other). By enabling signature
            # verification, the kata-agennt will be triggered to consume the
            # secret and, as a consequence, apply the policy
            # NOTE: the kata-agent will pull _all_ policies
            # TODO: update explanation when i understand what is going on
            policy_id = 10
            secret_id = 10
            secret_name = "default/security-policy/test"
            sql = "INSERT INTO secrets VALUES({}, ".format(secret_id)
            sql += "'{}', 'secret-value', {})".format(secret_name, policy_id)
            cursor.execute(sql)
            # TODO: also secret name?
            resource_type = "default/security-policy/test"
            sql = "INSERT INTO resources VALUES(NULL, NULL, '{}', NULL, {})".format(resource_type, policy_id)
            cursor.execute(sql)
            sql = "INSERT INTO policy VALUES ({}, ".format(policy_id)
            sql += "'[\"{}\"]', '[]', 0, 0, '[]', now(), NULL, 1)".format(ld_b64)
            cursor.execute(sql)

        connection.commit()
