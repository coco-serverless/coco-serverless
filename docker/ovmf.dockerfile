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

COPY ./patches/ovmf_profile.patch /tmp/ovmf_profile.patch
ARG TARGET
RUN mkdir -p /usr/src/edk2 \
    && git clone \
        -b edk2-stable202302 \
        --single-branch --depth 1 \
        https://github.com/tianocore/edk2.git \
        /usr/src/edk2 \
    && cd /usr/src/edk2 \
    && git submodule update --init \
    && make -C BaseTools/ \
    && touch OvmfPkg/AmdSev/Grub/grub.efi \
    && git apply /tmp/ovmf_profile.patch \
    && cd OvmfPkg \
    && ./build.sh \
        -b ${TARGET} \
        -D DEBUG_ON_SERIAL_PORT \
        -p OvmfPkg/AmdSev/AmdSevX64.dsc
        # -D DEBUG_VERBOSE \

WORKDIR /usr/src/edk2
