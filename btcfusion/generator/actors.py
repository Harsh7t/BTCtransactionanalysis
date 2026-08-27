"""Eight actor archetypes and the licit background traffic they produce.

The archetypes are behavioural, not cosmetic: each one differs in fan-in/fan-out
shape, address-reuse policy, activity rhythm and network profile. That is what
gives the graph and the temporal features something real to learn, and it is why
HDBSCAN can recover behavioural clusters nobody labelled.

Extortion is modelled as its own archetype rather than a ransomware variant
(roadmap §16.4-I) because its on-chain shape genuinely differs: many small
near-fixed payments from many distinct payers inside a short campaign window,
then fast consolidation with light layering.

LEAK DISCIPLINE (§6.3): archetype must NOT determine fee or port. Those are
functions of transaction size, network congestion and OS only. If an archetype
ever biases them, the leak test starts passing and every downstream number dies.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from .model import Actor

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
B32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


@dataclass(frozen=True)
class Archetype:
    name: str
    tx_per_day: float          # licit activity rate
    n_addresses: tuple[int, int]
    reuse_prob: float          # chance of reusing a funded address as an output
    fan_out: tuple[int, int]   # outputs per transaction
    multi_input: tuple[int, int]
    diurnal: float             # 0 = flat 24/7, 1 = strongly office-hours
    burstiness: float          # 0 = regular, 1 = heavily clustered
    net_kinds: tuple[str, ...]
    n_ips: tuple[int, int]
    initial_btc: tuple[float, float]
    equal_outputs: bool = False   # CoinJoin-style uniform value outputs


ARCHETYPES: dict[str, Archetype] = {
    "exchange": Archetype("exchange", 140.0, (400, 900), 0.72, (8, 40), (3, 12), 0.05, 0.15,
                          ("hosting", "cdn"), (6, 14), (400.0, 2500.0)),
    "merchant": Archetype("merchant", 9.0, (30, 90), 0.45, (1, 3), (1, 4), 0.45, 0.30,
                          ("hosting",), (1, 3), (5.0, 40.0)),
    "retail": Archetype("retail", 0.6, (2, 9), 0.22, (1, 2), (1, 2), 0.85, 0.65,
                        ("residential", "mobile"), (1, 3), (0.02, 2.5)),
    "miner": Archetype("miner", 22.0, (40, 120), 0.30, (2, 8), (1, 3), 0.02, 0.10,
                       ("hosting",), (2, 5), (60.0, 400.0)),
    "mixer": Archetype("mixer", 34.0, (300, 700), 0.0, (8, 24), (4, 14), 0.10, 0.35,
                       ("tor", "vpn", "hosting"), (3, 8), (80.0, 600.0), equal_outputs=True),
    # Mixed network profiles on purpose: most illicit actors route through shared
    # infrastructure (and attribution correctly suppresses those), but a minority
    # announce from residential or mobile addresses. That minority is the realistic
    # case the attribution engine exists for.
    "darknet": Archetype("darknet", 16.0, (80, 260), 0.18, (1, 5), (2, 8), 0.35, 0.55,
                         ("tor", "vpn", "hosting", "residential"), (2, 6), (10.0, 120.0)),
    "ransomware": Archetype("ransomware", 2.2, (10, 40), 0.10, (1, 3), (1, 5), 0.25, 0.85,
                            ("vpn", "tor", "residential", "mobile"), (1, 4), (0.5, 12.0)),
    "extortion": Archetype("extortion", 5.5, (8, 30), 0.12, (1, 2), (2, 9), 0.40, 0.90,
                           ("vpn", "residential", "mobile"), (1, 3), (0.2, 6.0)),
}

# Archetypes whose *entities* are ground-truth illicit. Note this is the actor
# label; individual laundering campaigns carry their own typology labels.
ILLICIT_ARCHETYPES = {"darknet", "ransomware", "extortion"}

# Operating system is a pure host fingerprint and MUST be drawn identically for
# every actor, criminal or not. Mules originally used a different distribution
# here, which the leak test detected as ~1.2x lift on ephemeral-port features -
# the model was reading "no BSD hosts" as evidence of laundering.
OS_FAMILIES = ["linux", "windows", "bsd"]
OS_PROBS = [0.55, 0.38, 0.07]


def draw_os(rng: np.random.Generator) -> str:
    return str(rng.choice(OS_FAMILIES, p=OS_PROBS))


# Real-world address lengths. These matter: the change heuristic and the
# wallet-fingerprint features infer script type from the address string alone, so
# p2wpkh and p2wsh have to be distinguishable by length exactly as they are on
# mainnet (20- vs 32-byte witness programs).
_ADDR_LEN = {"p2pkh": 33, "p2sh": 33, "p2wpkh": 38, "p2wsh": 58, "p2tr": 58}


def make_address(rng: np.random.Generator, script_type: str) -> str:
    """Realistic-looking but entirely synthetic address strings."""
    n = _ADDR_LEN.get(script_type, 38)
    h = hashlib.blake2b(rng.bytes(16), digest_size=64).digest()
    if script_type in ("p2wpkh", "p2wsh"):
        return "bc1q" + "".join(B32[h[i % 64] % 32] for i in range(n))
    if script_type == "p2tr":
        return "bc1p" + "".join(B32[h[i % 64] % 32] for i in range(n))
    lead = "1" if script_type == "p2pkh" else "3"
    return lead + "".join(B58[h[i % 64] % 58] for i in range(n))


def _script_for(archetype: str, rng: np.random.Generator) -> str:
    """Wallet-software fingerprint. Correlates with actor sophistication, which is
    a real-world signal (§6.5 script-type features) - not with legitimacy."""
    if archetype in ("exchange", "miner"):
        return str(rng.choice(["p2wpkh", "p2sh", "p2wsh"], p=[0.6, 0.2, 0.2]))
    if archetype == "mixer":
        return "p2wpkh"          # uniform scripts are a CoinJoin signature
    return str(rng.choice(["p2wpkh", "p2pkh", "p2sh", "p2tr"], p=[0.5, 0.2, 0.15, 0.15]))


def build_population(cfg: dict, space, rng: np.random.Generator) -> list[Actor]:
    n = int(cfg["population"]["n_entities"])
    mix = cfg["population"]["mix"]
    names = list(mix)
    probs = np.array([mix[k] for k in names], dtype=float)
    probs = probs / probs.sum()
    counts = rng.multinomial(n, probs)

    actors: list[Actor] = []
    idx = 0
    for name, count in zip(names, counts):
        spec = ARCHETYPES[name]
        for _ in range(int(count)):
            script = _script_for(name, rng)
            kind = str(rng.choice(list(spec.net_kinds)))
            asn = space.pick_asn(kind)
            n_ip = int(rng.integers(*spec.n_ips))
            a = Actor(
                eid=f"ENT-{idx:05d}",
                archetype=name,
                script_type=script,
                ips=[space.issue(asn) for _ in range(n_ip)],
                asn=asn.number,
                asn_type=kind,
                country=asn.country,
                tz_offset_min=asn.tz_offset_min,
                # OS is drawn independently of everything else. Deliberate: it must
                # be a pure fingerprint, never a shortcut to legitimacy.
                os_family=draw_os(rng),
                illicit=name in ILLICIT_ARCHETYPES,
                typology=None,
            )
            n_addr = int(rng.integers(*spec.n_addresses))
            a.addresses = [make_address(rng, script) for _ in range(n_addr)]
            # Seed initial funds across a few of the actor's addresses.
            total = int(float(rng.uniform(*spec.initial_btc)) * 1e8)
            k = min(len(a.addresses), max(1, int(rng.integers(1, 6))))
            for addr in a.addresses[:k]:
                a.balances[addr] = total // k
            actors.append(a)
            idx += 1
    rng.shuffle(actors)  # avoid eid order correlating with archetype
    return actors


def draw_timestamps(rng: np.random.Generator, n: int, t0: int, t1: int,
                    tz_offset_min: int, diurnal: float, burstiness: float) -> np.ndarray:
    """Timestamps with a diurnal profile expressed in the actor's LOCAL time.

    Emitting local-time rhythms and storing UTC is what makes behavioural timezone
    profiling (roadmap §5.1 step 6) a real inference rather than a tautology: the
    analyst recovers the offset from the data, we never write it down.
    """
    if n <= 0:
        return np.empty(0, dtype=np.int64)
    span = max(1, t1 - t0)
    if burstiness > 0:
        # Cluster activity into a few campaign windows rather than spreading it.
        n_bursts = max(1, int(round(n * (1.0 - burstiness) + 1)))
        centres = rng.uniform(t0, t1, size=n_bursts)
        width = span * (0.02 + 0.25 * (1.0 - burstiness))
        base = rng.normal(rng.choice(centres, size=n), width)
    else:
        base = rng.uniform(t0, t1, size=n)
    base = np.clip(base, t0, t1)

    if diurnal > 0:
        # Reject-and-shift toward local working hours in proportion to `diurnal`.
        local = (base + tz_offset_min * 60) % 86400
        hour = local / 3600.0
        # Preference curve: peak ~14:00 local, trough ~04:00 local.
        pref = 0.5 * (1.0 + np.cos((hour - 14.0) / 24.0 * 2 * np.pi))
        move = rng.random(n) < (diurnal * (1.0 - pref))
        target_hour = rng.normal(14.0, 3.5, size=n) % 24.0
        shift = (target_hour - hour) * 3600.0
        base = base + np.where(move, shift, 0.0)
        base = np.clip(base, t0, t1)
    return np.sort(base.astype(np.int64))
