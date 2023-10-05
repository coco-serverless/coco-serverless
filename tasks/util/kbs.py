from pymysql import connect as mysql_connect
from pymysql.cursors import DictCursor
from subprocess import run

KBS_PORT = 44444


def connect_to_kbs_db():
    """
    Get a working MySQL connection to the KBS DB
    """
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
    ip_cmd_out = run(ip_cmd, shell=True, capture_output=True).stdout.decode("utf-8").strip().split(" ")
    idx = ip_cmd_out.index("src") + 1
    kbs_url = ip_cmd_out[idx]
    return kbs_url
