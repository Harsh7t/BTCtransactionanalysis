"""Tests, weighted by what actually breaks.

The roadmap names three as worth more than the rest combined, and they are the
three here that are not ordinary unit tests:

  1. SPLIT INTEGRITY  - group leakage is the most common silent error in this
     exact problem, and it is silent precisely because it makes numbers better.
  2. ENTITY RESOLUTION CORRECTNESS - if Union-Find is wrong, every entity-level
     number downstream is wrong in a way no metric will reveal.
  3. ROBUSTNESS TO A JUDGE'S FILE - different headers, missing IP columns,
     malformed rows. Must produce a clear error or degrade, never a traceback.

The leak test itself lives in btcfusion/generator/leak_test.py because it needs
a full capture; `make leak-test` gates it in CI.
"""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from btcfusion.eval.splits import SplitViolation, verify
from btcfusion.graph.resolve import resolve_entities, script_of_address, to_transactions
from btcfusion.ingest.mapper import SchemaError, build_mapping, norm, require_mappable
from btcfusion.attribute.behaviour import agreement, hour_histogram, infer_offset
from btcfusion.attribute.significance import benjamini_hochberg
from btcfusion.detect.fuse import fuse_scores
from btcfusion.eval import metrics as M

SCHEMA_CFG = {
    "aliases": {
        "timestamp": ["timestamp", "time"], "txid": ["txid", "tx_hash"],
        "src_ip": ["src_ip", "source_ip"], "dst_ip": ["dst_ip"],
        "input_addresses": ["input_addresses", "inputs"],
        "output_addresses": ["output_addresses", "outputs"],
        "output_amounts": ["output_amounts"], "fee": ["fee"],
    },
    "required": ["timestamp", "txid", "input_addresses", "output_addresses", "output_amounts"],
}


# --------------------------------------------------------------- schema map
def test_header_normalisation_is_separator_and_case_insensitive():
    assert norm("Src IP") == norm("src_ip") == norm("SRC-IP") == "srcip"


def test_mapper_accepts_a_judges_alternative_headers():
    m = build_mapping(["time", "tx_hash", "source_ip", "inputs", "outputs",
                       "output_amounts"], SCHEMA_CFG)
    assert m.columns["timestamp"] == "time"
    assert m.columns["txid"] == "tx_hash"
    assert m.missing_required == []
    assert not m.chain_only


def test_missing_ip_columns_degrade_to_chain_only_rather_than_failing():
    m = build_mapping(["timestamp", "txid", "inputs", "outputs", "output_amounts"], SCHEMA_CFG)
    assert m.chain_only is True
    assert m.missing_required == []          # still runnable


def test_unmappable_file_raises_a_readable_error_not_a_traceback():
    headers = ["col_a", "col_b"]
    m = build_mapping(headers, SCHEMA_CFG)
    with pytest.raises(SchemaError) as e:
        require_mappable(m, headers)
    msg = str(e.value)
    assert "schema_map.yaml" in msg          # tells the analyst what to do
    assert "col_a" in msg                    # shows what we actually saw


# ---------------------------------------------------- entity resolution (H1/H2)
def _tx(txid, ins, outs, amts, ts="2026-06-01T00:00:00Z", script="p2wpkh"):
    return {"txid": txid, "timestamp": ts, "input_addresses": ins,
            "output_addresses": outs, "input_amounts": [1] * len(ins),
            "output_amounts": amts, "fee": 1000, "script_type": script}


def _frame(rows):
    df = pl.DataFrame(rows).with_columns(
        pl.col("timestamp").str.to_datetime(time_zone="UTC"))
    return df


def test_cospent_inputs_are_merged_into_one_entity():
    """Common-input-ownership: co-spending proves shared control."""
    txs = _frame([
        _tx("t1", ["A", "B"], ["X"], [100]),
        _tx("t2", ["B", "C"], ["Y"], [100]),
    ])
    mapping, stats = resolve_entities(txs)
    m = dict(zip(mapping.get_column("address").to_list(),
                 mapping.get_column("entity_id").to_list()))
    assert m["A"] == m["B"] == m["C"], "A-B and B-C co-spends must transitively merge"
    assert m["X"] != m["A"], "a pure recipient must not join the spender's cluster"


def test_unrelated_spenders_are_never_merged():
    txs = _frame([_tx("t1", ["A"], ["X"], [100]), _tx("t2", ["B"], ["Y"], [100])])
    mapping, _ = resolve_entities(txs)
    m = dict(zip(mapping.get_column("address").to_list(),
                 mapping.get_column("entity_id").to_list()))
    assert m["A"] != m["B"], "a false merge invents an actor that does not exist"


def test_resolution_is_order_independent():
    """Union-Find must not depend on the order transactions arrive in."""
    rows = [_tx("t1", ["A", "B"], ["X"], [100]), _tx("t2", ["C", "D"], ["Y"], [100]),
            _tx("t3", ["B", "C"], ["Z"], [100])]
    a, _ = resolve_entities(_frame(rows))
    b, _ = resolve_entities(_frame(list(reversed(rows))))

    def groups(mapping):
        d: dict[str, set] = {}
        for addr, eid in zip(mapping.get_column("address").to_list(),
                             mapping.get_column("entity_id").to_list()):
            d.setdefault(eid, set()).add(addr)
        return sorted(sorted(v) for v in d.values())
    assert groups(a) == groups(b)


def test_script_type_inferred_from_address_encoding():
    """The change heuristic and the wallet fingerprint both depend on this."""
    df = pl.DataFrame({"address": [
        "1" + "a" * 33, "3" + "b" * 33, "bc1q" + "c" * 38, "bc1q" + "d" * 58,
        "bc1p" + "e" * 58]})
    got = df.select(script_of_address(pl.col("address"))).to_series().to_list()
    assert got == ["p2pkh", "p2sh", "p2wpkh", "p2wsh", "p2tr"]


def test_transaction_collapse_does_not_multiply_per_tx_statistics():
    """Many announcements of one tx must collapse to a single chain-layer row."""
    rows = [_tx("t1", ["A"], ["X"], [100]) for _ in range(5)]
    for i, r in enumerate(rows):
        r["src_ip"] = f"198.18.0.{i}"
    df = _frame(rows)
    txs = to_transactions(df)
    assert txs.height == 1
    assert txs.get_column("n_announcements")[0] == 5


# ------------------------------------------------------------ split integrity
def _split_frame():
    return pl.DataFrame({
        "idx": [0, 1, 2, 3], "illicit": [0, 1, 0, 1],
        "typology": ["", "peel_chain", "", "dormancy_burst"],
        "first_ts": [10, 20, 30, 40],
    })


def test_entity_in_two_splits_is_rejected():
    with pytest.raises(SplitViolation, match="leakage"):
        verify(_split_frame(),
               {"train": np.array([0, 1]), "test": np.array([1, 2])}, [])


def test_test_set_before_train_set_is_rejected():
    with pytest.raises(SplitViolation, match="past from the future"):
        verify(_split_frame(),
               {"train": np.array([2, 3]), "test": np.array([0, 1])}, [])


def test_heldout_typology_leaking_into_training_is_rejected():
    # Deliberately temporally VALID (train ts 10,20 < test ts 30,40) so this
    # isolates the typology rule instead of tripping the ordering check first.
    with pytest.raises(SplitViolation, match="not one example"):
        verify(_split_frame(),
               {"train": np.array([0, 1]), "calib": np.array([], dtype=int),
                "test": np.array([2, 3])}, ["peel_chain"])


def test_a_clean_split_passes_all_three_rules():
    verify(_split_frame(),
           {"train": np.array([0, 1]), "calib": np.array([], dtype=int),
            "test": np.array([2, 3])}, ["cross_asn_structuring"])


# ----------------------------------------------------------------- attribution
def test_behavioural_offset_recovers_the_timezone_it_was_generated_in():
    """The whole point: recover an operator's timezone from activity shape alone."""
    for true_offset in (330, -300, 60):      # IST, US-Central, CET
        # Activity concentrated at 14:00 LOCAL, stored as UTC.
        local_peak = 14
        utc_hours = [(local_peak - true_offset // 60 + h) % 24
                     for h in (-2, -1, 0, 0, 0, 1, 2)]
        ts = np.array([h * 3600 for h in utc_hours] * 12)
        off, fit, diurnality = infer_offset(hour_histogram(ts))
        assert abs(off - true_offset) <= 90, f"expected ~{true_offset}, got {off}"
        assert diurnality > 0.3


def test_flat_activity_reports_low_diurnality_so_confidence_can_discount_it():
    """A 24/7 exchange fits every offset equally; the engine must know that."""
    ts = np.array([h * 3600 for h in range(24)] * 20)
    _, _, diurnality = infer_offset(hour_histogram(ts))
    assert diurnality < 0.15


def test_timezone_agreement_decays_with_distance():
    assert agreement(330, 330) == 1.0
    assert agreement(330, 360) == 1.0            # within tolerance
    assert agreement(330, -300) < 0.5            # opposite side of the world
    assert agreement(0, 1380) == 1.0             # wraps around midnight


def test_fdr_control_is_stricter_than_a_raw_threshold():
    """Testing 100k pairs at p<0.01 uncorrected would return ~1000 false links."""
    p = np.concatenate([np.full(5, 1e-9), np.random.default_rng(0).uniform(0.02, 1, 995)])
    passed = benjamini_hochberg(p, alpha=0.01)
    assert passed[:5].all()
    assert passed.sum() < 20


# ---------------------------------------------------------------- scoring math
def test_fusion_respects_its_weights():
    hi = fuse_scores(np.array([1.0]), np.array([0.0]), np.array([0.0]),
                     {"supervised": 1.0, "novelty": 0.0, "evidence": 0.0})
    assert hi[0] == pytest.approx(1.0)
    mixed = fuse_scores(np.array([1.0]), np.array([0.0]), np.array([0.0]),
                        {"supervised": 0.5, "novelty": 0.5, "evidence": 0.0})
    assert mixed[0] == pytest.approx(0.5)


def test_fused_score_is_always_a_valid_probability():
    rng = np.random.default_rng(0)
    out = fuse_scores(rng.random(500), rng.random(500), rng.random(500),
                      {"supervised": 0.65, "novelty": 0.25, "evidence": 0.10})
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_precision_at_k_reads_the_top_of_the_ranking():
    y = np.array([1, 1, 0, 0, 0])
    s = np.array([0.9, 0.8, 0.7, 0.6, 0.5])
    assert M.precision_at_k(y, s, 2) == 1.0
    assert M.precision_at_k(y, s, 4) == 0.5


def test_ece_is_zero_for_a_perfectly_calibrated_model():
    rng = np.random.default_rng(0)
    p = rng.random(20000)
    y = (rng.random(20000) < p).astype(int)
    assert M.expected_calibration_error(y, p) < 0.02


def test_pr_auc_of_a_random_ranker_approaches_the_base_rate():
    rng = np.random.default_rng(0)
    y = (rng.random(20000) < 0.05).astype(int)
    assert M.pr_auc(y, rng.random(20000)) == pytest.approx(0.05, abs=0.02)
