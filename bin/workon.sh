#!/bin/bash

THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJ_ROOT=${THIS_DIR}/..

pushd ${PROJ_ROOT} >> /dev/null

# ----------------------------------
# Python tasks config
# ----------------------------------

export VIRTUAL_ENV_DISABLE_PROMPT=1

if [ ! -d "venv" ]; then
    ./bin/create_venv.sh
fi
source venv/bin/activate

# Invoke tab-completion
_complete_invoke() {
    local candidates
    candidates=`invoke --complete -- ${COMP_WORDS[*]}`
    COMPREPLY=( $(compgen -W "${candidates}" -- $2) )
}

# If running from zsh, run autoload for tab completion
if [ "$(ps -o comm= -p $$)" = "zsh" ]; then
    autoload bashcompinit
    bashcompinit
fi
complete -F _complete_invoke -o default invoke inv

# ----------------------------------
# TEE detection
# ----------------------------------

TEE_DETECT_ROOT=${PROJ_ROOT}/tee-detect
TEE_DETECT_BINARY=${TEE_DETECT_ROOT}/target/release/tee-detect
cargo build -q --release --manifest-path ${TEE_DETECT_ROOT}/Cargo.toml

if "${TEE_DETECT_BINARY}" snp; then
    TEE=snp
    export SC2_RUNTIME_CLASS=qemu-snp-sc2
elif "${TEE_DETECT_BINARY}" tdx; then
    TEE=tdx
    export SC2_RUNTIME_CLASS=qemu-tdx-sc2
else
    TEE=none
    echo "sc2-deploy: WARN: neither SNP nor TDX is enabled"
fi

# ----------------------------------
# VM cache config
# ----------------------------------

VM_CACHE_ROOT=${PROJ_ROOT}/vm-cache
VM_CACHE_BINARY=${VM_CACHE_ROOT}/target/release/vm-cache
cargo build -q --release --manifest-path ${VM_CACHE_ROOT}/Cargo.toml
alias sc2-vm-cache="cargo build -q --release --manifest-path ${VM_CACHE_ROOT}/Cargo.toml && sudo -E ${VM_CACHE_BINARY}"

# ----------------------------------
# Useful env. variables
# ----------------------------------

COCO_VERSION=$(grep -oP '^COCO_VERSION\s*=\s*"\K[^"]+' ${PROJ_ROOT}/tasks/util/versions.py)
export KUBECONFIG=${PROJ_ROOT}/.config/kubeadm_kubeconfig
export PATH=${PROJ_ROOT}/bin:${PATH}
export PS1="(sc2-deploy) $PS1"

# -----------------------------
# Splash
# -----------------------------

echo ""
echo "----------------------------------"
echo "CLI for SC2 Deployment Scripts"
echo "CoCo Version: ${COCO_VERSION}"
echo "TEE: ${TEE}"
echo "----------------------------------"
echo ""

popd >> /dev/null

