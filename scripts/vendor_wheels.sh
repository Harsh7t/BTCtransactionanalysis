#!/usr/bin/env bash
# Vendor every runtime dependency as a Linux wheel.
#
# Build-time only, and one of only two steps that need network (the other is
# fetch_geoip.sh). After this the image builds and installs with networking
# disabled, which is what "offline" has to mean on demo day.
#
# Platform is pinned to manylinux x86_64 because that is the deployment target;
# building on an arm64 Mac would otherwise vendor Darwin wheels the container
# cannot install, and the failure would only appear inside Docker.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/wheels"
rm -rf "$DEST" && mkdir -p "$DEST"

python3 -m pip download \
  --dest "$DEST" \
  --platform manylinux2014_x86_64 \
  --python-version 3.11 \
  --implementation cp \
  --only-binary=:all: \
  fastapi "uvicorn[standard]" pydantic python-multipart \
  numpy scipy scikit-learn polars pyarrow pandas \
  lightgbm shap duckdb python-igraph gensim \
  lxml ijson pyyaml jinja2 maxminddb \
  pytest hypothesis

echo "vendored $(ls "$DEST" | wc -l | tr -d ' ') wheels into wheels/"
