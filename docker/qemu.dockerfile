FROM ubuntu:22.04

RUN apt update \
    && apt upgrade -y \
    && apt install -y \
        bzip2 \
        g++ \
        gcc \
        git \
        libglib2.0-dev \
        libpixman-1-dev \
        make \
        ninja-build \
        python3 \
        python3-venv \
        wget

# The QEMU configure flags are picked to match those in Kata's QEMU build here:
# https://github.com/kata-containers/kata-containers/blob/main/tools/packaging/scripts/configure-hypervisor.sh
RUN mkdir -p /usr/src \
    && git clone \
        -b v8.1.2 \
        --single-branch --depth 1 \
        https://gitlab.com/qemu-project/qemu.git \
        /usr/src/qemu \
    && cd /usr/src/qemu \
    && ./configure \
        --cpu=x86_64 \
        --datadir=/opt/confidential-containers/share/kata-qemu-csg/ \
        --target-list=x86_64-softmmu \
        --enable-kvm \
        --enable-trace-backends=log,simple \
        --disable-auth-pam \
        --disable-bsd-user \
        --disable-capstone \
        --disable-curl \
        --disable-curses \
        --disable-docs \
        --disable-gio \
        --disable-glusterfs \
        --disable-gtk \
        --disable-guest-agent \
        --disable-guest-agent-msi \
        --disable-libiscsi \
        --disable-libudev \
        --disable-linux-user \
        --disable-live-block-migration \
        --disable-lzo \
        --disable-opengl \
        --disable-rdma \
        --disable-replication \
        --disable-sdl \
        --disable-snappy \
        --disable-spice \
        --disable-tools \
        --disable-tpm \
        --disable-vde \
        --disable-virglrenderer \
        --disable-vnc \
        --disable-vnc-jpeg \
        --disable-vnc-sasl \
        --disable-vte \
        --disable-xen \
        --static \
    && make -j $(nproc)

WORKDIR /usr/src/qemu
