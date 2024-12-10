FROM ghcr.io/sc2-sys/base:0.10.0

# ---------------------------
# Nydus snapshotter daemon set-up
# ---------------------------

# Install APT dependencies
RUN apt-get update \
    && apt-get install -y \
    # gcc clang cmake \
        gopls \
        # libseccomp-dev \
        make \
        # musl-tools \
        # wget \
        # libdevmapper-dev \
        protobuf-compiler

ARG CODE_DIR=/go/src/github.com/sc2-sys/nydus-snapshotter
RUN mkdir -p ${CODE_DIR} \
    && git clone\
        -b sc2-main \
        https://github.com/sc2-sys/nydus-snapshotter.git \
        ${CODE_DIR} \
    && git config --global --add safe.directory ${CODE_DIR} \
    && cd ${CODE_DIR} \
    && make

WORKDIR ${CODE_DIR}
