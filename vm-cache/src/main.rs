use colored::*;
use env_logger::Builder;
use log::{debug, error, info, trace, warn, LevelFilter};
use nix::sys::signal::{kill, Signal};
use nix::unistd::Pid;
use regex::Regex;
use serde::Deserialize;
use std::{
    env, fs,
    fs::File,
    io::{BufRead, BufReader, Seek, SeekFrom, Write},
    process::{Child, Command, Stdio},
    thread,
    time::Duration,
};

const BINARY_NAME: &str = "sc2-vm-cache";
const CONFIG_PATH: &str =
    "/opt/kata/share/defaults/kata-containers/configuration-qemu-snp-sc2.toml";
const KATA_COMMAND: &str = "/opt/kata/bin/kata-runtime-sc2";
const LOG_FILE: &str = "/tmp/sc2_kata_factory.log";
const PAUSED_VM_STRING: &str = "pause vm";
const PID_FILE: &str = "/tmp/sc2_kata_factory.pid";

#[derive(Deserialize, Debug)]
struct FactoryConfig {
    factory: Factory,
}

#[derive(Deserialize, Debug)]
struct Factory {
    vm_cache_number: u32,
}

/// Function to read the `vm_cache_number` from the TOML configuration file
fn read_vm_cache_number() -> Option<u32> {
    // Read the file contents
    let contents = match fs::read_to_string(CONFIG_PATH) {
        Ok(contents) => contents,
        Err(e) => {
            error!("failed to read config file {CONFIG_PATH}: {e}");
            return None;
        }
    };

    // Parse the TOML contents into the struct
    let config: FactoryConfig = match toml::from_str(&contents) {
        Ok(config) => config,
        Err(e) => {
            error!("failed to parse TOML config: {e}");
            return None;
        }
    };

    // Return the value of `vm_cache_number`
    Some(config.factory.vm_cache_number)
}

// Initialize the logger
fn init_logger() {
    let mut builder = Builder::new();
    builder.filter(None, LevelFilter::Info);
    builder.format(|buf, record| {
        let prefix = "sc2(vm-cache)";
        let level = match record.level() {
            log::Level::Error => "ERROR".red().bold(),
            log::Level::Warn => "WARN".yellow().bold(),
            log::Level::Info => "INFO".green().bold(),
            log::Level::Debug => "DEBUG".blue().bold(),
            log::Level::Trace => "TRACE".magenta().bold(),
        };
        writeln!(buf, "{} [{}] - {}", prefix, level, record.args())
    });

    builder.init();
}

fn run_kata_runtime() -> std::io::Result<Child> {
    Command::new(KATA_COMMAND)
        .args([
            "--config",
            CONFIG_PATH,
            "--log",
            LOG_FILE,
            "factory",
            "init",
        ])
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
}

fn save_pid(pid: u32) -> std::io::Result<()> {
    let mut file = File::create(PID_FILE)?;
    writeln!(file, "{}", pid)?;

    Ok(())
}

fn read_pid() -> std::io::Result<u32> {
    let content = std::fs::read_to_string(PID_FILE)?;
    content.trim().parse::<u32>().map_err(|e| {
        error!("failed to parse PID: {e}");
        std::io::Error::new(
            std::io::ErrorKind::Other,
            "std(vm-cache): invalid PID format",
        )
    })
}

fn stop_background_process() -> std::io::Result<()> {
    if let Ok(pid) = read_pid() {
        kill(Pid::from_raw(pid as i32), Signal::SIGTERM).map_err(|e| {
            error!("failed to kill process: {e}");
            std::io::Error::new(
                std::io::ErrorKind::Other,
                "sc2(vm-cache): failed to kill process",
            )
        })?;

        info!("stopped background process with PID {pid}");
        std::fs::remove_file(PID_FILE)?;
        std::fs::remove_file(LOG_FILE)?;
    } else {
        error!("no running process found");
    }

    Ok(())
}

/// Given a log line from the kata-runtime, as an entry to the journal, parse
/// the log level and the message to print it in our format
fn parse_log_line(line: &str) -> Option<(String, String)> {
    // Define a regular expression to capture the level and msg fields
    let re = Regex::new(r#"level=(\w+)\s+msg="(.*)""#).unwrap();

    // Match the line with the regex pattern
    if let Some(captures) = re.captures(line) {
        let level = captures.get(1)?.as_str().to_string();
        let msg = captures.get(2)?.as_str().to_string();
        Some((level, msg))
    } else {
        None
    }
}

fn tail_log_file(in_background: bool) {
    let expected_cache_size: u32 =
        read_vm_cache_number().expect("sc2(vm-cache): error reading cache size");
    info!("expecting {expected_cache_size} VMs in the cache");

    // Open log file
    let file = loop {
        match File::open(LOG_FILE) {
            Ok(file) => break file,
            Err(e) => {
                warn!("failed to open log file {LOG_FILE}: {e}");
                thread::sleep(Duration::from_secs(1));
            }
        }
    };

    let mut reader = BufReader::new(file);

    // Move the cursor to the end of the file so we only read new lines
    if let Err(e) = reader.seek(SeekFrom::End(0)) {
        error!("failed to seek to the end of the log file: {e}");
        return;
    }

    // Keep count of how many VMs we have started in the cache
    let mut num_vms = 0;

    loop {
        let mut line = String::new();
        match reader.read_line(&mut line) {
            Ok(0) => {
                // No new data; wait a bit before trying again
                thread::sleep(Duration::from_millis(500));
            }
            Ok(_) => {
                // Parse the line to extract the log level and message
                if let Some((level, msg)) = parse_log_line(&line) {
                    if msg == PAUSED_VM_STRING {
                        num_vms += 1;
                        info!("initialised VM {num_vms}/{expected_cache_size}");
                    }

                    if num_vms == expected_cache_size {
                        info!("done initialising cache!");
                        if in_background {
                            return;
                        }
                    }

                    // Map the parsed level to log crate levels and print accordingly
                    if !in_background {
                        match level.as_str() {
                            "info" => info!("{}", msg),
                            "warning" => warn!("{}", msg),
                            "error" => error!("{}", msg),
                            "debug" => debug!("{}", msg),
                            "trace" => trace!("{}", msg),
                            _ => info!("{}", msg), // Default to info if level is unknown
                        }
                    }
                }
            }
            Err(e) => {
                error!("error reading from log file: {}", e);
                break;
            }
        }
    }
}

fn run_foreground() -> std::io::Result<()> {
    let mut child = run_kata_runtime()?;
    let pid = child.id();
    info!("running in foreground with PID: {pid}");

    // Spawn a thread to tail the log file
    let _log_thread = thread::spawn(|| loop {
        tail_log_file(false);
    });

    // Wait for the process to finish
    let _ = child.wait()?;
    std::fs::remove_file(LOG_FILE)?;

    Ok(())
}

/// Function to run in background mode
fn run_background() -> std::io::Result<()> {
    let child = run_kata_runtime()?;

    let pid = child.id();
    info!("running in background with PID {pid}");
    save_pid(pid)?;

    // Tail the output log until we detect that the VM cache has finished
    // initializing
    tail_log_file(true);

    Ok(())
}

fn main() {
    init_logger();
    let args: Vec<String> = env::args().collect();

    if args.len() < 2 {
        error!("usage: {BINARY_NAME} <foreground|background|stop>");
        std::process::exit(1);
    }

    let result = match args[1].as_str() {
        "foreground" => run_foreground(),
        "background" => run_background(),
        "stop" => stop_background_process(),
        _ => {
            error!("invalid mode: {}", args[1]);
            error!("usage: {BINARY_NAME} <foreground|background|stop>");

            std::process::exit(1);
        }
    };

    if let Err(e) = result {
        error!("error: {}", e);
        std::process::exit(1);
    }

    std::process::exit(0);
}
