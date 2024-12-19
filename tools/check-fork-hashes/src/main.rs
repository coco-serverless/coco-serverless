use std::{
    collections::HashMap,
    fs,
    io::{self, BufRead},
    process::{exit, Command, Stdio},
};

const SCRIPT_NAME: &str = "sc2-deploy(check-fork-hashes)";

fn get_version_from_file(version_str: &str) -> Result<String, String> {
    // Work-out the versions file path from the binary's real path
    let mut file_path =
        std::env::current_exe().expect("sc2-deploy: failed to get current exe path");
    file_path = file_path.parent().unwrap().to_path_buf();
    file_path = file_path.parent().unwrap().to_path_buf();
    file_path = file_path.parent().unwrap().to_path_buf();
    file_path = file_path.parent().unwrap().to_path_buf();
    file_path = file_path.parent().unwrap().to_path_buf();
    file_path.push("tasks/util/versions.py");

    let file = fs::File::open(file_path.clone()).map_err(|e| {
        format!(
            "{SCRIPT_NAME}: failed to open file '{}': {e}",
            file_path.to_string_lossy()
        )
    })?;
    let reader = io::BufReader::new(file);

    for line in reader.lines() {
        let line = line.map_err(|e| format!("{SCRIPT_NAME}: failed to read line: {e}"))?;
        if line.starts_with(version_str) {
            let parts: Vec<&str> = line.split('=').collect();
            if parts.len() == 2 {
                return Ok(parts[1].trim().trim_matches('"').to_string());
            }
        }
    }

    Err(format!(
        "{version_str} not found in file '{}'",
        file_path.to_string_lossy()
    ))
}

fn get_upstream_hash(repo: &str, branch: &str) -> Result<String, String> {
    let url = format!("https://api.github.com/repos/{repo}/branches/{branch}");
    let output = Command::new("curl")
        .arg("-s")
        .arg(&url)
        .output()
        .map_err(|e| format!("{SCRIPT_NAME}: failed to execute curl: {e}"))?;

    if !output.status.success() {
        return Err(format!(
            "{SCRIPT_NAME}: failed to fetch branch data: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    let json: serde_json::Value = serde_json::from_slice(&output.stdout)
        .map_err(|e| format!("{SCRIPT_NAME}: failed to parse JSON: {e}"))?;

    json["commit"]["sha"]
        .as_str()
        .map(|s| s.to_string())
        .ok_or_else(|| "upstream commit hash not found".to_string())
}

fn get_local_hash(container: &str, path: &str, branch: &str) -> Result<String, String> {
    let output = Command::new("docker")
        .arg("run")
        .arg("--rm")
        .arg("--workdir")
        .arg(path)
        .arg(container)
        .arg("git")
        .arg("rev-parse")
        .arg(branch)
        .output()
        .map_err(|e| format!("{SCRIPT_NAME}: failed to execute git rev-parse: {e}"))?;

    if !output.status.success() {
        return Err(format!(
            "{SCRIPT_NAME}: failed to fetch container branch hash: {}",
            String::from_utf8_lossy(&output.stderr)
        ));
    }

    Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
}

/// This script checks that the branches in our forked repositories match the
/// ones tracked in our build containers. We use containers to install our
/// patched binaries.
fn main() {
    let forks = vec![
        {
            let mut dict = HashMap::new();
            dict.insert("repo_name", "kata-containers");
            dict.insert("version_str", "KATA_VERSION");
            dict.insert("ctr_src_paths", "/go/src/github.com/kata-containers/kata-containers-sc2,/go/src/github.com/kata-containers/kata-containers-baseline");
            dict.insert("branches", "sc2-main,sc2-baseline");
            dict
        },
        {
            let mut dict = HashMap::new();
            dict.insert("repo_name", "guest-components");
            dict.insert("version_str", "COCO_VERSION");
            dict.insert("ctr_src_paths", "/usr/src/guest-components");
            dict.insert("branches", "sc2-main");
            dict
        },
        {
            let mut dict = HashMap::new();
            dict.insert("repo_name", "containerd");
            dict.insert("version_str", "CONTAINERD_VERSION");
            dict.insert("ctr_src_paths", "/go/src/github.com/sc2-sys/containerd");
            dict.insert("branches", "sc2-main");
            dict
        },
    ];

    let mut all_match = true;
    for fork in &forks {
        let repo_name = fork.get("repo_name").unwrap();
        let repo = format!("sc2-sys/{repo_name}");
        let container = format!(
            "ghcr.io/sc2-sys/{repo_name}:{}",
            get_version_from_file(fork.get("version_str").unwrap()).unwrap()
        );

        let src_paths: Vec<&str> = fork
            .get("ctr_src_paths")
            .unwrap()
            .split(",")
            .filter(|s| !s.is_empty())
            .collect();
        let branches: Vec<&str> = fork
            .get("branches")
            .unwrap()
            .split(",")
            .filter(|s| !s.is_empty())
            .collect();
        assert!(src_paths.len() == branches.len());

        // Pull docker image first
        let output = Command::new("docker")
            .arg("pull")
            .arg(container.clone())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status()
            .unwrap();

        if !output.success() {
            eprintln!("{SCRIPT_NAME}: {repo_name}: failed to fetch container image: {container}");
            exit(1);
        }

        for (path, branch) in src_paths.into_iter().zip(branches) {
            let upstream_hash = match get_upstream_hash(&repo, branch) {
                Ok(hash) => hash,
                Err(e) => {
                    eprintln!("{SCRIPT_NAME}: {repo_name}: error fetching upstream hash for {branch}: {e}");
                    all_match = false;
                    continue;
                }
            };

            let local_hash = match get_local_hash(&container, path, branch) {
                Ok(hash) => hash,
                Err(e) => {
                    eprintln!("{SCRIPT_NAME}: {repo_name}: error fetching container hash for {branch}: {e}");
                    all_match = false;
                    continue;
                }
            };

            if upstream_hash == local_hash {
                println!("{SCRIPT_NAME}: {repo_name}: {branch} is up to date");
            } else {
                println!("{SCRIPT_NAME}: {repo_name}: {branch} is NOT up to date");
                all_match = false;
            }
        }
    }

    if all_match {
        exit(0);
    } else {
        exit(1);
    }
}
