from re import search as re_search


# This is hard-coded in the bash redirection output. It is not very straight
# forward to change it there, so we keep it like this for the time being
# (e.g. we could template the bash script, but I cba atm)
OVMF_SERIAL_OUTPUT = "/tmp/qemu-serial.log"


def get_ovmf_boot_events(events_ts, guest_kernel_start_ts):
    """
    Parse the OVMF boot events from the serial output, and create timestamps as
    negative offsets from the guest kernel start timestamp.
    """
    with open(OVMF_SERIAL_OUTPUT, "r") as fh:
        lines = fh.readlines()

    # Filter relevant log lines
    magic = "CSG-M4G1C"
    lines = [li for li in lines if magic in li]

    # Get the overall time elapsed
    ticks_re_str = r"\(ticks\): ([0-9]*)"
    start_ticks = int(re_search(ticks_re_str, lines[0]).groups(1)[0])
    start_freq = int(re_search(r"Freq: ([0-9]*)", lines[0]).groups(1)[0])
    end_ticks = int(re_search(ticks_re_str, lines[-1]).groups(1)[0])
    end_freq = int(re_search(r"Freq: ([0-9]*)", lines[-1]).groups(1)[0])

    # Establish OVMF's relative 0 timestamp
    assert start_freq == end_freq, "Different frequencies!"
    total_time_in_secs = (end_ticks - start_ticks) / start_freq
    ovmf_zero_ts = guest_kernel_start_ts - total_time_in_secs
    ovmf_zero_ticks = start_ticks
    events_ts.append(("StartOVMFBoot", ovmf_zero_ts))
    events_ts.append(("EndOVMFBoot", guest_kernel_start_ts))
    print("OVMF spent {} s booting".format(total_time_in_secs))

    def get_ts_from_ticks(ticks):
        delay_sec = (ticks - ovmf_zero_ticks) / start_freq
        return ovmf_zero_ts + delay_sec

    # Now we can discard the overall timestamps, and calculate the intermediate
    # bits
    lines = lines[1:-1]

    # We also discard additional calls to the entrypoint
    # TODO: why are these here?
    genesis_magic = "G3N3S1S"
    lines = [li for li in lines if genesis_magic not in li]

    # We also discard PeiCore repeated events
    # TODO: why do these exist?
    pei_core_str = "PeiCore"
    first_pei_core = -1
    ind_to_remove = []
    for ind, li in enumerate(lines):
        if pei_core_str in li and "BEGIN" in li:
            if first_pei_core < 0:
                first_pei_core = ind
            else:
                ind_to_remove.append(ind)
    lines = [li for ind, li in enumerate(lines) if ind not in ind_to_remove]
    # for li in lines:
    # print(li.strip())

    def get_end_ticks(lines, event):
        for li in lines:
            if event in li and "END" in li:
                end_ticks = int(re_search(ticks_re_str, li).groups(1)[0])
                return end_ticks

        raise RuntimeError("Could not find ending event for: {}".format(event))

    # TODO: finish plotting this
    # TODO: DxeMain seems to also start at tick 0?
    event_allow_list = ["DxeMain"]

    verify_start_ts = -1
    verify_duration = 0
    for li in lines:
        if "BEGIN" in li:
            event = re_search(r"(^[a-zA-Z\-]*)", li).groups(1)[0]

            # Filter only the events that we care about
            if event not in event_allow_list and "Verify" not in event:
                continue

            start_ticks = int(re_search(ticks_re_str, li).groups(1)[0])
            start_ts = get_ts_from_ticks(start_ticks)
            end_ticks = get_end_ticks(lines, event)
            end_ts = get_ts_from_ticks(end_ticks)

            if event in event_allow_list:
                events_ts.append(("StartOVMF" + event, start_ts))
                events_ts.append(("EndOVMF" + event, end_ts))
            else:
                if verify_start_ts < 0 or start_ts < verify_start_ts:
                    verify_start_ts = start_ts

                verify_duration += end_ts - start_ts

    events_ts.append(("StartOVMFVerify", verify_start_ts))
    events_ts.append(("EndOVMFVerify", verify_start_ts + verify_duration))

    return events_ts
