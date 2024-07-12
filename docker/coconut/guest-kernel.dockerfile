FROM ubuntu:22.04

ARG KERNEL_CONFIG_FILE=./.kernel_config

RUN apt update \
    && apt upgrade -y \
    && apt install -y \
        git \
        fakeroot \
        build-essential \
        ncurses-dev \
        xz-utils \
        libssl-dev \
        bc \
        flex \
        libelf-dev \
        bison \
        kmod
# /boot/config-$(uname -r)
COPY ${KERNEL_CONFIG_FILE} /root/.config


RUN git clone https://github.com/coconut-svsm/linux ~/linux \
    && cd ~/linux \
    && git checkout svsm \
    && cp /root/.config .config \
    #  && make menuconfig \
    && make defconfig \
    && echo "CONFIG_KVM_AMD_SEV=y" >> .config \
    && make -j $(nproc)