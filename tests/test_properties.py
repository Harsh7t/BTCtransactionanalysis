"""Property tests: invariants that must hold for ALL inputs, not three examples.

These catch the bugs unit tests miss - the case nobody thought of. Each property
below is a statement the system's correctness genuinely depends on.
"""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from hypothesis import given, settings, strategies as st

from btcfusion.attribute.behaviour import hour_histogram, infer_offset
from btcfusion.attribute.diffusion import repeat_weight
from btcfusion.detect.fuse import fuse_scores
from btcfusion.features.extract import transaction_features
from btcfusion.graph.resolve import resolve_entities

ADDR = st.text(alphabet="abcdef0123456789", min_size=4, max_size=8).map(lambda s: "1" + s)


@st.composite
def tx_batch(draw):
    n = draw(st.integers(min_value=1, max_value=10))
    rows = []
    for i in range(n):
        ins = draw(st.lists(ADDR, min_size=1, max_size=4, unique=True))
        outs = draw(st.lists(ADDR, min_size=1, max_size=4, unique=True))
        amts = draw(st.lists(st.integers(min_value=600, max_value=10**12),
                             min_size=len(outs), max_size=len(outs)))
        rows.append({"txid": f"t{i}", "timestamp": "2026-06-01T00:00:00Z",
                     "input_addresses": ins, "output_addresses": outs,
                     "input_amounts": [1] * len(ins), "output_amounts": amts,
                     "fee": 1000, "script_type": "p2pkh"})
    return pl.DataFrame(rows).with_columns(
        pl.col("timestamp").str.to_datetime(time_zone="UTC"))


def _groups(df):
    m, _ = resolve_entities(df)
    d: dict[str, set] = {}
    for a, e in zip(m.get_column("address").to_list(),
                    m.get_column("entity_id").to_list()):
        d.setdefault(e, set()).add(a)
    return sorted(sorted(v) for v in d.values())


@settings(max_examples=30, deadline=None)
@given(txs=tx_batch())
def test_resolution_is_order_independent_for_any_batch(txs):
    """Union-Find must never depend on the order transactions arrive in."""
    assert _groups(txs) == _groups(txs.reverse())


@settings(max_examples=30, deadline=None)
@given(txs=tx_batch())
def test_every_address_lands_in_exactly_one_entity(txs):
    """A partition, not an overlap. An address in two clusters is a merge bug."""
    m, _ = resolve_entities(txs)
    addrs = m.get_column("address").to_list()
    assert len(addrs) == len(set(addrs))


def _entropy(vals):
    df = pl.DataFrame([{
        "txid": "t", "timestamp": "2026-06-01T00:00:00Z",
        "input_addresses": ["a"],
        "output_addresses": [f"o{i}" for i in range(len(vals))],
        "input_amounts": [1], "output_amounts": list(vals), "fee": 10,
        "script_type": "p2pkh",
    }]).with_columns(pl.col("timestamp").str.to_datetime(time_zone="UTC"))
    return transaction_features(df).get_column("output_entropy")[0]


@settings(max_examples=50, deadline=None)
@given(amounts=st.lists(st.integers(min_value=1, max_value=10**10),
                        min_size=2, max_size=25))
def test_output_entropy_is_bounded_in_unit_interval(amounts):
    """Entropy is normalised; outside [0,1] means the normalisation is wrong."""
    e = _entropy(amounts)
    assert 0.0 - 1e-9 <= e <= 1.0 + 1e-9


@settings(max_examples=50, deadline=None)
@given(amounts=st.lists(st.integers(min_value=1000, max_value=10**8),
                        min_size=3, max_size=15))
def test_identical_outputs_maximise_entropy(amounts):
    """Shannon entropy peaks on a UNIFORM distribution.

    Equal-value outputs therefore score at the TOP of the range, not the bottom.
    This assertion was originally written the other way round, and the mixer
    matcher was keyed on it - so the rule matched the inverse of a CoinJoin until
    this property failed.
    """
    uniform = [amounts[0]] * len(amounts)
    assert _entropy(uniform) >= _entropy(amounts) - 1e-6


def _uniformity(vals):
    df = pl.DataFrame([{
        "txid": "t", "timestamp": "2026-06-01T00:00:00Z",
        "input_addresses": ["a"],
        "output_addresses": [f"o{i}" for i in range(len(vals))],
        "input_amounts": [1], "output_amounts": list(vals), "fee": 10,
        "script_type": "p2pkh",
    }]).with_columns(pl.col("timestamp").str.to_datetime(time_zone="UTC"))
    return transaction_features(df).get_column("output_uniformity")[0]


@settings(max_examples=50, deadline=None)
@given(n=st.integers(min_value=2, max_value=20), v=st.integers(1000, 10**8))
def test_repeated_output_values_score_high_uniformity(n, v):
    """The unambiguous mixer measure: N identical outputs score (N-1)/N."""
    assert _uniformity([v] * n) == pytest.approx((n - 1) / n)
    assert _uniformity([v + i for i in range(n)]) == pytest.approx(0.0)


@settings(max_examples=80)
@given(sup=st.floats(0, 1), nov=st.floats(0, 1), ev=st.floats(0, 1),
       ws=st.floats(0.01, 1), wn=st.floats(0, 1), we=st.floats(0, 1))
def test_fused_score_is_always_a_probability(sup, nov, ev, ws, wn, we):
    out = fuse_scores(np.array([sup]), np.array([nov]), np.array([ev]),
                      {"supervised": ws, "novelty": wn, "evidence": we})
    assert 0.0 <= out[0] <= 1.0


@settings(max_examples=80)
@given(n=st.integers(min_value=1, max_value=500))
def test_repeat_weight_is_monotonic_and_bounded(n):
    """More observations must never be weaker evidence."""
    a = float(repeat_weight(np.array([n]))[0])
    b = float(repeat_weight(np.array([n + 1]))[0])
    assert 0.0 <= a <= b <= 1.0


@settings(max_examples=40)
@given(counts=st.lists(st.integers(min_value=0, max_value=50),
                       min_size=24, max_size=24))
def test_timezone_inference_never_returns_an_impossible_offset(counts):
    off, fit, diurnality = infer_offset(np.array(counts, dtype=float))
    assert -720 <= off <= 720
    assert 0.0 <= fit <= 1.0
    assert 0.0 <= diurnality <= 1.0


@settings(max_examples=24)
@given(shift=st.integers(min_value=0, max_value=23))
def test_a_flat_histogram_is_never_reported_as_strongly_diurnal(shift):
    """Uniform activity fits every offset; claiming a timezone would be nonsense."""
    hist = np.roll(np.full(24, 10.0), shift)
    _, _, diurnality = infer_offset(hist)
    assert diurnality < 0.1
