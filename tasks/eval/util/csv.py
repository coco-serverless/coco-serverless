def init_csv_file(file_name, header):
    with open(file_name, "w") as fh:
        fh.write("{}\n".format(header))


def write_csv_line(file_name, *args):
    layout = ",".join(["{}" for _ in range(len(args))]) + "\n"
    with open(file_name, "a") as fh:
        fh.write(layout.format(*args))
