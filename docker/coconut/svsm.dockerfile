FROM ubuntu:24.04 

RUN apt update \
    && apt upgrade -y \
    && apt install -y \
        curl \
        git \
        gcc \
        make \
        automake \
        libssl-dev \
        autoconf \
        autoconf-archive \
        build-essential \
        pkg-config \
        libclang-dev 


COPY {FIRMWARE_FILE} ~/ovmf-svsm.fd

RUN curl https://sh.rustup.rs -sSf | sh -s -- -y \
    && . "$HOME/.cargo/env" \
    && rustup target add x86_64-unknown-none \
    && git clone https://github.com/coconut-svsm/svsm ~/svsm \
    && cd ~/svsm \
    && git submodule update --init \
    && cargo install bindgen-cli \
    && FW_FILE=~/ovmf-svsm.fd make RELEASE=1