"""Attribution confidence, its interval, and what would change it.

THE COUNTERFACTUAL IS THE POINT. Every dashboard on the market shows a number.
None of them show what would move it. Analysts do not reason in point estimates -
they reason about what new evidence would confirm or collapse a hypothesis - so
the case file states, in plain English, the specific findings that would raise or
sink this attribution and by how much.

That is also a discipline for us, not just a UI flourish: to name what would
change the answer, the model has to be genuinely sensitive to those inputs, which
rules out fitting an opaque score and decorating it afterwards.

CONFIDENCE = statistical strength
           x repeat-observation weight   (single sightings cannot be confident)
           x propagation-root bonus      (tree roots beat "seen first")
           x infrastructure penalty      (shared hosts tell you little)
           x timezone corroboration      (two independent methods agreeing)
"""
from __future__ import annotations

import numpy as np

from .behaviour import offset_label
from .infra import DECLARED_PENALTY, penalty_reason

ROOT_BONUS = 0.35        # maximum uplift when every observation is a tree root
TZ_WEIGHT = 0.15         # how much behavioural/GeoIP agreement can move confidence


def significance_strength(p_value: float, ppmi: float) -> float:
    """Turn a p-value and a PMI magnitude into a [0,1] base strength.

    The p-value says "not chance"; the PMI says "how strongly". A link can be
    highly significant and still weak (a busy relay observed many times), so both
    are needed and the geometric mean keeps either one from dominating.
    """
    sig = float(np.clip(-np.log10(max(p_value, 1e-300)) / 12.0, 0.0, 1.0))
    mag = float(np.clip(ppmi / 4.0, 0.0, 1.0))
    return float(np.sqrt(max(sig, 1e-9) * max(mag, 1e-9)))


def compute_confidence(base: float, n_obs: int, root_frac: float,
                       infra_penalty: float, tz_agreement: float,
                       repeat_w: float) -> float:
    root_factor = 1.0 + ROOT_BONUS * float(np.clip(root_frac, 0.0, 1.0))
    tz_factor = (1.0 - TZ_WEIGHT) + TZ_WEIGHT * float(np.clip(tz_agreement, 0.0, 1.0))
    c = base * repeat_w * root_factor * infra_penalty * tz_factor
    return float(np.clip(c, 0.0, 0.99))


def interval(conf: float, n_obs: int) -> float:
    """Half-width that widens as evidence thins (Wilson-style)."""
    n = max(1, int(n_obs))
    half = 1.96 * np.sqrt(max(conf * (1 - conf), 1e-4) / n)
    return float(np.clip(half, 0.02, 0.45))


def counterfactuals(conf: float, base: float, n_obs: int, root_frac: float,
                    infra_penalty: float, tz_agreement: float, repeat_w: float,
                    asn_type: str, n_entities_on_ip: int) -> list[dict]:
    """The findings that would move this attribution, with the resulting number.

    Each is computed by re-running the confidence model with one input changed -
    never estimated or written by hand. If the model is not actually sensitive to
    a factor, no counterfactual is emitted for it.
    """
    out: list[dict] = []

    def recompute(**kw) -> float:
        args = dict(base=base, n_obs=n_obs, root_frac=root_frac,
                    infra_penalty=infra_penalty, tz_agreement=tz_agreement,
                    repeat_w=repeat_w)
        args.update(kw)
        return compute_confidence(**args)

    # Downside: the address turns out to be shared infrastructure.
    if asn_type not in ("vpn", "tor", "cdn"):
        c_vpn = recompute(infra_penalty=DECLARED_PENALTY["vpn"])
        out.append({
            "direction": "down",
            "value": round(c_vpn, 2),
            "text": f"falls to {c_vpn:.2f} if the announcing IPs resolve to a shared VPN exit",
        })

    # Downside: the sightings were re-relays rather than origin announcements.
    if root_frac > 0.05:
        c_noroot = recompute(root_frac=0.0)
        if abs(c_noroot - conf) > 0.01:
            out.append({
                "direction": "down",
                "value": round(c_noroot, 2),
                "text": (f"falls to {c_noroot:.2f} if the propagation-tree roots are "
                         f"re-relays rather than origin announcements"),
            })

    # Upside: more observations of the same entity on the same address.
    if n_obs < 40:
        from .diffusion import repeat_weight
        c_more = recompute(n_obs=n_obs * 3,
                           repeat_w=float(repeat_weight(np.array([n_obs * 3]))[0]))
        if c_more - conf > 0.01:
            out.append({
                "direction": "up",
                "value": round(c_more, 2),
                "text": (f"rises to {c_more:.2f} with {n_obs * 3} observations instead of "
                         f"{n_obs} - this link is currently evidence-limited, not weak"),
            })

    # Upside: the behavioural timezone corroborates the GeoIP location.
    if tz_agreement < 0.6:
        c_tz = recompute(tz_agreement=1.0)
        if c_tz - conf > 0.005:
            out.append({
                "direction": "up",
                "value": round(c_tz, 2),
                "text": (f"rises to {c_tz:.2f} if the operator's activity hours matched "
                         f"the timezone of the announcing ASN"),
            })
    return out[:4]


def describe(entity: str, ip: str, row: dict, conf: float, half: float,
             behaviour: dict | None) -> str:
    """One sentence an analyst can put in a briefing."""
    bits = [f"{ip}"]
    if row.get("asn"):
        bits.append(f"AS{int(row['asn'])}")
    if row.get("asn_org"):
        bits.append(str(row["asn_org"]))
    if row.get("asn_type"):
        bits.append(str(row["asn_type"]))
    if row.get("country") and row["country"] != "ZZ":
        bits.append(str(row["country"]))
    head = " · ".join(bits)
    tail = f"confidence {conf:.2f} ±{half:.2f}"
    if behaviour and behaviour.get("diurnality", 0) > 0.25:
        tail += (f"; activity consistent with "
                 f"{offset_label(behaviour['inferred_offset_min'])}")
    reason = penalty_reason(row)
    if reason:
        tail += f"; discounted: {reason}"
    return f"{head} — {tail}"
