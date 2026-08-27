"""Spend mechanics: input selection, change, and fees.

Two properties this file must preserve or the whole project is worthless:

1. COMMON-INPUT-OWNERSHIP MUST HOLD. When an actor spends, it may co-spend
   several of its own addresses. That co-spend is the only thing the Union-Find
   resolver has to work with, so if we never emit multi-input transactions the
   entity layer is a fiction (Meiklejohn et al., IMC 2013).

2. FEE MUST BE INDEPENDENT OF LEGITIMACY. fee = f(vsize, congestion at ts) and
   nothing else. The moment an archetype nudges the fee, the leak test starts
   predicting and every accuracy number downstream becomes meaningless (§6.3).
"""
from __future__ import annotations

import hashlib

import numpy as np

from .actors import ARCHETYPES, make_address
from .model import Actor, Tx

DUST = 546  # satoshis; below this an output is unspendable in practice


def _txid(seed: bytes) -> str:
    return hashlib.blake2b(seed, digest_size=32).hexdigest()


def vsize(n_in: int, n_out: int) -> int:
    """Approximate virtual size of a segwit transaction, in vbytes."""
    return 11 + 68 * n_in + 31 * n_out


class Ledger:
    def __init__(self, actors: list[Actor], cfg: dict, rng: np.random.Generator, t0: int):
        self.actors = {a.eid: a for a in actors}
        self.rng = rng
        self.cfg = cfg
        self.t0 = t0
        self.txs: list[Tx] = []
        self._n = 0
        f = cfg["fees"]
        self._fee_base = float(f["base_sat_per_vb"])
        self._fee_amp = float(f["diurnal_amplitude"])
        self._fee_sigma = float(f["noise_sigma"])
        # index of which actor owns which address, for counterparty resolution
        self.owner: dict[str, str] = {}
        for a in actors:
            for addr in a.addresses:
                self.owner[addr] = a.eid

    # -- fees -------------------------------------------------------------
    def feerate(self, ts: int) -> float:
        """Network fee pressure: a daily congestion cycle plus lognormal noise.

        Depends only on wall-clock time, so every actor spending in the same hour
        faces the same market. This is the leak firewall.
        """
        hour = (ts % 86400) / 3600.0
        cycle = 1.0 + self._fee_amp * np.sin((hour - 9.0) / 24.0 * 2 * np.pi)
        noise = float(self.rng.lognormal(0.0, self._fee_sigma))
        return max(1.0, self._fee_base * cycle * noise)

    # -- addresses --------------------------------------------------------
    def register(self, actor: Actor, addr: str) -> None:
        self.owner[addr] = actor.eid

    def receiving_address(self, actor: Actor) -> str:
        """Reuse a known address or mint a new one, per the archetype's policy."""
        spec = ARCHETYPES.get(actor.archetype)
        reuse = spec.reuse_prob if spec else 0.2
        if actor.addresses and self.rng.random() < reuse:
            return actor.addresses[int(self.rng.integers(len(actor.addresses)))]
        addr = make_address(self.rng, actor.script_type)
        actor.addresses.append(addr)
        self.register(actor, addr)
        return addr

    # A wallet does not ALWAYS return change to its own script type: mixed
    # wallets, migrations and manual coin control all break the rule. If the
    # generator honoured it perfectly the change heuristic would be exact by
    # construction and we would be grading our own homework, so ~9% of change
    # deliberately lands on a different type and the heuristic pays for it.
    CHANGE_SCRIPT_MISMATCH = 0.09

    def _change_address(self, actor: Actor) -> str:
        """A fresh address, usually matching the input script type.

        Script-type matching between inputs and change is a published refinement
        of the change heuristic (§16.2-B), so the generator has to honour it -
        imperfectly - for that heuristic to be testable at a realistic error rate.
        """
        script = actor.script_type
        if self.rng.random() < self.CHANGE_SCRIPT_MISMATCH:
            alts = [s for s in ("p2pkh", "p2sh", "p2wpkh", "p2wsh", "p2tr") if s != script]
            script = str(self.rng.choice(alts))
        addr = make_address(self.rng, script)
        actor.addresses.append(addr)
        self.register(actor, addr)
        return addr

    # -- spending ---------------------------------------------------------
    def _select_inputs(self, actor: Actor, need: int) -> list[tuple[str, int]]:
        funded = [(a, v) for a, v in actor.balances.items() if v > DUST]
        if not funded:
            return []
        self.rng.shuffle(funded)
        spec = ARCHETYPES.get(actor.archetype)
        lo, hi = spec.multi_input if spec else (1, 3)
        want = int(self.rng.integers(lo, max(lo + 1, hi)))
        picked: list[tuple[str, int]] = []
        total = 0
        for addr, val in funded:
            picked.append((addr, val))
            total += val
            if total >= need and len(picked) >= min(want, len(funded)):
                break
        return picked if total >= need else []

    def spend(self, actor: Actor, recipients: list[tuple[str, int]], ts: int,
              *, illicit: bool = False, typology: str | None = None,
              hop: int | None = None, campaign: str | None = None,
              equal_outputs: bool = False) -> Tx | None:
        """Move value. Returns None if the actor cannot fund the spend."""
        recipients = [(a, v) for a, v in recipients if v > DUST]
        if not recipients:
            return None
        want = sum(v for _, v in recipients)
        est_fee = int(vsize(3, len(recipients) + 1) * self.feerate(ts))
        inputs = self._select_inputs(actor, want + est_fee)
        if not inputs:
            return None

        n_out = len(recipients) + 1
        fee = int(vsize(len(inputs), n_out) * self.feerate(ts))
        supplied = sum(v for _, v in inputs)
        change = supplied - want - fee
        if change < 0:
            # Trim the largest recipient rather than fail; mirrors a real wallet
            # reducing the payment when fees spike.
            deficit = -change
            recipients = sorted(recipients, key=lambda r: -r[1])
            addr, val = recipients[0]
            if val - deficit <= DUST:
                return None
            recipients[0] = (addr, val - deficit)
            change = 0

        outputs = list(recipients)
        if change > DUST:
            outputs.append((self._change_address(actor), change))

        # apply balance changes
        for addr, val in inputs:
            actor.balances.pop(addr, None)
        for addr, val in outputs:
            owner = self.owner.get(addr)
            if owner and owner in self.actors:
                tgt = self.actors[owner]
                tgt.balances[addr] = tgt.balances.get(addr, 0) + val

        self._n += 1
        tx = Tx(
            txid=_txid(f"{actor.eid}:{ts}:{self._n}".encode()),
            ts=int(ts), sender_eid=actor.eid, inputs=inputs, outputs=outputs,
            fee=fee, script_type=actor.script_type,
            illicit=illicit, typology=typology, hop=hop, campaign=campaign,
        )
        self.txs.append(tx)
        return tx

    def equal_split(self, actor: Actor, targets: list[Actor], amount_each: int, ts: int,
                    **kw) -> Tx | None:
        """CoinJoin-shaped spend: identical output values, no address reuse.

        Uniform output value is the single strongest mixer signal available, and
        it is what drives output_value_entropy in the feature set.
        """
        recips = [(self.receiving_address(t), amount_each) for t in targets]
        return self.spend(actor, recips, ts, equal_outputs=True, **kw)
