"""Robustness fixtures: the file a judge hands you is not the file you generated.

Each case here corresponds to a specific way a live demo dies (roadmap R5, §16.2-D,
§4.4). The requirement is never "parse everything" - it is "either parse it, or
explain precisely what is wrong". A stack trace on stage is the failure mode.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import polars as pl
import pytest
import yaml

from btcfusion.ingest.mapper import SchemaError, build_mapping
from btcfusion.ingest.parsers import ingest

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "schema_map.yaml").read_text())

ROWS = [
    {
        "timestamp": "2026-06-01T10:15:00Z", "src_ip": "198.18.0.5", "dst_ip": "198.18.0.9",
        "src_port": 41234, "dst_port": 8333, "txid": "a" * 64,
        "input_addresses": ["bc1qaaa", "bc1qbbb"], "output_addresses": ["bc1qccc", "bc1qddd"],
        "input_amounts": [500000, 400000], "output_amounts": [600000, 290000],
        "fee": 10000, "script_type": "p2wpkh", "geo_country": "IN", "asn": 64512,
    },
    {
        "timestamp": "2026-06-01T10:16:00Z", "src_ip": "198.18.0.6", "dst_ip": "198.18.0.9",
        "src_port": 51234, "dst_port": 8333, "txid": "b" * 64,
        "input_addresses": ["bc1qccc"], "output_addresses": ["bc1qeee"],
        "input_amounts": [600000], "output_amounts": [590000],
        "fee": 10000, "script_type": "p2wpkh", "geo_country": "DE", "asn": 64530,
    },
]


def _write_csv(path: Path, rows, headers=None, delim="|", encode="delimited"):
    headers = headers or {k: k for k in rows[0]}
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(headers.values()))
        w.writeheader()
        for r in rows:
            out = {}
            for k, v in r.items():
                if k not in headers:
                    continue
                if isinstance(v, list):
                    v = json.dumps(v) if encode == "json" else delim.join(str(x) for x in v)
                out[headers[k]] = v
            w.writerow(out)


def test_canonical_headers_parse(tmp_path):
    p = tmp_path / "clean.csv"
    _write_csv(p, ROWS)
    df, bad, mapping, receipt = ingest(p, CFG)
    assert receipt["rows_clean"] == 2
    assert receipt["rows_quarantined"] == 0
    assert df.get_column("output_amounts").list.sum().to_list() == [890000, 590000]


def test_judge_supplied_headers(tmp_path):
    """A file whose columns are named nothing like ours still maps cleanly."""
    alt = {
        "timestamp": "Observed At", "src_ip": "source-ip", "dst_ip": "PEER_IP",
        "src_port": "sport", "dst_port": "dport", "txid": "Transaction ID",
        "input_addresses": "vin_addresses", "output_addresses": "vout_addresses",
        "input_amounts": "vin_values", "output_amounts": "vout_values",
        "fee": "miner_fee", "script_type": "ScriptType",
        "geo_country": "country_code", "asn": "AS Number",
    }
    p = tmp_path / "judge.csv"
    _write_csv(p, ROWS, headers=alt)
    df, bad, mapping, receipt = ingest(p, CFG)
    assert receipt["rows_clean"] == 2
    assert mapping.get("src_ip") == "source-ip"
    assert not mapping.missing_required


def test_json_in_cell_arrays(tmp_path):
    """Exported captures commonly encode arrays as JSON inside a CSV cell."""
    p = tmp_path / "jsoncell.csv"
    _write_csv(p, ROWS, encode="json")
    df, bad, mapping, receipt = ingest(p, CFG)
    assert receipt["rows_clean"] == 2
    assert df.get_column("output_addresses").list.len().to_list() == [2, 1]


def test_missing_required_column_explains_itself(tmp_path):
    """No txid at all: a listed error naming the field, not a traceback."""
    headers = {k: k for k in ROWS[0] if k != "txid"}
    p = tmp_path / "notxid.csv"
    _write_csv(p, ROWS, headers=headers)
    with pytest.raises(SchemaError) as e:
        ingest(p, CFG)
    msg = str(e.value)
    assert "txid" in msg
    assert "schema_map.yaml" in msg          # tells the operator how to fix it


def test_no_ip_columns_falls_back_to_chain_only(tmp_path):
    """Chain-only mode: detection still runs, attribution is simply disabled."""
    headers = {k: k for k in ROWS[0] if k not in ("src_ip", "dst_ip")}
    p = tmp_path / "chainonly.csv"
    _write_csv(p, ROWS, headers=headers)
    df, bad, mapping, receipt = ingest(p, CFG)
    assert receipt["chain_only_mode"] is True
    assert receipt["rows_clean"] == 2


def test_malformed_rows_are_quarantined_not_dropped(tmp_path):
    """Every rejected row is counted and given a reason. Silent drops corrupt
    every downstream number and leave no trace that they happened."""
    rows = [
        dict(ROWS[0]),
        {**ROWS[1], "txid": ""},                                   # missing_txid
        {**ROWS[1], "txid": "c" * 64, "timestamp": "not-a-date"},  # bad_timestamp
        {**ROWS[1], "txid": "d" * 64, "output_amounts": [-5]},     # amount_out_of_range
        {**ROWS[1], "txid": "e" * 64, "output_amounts": [1, 2, 3]},  # length_mismatch
    ]
    p = tmp_path / "messy.csv"
    _write_csv(p, rows)
    df, bad, mapping, receipt = ingest(p, CFG)

    assert receipt["rows_read"] == 5
    assert receipt["rows_clean"] + receipt["rows_quarantined"] == 5   # nothing vanishes
    reasons = set(receipt["quarantine_breakdown"])
    assert "missing_txid" in reasons
    assert reasons & {"bad_timestamp", "amount_out_of_range", "length_mismatch"}


def test_empty_file_gives_a_clear_message(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("timestamp,txid\n")
    with pytest.raises(SchemaError) as e:
        ingest(p, CFG)
    assert "zero rows" in str(e.value)


def test_unmapped_columns_are_reported_not_ignored(tmp_path):
    rows = [{**ROWS[0], "operator_notes": "internal", "batch_id": "X-1"}]
    p = tmp_path / "extra.csv"
    _write_csv(p, rows)
    df, bad, mapping, receipt = ingest(p, CFG)
    assert set(receipt["unmapped_input_columns"]) == {"operator_notes", "batch_id"}


def test_header_normalisation_is_case_and_separator_insensitive():
    m = build_mapping(["SRC-IP", "Dst_Ip", "TxID", "  timestamp  "], CFG)
    assert m.get("src_ip") == "SRC-IP"
    assert m.get("dst_ip") == "Dst_Ip"
    assert m.get("txid") == "TxID"
