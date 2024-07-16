#!/bin/bash

readonly BUILD_DIR="tmp-build-guest-image"
readonly MKOSI_KERNEL_DIR="mkosi-kernel"
readonly KERNEL_DIR="linux"
readonly PARENT_DIR=$(dirname "$(pwd)") 

function clone_kernel {
    local REPO_URL="https://github.com/coconut-svsm/linux"
    local BRANCH="svsm"
    
    if ! git clone "$REPO_URL" "$KERNEL_DIR"; then
        echo "Failed to clone repository: $REPO_URL"
        exit 1
    fi

    if ! cd "$KERNEL_DIR"; then
        echo "Failed to change directory to $KERNEL_DIR"
        exit 1
    fi

    if ! git checkout "$BRANCH"; then
        echo "Failed to checkout branch: $BRANCH"
        cd - || { echo "Failed to return to the original directory"; exit 1; }
        exit 1
    fi

    if ! cd -; then
        echo "Failed to return to the original directory"
        exit 1
    fi
}


function clone_mkosi {
    local REPO_URL="https://github.com/systemd/mkosi"
    local TAG="v23"
    local MKOSI_BIN="/usr/local/bin/mkosi"

    if ! git clone "$REPO_URL"; then
        echo "Failed to clone repository: $REPO_URL"
        exit 1
    fi

    if ! cd mkosi; then
        echo "Failed to change directory to mkosi"
        exit 1
    fi

    if ! git checkout "$TAG"; then
        echo "Failed to checkout tag: $TAG"
        cd - || { echo "Failed to return to the original directory"; exit 1; }
        exit 1
    fi

    if [ -f "$MKOSI_BIN" ]; then
        if ! sudo mv "$MKOSI_BIN" "${MKOSI_BIN}.old"; then
            echo "Failed to backup existing mkosi binary"
            cd - || { echo "Failed to return to the original directory"; exit 1; }
            exit 1
        fi
    fi

    if ! sudo ln -s "$PWD/bin/mkosi" "$MKOSI_BIN"; then
        echo "Failed to create symbolic link to mkosi binary"
        cd - || { echo "Failed to return to the original directory"; exit 1; }
        exit 1
    fi

    if ! cd -; then
        echo "Failed to return to the original directory"
        exit 1
    fi
}

function restore_mkosi {
    if [ -f /usr/local/bin/mkosi.old ]; then mv /usr/local/bin/mkosi.old /usr/local/bin/mkosi; fi
}

function clone_mkosi_kernel {
    local REPO_URL="https://github.com/DaanDeMeyer/mkosi-kernel.git"
    local COMMIT_SHA="777d8cec1453b9f86803adc26051549a36875e9a"
    local CONF_FILES_DIR="$PARENT_DIR/conf-files"

    if ! git clone "$REPO_URL"; then
        echo "Failed to clone repository: $REPO_URL"
        exit 1
    fi

    if ! cd mkosi-kernel; then
        echo "Failed to change directory to mkosi-kernel"
        exit 1
    fi

    if ! git checkout "$COMMIT_SHA"; then
        echo "Failed to checkout commit: $COMMIT_SHA"
        cd - || { echo "Failed to return to the original directory"; exit 1; }
        exit 1
    fi

    if ! cp "$CONF_FILES_DIR/mkosi."* .; then
        echo "Failed to copy configuration files from $CONF_FILES_DIR"
        cd - || { echo "Failed to return to the original directory"; exit 1; }
        exit 1
    fi

    if ! cd -; then
        echo "Failed to return to the original directory"
        exit 1
    fi
}


function create_operating_system_dir {
    local CONFIG_FILE="mkosi.kernel.config"

    if ! cd $MKOSI_KERNEL_DIR; then
        echo "Failed to change directory to $MKOSI_KERNEL_DIR"
        exit 1
    fi

    if ! mkosi -f build -c "$CONFIG_FILE"; then
        echo "Failed to build operating system image"
        cd - || { echo "Failed to return to the original directory"; exit 1; }
        exit 1
    fi

    if ! cd -; then
        echo "Failed to return to the original directory"
        exit 1
    fi
}


function create_qcow2_img {
    local IMAGE_FILE="guest.img"
    local QCOW2_FILE="guest.qcow2"
    local MOUNT_POINT="/mnt/tmp-guest-img"
 
    cd $MKOSI_KERNEL_DIR || { echo "Failed to change directory to $MKOSI_KERNEL_DIR "; exit 1; }

    if ! dd if=/dev/null of=$IMAGE_FILE bs=1M seek=5120; then
        echo "Failed to create raw disk image"
        exit 1
    fi

    if ! mkfs.ext4 -F $IMAGE_FILE; then
        echo "Failed to format the image with ext4"
        exit 1
    fi

    LOOP_DEVICE=$(losetup -fP --show $IMAGE_FILE)
    if [ -z "$LOOP_DEVICE" ]; then
        echo "Failed to set up loop device"
        exit 1
    fi

    mkdir -p $MOUNT_POINT

    if ! mount $LOOP_DEVICE $MOUNT_POINT; then
        echo "Failed to mount $LOOP_DEVICE at $MOUNT_POINT"
        losetup -d $LOOP_DEVICE
        exit 1
    fi

    if ! cp -r /* $MOUNT_POINT; then
        echo "Failed to copy files to the mounted image"
        umount $MOUNT_POINT
        losetup -d $LOOP_DEVICE
        exit 1
    fi

    if ! umount $MOUNT_POINT; then
        echo "Failed to unmount $MOUNT_POINT"
        losetup -d $LOOP_DEVICE
        exit 1
    fi

    rmdir $MOUNT_POINT

    if ! sudo losetup -d $LOOP_DEVICE; then
        echo "Failed to detach loop device $LOOP_DEVICE"
        exit 1
    fi

    if ! qemu-img convert -f raw -O qcow2 $IMAGE_FILE $QCOW2_FILE; then
        echo "Failed to convert $IMAGE_FILE to $QCOW2_FILE"
        exit 1
    fi

    cd - || { echo "Failed to return to the original directory"; exit 1; }
}

if [ -d "${BUILD_DIR}" ]; then
    if ! rm -rf "${BUILD_DIR}"; then
        echo "Failed to remove existing ${BUILD_DIR}"
        exit 1
    fi
fi

if ! mkdir -p "${BUILD_DIR}" && cd "${BUILD_DIR}"; then
    echo "Failed to create or change directory to ${BUILD_DIR}"
    exit 1
fi

clone_kernel \
    && clone_mkosi \
    && clone_mkosi_kernel \
    && create_operating_system_dir \
    && create_qcow2_img && restore_mkosi 

if ! mv "$MKOSI_KERNEL_DIR/guest.qcow2" "${PARENT_DIR}/guest.qcow2"; then
    echo "Failed to move guest.qcow2 to ${PARENT_DIR}"
    exit 1
fi

cd "${PARENT_DIR}" || { echo "Failed to change directory to ${PARENT_DIR}"; exit 1; }

if ! rm -rf "${BUILD_DIR}"; then
    echo "Failed to remove ${BUILD_DIR}"
    exit 1
fi

echo "Successfully created the guest image and cleaned up"