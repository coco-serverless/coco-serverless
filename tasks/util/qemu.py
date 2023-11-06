from tasks.util.pid import get_pid
from time import sleep


def get_qemu_pid(poll_period):
    """
    Get the PID for the QEMU command
    """
    while True:
        pid = get_pid("qemu-system-x86_64")
        if pid is not None:
            return pid

        sleep(poll_period)
