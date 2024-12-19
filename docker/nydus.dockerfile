FROM ghcr.io/sc2-sys/base:0.10.0

# ---------------------------
# Nydus daemon set-up
# ---------------------------

# Install APT dependencies
RUN apt-get update \
    && apt-get install -y \
        cmake \
        gopls \
        make

# Build the daemon and other tools like nydusify
ARG CODE_DIR=/go/src/github.com/sc2-sys/nydus
RUN mkdir -p ${CODE_DIR} \
    && git clone\
        -b sc2-main \
        https://github.com/sc2-sys/nydus.git \
        ${CODE_DIR} \
    && git config --global --add safe.directory ${CODE_DIR} \
    && cd ${CODE_DIR} \
    && DOCKER=false GOPROXY=https://proxy.golang.org make all-release

WORKDIR ${CODE_DIR}
