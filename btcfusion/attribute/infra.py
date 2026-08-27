"""Infrastructure classification, and the confidence penalty it implies.

Attribution only means something if the address belongs to the entity rather than
to a machine thousands of people share. A Tor exit, a commercial VPN endpoint and
a CDN edge all carry traffic for unrelated parties, so linking an entity to one
of them is close to meaningless no matter how strong the co-occurrence looks.

TWO SOURCES, because either alone is exploitable:
  * DECLARED - the ASN type from the offline GeoIP database.
  * OBSERVED - how many distinct entities we actually saw announcing from this
    address in THIS capture. An ASN labelled residential that carries 400
    entities is a shared box whatever the database says, and this catches VPN
    ranges the database has never heard of.

The penalty is multiplicative on the final confidence and is reported to the
analyst by name, because "0.31, penalised for shared infrastructure" is
actionable and a bare 0.31 is not.
"""
from __future__ import annotations

import numpy as np
import polars as pl

# Multiplicative confidence penalty by declared infrastructure class.
DECLARED_PENALTY = {
    "residential": 1.00,
    "mobile": 0.90,     # carrier-grade NAT puts many subscribers behind one address
    "hosting": 0.72,    # could be the entity's own server, could be a rented VPS
    "cdn": 0.30,
    "vpn": 0.22,
    "tor": 0.12,        # an exit relay tells you almost nothing about the origin
    "unknown": 0.60,
}

# Above this many distinct entities on one address, treat it as shared regardless
# of what the database says.
SHARED_ENTITY_THRESHOLD = 8


def classify(df: pl.DataFrame, txs: pl.DataFrame) -> pl.DataFrame:
    """Per-IP infrastructure profile, declared and observed."""
    if "src_ip" not in df.columns:
        return pl.DataFrame({"ip": [], "asn": [], "asn_type": [], "country": [],
                             "n_entities": [], "penalty": []})

    owner = txs.select(["txid", "sender_entity"]).drop_nulls("sender_entity")
    a = df.join(owner, on="txid", how="inner")
    cols = [pl.col("sender_entity").n_unique().alias("n_entities"),
            pl.len().alias("n_announcements"),
            pl.col("txid").n_unique().alias("n_txs")]
    for c, alias in (("src_asn", "asn"), ("src_asn_type", "asn_type"),
                     ("src_country", "country"), ("src_asn_org", "asn_org"),
                     ("src_tz_offset_min", "tz_offset_min")):
        if c in a.columns:
            cols.append(pl.col(c).first().alias(alias))

    prof = a.group_by("src_ip").agg(cols).rename({"src_ip": "ip"})
    if "asn_type" not in prof.columns:
        prof = prof.with_columns(pl.lit("unknown").alias("asn_type"))

    declared = pl.col("asn_type").replace_strict(
        DECLARED_PENALTY, default=DECLARED_PENALTY["unknown"], return_dtype=pl.Float64)
    # Observed sharing decays the penalty smoothly rather than at a cliff edge, so
    # an address used by nine entities is not treated identically to one used by
    # nine hundred.
    observed = (1.0 / (1.0 + (pl.col("n_entities").cast(pl.Float64) - 1.0)
                       / SHARED_ENTITY_THRESHOLD)).clip(0.05, 1.0)

    return prof.with_columns([
        declared.alias("declared_penalty"),
        observed.alias("observed_penalty"),
        (declared * observed).alias("penalty"),
        (pl.col("n_entities") >= SHARED_ENTITY_THRESHOLD).alias("is_shared_observed"),
        pl.col("asn_type").is_in(["vpn", "tor", "cdn"]).alias("is_shared_declared"),
    ])


def penalty_reason(row: dict) -> str | None:
    """Analyst-readable explanation of why an address was discounted."""
    kind = row.get("asn_type", "unknown")
    n = int(row.get("n_entities", 1) or 1)
    if kind == "tor":
        return "Tor exit relay - carries traffic for unrelated parties; origin not inferable"
    if kind == "vpn":
        return "commercial VPN endpoint - shared by many subscribers"
    if kind == "cdn":
        return "CDN edge node - shared infrastructure"
    if n >= SHARED_ENTITY_THRESHOLD:
        return f"observed announcing for {n} distinct entities - shared host"
    if kind == "hosting":
        return "datacentre address - may be a rented host rather than the entity's own"
    if kind == "mobile":
        return "mobile carrier address - CGNAT means many subscribers share it"
    return None
