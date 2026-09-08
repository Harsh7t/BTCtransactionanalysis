"""Network layer: address space, infrastructure classes, and P2P diffusion.

This module is where the project's credibility lives (roadmap §6.3). Two design
choices matter more than the rest of the file combined:

1. DIFFUSION. Bitcoin Core announces to peers with a randomised per-peer delay,
   specifically to frustrate the first-relay deanonymisation of Koshy et al.
   (FC 2014) and Biryukov et al. (CCS 2014). We simulate that defence, so a
   relayed announcement often arrives before the originator's own. Naive
   "earliest src_ip wins" attribution is therefore WRONG a lot of the time -
   which is the honest result we want to measure rather than hide.

2. OBSERVATION COVERAGE IS PER-VANTAGE-POINT, NOT PER-EVENT. A real collector
   monitors a SET of nodes; it sees an announcement iff the destination is one
   of its monitored peers. Sampling events independently at random would make
   attribution far too easy and would flatter every downstream number.

All synthetic IPs are drawn from reserved, non-routable space (RFC 2544
benchmark 198.18.0.0/15, RFC 6598 CGNAT 100.64.0.0/10, RFC 5737 TEST-NET) so no
real host is ever named in generated data.
"""
from __future__ import annotations

import zlib
import ipaddress
from dataclasses import dataclass

import numpy as np

from .model import Actor, Announcement, Tx

# Ephemeral source-port ranges differ by OS - a nearly free OS fingerprint on the
# announcing host (roadmap §16.2-A). IANA/Linux/Windows defaults.
EPHEMERAL_RANGES = {
    "linux": (32768, 60999),
    "windows": (49152, 65535),
    "bsd": (10000, 65535),
}

BITCOIN_PORT = 8333


@dataclass(frozen=True)
class Asn:
    number: int
    name: str
    kind: str      # residential | hosting | mobile | vpn | tor | cdn
    country: str
    tz_offset_min: int
    block: str     # CIDR this ASN's addresses are drawn from


def _blocks() -> list[str]:
    """Carve reserved space into /20s we can hand out to ASNs."""
    pools = [ipaddress.ip_network("198.18.0.0/15"), ipaddress.ip_network("100.64.0.0/12")]
    out: list[str] = []
    for p in pools:
        out.extend(str(n) for n in p.subnets(new_prefix=20))
    return out


# 40 ASNs across six infrastructure classes and nine jurisdictions. Shared
# infrastructure (vpn/tor/cdn) is deliberately over-represented relative to its
# share of hosts, because it is the attribution engine's hardest case.
_SPEC = [
    ("residential", "IN", 330, ["Bharat Broadband", "Mumbai Metro Net", "Delhi FiberLink", "Chennai Access"]),
    ("residential", "US", -300, ["Cascade Cable", "Midwest Broadband", "Atlantic Access"]),
    ("residential", "DE", 60, ["Rhein Telekabel", "Bavaria Netz"]),
    ("residential", "RU", 180, ["Volga Telecom", "Ural Netcom"]),
    ("residential", "UA", 120, ["Dnipro Online", "Kyiv Link"]),
    ("residential", "BR", -180, ["Sao Paulo Banda"]),
    ("residential", "NG", 60, ["Lagos Broadband"]),
    ("mobile", "IN", 330, ["Bharat Mobile Data", "Indus Cellular"]),
    ("mobile", "US", -300, ["Northstar Wireless"]),
    ("hosting", "US", -300, ["Ridgeline Cloud", "Bluewater Hosting", "Sierra Datacenter"]),
    ("hosting", "NL", 60, ["Amstel Servers", "Randstad Hosting"]),
    ("hosting", "SG", 480, ["Straits Compute"]),
    ("hosting", "DE", 60, ["Hessen Rechenzentrum"]),
    ("hosting", "HK", 480, ["Victoria Peak Systems"]),
    ("cdn", "US", -300, ["Meridian Edge", "Northlight CDN"]),
    ("cdn", "NL", 60, ["Lowlands Edge"]),
    ("vpn", "PA", -300, ["Isthmus Privacy Net"]),
    ("vpn", "SC", 240, ["Coral Anonymity"]),
    ("vpn", "IS", 0, ["Hekla Secure Tunnel"]),
    ("vpn", "RO", 120, ["Carpathian VPN"]),
    ("tor", "DE", 60, ["Freihafen Exit Relay", "Schwarzwald Exit"]),
    ("tor", "FR", 60, ["Occitanie Exit Node"]),
    ("tor", "US", -300, ["Beacon Hill Exit"]),
]


def build_asns() -> list[Asn]:
    blocks = _blocks()
    out: list[Asn] = []
    n = 0
    for kind, country, tz, names in _SPEC:
        for name in names:
            out.append(Asn(64512 + n * 7, name, kind, country, tz, blocks[n % len(blocks)]))
            n += 1
    return out


class AddressSpace:
    """Hands out IPs from ASN blocks and answers reverse lookups.

    The reverse map is exported as the bundled offline GeoIP database, so the
    ingest layer can independently derive geo_country/asn from src_ip exactly as
    it would from a real DB-IP .mmdb (roadmap §16.2-E).
    """

    def __init__(self, rng: np.random.Generator):
        self.rng = rng
        self.asns = build_asns()
        self._by_kind: dict[str, list[Asn]] = {}
        for a in self.asns:
            self._by_kind.setdefault(a.kind, []).append(a)
        self._issued: dict[str, Asn] = {}

    def kinds(self) -> list[str]:
        return list(self._by_kind)

    def pick_asn(self, kind: str) -> Asn:
        pool = self._by_kind[kind]
        return pool[int(self.rng.integers(len(pool)))]

    def issue(self, asn: Asn) -> str:
        """Allocate one address inside the ASN's block."""
        net = ipaddress.ip_network(asn.block)
        # offset 1.. to skip the network address
        off = int(self.rng.integers(1, net.num_addresses - 1))
        ip = str(net.network_address + off)
        self._issued[ip] = asn
        return ip

    def lookup(self, ip: str) -> Asn | None:
        """Exact reverse lookup; falls back to CIDR containment for unseen IPs."""
        hit = self._issued.get(ip)
        if hit is not None:
            return hit
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return None
        for a in self.asns:
            if addr in ipaddress.ip_network(a.block):
                return a
        return None

    def geoip_table(self) -> list[dict]:
        """The bundled offline enrichment database, as CIDR -> attributes rows."""
        return [
            {
                "cidr": a.block,
                "asn": a.number,
                "asn_org": a.name,
                "asn_type": a.kind,
                "country": a.country,
                "tz_offset_min": a.tz_offset_min,
            }
            for a in self.asns
        ]


class SharedInfrastructure:
    """VPN exits and Tor exits carry traffic for many unrelated entities.

    This is the single biggest confidence-killer the attribution engine has to
    survive, so the generator must produce it deliberately rather than by accident.
    """

    def __init__(self, space: AddressSpace, rng: np.random.Generator, size: int):
        self.rng = rng
        self.space = space
        self.exits: list[tuple[str, Asn]] = []
        for _ in range(size):
            kind = "tor" if rng.random() < 0.45 else "vpn"
            asn = space.pick_asn(kind)
            self.exits.append((space.issue(asn), asn))

    def pick(self) -> tuple[str, Asn]:
        return self.exits[int(self.rng.integers(len(self.exits)))]


class PeerNetwork:
    """The wider P2P network plus our collector's monitored vantage points."""

    def __init__(self, space: AddressSpace, rng: np.random.Generator, n_peers: int, coverage: float):
        self.rng = rng
        self.peers: list[str] = []
        for _ in range(n_peers):
            kind = "hosting" if rng.random() < 0.6 else "residential"
            self.peers.append(space.issue(space.pick_asn(kind)))
        # Our vantage point: a fixed monitored subset. Coverage is a property of
        # the collector, not of individual packets - see module docstring.
        k = max(1, int(round(coverage * n_peers)))
        self.monitored = set(rng.choice(np.array(self.peers), size=k, replace=False).tolist())

    def sample_peers(self, k: int) -> list[str]:
        idx = self.rng.integers(0, len(self.peers), size=k)
        return [self.peers[int(i)] for i in idx]

    def observes(self, dst_ip: str) -> bool:
        return dst_ip in self.monitored


def source_port(rng: np.random.Generator, os_family: str) -> int:
    lo, hi = EPHEMERAL_RANGES[os_family]
    return int(rng.integers(lo, hi))


def actor_ip_for(actor: Actor, ts: int, shared: SharedInfrastructure,
                 rng: np.random.Generator, churn_prob: float) -> tuple[str, int, str, str]:
    """Which address does this actor announce from right now?

    Models multi-homing (several IPs per entity) and residential churn (the IP
    rotates on a realistic cadence), plus routing via shared exits for the
    archetypes that would use them.
    """
    if actor.asn_type in ("tor", "vpn"):
        ip, asn = shared.pick()
        return ip, asn.number, asn.country, asn.kind
    day = ts // 86400
    # Deterministic per-day selection: same entity, same day -> same IP, which is
    # what makes churn observable rather than pure noise.
    #
    # crc32, not the built-in hash(). Python randomises string hashing per
    # process unless PYTHONHASHSEED is pinned, so this line - and only this line -
    # made generation non-reproducible: two runs at the same --seed produced
    # byte-identical output in every column except src_ip. src_ip is the network
    # half of the whole thesis, so `make reproduce` did not reproduce the thing
    # the attribution figures are computed from.
    idx = (day * 1103515245 + zlib.crc32(actor.eid.encode())) % max(1, len(actor.ips))
    if actor.asn_type == "residential" and rng.random() < churn_prob:
        idx = (idx + 1) % max(1, len(actor.ips))
    return actor.ips[idx], actor.asn, actor.country, actor.asn_type


def diffuse(tx: Tx, actor: Actor, peers: PeerNetwork, shared: SharedInfrastructure,
            rng: np.random.Generator, cfg: dict) -> list[Announcement]:
    """Simulate one transaction's propagation and return only what we OBSERVE.

    Returns announcements whose destination is a monitored peer. The origin's own
    announcements (relay_depth 0) are the attribution signal; relayed ones
    (depth > 0) are the noise that makes naive first-relay attribution fail.
    """
    net = cfg["network"]
    mean_delay = float(net["peer_delay_mean_s"])
    fanout = int(net["fanout_peers"])
    depth_max = int(net["relay_depth"])
    churn = float(net["churn_prob_residential"])

    src_ip, asn, country, _kind = actor_ip_for(actor, tx.ts, shared, rng, churn)
    observed: list[Announcement] = []

    # Depth 0: the originator trickles the tx to its peers with randomised delays.
    frontier: list[tuple[str, float, int, str]] = []
    delays = rng.exponential(mean_delay, size=fanout)
    for peer, d in zip(peers.sample_peers(fanout), delays):
        t = tx.ts + float(d)
        frontier.append((peer, t, 1, src_ip))
        if peers.observes(peer):
            observed.append(Announcement(
                txid=tx.txid, ts=int(t), src_ip=src_ip, dst_ip=peer,
                src_port=source_port(rng, actor.os_family),
                dst_port=BITCOIN_PORT if rng.random() > 0.03 else int(rng.integers(8000, 9000)),
                geo_country=country, asn=asn, relay_depth=0,
            ))

    # Further hops: a couple of the peers re-announce onward. Their src_ip is a
    # relay, NOT the originator - this is the trap the attribution engine must
    # not fall into.
    for _ in range(depth_max):
        nxt: list[tuple[str, float, int, str]] = []
        for relay_ip, t0, depth, _parent in frontier[:2]:
            relay_asn = peers_asn(relay_ip, shared)
            for peer, d in zip(peers.sample_peers(2), rng.exponential(mean_delay, size=2)):
                t = t0 + float(d)
                nxt.append((peer, t, depth + 1, relay_ip))
                if peers.observes(peer):
                    observed.append(Announcement(
                        txid=tx.txid, ts=int(t), src_ip=relay_ip, dst_ip=peer,
                        src_port=source_port(rng, "linux"), dst_port=BITCOIN_PORT,
                        geo_country=relay_asn[1], asn=relay_asn[0], relay_depth=depth,
                    ))
        frontier = nxt
        if not frontier:
            break
    return observed


_PEER_ASN_CACHE: dict[str, tuple[int, str]] = {}


def peers_asn(ip: str, shared: SharedInfrastructure) -> tuple[int, str]:
    hit = _PEER_ASN_CACHE.get(ip)
    if hit is None:
        a = shared.space.lookup(ip)
        hit = (a.number, a.country) if a else (0, "ZZ")
        _PEER_ASN_CACHE[ip] = hit
    return hit
