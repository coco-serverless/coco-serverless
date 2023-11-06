from psutil import process_iter


def get_pid(string):
    for proc in process_iter():
        if string in proc.name():
            return proc.pid

    return None
