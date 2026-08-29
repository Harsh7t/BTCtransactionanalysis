"""Deterministic fingerprint of the shipped model's outputs.

WHY. The container installs whatever `vendor_wheels.sh` resolved - today sklearn
1.7.2 - while the artefacts under artifacts/v1 were pickled by whatever the
developer machine had (1.9.0). scikit-learn warns on that mismatch that it "might
lead to breaking code or invalid results", and it is right to: a pickle is not a
stable format across versions.

We measured it and the scores are bit-identical. But that is a fact about these
two versions, not a property of the design, and the vendor script pins no
versions - so the next `make wheels` could resolve a release where it is no longer
true, silently. This turns the assumption into a check: the container reproduces
the fingerprint, or the offline verification fails.

Run on the host to regenerate the golden value:
    PYTHONPATH=. .venv/bin/python scripts/score_fingerprint.py > tests/golden/score_fingerprint.txt
"""
import hashlib
import json
from pathlib import Path

import numpy as np

from btcfusion.detect.supervised import SupervisedDetector

# Paths are relative to the working directory, NOT to this file: the container
# mounts the script at /app/ while the repo keeps it in scripts/, so a
# file-relative root resolves differently in the two places we need it to agree.
# Both invocations run from the project root.
ART = Path("artifacts") / "v1"


def fingerprint() -> str:
    model = SupervisedDetector.load(ART / "supervised.pkl")
    names = json.loads((ART / "feature_names.json").read_text())
    # Fixed synthetic design matrix: this checks the DESERIALISED MODEL, not the
    # pipeline, so it must not depend on a capture file being mounted.
    X = np.random.default_rng(7).normal(size=(500, len(names))).astype(np.float32)
    s = np.round(model.predict_proba(X), 8)
    return hashlib.sha256(s.tobytes()).hexdigest()


if __name__ == "__main__":
    print(fingerprint())
