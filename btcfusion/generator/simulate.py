"""The generator driver: population -> licit traffic -> laundering -> capture.

Output is a list of *announcement rows* (what a network capture actually
records) plus the ground truth we grade against. Ground truth never leaves this
module into the feature pipeline.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import numpy as np

from .actors import ARCHETYPES, build_population, draw_timestamps
from .ledger import DUST, Ledger
from .model import Actor, Tx
from .network import AddressSpace, PeerNetwork, SharedInfrastructure, diffuse
from .typologies import ALL_TYPOLOGIES, TypologyEngine

# Counterparty preference by archetype. Real payment graphs are not uniform:
# retail pays merchants and exchanges, miners pay exchanges, and so on.
COUNTERPARTY_PREF: dict[str, dict[str, float]] = {
    "exchange": {"retail": 0.55, "merchant": 0.2, "exchange": 0.1, "miner": 0.05, "darknet": 0.05, "mixer": 0.05},
    "merchant": {"exchange": 0.7, "merchant": 0.15, "retail": 0.15},
    "retail": {"merchant": 0.5, "exchange": 0.3, "retail": 0.2},
    "miner": {"exchange": 0.8, "merchant": 0.1, "retail": 0.1},
    "mixer": {"retail": 0.4, "mixer": 0.2, "exchange": 0.2, "merchant": 0.2},
    "darknet": {"exchange": 0.35, "mixer": 0.3, "retail": 0.2, "merchant": 0.15},
    "ransomware": {"mixer": 0.4, "exchange": 0.35, "retail": 0.25},
    "extortion": {"exchange": 0.45, "mixer": 0.3, "retail": 0.25},
}


@dataclass
class Capture:
    rows: list[dict]                 # announcement rows = the emitted dataset
    txs: list[Tx]
    actors: list[Actor]
    truth_entities: list[dict]       # ground-truth entity labels
    truth_addresses: list[dict]      # ground-truth address -> entity, for clustering eval
    truth_txs: list[dict]            # ground-truth transaction labels
    geoip_table: list[dict]          # the bundled offline enrichment DB
    stats: dict


def _parse_ts(s: str) -> int:
    return int(dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp())


# Payment size as a fraction of the payer's balance. ONE distribution, used by
# licit traffic and by crime proceeds alike (see TypologyEngine.fund_campaign).
#
# This is the leak firewall. If illicit money were drawn from even a slightly
# different family, the model would learn "big = bad", score beautifully, and
# teach us nothing - the exact silent failure the leak test exists to catch.
# sigma is wide on purpose so licit payments span the same range illicit ones do;
# a 1 BTC payment must not be evidence of anything by itself.
PAYMENT_LOG_MEAN = -3.0
PAYMENT_LOG_SIGMA = 1.9


def payment_fraction(rng: np.random.Generator) -> float:
    return float(rng.lognormal(mean=PAYMENT_LOG_MEAN, sigma=PAYMENT_LOG_SIGMA))


def _amount(rng: np.random.Generator, wealth: int) -> int:
    """Shared heavy-tailed payment size."""
    return max(DUST * 3, int(min(wealth * 0.9, wealth * payment_fraction(rng))))


def simulate(cfg: dict, seed: int | None = None) -> Capture:
    rng = np.random.default_rng(seed if seed is not None else int(cfg["seed"]))
    t0 = _parse_ts(cfg["time"]["start"])
    t1 = t0 + int(cfg["time"]["days"]) * 86400

    space = AddressSpace(rng)
    shared = SharedInfrastructure(space, rng, int(cfg["network"]["shared_pool_size"]))
    actors = build_population(cfg, space, rng)
    peers = PeerNetwork(space, rng, n_peers=2500,
                        coverage=float(cfg["network"]["observation_coverage"]))
    lg = Ledger(actors, cfg, rng, t0)

    by_arch: dict[str, list[Actor]] = {}
    for a in actors:
        by_arch.setdefault(a.archetype, []).append(a)

    # ---- 1. licit background traffic ------------------------------------
    days = int(cfg["time"]["days"])
    for a in actors:
        spec = ARCHETYPES[a.archetype]
        n = int(max(0, rng.poisson(spec.tx_per_day * days)))
        if n == 0:
            continue
        times = draw_timestamps(rng, n, t0, t1, a.tz_offset_min, spec.diurnal, spec.burstiness)
        prefs = COUNTERPARTY_PREF.get(a.archetype, {"retail": 1.0})
        kinds = list(prefs)
        probs = np.array([prefs[k] for k in kinds], float)
        probs /= probs.sum()
        for ts in times:
            bal = a.total_balance()
            if bal <= DUST * 8:
                break
            n_out = int(rng.integers(*spec.fan_out))
            targets: list[Actor] = []
            for _ in range(n_out):
                kind = str(rng.choice(kinds, p=probs))
                pool = by_arch.get(kind) or actors
                targets.append(pool[int(rng.integers(len(pool)))])
            if spec.equal_outputs:
                each = _amount(rng, bal) // max(1, n_out)
                lg.equal_split(a, targets, each, int(ts))
            else:
                recips = [(lg.receiving_address(t), _amount(rng, bal) // max(1, n_out))
                          for t in targets]
                lg.spend(a, recips, int(ts))

    # ---- 2. laundering campaigns ----------------------------------------
    cashouts = by_arch.get("exchange", []) + by_arch.get("merchant", [])
    eng = TypologyEngine(lg, space, shared, cfg, rng, t0, t1, cashouts=cashouts)
    sources = (by_arch.get("ransomware", []) + by_arch.get("darknet", [])
               + by_arch.get("extortion", []))
    mixers = by_arch.get("mixer", [])
    n_camp = int(cfg["typologies"]["n_campaigns"])
    campaign_log: list[dict] = []
    victims = by_arch.get("retail", []) + by_arch.get("merchant", [])
    if sources:
        for c in range(n_camp):
            src = sources[int(rng.integers(len(sources)))]
            typ = str(rng.choice(ALL_TYPOLOGIES))
            # Dormancy needs headroom at the front of the window to be dormant in.
            hi = t1 - 86400 * (40 if typ == "dormancy_burst" else 2)
            ts = int(rng.integers(t0, max(t0 + 3600, hi)))
            mixer = mixers[int(rng.integers(len(mixers)))] if mixers else None
            cid = f"CAMP-{c:04d}"
            # Proceeds must land before the laundering can move them.
            proceeds = eng.fund_campaign(src, victims, ts, typ, cid)
            txs = eng.run(typ, src, ts, cid, mixer=mixer)
            if txs:
                campaign_log.append({"campaign": cid, "typology": typ, "source": src.eid,
                                     "n_tx": len(txs), "n_proceeds": len(proceeds),
                                     "start_ts": ts})

    # ---- 2b. licit pass-through chains ----------------------------------
    # Structural counterweight to the laundering mules (see
    # TypologyEngine.licit_passthrough). Without these, "short-lived wallet that
    # forwards one chunk" is a perfect illicit predictor and the model never has
    # to learn laundering at all.
    n_passthrough = int(cfg["typologies"].get("n_licit_passthrough", 0))
    movers = (by_arch.get("retail", []) + by_arch.get("merchant", [])
              + by_arch.get("miner", []))
    dests = by_arch.get("exchange", []) + by_arch.get("merchant", [])
    if movers and dests:
        for _ in range(n_passthrough):
            src = movers[int(rng.integers(len(movers)))]
            dst = dests[int(rng.integers(len(dests)))]
            eng.licit_passthrough(src, dst, int(rng.integers(t0, t1 - 86400)),
                                  hops=int(rng.integers(2, 6)))

    all_actors = actors + eng.mules

    # ---- 3. capture: propagate and observe ------------------------------
    lg.txs.sort(key=lambda t: t.ts)
    rows: list[dict] = []
    for tx in lg.txs:
        actor = lg.actors.get(tx.sender_eid)
        if actor is None:
            continue
        for ann in diffuse(tx, actor, peers, shared, rng, cfg):
            rows.append({
                "timestamp": dt.datetime.fromtimestamp(ann.ts, dt.timezone.utc)
                              .isoformat().replace("+00:00", "Z"),
                "src_ip": ann.src_ip,
                "dst_ip": ann.dst_ip,
                "src_port": ann.src_port,
                "dst_port": ann.dst_port,
                "txid": tx.txid,
                "input_addresses": [a for a, _ in tx.inputs],
                "output_addresses": [a for a, _ in tx.outputs],
                "input_amounts": [v for _, v in tx.inputs],
                "output_amounts": [v for _, v in tx.outputs],
                "fee": tx.fee,
                "script_type": tx.script_type,
                "geo_country": ann.geo_country,
                "asn": ann.asn,
            })
    rows.sort(key=lambda r: r["timestamp"])

    # ---- 4. ground truth -------------------------------------------------
    truth_entities = [{
        "eid": a.eid, "archetype": a.archetype, "illicit": int(a.illicit),
        "typology": a.typology or "", "asn": a.asn, "asn_type": a.asn_type,
        "country": a.country, "tz_offset_min": a.tz_offset_min,
        "n_addresses": len(a.addresses), "ips": "|".join(a.ips),
    } for a in all_actors]

    truth_addresses = [{"address": addr, "eid": a.eid}
                       for a in all_actors for addr in a.addresses]

    truth_txs = [{
        "txid": t.txid, "sender_eid": t.sender_eid, "illicit": int(t.illicit),
        "typology": t.typology or "", "hop": -1 if t.hop is None else t.hop,
        "campaign": t.campaign or "", "ts": t.ts,
    } for t in lg.txs]

    stats = {
        "n_rows": len(rows),
        "n_txs": len(lg.txs),
        "n_entities": len(all_actors),
        "n_illicit_entities": sum(1 for a in all_actors if a.illicit),
        "n_illicit_txs": sum(1 for t in lg.txs if t.illicit),
        "n_campaigns": len(campaign_log),
        "observation_coverage": float(cfg["network"]["observation_coverage"]),
        "window": [cfg["time"]["start"], int(cfg["time"]["days"])],
        "campaigns": campaign_log,
    }
    return Capture(rows, lg.txs, all_actors, truth_entities, truth_addresses, truth_txs,
                   space.geoip_table(), stats)
