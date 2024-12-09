use std::{env, fs, process};

fn check_snp() -> bool {
    if let Ok(data) = fs::read_to_string("/sys/module/kvm_amd/parameters/sev_snp") {
        if data.trim() == "Y" {
            return true;
        }
    }

    false
}

fn check_tdx() -> bool {
    if let Ok(data) = fs::read_to_string("/sys/module/kvm_intel/parameters/tdx") {
        if data.trim() == "Y" {
            return true;
        }
    }

    false
}

fn main() {
    // Get command line arguments
    let args: Vec<String> = env::args().collect();

    if args.len() != 2 {
        eprintln!("sc2-deploy(tee-detect): usage: {} <snp|tdx>", args[0]);
        process::exit(1);
    }

    let mechanism = args[1].to_lowercase();

    match mechanism.as_str() {
        "snp" => {
            if check_snp() {
                process::exit(0);
            } else {
                process::exit(1);
            }
        }
        "tdx" => {
            if check_tdx() {
                process::exit(0);
            } else {
                process::exit(1);
            }
        }
        _ => {
            eprintln!("sc2-deploy(tee-detect): invalid argument: {mechanism}. Use 'snp' or 'tdx'.");
            process::exit(1);
        }
    }
}
