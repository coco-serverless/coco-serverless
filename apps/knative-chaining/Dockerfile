FROM rust:1.80

WORKDIR /app
COPY . ./

# RUN rustup target add x86_64-unknown-linux-musl \
RUN cargo build --release

EXPOSE 8080
CMD ["cargo", "run", "--release"]
