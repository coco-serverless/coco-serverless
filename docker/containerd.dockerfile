FROM csegarragonz/dotfiles:0.2.0 as dotfiles
FROM golang

# ---------------------------
# Work. Env. Set-Up (do this first to benefit from caching)
# ---------------------------

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
# containerd source set-up
# ---------------------------

# Install APT dependencies
RUN apt update \
    && apt upgrade -y \
    && apt install -y \
        libbtrfs-dev \
        gopls

# Clone and build CoCo's containerd fork
RUN git clone \
        # TODO: change this to an upstream release tag once the merge to
        # main has happened
        -b CC-main \
        https://github.com/confidential-containers/containerd.git \
        /go/src/github.com/containerd/containerd \
    && cd /go/src/github.com/containerd/containerd \
    && make

WORKDIR /go/src/github.com/containerd/containerd
