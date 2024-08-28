FROM rust:1.80

COPY . ./

RUN rustup target add x86_64-unknown-linux-musl \
    && cargo build --release

EXPOSE 8080
CMD ["cargo", "run", "--release"]
