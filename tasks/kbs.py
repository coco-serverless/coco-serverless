from base64 import b64encode
from invoke import task
from json import dumps as json_dumps, loads as json_loads
from os.path import exists, join
from pymysql import connect as mysql_connect
from pymysql.cursors import DictCursor
from subprocess import run
from tasks.util.env import PROJ_ROOT
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
def provision_launch_digest(ctx):
    """
    Provision the KBS with the launch digest for the current node
    """
    # First, add our launch digest to the KBS policy
    ld = get_launch_digest("sev")
    ld_b64 = b64encode(ld).decode()

    # Get the database IP
    docker_cmd = "docker network inspect simple-kbs_default | jq -r "
    docker_cmd += "'.[].Containers[] | select(.Name | test(\"simple-kbs[_-]db.*\")).IPv4Address'"
    db_ip = run(docker_cmd, shell=True, capture_output=True).stdout.decode("utf-8").strip()[:-3]

    # Connect to the database
    connection = mysql_connect(host=db_ip,
                               user='kbsuser',
                               password='kbspassword',
                               database='simple_kbs',
                               cursorclass=DictCursor)

    with connection:
        with connection.cursor() as cursor:
            # Create a new record
            sql = "INSERT INTO policy VALUES (10, "
            sql += "'[\"{}\"]', '[]', 0, 0, '[]', now(), NULL, 1)".format(ld_b64)
            print(sql)
            cursor.execute(sql)

        connection.commit()
