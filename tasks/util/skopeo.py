from base64 import b64encode
from json import loads as json_loads
from os.path import exists, join
from pymysql.err import IntegrityError
from subprocess import run
from tasks.util.cosign import sign_container_image
from tasks.util.env import CONF_FILES_DIR, K8S_CONFIG_DIR
from tasks.util.guest_components import (
    start_coco_keyprovider,
    stop_coco_keyprovider,
)
from tasks.util.kbs import create_kbs_secret
from tasks.util.versions import SKOPEO_VERSION

SKOPEO_IMAGE = "quay.io/skopeo/stable:v{}".format(SKOPEO_VERSION)
SKOPEO_ENCRYPTION_KEY = join(K8S_CONFIG_DIR, "image_enc.key")
AA_CTR_ENCRYPTION_KEY = "/tmp/image_enc.key"


def run_skopeo_cmd(cmd, capture_stdout=False):
    ocicrypt_conf_host = join(CONF_FILES_DIR, "ocicrypt.conf")
    ocicrypt_conf_guest = "/ocicrypt.conf"
    skopeo_cmd = [
        "docker run --rm",
        "--net host",
        "-e OCICRYPT_KEYPROVIDER_CONFIG={}".format(ocicrypt_conf_guest),
        "-v {}:{}".format(ocicrypt_conf_host, ocicrypt_conf_guest),
        "-v ~/.docker/config.json:/config.json",
        "-v {}:/certs/domain.crt".format(
            join(K8S_CONFIG_DIR, "local-registry", "domain.crt")
        ),
        SKOPEO_IMAGE,
        cmd,
    ]
    skopeo_cmd = " ".join(skopeo_cmd)
    if capture_stdout:
        return (
            run(skopeo_cmd, shell=True, capture_output=True)
            .stdout.decode("utf-8")
            .strip()
        )
    else:
        run(skopeo_cmd, shell=True, check=True)


def create_encryption_key():
    cmd = "head -c32 < /dev/random > {}".format(SKOPEO_ENCRYPTION_KEY)
    run(cmd, shell=True, check=True)


def encrypt_container_image(image_tag, sign=False):
    encryption_key_resource_id = "default/image-encryption-key/1"
    if not exists(SKOPEO_ENCRYPTION_KEY):
        create_encryption_key()

    # We use CoCo's keyprovider server (that implements the ocicrypt protocol)
    # to encrypt the OCI image. To that extent, we need to mount the encryption
    # key somewhere that the attestation agent (in the keyprovider) can find
    # it
    start_coco_keyprovider(SKOPEO_ENCRYPTION_KEY, AA_CTR_ENCRYPTION_KEY)

    encrypted_image_tag = image_tag.split(":")[0] + ":encrypted"
    skopeo_cmd = [
        "copy --insecure-policy",
        "--authfile /config.json",
        "--dest-cert-dir=/certs",
        "--src-cert-dir=/certs",
        "--encryption-key",
        "provider:attestation-agent:keyid=kbs:///{}::keypath={}".format(
            encryption_key_resource_id, AA_CTR_ENCRYPTION_KEY
        ),
        "docker://{}".format(image_tag),
        "docker://{}".format(encrypted_image_tag),
    ]
    skopeo_cmd = " ".join(skopeo_cmd)
    run_skopeo_cmd(skopeo_cmd)

    # Stop the keyprovider when we are done encrypting layers
    stop_coco_keyprovider()

    # Sanity check that the image is actually encrypted
    inspect_jsonstr = run_skopeo_cmd(
        "inspect --cert-dir /certs --authfile /config.json docker://{}".format(
            encrypted_image_tag
        ),
        capture_stdout=True,
    )
    inspect_json = json_loads(inspect_jsonstr)
    layers = [
        layer["MIMEType"].endswith("tar+gzip+encrypted")
        for layer in inspect_json["LayersData"]
    ]
    if not all(layers):
        print("Some layers in image {} are not encrypted!".format(encrypted_image_tag))
        stop_coco_keyprovider()
        raise RuntimeError("Image encryption failed!")

    # Create a secret in KBS with the encryption key. Skopeo needs it as raw
    # bytes, whereas KBS wants it base64 encoded, so we do the conversion first
    with open(SKOPEO_ENCRYPTION_KEY, "rb") as fh:
        key_b64 = b64encode(fh.read()).decode()

    # When we are encrypting multiple container images, it may happen that the
    # encryption key is already there. Thus it is safe to ignore this exception
    # here
    try:
        create_kbs_secret(encryption_key_resource_id, key_b64)
    except IntegrityError:
        print("WARNING: error creating KBS secret...")
        pass

    if sign:
        sign_container_image(encrypted_image_tag)
