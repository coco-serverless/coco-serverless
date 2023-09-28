from os.path import basename
from subprocess import run
from toml import (
    dump as toml_dump,
    load as toml_load,
    loads as toml_load_from_string,
)


def merge_dicts_recursively(dict_a, dict_b):
    """
    Merge dict_b into dict_a recursively (allowing nested dictionaries)

    Invariant: dict_b is a subset of dict_a
    """
    # If A is not a dict return
    if not isinstance(dict_a, dict):
        print("hello?")
        return

    if not isinstance(dict_b, dict):
        print("world?")
        return

    for k in dict_b:
        if k in dict_a:
            # If dict_a[k] is not a dict, it means we have reached a leaf of
            # A, shared with B. In this case we always copy the subtree from B
            # (irrespective of whether it is a subtree or not)
            if not isinstance(dict_a[k], dict):
                dict_a[k] = dict_b[k]
                return

            merge_dicts_recursively(dict_a[k], dict_b[k])
        else:
            # If the key is not in the to-be merged dict, we want to copy all
            # the sub-tree
            dict_a[k] = dict_b[k]


def update_toml(toml_path, updates_toml, requires_root=True):
    """
    Helper method to update entries in a TOML file

    Updating a TOML file is very frequent in the CoCo environment, particularly
    `root` owned TOML files. So this utility method aims to make that easier.
    Parameters:
    - toml_path: path to the TOML file to modify
    - updates_toml: TOML string with the required updates (simplest way to
                    express arbitrarily complex TOML files)
    - requires_root: whether the TOML file is root-owned (usually the case)
    """
    conf_file = toml_load(toml_path)
    merge_dicts_recursively(conf_file, toml_load_from_string(updates_toml))

    if requires_root:
        # Dump the TOML contents to a temporary file (can't sudo-write)
        tmp_conf = "/tmp/{}".format(basename(toml_path))
        with open(tmp_conf, "w") as fh:
            toml_dump(conf_file, fh)

        # sudo-copy the TOML file in place
        run(
            "sudo cp {} {}".format(tmp_conf, toml_path), shell=True, check=True
        )
    else:
        with open(toml_path, "w") as fh:
            toml_dump(conf_file, fh)


def read_value_from_toml(toml_file_path, toml_path):
    """
    Return the value in a TOML specified by a "." delimited TOML path
    """
    toml_file = toml_load(toml_file_path)
    for toml_level in toml_path.split("."):
        toml_file = toml_file[toml_level]

    if isinstance(toml_file, dict):
        print("ERROR: error reading from TOML, must provide a full path")
        raise RuntimeError("Haven't reached TOML leaf!")

    return toml_file
