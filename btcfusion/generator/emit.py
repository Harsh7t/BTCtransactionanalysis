"""Writers for the three formats the PS names: CSV, JSON, XML.

CSV has no native array type, so `input_addresses[]` and friends need an explicit
encoding convention (roadmap §16.2-D). We default to pipe-delimited and the
ingest layer accepts delimited, JSON-in-cell and long format, because a judge's
file will not necessarily use ours.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

ARRAY_FIELDS = ("input_addresses", "output_addresses", "input_amounts", "output_amounts")
FIELDS = ("timestamp", "src_ip", "dst_ip", "src_port", "dst_port", "txid",
          "input_addresses", "output_addresses", "input_amounts", "output_amounts",
          "fee", "script_type", "geo_country", "asn")


def _enc(v, style: str):
    if not isinstance(v, (list, tuple)):
        return v
    if style == "json":
        return json.dumps([str(x) for x in v])
    return "|".join(str(x) for x in v)


def write_csv(rows: Iterable[dict], path: str | Path, array_encoding: str = "delimited") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(FIELDS))
        w.writeheader()
        for r in rows:
            w.writerow({k: _enc(r[k], array_encoding) for k in FIELDS})
    return path


def write_jsonl(rows: Iterable[dict], path: str | Path) -> Path:
    """Newline-delimited JSON: streams cleanly at bulk sizes, unlike one big array."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({k: r[k] for k in FIELDS}) + "\n")
    return path


def write_json(rows: Iterable[dict], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump({"records": [{k: r[k] for k in FIELDS} for r in rows]}, fh)
    return path


def write_xml(rows: Iterable[dict], path: str | Path) -> Path:
    """Hand-rolled streaming writer.

    ponytail: lxml would need the whole tree in memory at bulk sizes. Escaping is
    the only tricky part and the values here are hex, IPs and enum strings.
    """
    from xml.sax.saxutils import escape

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<records>\n')
        for r in rows:
            fh.write("  <record>\n")
            for k in FIELDS:
                v = r[k]
                if k in ARRAY_FIELDS:
                    fh.write(f"    <{k}>\n")
                    for item in v:
                        fh.write(f"      <item>{escape(str(item))}</item>\n")
                    fh.write(f"    </{k}>\n")
                else:
                    fh.write(f"    <{k}>{escape(str(v))}</{k}>\n")
            fh.write("  </record>\n")
        fh.write("</records>\n")
    return path


def write_truth(capture, outdir: str | Path) -> dict[str, Path]:
    """Ground truth and the bundled GeoIP table. Never read by the feature pipeline."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, rows in (("truth_entities", capture.truth_entities),
                       ("truth_addresses", capture.truth_addresses),
                       ("truth_txs", capture.truth_txs),
                       ("geoip_table", capture.geoip_table)):
        p = outdir / f"{name}.csv"
        with p.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        paths[name] = p
    p = outdir / "capture_stats.json"
    p.write_text(json.dumps(capture.stats, indent=2))
    paths["stats"] = p
    return paths
