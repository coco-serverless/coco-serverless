FROM ghcr.io/sc2-sys/base:0.10.0

# ---------------------------
# containerd source set-up
# ---------------------------

# Install APT dependencies
RUN apt update \
    && apt upgrade -y \
    && apt install -y \
        libbtrfs-dev \
        gopls \
        make

# Clone and build containerd
ARG CODE_DIR=/go/src/github.com/sc2-sys/containerd
RUN git clone \
        -b sc2-main \
        https://github.com/sc2-sys/containerd.git \
        ${CODE_DIR} \
    && cd ${CODE_DIR} \
    && make

WORKDIR ${CODE_DIR}
