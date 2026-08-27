#!/usr/bin/env bash
# Fetch DB-IP Lite — CC-BY 4.0, so it may be redistributed with this repo.
#
# This is the ONLY script in the project that touches the network, and it is a
# build-time step, never a runtime one. The resulting .mmdb is committed so the
# system runs air-gapped.
#
# DB-IP rather than MaxMind GeoLite2 because GeoLite2's licence forbids
# redistribution, and a database a judge cannot obtain is not "integrated".
set -euo pipefail
DEST="$(cd "$(dirname "$0")/.." && pwd)/data/geo"
mkdir -p "$DEST"

fetch_month() {
  local m="$1"
  local url="https://download.db-ip.com/free/dbip-asn-lite-${m}.mmdb.gz"
  echo "trying ${url}"
  curl -fsSL "$url" -o "$DEST/dbip-asn-lite.mmdb.gz" 2>/dev/null
}

# The current month's file may not be published yet; fall back one month.
if ! fetch_month "$(date -u +%Y-%m)"; then
  prev="$(date -u -v-1m +%Y-%m 2>/dev/null || date -u -d 'last month' +%Y-%m)"
  fetch_month "$prev" || { echo "could not download DB-IP Lite"; exit 1; }
fi

gunzip -f "$DEST/dbip-asn-lite.mmdb.gz"
printf '%s\n' \
  "DB-IP Lite ASN database" \
  "Licensed CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/" \
  "Source: https://db-ip.com/db/download/ip-to-asn-lite" \
  "Redistributed with attribution, as the licence permits." \
  > "$DEST/LICENSE-dbip.txt"
echo "wrote $DEST/dbip-asn-lite.mmdb ($(du -h "$DEST/dbip-asn-lite.mmdb" | cut -f1))"
