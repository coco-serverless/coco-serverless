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

ENV GOPATH=/go
ENV PATH=${PATH}:/usr/local/go/bin

# Clone and build containerd
ARG CONTAINERD_VERSION
RUN git clone \
        # -b v1.7.19 \
        -b v${CONTAINERD_VERSION} \
        https://github.com/containerd/containerd.git \
        /go/src/github.com/containerd/containerd \
    && cd /go/src/github.com/containerd/containerd \
    && make

WORKDIR /go/src/github.com/containerd/containerd
