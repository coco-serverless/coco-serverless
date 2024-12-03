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
const LOG_FILE: &str = "/tmp/sc2_kata_factory.log";
const KATA_COMMAND: &str = "/opt/kata/bin/kata-runtime-sc2";
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

fn get_config_path() -> String {
    match env::var("SC2_RUNTIME_CLASS") {
        Ok(value) => format!("/opt/kata/share/defaults/kata-containers/configuration-{value}.toml"),
        Err(e) => {
            error!("failed to get runtime class from env. variable: {e}");
            panic!("failed to read SC2_RUNTIME_CLASS");
        },
    }
}

/// Function to read the `vm_cache_number` from the TOML configuration file
fn read_vm_cache_number() -> Option<u32> {
    // Read the file contents
    let config_path = get_config_path();
    let contents = match fs::read_to_string(&config_path) {
        Ok(contents) => contents,
        Err(e) => {
            error!("failed to read config file {config_path}: {e}");
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
            &get_config_path(),
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

/// Function to prune all qemu processes that may be dangling after a failed
/// cache stop
fn prune_qemu_processes() -> std::io::Result<()> {
    // List all QEMU commands using SC2
    let output = Command::new("sh")
        .arg("-c")
        .arg("ps -ef | grep qemu | grep sc2 | grep -v 'grep' || true")
        .output()?;

    if !output.status.success() {
        error!("failed to execute ps command");
        panic!("failed to execute ps command");
    }

    // Extract PID from output
    let stdout = String::from_utf8(output.stdout).unwrap();
    let pids: Vec<u32> = stdout
        .lines()
        .filter_map(|line| {
            let fields: Vec<&str> = line.split_whitespace().collect();
            fields.get(1).and_then(|pid| pid.parse::<u32>().ok())
        })
        .collect();

    if pids.is_empty() {
        info!("no matching processes found");
        return Ok(());
    }

    // Kill dangling processes
    for pid in pids {
        info!("killing PID: {}", pid);
        let status = Command::new("kill").arg("-9").arg(pid.to_string()).status();

        match status {
            Ok(status) if status.success() => debug!("successfully killed PID {}", pid),
            _ => error!("failed to kill PID {}", pid),
        }
    }

    // Lastly, when pruning also remove the kata cache socket
    let status = Command::new("rm")
        .arg("-f")
        .arg("/var/run/kata-containers/cache.sock")
        .status();

    match status {
        Ok(_) => info!("removed kata cache socket"),
        _ => error!("error removing kata cache socket"),
    }

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
        "prune" => prune_qemu_processes(),
        "stop" => stop_background_process(),
        _ => {
            error!("invalid mode: {}", args[1]);
            error!("usage: {BINARY_NAME} <foreground|background|prune|stop>");

            std::process::exit(1);
        }
    };

    if let Err(e) = result {
        error!("error: {}", e);
        std::process::exit(1);
    }

    std::process::exit(0);
}
