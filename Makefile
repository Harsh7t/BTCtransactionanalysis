# BTC-FUSION. Every published number regenerates from these targets.
PY      := .venv/bin/python
CAPTURE := data/samples/capture.csv
TRUTH   := data/samples/capture_truth
ART     := artifacts/v1
PORT    ?= 8000

.PHONY: help setup generate train run leak-test reproduce serve ui test offline-check clean

help:
	@grep -E '^[a-z-]+:.*?##' $(MAKEFILE_LIST) | sed 's/:.*##/\t/' | expand -t22

setup:            ## create the venv and install everything (needs network ONCE)
	uv venv --python 3.11
	uv pip install -e ".[dev]"
	cd ui && npm ci && npm run build

generate:         ## synthesise a labelled capture (CSV + JSONL + XML)
	$(PY) -m btcfusion.cli generate --name capture --format all
	cp data/samples/capture_truth/geoip_table.csv data/geo/asn-blocks.csv

train:            ## fit, calibrate, evaluate -> $(ART)/metrics.json
	$(PY) -m btcfusion.cli train $(CAPTURE) $(TRUTH) --artifacts $(ART)

run:              ## score a capture end to end   (make run FILE=path/to/x.csv)
	$(PY) -m btcfusion.cli run $(or $(FILE),$(CAPTURE)) --artifacts $(ART)

leak-test:        ## prove the generator encodes no shortcut. MUST pass.
	$(PY) -m btcfusion.cli leak-test $(CAPTURE) $(TRUTH) --out $(ART)/leak_test.json >/dev/null

serve:            ## run the API + built UI on :$(PORT)
	$(PY) -m btcfusion.cli serve --port $(PORT)

ui:               ## rebuild the frontend bundle
	cd ui && npm run build

test:             ## unit + property + integrity tests
	$(PY) -m pytest -q

# The single command behind every figure in the write-up. Fixed seed in,
# metrics.json out. If a number is not reproduced by this, it is not a result.
reproduce:        ## regenerate EVERY published number from the seed
	@echo "── 1/4 generate (seeded) ─────────────────────────────"
	@$(MAKE) --no-print-directory generate
	@echo "── 2/4 leak test (gate) ──────────────────────────────"
	@$(MAKE) --no-print-directory leak-test
	@echo "── 3/4 train + evaluate ──────────────────────────────"
	@$(MAKE) --no-print-directory train
	@echo "── 4/4 score ─────────────────────────────────────────"
	@$(MAKE) --no-print-directory run
	@echo ""
	@echo "Every number in docs/ and the deck now traces to:"
	@echo "  $(ART)/metrics.json      model + evaluation"
	@echo "  $(ART)/leak_test.json    generator integrity"
	@echo "  $(ART)/manifest.json     seed, git sha, feature version, input hash"

offline-check:    ## fail if any source file reaches the network at runtime
	@echo "scanning for runtime network calls…"
	@! grep -rnE "https?://" --include=*.py btcfusion/ \
		| grep -vE "#|\"\"\"|docs|example\.com" \
		|| (echo "FAIL: a runtime URL is present" && exit 1)
	@! grep -rn "fonts.googleapis\|cdn\." ui/src/ ui/index.html \
		|| (echo "FAIL: UI references an external asset host" && exit 1)
	@echo "PASS: no outbound endpoints in application code."

clean:
	rm -rf data/case.duckdb data/uploads data/exports ui/dist

geoip:            ## fetch DB-IP Lite (CC-BY). Build-time only; result is committed.
	./scripts/fetch_geoip.sh

sensitivity:      ## attribution accuracy vs observation coverage -> the honest curve
	$(PY) -m btcfusion.cli sensitivity

validate-external: ## validate the chain-side detector on real labelled data (Elliptic)
	$(PY) -m btcfusion.cli validate-external

golden-update:    ## regenerate the golden feature fingerprint (READ THE DIFF)
	@$(PY) -c "import tempfile, json, pathlib, sys; sys.path.insert(0,'.'); \
from tests.test_golden import _fingerprint; \
d=pathlib.Path('tests/golden'); d.mkdir(parents=True, exist_ok=True); \
(d/'feature_matrix.json').write_text(json.dumps(_fingerprint(pathlib.Path(tempfile.mkdtemp())), indent=2)); \
print('wrote tests/golden/feature_matrix.json')"
