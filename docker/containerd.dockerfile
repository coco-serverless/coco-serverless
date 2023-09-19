FROM golang

# Install APT dependencies
RUN apt update \
    && apt upgrade -y \
    && apt install -y \
        libbtrfs-dev

# Clone and build CoCo's containerd fork
RUN git clone \
        -b CC-main \
        https://github.com/confidential-containers/containerd.git \
        /go/src/github.com/containerd/containerd \
    && cd /go/src/github.com/containerd/containerd \
    && make

WORKDIR /go/src/github.com/containerd/containerd
