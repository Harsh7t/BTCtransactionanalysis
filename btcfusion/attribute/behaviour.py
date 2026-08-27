"""Behavioural timezone profiling.

People keep hours. An entity operated by a human in one place shows a clear
diurnal rhythm; an exchange running around the clock does not. If we take an
entity's activity histogram and ask which UTC offset makes it look most like a
human waking, working and sleeping, the best-fitting offset is an independent
estimate of where the operator physically is - derived from BEHAVIOUR, not from
the GeoIP database.

That independence is the whole value. When the behavioural estimate AGREES with
the offset implied by the announcing IP's ASN, two unrelated methods have
converged and confidence rises. When they disagree, something is off - a VPN, a
proxy, an operator working from a different country than their infrastructure -
and confidence should fall. Either way the analyst learns something a lookup
table could not tell them.

The generator emits activity in each actor's LOCAL time and stores UTC, so this
recovers a fact that was never written into the data.
"""
from __future__ import annotations

import numpy as np
import polars as pl

# Half-hour offsets exist and matter here: India is UTC+05:30, and rounding it to
# +05:00 or +06:00 would systematically misplace a large population.
CANDIDATE_OFFSETS_MIN = np.array(
    [-720, -660, -600, -540, -480, -420, -360, -300, -240, -210, -180, -120, -60,
     0, 60, 120, 180, 210, 240, 270, 300, 330, 360, 390, 420, 480, 540, 570, 600, 660, 720],
    dtype=np.int64)


def _human_profile() -> np.ndarray:
    """Expected activity by local hour for a human-operated entity.

    A broad single-peaked curve centred on the early afternoon with a deep
    overnight trough. Deliberately smooth - we are fitting a phase, not claiming
    to know anyone's calendar.
    """
    h = np.arange(24)
    prof = 0.5 * (1.0 + np.cos((h - 14.0) / 24.0 * 2 * np.pi))
    prof = prof ** 2
    return prof / prof.sum()


HUMAN = _human_profile()


def hour_histogram(timestamps: np.ndarray) -> np.ndarray:
    """Counts by UTC hour."""
    if len(timestamps) == 0:
        return np.zeros(24)
    hours = ((timestamps // 3600) % 24).astype(np.int64)
    return np.bincount(hours, minlength=24).astype(float)


def infer_offset(hist_utc: np.ndarray) -> tuple[int, float, float]:
    """Best-fitting UTC offset for an activity histogram.

    Returns (offset_minutes, fit_score in [0,1], diurnality in [0,1]).

    `diurnality` is the part that guards against nonsense: a flat 24/7 histogram
    fits every offset equally well, so a confident-looking offset drawn from a
    flat profile is meaningless. We report it alongside and let confidence.py
    discount accordingly.
    """
    total = hist_utc.sum()
    if total < 8:
        return 0, 0.0, 0.0
    p = hist_utc / total

    # Diurnality: how far this is from uniform, normalised so 1.0 is maximally
    # concentrated. Uses total variation distance from the flat distribution.
    diurnality = float(np.abs(p - 1.0 / 24).sum() / (2 * (1 - 1.0 / 24)))

    best_off, best_score = 0, -np.inf
    scores = []
    for off in CANDIDATE_OFFSETS_MIN:
        shift = int(round(off / 60.0))
        # local hour = utc hour + offset; rolling the profile the other way
        # compares the observed UTC histogram against the expected one.
        expected = np.roll(HUMAN, -shift)
        score = float(np.dot(p, expected))
        scores.append(score)
        if score > best_score:
            best_score, best_off = score, int(off)

    scores = np.array(scores)
    # Normalise the winner against the spread of alternatives, so a peak that is
    # barely better than its neighbours does not read as a confident fit.
    rng = scores.max() - scores.min()
    fit = float((best_score - scores.mean()) / rng) if rng > 1e-9 else 0.0
    return best_off, float(np.clip(fit, 0.0, 1.0)), diurnality


def profile_entities(txs: pl.DataFrame, entities: list[str]) -> dict[str, dict]:
    """Activity profile and inferred operating timezone per entity."""
    sub = (txs.filter(pl.col("sender_entity").is_in(entities))
           .select(["sender_entity", "timestamp"]))
    if sub.height == 0:
        return {}
    sub = sub.with_columns(pl.col("timestamp").dt.epoch("s").alias("ts"))
    out: dict[str, dict] = {}
    for eid, group in sub.group_by("sender_entity"):
        key = eid[0] if isinstance(eid, tuple) else eid
        ts = group.get_column("ts").to_numpy()
        hist = hour_histogram(ts)
        off, fit, diurnality = infer_offset(hist)
        out[str(key)] = {
            "hour_histogram_utc": hist.astype(int).tolist(),
            "inferred_offset_min": off,
            "offset_fit": round(fit, 3),
            "diurnality": round(diurnality, 3),
            "n_observations": int(hist.sum()),
        }
    return out


def offset_label(minutes: int) -> str:
    sign = "+" if minutes >= 0 else "-"
    m = abs(int(minutes))
    return f"UTC{sign}{m // 60:02d}:{m % 60:02d}"


def agreement(behavioural_offset: int, geoip_offset: int, tolerance_min: int = 90) -> float:
    """Do the behavioural and GeoIP timezone estimates agree?

    Returns 1.0 for close agreement, decaying to 0 as they diverge. Two
    independent methods landing in the same place is real corroboration; this is
    what turns a lookup into an inference.
    """
    delta = abs(int(behavioural_offset) - int(geoip_offset))
    delta = min(delta, 1440 - delta)      # wrap around the day
    if delta <= tolerance_min:
        return 1.0
    return float(max(0.0, 1.0 - (delta - tolerance_min) / 360.0))
