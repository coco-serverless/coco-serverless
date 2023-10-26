from os.path import join
from subprocess import run
from tasks.util.env import PROJ_ROOT

FLAME_GRAPH_ROOT = join(PROJ_ROOT, "..", "FlameGraph")


def generate_flame_graph(pid, time_in_secs, flame_path):
    perf_data_file = "/tmp/perf.data"
    cmd = "sudo perf record -F 99 -p {} -g -o {} -- sleep {}".format(
        pid,
        perf_data_file,
        time_in_secs
    )
    run(cmd, shell=True, check=True)

    perf_out_file = "/tmp/perf.out"
    cmd = "sudo perf script -i {} > {}".format(perf_data_file, perf_out_file)
    run(cmd, shell=True, check=True)

    run("sudo chown csegarra:csegarra {}".format(perf_out_file), shell=True, check=True)

    perf_folded_file = "/tmp/out.folded"
    cmd = "{}/stackcollapse-perf.pl {} > {}".format(
        FLAME_GRAPH_ROOT,
        perf_out_file,
        perf_folded_file,
    )
    run(cmd, shell=True, check=True)

    cmd = "{}/flamegraph.pl {} > {}".format(
        FLAME_GRAPH_ROOT,
        perf_folded_file,
        flame_path,
    )
    run(cmd, shell=True, check=True)
