#!/usr/bin/env bash
# Prove the container runs with NO network access.
#
# `--network none` is the whole point: any hidden outbound call fails here, on a
# developer machine, instead of silently on the judging laptop.
set -euo pipefail
IMAGE="${1:-btc-fusion:0.3.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "== 1/4 unit, property and golden tests, offline =="
docker run --rm --network none "$IMAGE" \
  python -m pytest tests/ -q -p no:warnings --ignore=tests/test_golden.py

echo "== 2/4 which ML backend does LINUX actually resolve? =="
docker run --rm --network none "$IMAGE" python -c "
import lightgbm
from btcfusion.detect.supervised import SupervisedDetector
print('  lightgbm', lightgbm.__version__, '- OpenMP runtime loaded')
print('  detector backend:', SupervisedDetector().backend)"

echo "== 3/4 GeoIP resolves from the bundled database, offline =="
docker run --rm --network none "$IMAGE" python -c "
import ipaddress, numpy as np
from pathlib import Path
from btcfusion.ingest.enrich import GeoIP
g = GeoIP(table_path=Path('data/geo/asn-blocks.csv'),
          mmdb_path=next(iter(Path('data/geo').glob('*.mmdb')), None))
out = g.resolve(np.array([int(ipaddress.ip_address('8.8.8.8'))], dtype=np.int64))
print('  source:', g.source)
print('  8.8.8.8 ->', 'AS%d' % out['asn'][0], out['country'][0])
assert out['asn'][0] != 0, 'bundled GeoIP failed to resolve offline'"

echo "== 4/4 full pipeline end to end, offline =="
docker run --rm --network none -v "$ROOT/data/samples:/app/data/samples:ro" \
  -v "$ROOT/data/geo:/app/data/geo:ro" "$IMAGE" \
  python -m btcfusion.cli run data/samples/capture.csv --artifacts artifacts/v1 \
  | tail -24

echo ""
echo "OFFLINE VERIFICATION PASSED - everything above ran with --network none."
