FROM csegarragonz/dotfiles:0.2.0 as dotfiles
FROM ubuntu:22.04

# ---------------------------
# Work. Env. Set-Up (do this first to benefit from caching)
# ---------------------------

# APT dependencies
RUN apt update \
    && apt upgrade -y \
    && apt install -y \
        curl \
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
# Guest Components source set-up
# ---------------------------

# Install APT dependencies
RUN apt install -y \
        gcc \
        make \
        musl-tools \
        pkg-config \
        protobuf-compiler \
        tss2 \
        wget

# Install latest rust and rust-analyser
RUN curl --proto '=https' --tlsv1.3 https://sh.rustup.rs -sSf | sh -s -- -y \
    && curl -L \
        https://github.com/rust-lang/rust-analyzer/releases/latest/download/rust-analyzer-x86_64-unknown-linux-gnu.gz \
        | gunzip -c - > /usr/bin/rust-analyzer \
    && chmod +x /usr/bin/rust-analyzer

# Fetch code and build the runtime and the agent
ENV PATH=${PATH}:/root/.cargo/bin
ARG CODE_DIR=/usr/src/guest-components
RUN mkdir -p ${CODE_DIR} \
    && git clone\
        # Note that we use our fork from 0.10.0 + patches
        -b sc2-main \
        https://github.com/sc2-sys/guest-components \
        ${CODE_DIR} \
    && git config --global --add safe.directory ${CODE_DIR} \
    && cd ${CODE_DIR}/image-rs \
    && cargo build --release

# Configure environment variables
RUN echo "export PATH=${PATH}:/root/.cargo/bin" >> ~/.bashrc

WORKDIR ${CODE_DIR}
