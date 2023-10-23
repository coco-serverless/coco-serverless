FROM ubuntu:22.04

RUN apt update \
    && apt upgrade -y \
    && apt install -y \
        g++ \
        gcc \
        git \
        iasl \
        make \
        nasm \
        python3 \
        python-is-python3 \
        uuid-dev \
        vim

ARG TARGET
RUN mkdir -p /usr/src/edk2 \
    && git clone \
        https://github.com/tianocore/edk2.git \
        /usr/src/edk2 \
    && cd /usr/src/edk2 \
    && git submodule update --init \
    && make -C BaseTools/ \
    && touch OvmfPkg/AmdSev/Grub/grub.efi \
    && cd OvmfPkg \
    && ./build.sh -b ${TARGET} -p OvmfPkg/AmdSev/AmdSevX64.dsc

WORKDIR /usr/src/edk2
