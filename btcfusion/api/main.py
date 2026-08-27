"""FastAPI surface. The models live in this same process - no serialisation
boundary, and no second service that can die mid-demo (roadmap §4.1).

There is deliberately no authentication. This is an air-gapped single-analyst
workstation; the operating system is the access boundary. Building login screens
would be theatre that costs a day and adds nothing (§3.4).
"""
from __future__ import annotations

import json
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..graph.build import khop_subgraph
from ..pipeline import DATA, ROOT, load_cfg, run_pipeline
from ..store.dao import Store

app = FastAPI(title="BTC-FUSION",
              description="AI-powered monitoring and analysis of Bitcoin transaction "
                          "traffic. SIH 2026 · PS 26146 · NTRO.",
              version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

DB = DATA / "case.duckdb"
UPLOADS = DATA / "uploads"
JOBS: dict[str, dict] = {}
_lock = threading.Lock()


def store() -> Store:
    return Store(DB)


# ----------------------------------------------------------------- runs
class RunRequest(BaseModel):
    path: str | None = None


@app.get("/api/health")
def health():
    cfg = load_cfg("detect.yaml")
    art = ROOT / "artifacts" / "v1" / "manifest.json"
    return {
        "status": "ok",
        "offline": True,
        "model_artifacts": art.exists(),
        "backend": (json.loads(art.read_text()).get("backend") if art.exists() else None),
        "threshold": cfg["alerts"]["threshold"],
    }


@app.get("/api/runs")
def list_runs():
    s = store()
    try:
        return {"runs": s.runs()}
    finally:
        s.close()


@app.get("/api/runs/latest")
def latest_run():
    s = store()
    try:
        r = s.latest_run()
        if not r:
            return {"run": None}
        for k in ("receipt", "timings", "provenance", "metrics"):
            if isinstance(r.get(k), str):
                r[k] = json.loads(r[k])
        return {"run": r}
    finally:
        s.close()


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "unknown job")
    return j


def _execute(job_id: str, path: Path):
    JOBS[job_id] = {"job_id": job_id, "state": "running", "stage": "ingest",
                    "file": path.name}

    def progress(stage: str):
        JOBS[job_id]["stage"] = stage

    try:
        res = run_pipeline(path, artifacts=ROOT / "artifacts" / "v1", db=DB,
                           progress=progress)
        JOBS[job_id] = {"job_id": job_id, "state": "done", "stage": "complete",
                        "file": path.name, "run_id": res["run_id"],
                        "receipt": res["receipt"]}
    except Exception as exc:
        JOBS[job_id] = {"job_id": job_id, "state": "error", "file": path.name,
                        "error": f"{type(exc).__name__}: {exc}"}


@app.post("/api/runs")
def start_run(req: RunRequest):
    """Score a capture already on disk (the data-engineer path)."""
    path = Path(req.path or (DATA / "samples" / "capture.csv"))
    if not path.exists():
        raise HTTPException(404, f"no such file: {path}")
    job_id = uuid.uuid4().hex[:10]
    threading.Thread(target=_execute, args=(job_id, path), daemon=True).start()
    return {"job_id": job_id}


@app.post("/api/upload")
async def upload(file: UploadFile):
    UPLOADS.mkdir(parents=True, exist_ok=True)
    dest = UPLOADS / (file.filename or "capture.csv")
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    job_id = uuid.uuid4().hex[:10]
    threading.Thread(target=_execute, args=(job_id, dest), daemon=True).start()
    return {"job_id": job_id, "file": dest.name, "bytes": dest.stat().st_size}


@app.get("/api/samples")
def samples():
    d = DATA / "samples"
    out = []
    if d.exists():
        for p in sorted(d.glob("*")):
            if p.is_file() and p.suffix.lower() in (".csv", ".json", ".jsonl", ".xml"):
                out.append({"name": p.name, "path": str(p),
                            "mb": round(p.stat().st_size / 1e6, 1)})
    return {"samples": out}


# --------------------------------------------------------------- alerts
@app.get("/api/alerts")
def alerts(run_id: str | None = None, min_confidence: float = 0.0,
           typology: str | None = None, country: str | None = None,
           asn_type: str | None = None, unreviewed: bool = False, limit: int = 200):
    s = store()
    try:
        rid = run_id or (s.latest_run() or {}).get("run_id")
        if not rid:
            return {"alerts": [], "run_id": None}
        sql = ["SELECT * FROM alerts WHERE run_id = ? AND confidence >= ?"]
        params: list = [rid, min_confidence]
        if typology:
            sql.append("AND typologies LIKE ?")
            params.append(f"%{typology}%")
        if country:
            sql.append("AND top_country = ?")
            params.append(country)
        if asn_type:
            sql.append("AND top_asn_type = ?")
            params.append(asn_type)
        if unreviewed:
            sql.append("AND (verdict IS NULL OR verdict = '')")
        sql.append("ORDER BY rank ASC LIMIT ?")
        params.append(limit)
        rows = s.q(" ".join(sql), params)
        # Threshold sweep for the live precision/recall trade-off slider.
        sweep = s.q(
            "SELECT round(confidence, 1) AS bucket, count(*) AS n FROM alerts "
            "WHERE run_id = ? GROUP BY 1 ORDER BY 1 DESC", [rid])
        return {"run_id": rid, "alerts": rows, "sweep": sweep}
    finally:
        s.close()


@app.get("/api/alerts/{entity}")
def case_file(entity: str, run_id: str | None = None):
    """Everything needed to assemble a case file, in one round trip."""
    s = store()
    try:
        rid = run_id or (s.latest_run() or {}).get("run_id")
        alert = s.q("SELECT * FROM alerts WHERE run_id = ? AND entity = ?", [rid, entity])
        if not alert:
            raise HTTPException(404, f"no alert for {entity} in run {rid}")
        ev = s.q("SELECT * FROM evidence WHERE run_id = ? AND entity = ?", [rid, entity])
        for e in ev:
            e["txids"] = json.loads(e["txids"] or "[]")
            e["detail"] = json.loads(e["detail"] or "[]")
        attr = s.q("SELECT * FROM attributions WHERE run_id = ? AND entity = ? "
                   "ORDER BY rank", [rid, entity])
        for a in attr:
            a["counterfactuals"] = json.loads(a["counterfactuals"] or "[]")
        shap = s.q("SELECT * FROM shap_values WHERE run_id = ? AND entity = ? "
                   "ORDER BY abs(contribution) DESC", [rid, entity])
        beh = s.q("SELECT * FROM behaviour WHERE run_id = ? AND entity = ?", [rid, entity])
        for b in beh:
            b["hour_histogram"] = json.loads(b["hour_histogram"] or "[]")
        txs = s.q("SELECT * FROM entity_txs WHERE run_id = ? AND entity = ? "
                  "ORDER BY tx_score DESC, ts DESC LIMIT 200", [rid, entity])
        return {"run_id": rid, "alert": alert[0], "evidence": ev, "attribution": attr,
                "shap": shap, "behaviour": beh[0] if beh else None, "transactions": txs}
    finally:
        s.close()


class Verdict(BaseModel):
    verdict: str
    reason: str = ""


@app.post("/api/alerts/{entity}/verdict")
def set_verdict(entity: str, v: Verdict, run_id: str | None = None):
    """Analyst confirm / dismiss. Feeds the re-ranking signal."""
    s = store()
    try:
        rid = run_id or (s.latest_run() or {}).get("run_id")
        s.set_verdict(rid, entity, v.verdict, v.reason)
        return {"ok": True, "entity": entity, "verdict": v.verdict}
    finally:
        s.close()


# ---------------------------------------------------------------- graph
@app.get("/api/graph/{entity}")
def graph(entity: str, hops: int = 2, run_id: str | None = None):
    """k-hop neighbourhood, extracted server-side with a hard node cap.

    Sending the raw neighbourhood to the browser is how link-analysis views die
    (§4.4 R4). We cap, we reduce hops to fit, and we tell the analyst what was
    trimmed instead of silently truncating.
    """
    import polars as pl
    s = store()
    try:
        rid = run_id or (s.latest_run() or {}).get("run_id")
        rows = s.q("SELECT src, dst, value, n_tx FROM entity_edges WHERE run_id = ?", [rid])
        if not rows:
            return {"nodes": [], "edges": [], "meta": {"nodes_shown": 0, "hops": 0}}
        edges = pl.DataFrame(rows)
        cfg = load_cfg("detect.yaml")["graph"]
        nodes, sub, meta = khop_subgraph(edges, entity, hops=hops,
                                         node_cap=int(cfg["node_cap"]))
        alerted = {r["entity"] for r in s.q(
            "SELECT entity FROM alerts WHERE run_id = ?", [rid])}
        meta["total_nodes_in_run"] = int(
            (s.q("SELECT count(*) AS n FROM alerts WHERE run_id = ?", [rid]) or
             [{"n": 0}])[0]["n"])
        return {
            "nodes": [{"id": n, "subject": n == entity, "alerted": n in alerted}
                      for n in nodes],
            "edges": sub.to_dicts(),
            "meta": meta,
        }
    finally:
        s.close()


@app.get("/api/transactions")
def transactions(run_id: str | None = None, min_score: float = 0.0, limit: int = 200):
    """Transaction-level alert list - the PS's 'wallet/transaction' second half."""
    s_ = store()
    try:
        rid = run_id or (s_.latest_run() or {}).get("run_id")
        return {"run_id": rid, "transactions": s_.q(
            "SELECT * FROM entity_txs WHERE run_id = ? AND tx_score >= ? "
            "ORDER BY tx_score DESC LIMIT ?", [rid, min_score, limit])}
    finally:
        s_.close()


@app.get("/api/graph/{entity}/expand")
def graph_expand(entity: str, run_id: str | None = None):
    """Constituent wallets and transactions beneath one entity supernode."""
    s_ = store()
    try:
        rid = run_id or (s_.latest_run() or {}).get("run_id")
        addrs = s_.q("SELECT address FROM entity_addresses "
                     "WHERE run_id = ? AND entity = ? LIMIT 200", [rid, entity])
        txs = s_.q("SELECT txid, ts, value_out FROM entity_txs "
                   "WHERE run_id = ? AND entity = ? ORDER BY tx_score DESC LIMIT 60",
                   [rid, entity])
        return {
            "entity": entity,
            "addresses": [{"address": a["address"]} for a in addrs[:60]],
            "transactions": [{"txid": t["txid"], "ts": str(t["ts"]),
                              "value": int(t["value_out"] or 0)} for t in txs],
            "truncated": len(addrs) > 60,
            "n_addresses_total": len(addrs),
        }
    finally:
        s_.close()


# ---------------------------------------------------- model transparency
@app.get("/api/model")
def model_panel():
    """Architecture, training size, held-out scores, calibration, ablation.

    The screen that makes the AI falsifiable rather than decorative.
    """
    art = ROOT / "artifacts" / "v1" / "manifest.json"
    if not art.exists():
        return {"available": False,
                "note": "No trained artefacts. Run `make train` to produce them."}
    manifest = json.loads(art.read_text())
    leak = ROOT / "artifacts" / "v1" / "leak_test.json"
    sens = ROOT / "artifacts" / "v1" / "sensitivity.json"
    ext = ROOT / "artifacts" / "v1" / "external_validation.json"
    return {"available": True, "manifest": manifest,
            "leak_test": json.loads(leak.read_text()) if leak.exists() else None,
            "sensitivity": json.loads(sens.read_text()) if sens.exists() else None,
            "external": json.loads(ext.read_text()) if ext.exists() else None}


@app.get("/api/provenance")
def provenance(run_id: str | None = None):
    s = store()
    try:
        rid = run_id or (s.latest_run() or {}).get("run_id")
        rows = s.q("SELECT run_id, created_at, source_file, provenance, receipt, timings "
                   "FROM runs WHERE run_id = ?", [rid])
        if not rows:
            return {"provenance": None}
        r = rows[0]
        for k in ("provenance", "receipt", "timings"):
            if isinstance(r.get(k), str):
                r[k] = json.loads(r[k])
        return r
    finally:
        s.close()


@app.get("/api/quarantine")
def quarantine(run_id: str | None = None):
    s = store()
    try:
        rid = run_id or (s.latest_run() or {}).get("run_id")
        return {"quarantine": s.q(
            "SELECT reason, n FROM quarantine WHERE run_id = ? ORDER BY n DESC", [rid])}
    finally:
        s.close()


# ------------------------------------------------------------- case PDF
@app.get("/api/alerts/{entity}/export")
def export_case(entity: str, run_id: str | None = None):
    """Self-contained HTML case file with an embedded provenance manifest.

    HTML rather than PDF: WeasyPrint's system dependencies are a liability on an
    air-gapped box, and every browser prints to PDF. Same artefact, one fewer
    thing to install (roadmap §3.4 reasoning applied to §F16 F22).
    """
    from ..explain.report import render_case_html
    s = store()
    try:
        rid = run_id or (s.latest_run() or {}).get("run_id")
        data = case_file(entity, rid)
        prov = provenance(rid)
        out = DATA / "exports"
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"case_{entity}_{rid}.html"
        path.write_text(render_case_html(data, prov), encoding="utf-8")
        return FileResponse(path, media_type="text/html", filename=path.name)
    finally:
        s.close()


# ------------------------------------------------------------- static UI
UI_DIST = ROOT / "ui" / "dist"
if UI_DIST.exists():
    app.mount("/", StaticFiles(directory=str(UI_DIST), html=True), name="ui")
