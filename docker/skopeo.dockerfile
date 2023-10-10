FROM golang:1.21.0

# Install APT dependencies
RUN apt update \
    && apt upgrade -y \
    && apt install -y \
        git \
        libassuan-dev \
        libbtrfs-dev \
        libdevmapper-dev \
        libgpgme-dev \
        pkg-config

# Clone and build CoCo's containerd fork
ARG SKOPEO_VERSION
RUN git clone \
        -b v${SKOPEO_VERSION} \
        https://github.com/containers/skopeo \
        /go/src/github.com/containers/skopeo
        #  && make

WORKDIR /go/src/github.com/containers/skopeo
