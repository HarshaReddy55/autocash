# AutoCash - multi-stage build: Rust kernel + Python service
FROM rust:1-slim AS kernel
WORKDIR /build
COPY rust-kernel/Cargo.toml rust-kernel/Cargo.lock* ./
COPY rust-kernel/src ./src
RUN cargo build --release

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    AUTOCASH_DATA_DIR=/app/data \
    AUTOCASH_KERNEL_BIN=/app/bin/autocash-kernel
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/app ./backend/app
COPY frontend ./frontend
COPY --from=kernel /build/target/release/autocash-kernel /app/bin/autocash-kernel
RUN mkdir -p /app/data && useradd -m autocash && chown -R autocash /app
USER autocash
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ready')" || exit 1
CMD ["sh", "-c", "python -m uvicorn api:app --app-dir backend/app --host 0.0.0.0 --port ${PORT:-8080}"]
