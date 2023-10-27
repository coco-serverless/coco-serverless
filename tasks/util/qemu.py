from psutil import process_iter
from time import sleep


def do_get_pid(string):
    for proc in process_iter():
        if string in proc.name():
            return proc.pid

    return None


def get_qemu_pid(poll_period):
    """
    Get the PID for the QEMU command
    """
    while True:
        pid = do_get_pid("qemu-system-x86_64")
        if pid is not None:
            return pid

        sleep(poll_period)
