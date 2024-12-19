use std::{io::Result, process::Command};

fn purge_k8s_processes() -> Result<()> {
    let output = Command::new("sh")
        .arg("-c")
        .arg("ps -ef | grep kube | grep -v 'grep' || true")
        .output()?;

    if !output.status.success() {
        panic!("failed to execute ps command");
    }

    let stdout = String::from_utf8(output.stdout).unwrap();
    let pids: Vec<u32> = stdout
        .lines()
        .filter_map(|line| {
            let fields: Vec<&str> = line.split_whitespace().collect();
            fields.get(1).and_then(|pid| pid.parse::<u32>().ok())
        })
        .collect();

    if pids.is_empty() {
        println!("sc2-deploy(purge-k8s): no matching processes found");
        return Ok(());
    }

    // Kill dangling processes
    for pid in pids {
        println!("sc2-deploy(purge-k8s): killing PID: {pid}");
        let status = Command::new("kill").arg("-9").arg(pid.to_string()).status();

        if !status?.success() {
            panic!("sc2-deploy(purge-k8s): failed to kill PID");
        }
    }

    Ok(())
}

fn main() {
    let _ = purge_k8s_processes();
}