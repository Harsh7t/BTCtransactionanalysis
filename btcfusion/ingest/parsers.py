"""Bulk readers for CSV / JSON / XML, and vectorised validation.

Everything is Polars from the first line: multi-threaded, and it does not fall
over at 1M+ rows the way pandas does. JSON and XML stream so we never hold the
whole document in memory.

Validation mirrors btcfusion.ingest.schema.RULES exactly. Bad rows are diverted
to a quarantine frame carrying the reason - never dropped, because a silent drop
corrupts every downstream number and leaves no trace that it happened.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl

from .mapper import Mapping, SchemaError, build_mapping, require_mappable
from .schema import ARRAY_FIELDS, CANONICAL, GENESIS, INT_ARRAY_FIELDS, MAX_SATS, SCRIPT_TYPES


def sniff_format(path: Path) -> str:
    suf = path.suffix.lower()
    if suf in (".csv", ".tsv"):
        return "csv"
    if suf in (".json", ".jsonl", ".ndjson"):
        return "json"
    if suf == ".xml":
        return "xml"
    head = path.open("rb").read(2048).lstrip()
    if head.startswith(b"<"):
        return "xml"
    if head.startswith(b"{") or head.startswith(b"["):
        return "json"
    return "csv"


# ---------------------------------------------------------------- readers
def _read_csv(path: Path) -> pl.DataFrame:
    return pl.read_csv(path, infer_schema_length=2000, try_parse_dates=False,
                       ignore_errors=True, truncate_ragged_lines=True)


def _read_json(path: Path) -> pl.DataFrame:
    """Handles both newline-delimited JSON and a single {"records":[...]} document."""
    with path.open("rb") as fh:
        first = fh.read(1)
    if first == b"{" or first == b"[":
        try:
            return pl.read_ndjson(path)
        except Exception:
            pass
        doc = json.loads(path.read_text())
        rows = doc.get("records", doc) if isinstance(doc, dict) else doc
        return pl.DataFrame(rows, infer_schema_length=2000)
    return pl.read_ndjson(path)


def _read_xml(path: Path) -> pl.DataFrame:
    """Streaming XML via lxml iterparse - the document never lands in memory whole."""
    from lxml import etree

    rows: list[dict] = []
    ctx = etree.iterparse(str(path), events=("end",))
    for _, el in ctx:
        if el.tag != "record":
            continue
        row: dict = {}
        for child in el:
            kids = list(child)
            if kids:
                row[child.tag] = [k.text or "" for k in kids]
            else:
                row[child.tag] = child.text
        rows.append(row)
        el.clear()
        while el.getprevious() is not None:
            del el.getparent()[0]
    return pl.DataFrame(rows, infer_schema_length=2000, strict=False)


READERS = {"csv": _read_csv, "json": _read_json, "xml": _read_xml}


# ------------------------------------------------------------ array fields
def _split_arrays(df: pl.DataFrame, cols: list[str], encoding: str, delim: str) -> pl.DataFrame:
    """Normalise array columns to Polars lists regardless of source encoding."""
    exprs = []
    for c in cols:
        dtype = df.schema[c]
        if isinstance(dtype, pl.List):
            e = pl.col(c).cast(pl.List(pl.Utf8))
        else:
            s = pl.col(c).cast(pl.Utf8).fill_null("")
            enc = encoding
            if enc == "auto":
                sample = df.get_column(c).cast(pl.Utf8).drop_nulls().head(20).to_list()
                enc = "json" if any(v.strip().startswith("[") for v in sample if v) else "delimited"
            if enc == "json":
                e = s.str.json_decode(dtype=pl.List(pl.Utf8))
            else:
                e = s.str.split(delim)
        if c in INT_ARRAY_FIELDS:
            e = e.list.eval(
                pl.element().cast(pl.Utf8).str.strip_chars().cast(pl.Int64, strict=False)
            ).list.drop_nulls()
        else:
            e = e.list.eval(pl.element().cast(pl.Utf8).str.strip_chars())
        exprs.append(e.alias(c))
    return df.with_columns(exprs)


def _from_long_format(df: pl.DataFrame, cfg: dict) -> pl.DataFrame:
    """Reassemble one-row-per-address input into one row per transaction."""
    lf = cfg["long_format"]
    key, adr, dr, amt = lf["group_key"], lf["address_col"], lf["direction_col"], lf["amount_col"]
    for c in (key, adr, dr, amt):
        if c not in df.columns:
            raise SchemaError(f"long format selected but column '{c}' is absent")
    grouped = df.group_by(key).agg([
        pl.col(adr).filter(pl.col(dr).str.to_lowercase() == "input").alias("input_addresses"),
        pl.col(adr).filter(pl.col(dr).str.to_lowercase() == "output").alias("output_addresses"),
        pl.col(amt).filter(pl.col(dr).str.to_lowercase() == "input").cast(pl.List(pl.Int64)).alias("input_amounts"),
        pl.col(amt).filter(pl.col(dr).str.to_lowercase() == "output").cast(pl.List(pl.Int64)).alias("output_amounts"),
        *[pl.col(c).first() for c in df.columns
          if c not in (key, adr, dr, amt) and not c.startswith("input")],
    ])
    return grouped


# -------------------------------------------------------------- validation
def _validate(df: pl.DataFrame, vcfg: dict) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Split into (clean, quarantined-with-reason). Mirrors schema.RULES."""
    max_fee = int(vcfg.get("max_fee_sat", MAX_SATS))
    skew_days = int(vcfg.get("max_future_skew_days", 2))
    now = dt.datetime.now(dt.timezone.utc)
    future_cut = now + dt.timedelta(days=skew_days)

    has = set(df.columns)
    reason = pl.lit(None, dtype=pl.Utf8)

    def when(cond, label):
        nonlocal reason
        reason = pl.when(reason.is_not_null()).then(reason).when(cond).then(pl.lit(label)).otherwise(None)

    when(pl.col("txid").is_null() | (pl.col("txid").cast(pl.Utf8).str.len_chars() < 4), "missing_txid")
    when(pl.col("timestamp").is_null()
         | (pl.col("timestamp") < pl.lit(GENESIS))
         | (pl.col("timestamp") > pl.lit(future_cut)), "bad_timestamp")
    when(pl.col("output_addresses").list.len() == 0, "no_outputs")
    when((pl.col("output_amounts").list.min() < 0)
         | (pl.col("output_amounts").list.max() > MAX_SATS), "amount_out_of_range")
    if "fee" in has:
        when((pl.col("fee") < 0) | (pl.col("fee") > max_fee), "fee_out_of_range")
    when(pl.col("output_addresses").list.len() != pl.col("output_amounts").list.len(),
         "length_mismatch")

    df = df.with_columns(reason.alias("_quarantine_reason"))
    bad = df.filter(pl.col("_quarantine_reason").is_not_null())
    good = df.filter(pl.col("_quarantine_reason").is_null()).drop("_quarantine_reason")
    return good, bad


# ------------------------------------------------------------------ entry
def ingest(path: Path, cfg: dict) -> tuple[pl.DataFrame, pl.DataFrame, Mapping, dict]:
    """Read, map, normalise and validate a capture file.

    Returns (clean, quarantined, mapping, receipt).
    """
    path = Path(path)
    fmt = sniff_format(path)
    raw = READERS[fmt](path)
    if raw.height == 0:
        raise SchemaError(f"{path.name} parsed to zero rows - is the file empty or truncated?")

    enc = cfg.get("array_encoding", "auto")
    if enc == "long":
        raw = _from_long_format(raw, cfg)

    mapping = build_mapping(list(raw.columns), cfg)
    require_mappable(mapping, list(raw.columns))

    df = raw.select([pl.col(src).alias(canon) for canon, src in mapping.columns.items()])

    arrays = [c for c in ARRAY_FIELDS if c in df.columns]
    df = _split_arrays(df, arrays, enc, cfg.get("array_delimiter", "|"))

    casts = []
    if "timestamp" in df.columns:
        if df.schema["timestamp"] == pl.Utf8:
            casts.append(
                pl.coalesce(
                    pl.col("timestamp").str.to_datetime(time_zone="UTC", strict=False),
                    pl.col("timestamp").cast(pl.Int64, strict=False)
                      .cast(pl.Datetime("us"), strict=False).dt.replace_time_zone("UTC"),
                ).alias("timestamp"))
        else:
            casts.append(pl.col("timestamp").cast(pl.Datetime("us"), strict=False)
                         .dt.replace_time_zone("UTC").alias("timestamp"))
    for c in ("fee", "asn", "src_port", "dst_port"):
        if c in df.columns:
            casts.append(pl.col(c).cast(pl.Int64, strict=False).alias(c))
    for c in ("src_ip", "dst_ip", "txid", "geo_country"):
        if c in df.columns:
            casts.append(pl.col(c).cast(pl.Utf8).alias(c))
    if "script_type" in df.columns:
        casts.append(
            pl.when(pl.col("script_type").cast(pl.Utf8).str.to_lowercase().is_in(list(SCRIPT_TYPES)))
              .then(pl.col("script_type").cast(pl.Utf8).str.to_lowercase())
              .otherwise(pl.lit("unknown")).alias("script_type"))
    if casts:
        df = df.with_columns(casts)

    for c in CANONICAL:
        if c not in df.columns:
            df = df.with_columns(pl.lit(None).alias(c))

    good, bad = _validate(df, cfg.get("validation", {}))

    # An announcement is identified by (txid, src_ip, dst_ip, timestamp). dst_ip
    # MUST be in the key: one node announcing the same tx to several peers within
    # the same second is several real propagation edges, and dropping them would
    # quietly demolish the propagation-tree evidence the attribution engine
    # depends on (§16.2-C).
    before = good.height
    subset = [c for c in ("txid", "src_ip", "dst_ip", "timestamp") if c in good.columns]
    # maintain_order matters: without it Polars returns rows in an arbitrary
    # order, which makes the pipeline non-deterministic and defeats golden-file
    # reproducibility - the whole point of `make reproduce`.
    good = good.unique(subset=subset, keep="first", maintain_order=True)
    dupes = before - good.height

    q_breakdown = (bad.group_by("_quarantine_reason").len().to_dicts() if bad.height else [])
    receipt = {
        "file": path.name,
        "format": fmt,
        "rows_read": raw.height,
        "rows_clean": good.height,
        "rows_quarantined": bad.height,
        "duplicates_removed": dupes,
        "quarantine_breakdown": {d["_quarantine_reason"]: d["len"] for d in q_breakdown},
        "mapped_columns": mapping.columns,
        "unmapped_input_columns": mapping.unmapped_inputs,
        "chain_only_mode": mapping.chain_only,
    }
    return good, bad, mapping, receipt
