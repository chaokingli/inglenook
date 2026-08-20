#!/bin/sh
# Download the llama-swap release binary into /usr/local/bin.
set -eu

VERSION="${1:-latest}"
ARCH="${2:-amd64}"

case "$ARCH" in
  amd64|x86_64) ARCH=amd64 ;;
  arm64|aarch64) ARCH=arm64 ;;
  *)
    echo "unsupported architecture: $ARCH" >&2
    exit 1
    ;;
esac

if [ "$VERSION" = "latest" ]; then
  VERSION="$(curl -fsSL https://api.github.com/repos/mostlygeek/llama-swap/releases/latest \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')"
fi

# Release tags look like v250; asset names drop the leading v.
NUM="${VERSION#v}"
URL="https://github.com/mostlygeek/llama-swap/releases/download/${VERSION}/llama-swap_${NUM}_linux_${ARCH}.tar.gz"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
curl -fsSL "$URL" | tar -xz -C "$tmpdir"
install -m 0755 "$tmpdir/llama-swap" /usr/local/bin/llama-swap
echo "installed llama-swap ${VERSION} (${ARCH})"
