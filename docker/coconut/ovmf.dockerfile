FROM ubuntu:22.04

RUN sed -Ei 's/^# deb-src /deb-src /' /etc/apt/sources.list 
RUN apt update \
    && apt upgrade -y \
    && apt install -y \
        git \
    && apt build-dep ovmf -y

RUN git clone https://github.com/coconut-svsm/edk2.git ~/edk2\
    && cd ~/edk2/ \
    && git checkout svsm \
    && git submodule init \
    && git submodule update \
    && export PYTHON3_ENABLE=TRUE \
    && export PYTHON_COMMAND=python3 \
    && make -j16 -C BaseTools/ \ 
    && . ./edksetup.sh --reconfig \
    && build -a X64 -b DEBUG -t GCC5 -D DEBUG_ON_SERIAL_PORT -D DEBUG_VERBOSE -DTPM2_ENABLE -p OvmfPkg/OvmfPkgX64.dsc