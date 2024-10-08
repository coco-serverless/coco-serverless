FROM ubuntu:24.04

RUN apt update \
    && apt upgrade -y \
    && apt install -y \
        git \
        make \
        cbindgen \
        curl \
        gcc \
        libcunit1 \
        libcunit1-doc \
        libcunit1-dev \
        gettext \
        python3-venv \
        ninja-build \
        bzip2 \
        libglib2.0-dev \
        rustc \
        iasl \
        build-essential \
        libglib2.0-dev \
        libfdt-dev \
        libpixman-1-dev \
        zlib1g-dev \
        libudev-dev \
        libvdeplug-dev \
        libslirp-dev \
        seabios

# Clone and build IGVM
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y \
    && . "$HOME/.cargo/env" \
    && git clone --branch igvm-v0.1.6 https://github.com/microsoft/igvm/ ~/igvm \
    && cd ~/igvm \
    && make -f igvm_c/Makefile \
    && make -f igvm_c/Makefile install 

# Clone and build IGVM-enabled Qemu
ARG QEMU_DATADIR
RUN git clone https://github.com/coconut-svsm/qemu ~/qemu \
    && cd ~/qemu \
    && git checkout svsm-igvm \
    && export PKG_CONFIG_PATH=$PKG_CONFIG_PATH:/usr/lib64/pkgconfig/ \
    && ./configure \
        --datadir=${QEMU_DATADIR} \
        --prefix=$HOME/bin/qemu-svsm/ \
        --target-list=x86_64-softmmu \
        --enable-igvm \
        --static \
        --disable-gio \
        --disable-libudev \
        --enable-kvm \
        --enable-trace-backends=log,simple \
        --enable-slirp \
    && ninja -C build/ \
    && make install -j $(nproc)
