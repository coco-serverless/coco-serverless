FROM ghcr.io/sc2-sys/base:0.10.0

# ---------------------------
# Kata Containers source set-up
# ---------------------------

# Install APT dependencies
RUN apt install -y \
        gcc \
        gopls \
        libseccomp-dev \
        make \
        musl-tools \
        wget

# Install rust
RUN curl --proto '=https' --tlsv1.3 https://sh.rustup.rs -sSf | sh -s -- -y

# Install go
ARG GO_VERSION
RUN mkdir -p /tmp/go \
    && cd /tmp/go \
    && wget https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz \
    && rm -rf /usr/local/go \
    && tar -C /usr/local -xzf go${GO_VERSION}.linux-amd64.tar.gz

ENV GOPATH=/go
ENV PATH=${PATH}:/usr/local/go/bin:/root/.cargo/bin

# ---------------------------
# Build Kata
#
# We need a few patches to get Knative and our baseline experiments to work
# on top of upstream Kata, so we maintain two separate source trees in our
# build container: one for the baselines (branch sc2-baseline) and one for
# SC2 (branch sc2-main). This introduces a bit of duplication but, at the same
# time, allows us to have clearly differentiated targets to, e.g., build
# different initrds.
# ---------------------------

# Kata does not build with Rust > 1.78, so we pin to an older version
# https://github.com/kata-containers/kata-containers/pull/10320
ARG RUST_VERSION

# Fetch code and build the runtime and the agent for our baselines
ARG CODE_DIR=/go/src/github.com/kata-containers/kata-containers-baseline
RUN mkdir -p ${CODE_DIR} \
    && git clone\
        -b sc2-baseline \
        https://github.com/sc2-sys/kata-containers \
        ${CODE_DIR} \
    && git config --global --add safe.directory ${CODE_DIR} \
    && cd ${CODE_DIR}/src/runtime \
    && make \
    && cd ${CODE_DIR}/src/agent \
    && rustup default ${RUST_VERSION} \
    && rustup component add rust-analyzer \
    && rustup target add x86_64-unknown-linux-musl \
    && make

# Fetch code and build the runtime and the agent for SC2
ARG CODE_DIR=/go/src/github.com/kata-containers/kata-containers-sc2
RUN mkdir -p ${CODE_DIR} \
    && git clone\
        -b sc2-main \
        https://github.com/sc2-sys/kata-containers \
        ${CODE_DIR} \
    && git config --global --add safe.directory ${CODE_DIR} \
    && cd ${CODE_DIR}/src/runtime \
    && make \
    && cd ${CODE_DIR}/src/agent \
    && rustup default ${RUST_VERSION} \
    && rustup component add rust-analyzer \
    && rustup target add x86_64-unknown-linux-musl \
    && make

# Configure environment variables
RUN echo "export PATH=${PATH}:/usr/local/go/bin:/root/.cargo/bin" >> ~/.bashrc
RUN echo "export GOPATH=/go" >> ~/.bashrc

WORKDIR ${CODE_DIR}
