"""BTC-FUSION command line. Everything the Makefile drives goes through here."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "data"


def load_cfg(name: str) -> dict:
    return yaml.safe_load((CONFIG / name).read_text())


def cmd_generate(args) -> int:
    from .generator.emit import write_csv, write_json, write_jsonl, write_truth, write_xml
    from .generator.simulate import simulate

    cfg = load_cfg("generator.yaml")
    if args.entities:
        cfg["population"]["n_entities"] = args.entities
    if args.days:
        cfg["time"]["days"] = args.days
    if args.coverage:
        cfg["network"]["observation_coverage"] = args.coverage

    t = time.perf_counter()
    cap = simulate(cfg, seed=args.seed)
    gen_s = time.perf_counter() - t

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stem = args.name
    written = []
    if args.format in ("csv", "all"):
        written.append(write_csv(cap.rows, out / f"{stem}.csv"))
    if args.format in ("json", "all"):
        written.append(write_jsonl(cap.rows, out / f"{stem}.jsonl"))
    if args.format in ("xml", "all"):
        written.append(write_xml(cap.rows, out / f"{stem}.xml"))
    if args.format == "json-array":
        written.append(write_json(cap.rows, out / f"{stem}.json"))
    write_truth(cap, out / f"{stem}_truth")

    s = cap.stats
    print(f"generated {s['n_rows']:,} announcement rows from {s['n_txs']:,} transactions "
          f"in {gen_s:.1f}s")
    print(f"  entities        {s['n_entities']:,}  ({s['n_illicit_entities']:,} illicit, "
          f"{100 * s['n_illicit_entities'] / max(1, s['n_entities']):.1f}%)")
    print(f"  illicit txs     {s['n_illicit_txs']:,}")
    print(f"  campaigns       {s['n_campaigns']:,}")
    print(f"  coverage        {s['observation_coverage']}")
    for p in written:
        print(f"  wrote {p.relative_to(ROOT)}  ({p.stat().st_size / 1e6:.1f} MB)")
    return 0


def cmd_run(args) -> int:
    from .pipeline import run_pipeline
    res = run_pipeline(Path(args.file), truth_dir=Path(args.truth) if args.truth else None,
                       artifacts=Path(args.artifacts) if args.artifacts else None,
                       db=Path(args.db))
    print(json.dumps(res["receipt"], indent=2))
    return 0


def cmd_train(args) -> int:
    from .train import train
    m = train(Path(args.file), Path(args.truth), Path(args.artifacts), db=Path(args.db))
    print(json.dumps(m, indent=2))
    return 0


def cmd_leak_test(args) -> int:
    from .generator.leak_test import leak_test
    ok, report = leak_test(Path(args.file), Path(args.truth))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        print(json.dumps(report, indent=2))
    if not ok:
        print("\nLEAK TEST FAILED — the generator encodes a shortcut. "
              "Every downstream number is meaningless until this is fixed.", file=sys.stderr)
        return 1
    print("\nLEAK TEST PASSED — non-predictive fields alone score at baseline.")
    return 0


def cmd_serve(args) -> int:
    import uvicorn
    uvicorn.run("btcfusion.api.main:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="btcfusion")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="synthesise a labelled capture")
    g.add_argument("--out", default=str(DATA / "samples"))
    g.add_argument("--name", default="capture")
    g.add_argument("--format", default="csv",
                   choices=["csv", "json", "xml", "json-array", "all"])
    g.add_argument("--entities", type=int)
    g.add_argument("--days", type=int)
    g.add_argument("--coverage", type=float)
    g.add_argument("--seed", type=int)
    g.set_defaults(func=cmd_generate)

    r = sub.add_parser("run", help="score a capture end to end")
    r.add_argument("file")
    r.add_argument("--truth")
    r.add_argument("--artifacts", default=str(ROOT / "artifacts" / "v1"))
    r.add_argument("--db", default=str(DATA / "case.duckdb"))
    r.set_defaults(func=cmd_run)

    t = sub.add_parser("train", help="fit and calibrate the models")
    t.add_argument("file")
    t.add_argument("truth")
    t.add_argument("--artifacts", default=str(ROOT / "artifacts" / "v1"))
    t.add_argument("--db", default=str(DATA / "train.duckdb"))
    t.set_defaults(func=cmd_train)

    lt = sub.add_parser("leak-test", help="prove the generator has no shortcut")
    lt.add_argument("file")
    lt.add_argument("truth")
    lt.add_argument("--out", help="write the report as clean JSON to this path")
    lt.set_defaults(func=cmd_leak_test)

    s = sub.add_parser("serve", help="run the API + UI")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true")
    s.set_defaults(func=cmd_serve)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
