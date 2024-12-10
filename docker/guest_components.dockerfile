FROM ghcr.io/sc2-sys/base:0.10.0

# ---------------------------
# Guest Components source set-up
# ---------------------------

# Install APT dependencies
RUN apt install -y \
        cmake \
        musl-tools \
        pkg-config \
        protobuf-compiler \
        tss2

# Fetch code and build the runtime and the agent
ARG CODE_DIR=/usr/src/guest-components
RUN mkdir -p ${CODE_DIR} \
    && git clone\
        -b sc2-main \
        https://github.com/sc2-sys/guest-components \
        ${CODE_DIR} \
    && git config --global --add safe.directory ${CODE_DIR} \
    && cd ${CODE_DIR}/image-rs \
    && cargo build --release --features "nydus"

WORKDIR ${CODE_DIR}
