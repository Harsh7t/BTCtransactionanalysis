"""Core datatypes for the synthetic generator.

Money is satoshis (int) everywhere. Never float BTC - floating point rounding on
money is indefensible in an evidentiary context (roadmap §6.4 step 7).
"""
from __future__ import annotations

from dataclasses import dataclass, field

SCRIPT_TYPES = ("p2pkh", "p2sh", "p2wpkh", "p2wsh", "p2tr")


@dataclass
class Actor:
    """One real-world entity. Ground truth: the resolver must rediscover these."""

    eid: str
    archetype: str
    script_type: str            # wallet-software fingerprint, stable per actor
    addresses: list[str] = field(default_factory=list)
    ips: list[str] = field(default_factory=list)
    asn: int = 0
    asn_type: str = "residential"
    country: str = "US"
    tz_offset_min: int = 0
    os_family: str = "linux"    # drives ephemeral source-port range
    illicit: bool = False
    typology: str | None = None
    # simplified UTXO: address -> satoshis held
    balances: dict[str, int] = field(default_factory=dict)

    def total_balance(self) -> int:
        return sum(self.balances.values())


@dataclass
class Tx:
    txid: str
    ts: int                                  # unix seconds, UTC
    sender_eid: str
    inputs: list[tuple[str, int]]            # (address, satoshis)
    outputs: list[tuple[str, int]]           # (address, satoshis)
    fee: int
    script_type: str
    illicit: bool = False
    typology: str | None = None
    hop: int | None = None                   # position within a laundering chain
    campaign: str | None = None

    @property
    def value_out(self) -> int:
        return sum(a for _, a in self.outputs)


@dataclass
class Announcement:
    """One observed P2P relay event. This is what a capture actually records."""

    txid: str
    ts: int                # observation time, unix seconds
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    geo_country: str
    asn: int
    relay_depth: int       # 0 = origin announced it, >0 = re-relay
