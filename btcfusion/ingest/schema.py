"""The canonical schema and its validation rules.

DESIGN NOTE on Pydantic. The roadmap specifies Pydantic v2 validation. Running a
per-row model over 700k rows costs ~40s, which blows the entire 15s ingest
budget (§5.2) on type-checking alone. So Pydantic defines the *contract* - it is
the single source of truth for field types and bounds, and it validates
individual records at the API boundary and in tests - while bulk ingest applies
the SAME rules vectorised in Polars. The rules live here once, in RULES, so the
two paths cannot drift apart.

Every rejected row goes to quarantine with a reason. Nothing is ever dropped
silently: a silent drop corrupts every number downstream and is untraceable
(roadmap §6.4 step 3).
"""
from __future__ import annotations

import datetime as dt
import ipaddress
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

CANONICAL = (
    "timestamp", "src_ip", "dst_ip", "src_port", "dst_port", "txid",
    "input_addresses", "output_addresses", "input_amounts", "output_amounts",
    "fee", "script_type", "geo_country", "asn",
)

ARRAY_FIELDS = ("input_addresses", "output_addresses", "input_amounts", "output_amounts")
INT_ARRAY_FIELDS = ("input_amounts", "output_amounts")

# Network-layer fields. Absent -> chain-only mode, attribution disabled (§4.4).
NETWORK_FIELDS = ("src_ip", "dst_ip", "src_port", "dst_port", "geo_country", "asn")

SCRIPT_TYPES = ("p2pkh", "p2sh", "p2wpkh", "p2wsh", "p2tr", "unknown")

GENESIS = dt.datetime(2009, 1, 3, tzinfo=dt.timezone.utc)
MAX_SATS = 2_100_000_000_000_000   # 21M BTC, the hard supply cap


class Record(BaseModel):
    """One announcement observation. The contract, not the hot path."""

    timestamp: dt.datetime
    txid: str = Field(min_length=4, max_length=128)
    input_addresses: list[str] = Field(default_factory=list)
    output_addresses: list[str] = Field(default_factory=list)
    input_amounts: list[int] = Field(default_factory=list)
    output_amounts: list[int] = Field(default_factory=list)
    fee: int = Field(default=0, ge=0, le=MAX_SATS)
    script_type: str = "unknown"
    src_ip: str | None = None
    dst_ip: str | None = None
    src_port: int | None = Field(default=None, ge=0, le=65535)
    dst_port: int | None = Field(default=None, ge=0, le=65535)
    geo_country: str | None = None
    asn: int | None = None

    @field_validator("src_ip", "dst_ip")
    @classmethod
    def _ip(cls, v):
        if v in (None, "", "-"):
            return None
        ipaddress.ip_address(v)   # raises on malformed, which is the point
        return v

    @field_validator("input_amounts", "output_amounts")
    @classmethod
    def _amounts(cls, v):
        for a in v:
            if a < 0 or a > MAX_SATS:
                raise ValueError(f"amount out of range: {a}")
        return v

    @field_validator("script_type")
    @classmethod
    def _script(cls, v):
        return v if v in SCRIPT_TYPES else "unknown"


# Quarantine reasons, applied in this order. Kept as data so the ingest receipt
# can report a breakdown and the UI can show the analyst what was lost and why.
RULES = (
    ("missing_txid", "txid is null or empty"),
    ("bad_timestamp", "timestamp unparseable, before genesis, or implausibly future"),
    ("no_outputs", "transaction has no output addresses"),
    ("amount_out_of_range", "an amount is negative or exceeds the 21M BTC supply cap"),
    ("fee_out_of_range", "fee is negative or implausibly large"),
    ("bad_src_ip", "src_ip is present but not a valid IP address"),
    ("length_mismatch", "output_addresses and output_amounts differ in length"),
)
