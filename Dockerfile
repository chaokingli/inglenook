# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm AS build

WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir build \
    && python -m build --wheel

FROM python:3.12-slim-bookworm

ARG TARGETARCH=amd64
ARG LLAMA_SWAP_VERSION=latest
ARG CADDY_VERSION=2.10.2
ARG INGLENOOK_VERSION=0.1.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INGLENOOK_VRAM_SOURCE=comfy \
    HOME=/home/inglenook \
    XDG_DATA_HOME=/var/lib/inglenook

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY docker/install-llama-swap.sh /tmp/install-llama-swap.sh
RUN chmod +x /tmp/install-llama-swap.sh \
    && /tmp/install-llama-swap.sh "${LLAMA_SWAP_VERSION}" "${TARGETARCH}" \
    && rm /tmp/install-llama-swap.sh \
    && curl -fsSL "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_${TARGETARCH}.tar.gz" \
      | tar -xz -C /usr/local/bin caddy

COPY --from=build /src/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl \
    && rm -rf /tmp/*.whl

COPY deploy/docker/gate.yaml /etc/inglenook/gate.yaml
COPY deploy/docker/llama-swap.yaml /etc/inglenook/llama-swap.yaml
COPY docker/Caddyfile.template /etc/inglenook/Caddyfile
COPY deploy/scripts/comfy-free.sh /etc/inglenook/scripts/comfy-free.sh
COPY deploy/docker/comfy-keepalive.sh /etc/inglenook/scripts/comfy-keepalive.sh
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod 0755 /usr/local/bin/entrypoint.sh /etc/inglenook/scripts/*.sh \
    && useradd --create-home --uid 1000 --shell /bin/false inglenook \
    && mkdir -p /var/lib/inglenook \
    && chown -R inglenook:inglenook /var/lib/inglenook /etc/inglenook

USER inglenook
WORKDIR /var/lib/inglenook
EXPOSE 9292 9293
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://127.0.0.1:9292/health || exit 1

LABEL org.opencontainers.image.title="inglenook" \
      org.opencontainers.image.description="VRAM gate plus llama-swap for NAS Docker" \
      org.opencontainers.image.version="${INGLENOOK_VERSION}" \
      org.opencontainers.image.source="https://github.com/chaokingli/inglenook"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
