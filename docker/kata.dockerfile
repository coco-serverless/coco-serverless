FROM csegarragonz/dotfiles:0.2.0 as dotfiles
FROM ubuntu:22.04

# ---------------------------
# Work. Env. Set-Up (do this first to benefit from caching)
# ---------------------------

# APT dependencies
RUN apt update \
    && apt upgrade -y \
    && apt install -y \
        clang \
        curl \
        libclang-dev \
        libdevmapper-dev \
        git

# Clone the dotfiles repo
RUN rm -rf ~/dotfiles \
    && mkdir -p ~/dotfiles \
    && git clone https://github.com/csegarragonz/dotfiles ~/dotfiles

# Configure Neovim
COPY --from=dotfiles /neovim/build/bin/nvim /usr/bin/nvim
COPY --from=dotfiles /usr/local/share/nvim /usr/local/share/nvim
RUN curl -fLo ~/.local/share/nvim/site/autoload/plug.vim --create-dirs \
        https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim \
    && mkdir -p ~/.config/nvim/ \
    && ln -sf ~/dotfiles/nvim/init.vim ~/.config/nvim/init.vim \
    && ln -sf ~/dotfiles/nvim/after ~/.config/nvim/ \
    && ln -sf ~/dotfiles/nvim/syntax ~/.config/nvim/ \
    && nvim +PlugInstall +qa \
    && nvim +PlugUpdate +qa

# Configure Bash
RUN ln -sf ~/dotfiles/bash/.bashrc ~/.bashrc \
    && ln -sf ~/dotfiles/bash/.bash_profile ~/.bash_profile \
    && ln -sf ~/dotfiles/bash/.bash_aliases ~/.bash_aliases

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

# Install latest rust and rust-analyser
RUN curl --proto '=https' --tlsv1.3 https://sh.rustup.rs -sSf | sh -s -- -y \
    && curl -L \
        https://github.com/rust-lang/rust-analyzer/releases/latest/download/rust-analyzer-x86_64-unknown-linux-gnu.gz \
        | gunzip -c - > /usr/bin/rust-analyzer \
    && chmod +x /usr/bin/rust-analyzer

# Install go
ARG GO_VERSION="1.21.1"
RUN mkdir -p /tmp/go \
    && cd /tmp/go \
    && wget https://go.dev/dl/go${GO_VERSION}.linux-amd64.tar.gz \
    && rm -rf /usr/local/go \
    && tar -C /usr/local -xzf go${GO_VERSION}.linux-amd64.tar.gz

# Fetch code and build the runtime and the agent
ENV GOPATH=/go
ENV PATH=${PATH}:/usr/local/go/bin:/root/.cargo/bin
ARG CODE_DIR=/go/src/github.com/kata-containers/kata-containers
RUN mkdir -p ${CODE_DIR} \
    && git clone\
        # Note that we use our fork from CC-0.8.0 + patches
        -b sc2-main \
        https://github.com/coco-serverless/kata-containers \
        ${CODE_DIR} \
    && git config --global --add safe.directory ${CODE_DIR} \
    && cd ${CODE_DIR}/src/runtime && make \
    && cd ${CODE_DIR}/src/agent \
    && rustup target add x86_64-unknown-linux-musl \
    && make

# Configure environment variables
RUN echo "export PATH=${PATH}:/usr/local/go/bin:/root/.cargo/bin" >> ~/.bashrc
RUN echo "export GOPATH=/go" >> ~/.bashrc

WORKDIR ${CODE_DIR}
