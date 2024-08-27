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

ARG OVMF_DIR
COPY ${OVMF_DIR}/ovmf-svsm.fd /bin/ovmf-svsm.fd

RUN curl https://sh.rustup.rs -sSf | sh -s -- -y \
    && . "$HOME/.cargo/env" \
    && rustup target add x86_64-unknown-none \
    && git clone https://github.com/coco-serverless/svsm.git ~/svsm \
    && cd ~/svsm \
    && git submodule update --init \
    && cargo install bindgen-cli \
    && FW_FILE=/bin/ovmf-svsm.fd make
