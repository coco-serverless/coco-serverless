FROM rust:1.80

WORKDIR /app
COPY . ./

RUN cargo build --release

EXPOSE 8080
CMD ["cargo", "run", "--release"]
