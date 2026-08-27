"""Six laundering typologies, of which two are held out of training.

Holding out `dormancy_burst` and `cross_asn_structuring` is what lets us report
recall on laundering patterns the model has never seen (roadmap §6.3). That
number will be low. Reporting it anyway is the point - it is the difference
between an evaluation and a sales pitch.

Each typology is a *shape*, not an amount distribution. Illicit and licit value
are drawn from the same heavy-tailed process on purpose: if illicit money were
simply bigger, the classifier would learn "big = bad" and learn nothing about
laundering. Signal lives in topology and timing.
"""
from __future__ import annotations

import numpy as np

from .actors import draw_os, make_address
from .ledger import DUST, Ledger
from .model import Actor, Tx

TRAIN_TYPOLOGIES = ("peel_chain", "fan_out_in", "rapid_layering", "mixer_passthrough")
HOLDOUT_TYPOLOGIES = ("dormancy_burst", "cross_asn_structuring")
ALL_TYPOLOGIES = TRAIN_TYPOLOGIES + HOLDOUT_TYPOLOGIES


class TypologyEngine:
    def __init__(self, ledger: Ledger, space, shared, cfg: dict,
                 rng: np.random.Generator, t0: int, t1: int,
                 cashouts: list[Actor] | None = None):
        self.lg = ledger
        self.space = space
        self.shared = shared
        self.cfg = cfg
        self.rng = rng
        self.t0, self.t1 = t0, t1
        self.mules: list[Actor] = []
        # Where laundered value actually leaves the system. Peels and final hops
        # land on real exchange/merchant deposit addresses rather than on yet more
        # throwaway wallets - which is both how cash-out works and the reason the
        # illicit entity count stays a small fraction of the population.
        self.cashouts: list[Actor] = cashouts or []
        self._n = 0

    def _cashout_addr(self) -> str | None:
        if not self.cashouts:
            return None
        tgt = self.cashouts[int(self.rng.integers(len(self.cashouts)))]
        return self.lg.receiving_address(tgt)

    # -- licit pass-through -------------------------------------------------
    def licit_passthrough(self, src: Actor, dst: Actor, ts: int, hops: int = 3) -> list[Tx]:
        """A legitimate chain of short-lived wallets moving value from A to B.

        THIS IS A LEAK FIX, and an important one. Laundering mules are new,
        short-lived, thinly-connected wallets that receive one concentrated chunk
        and forward nearly all of it. If the ONLY wallets in the dataset with that
        shape are criminal, the model learns "new pass-through wallet = illicit"
        and never has to learn anything about laundering at all - the leak test
        caught exactly this at ~2.4x baseline.

        Real Bitcoin is full of legitimate wallets with that profile: users
        migrating between wallets, hot-wallet rotation, exchange internal
        transfers, custody handoffs. Generating them makes the licit class
        structurally overlap the illicit one, so the model is forced to rely on
        what actually distinguishes laundering - chain depth, peel structure,
        timing, and the network layer.
        """
        out: list[Tx] = []
        amount = int(src.total_balance() * float(self.rng.uniform(0.2, 0.7)))
        if amount <= DUST * 20:
            return out
        holder = src
        for h in range(hops):
            nxt = self.spawn_mule("", "", illicit=False)
            bal = amount if h == 0 else holder.total_balance() - 40_000
            if bal <= DUST * 4:
                break
            addr = self.lg.receiving_address(nxt)
            t = self.lg.spend(holder, [(addr, bal)],
                              ts + h * int(self.rng.exponential(3600 * 6)))
            if t is None:
                break
            out.append(t)
            holder = nxt
        bal = holder.total_balance()
        if bal > DUST * 8:
            t = self.lg.spend(holder, [(self.lg.receiving_address(dst), bal - 30_000)],
                              ts + hops * int(self.rng.exponential(3600 * 6)))
            if t is not None:
                out.append(t)
        return out

    # -- mules ------------------------------------------------------------
    def spawn_mule(self, typology: str, campaign: str, kind: str | None = None,
                   illicit: bool = True) -> Actor:
        """A throwaway wallet. Few addresses, short life, thin network footprint."""
        self._n += 1
        kind = kind or str(self.rng.choice(["residential", "vpn", "hosting", "mobile"],
                                           p=[0.42, 0.28, 0.20, 0.10]))
        asn = self.space.pick_asn(kind)
        script = str(self.rng.choice(["p2wpkh", "p2pkh", "p2sh"], p=[0.6, 0.25, 0.15]))
        m = Actor(
            eid=(f"MULE-{self._n:05d}" if illicit else f"TRAN-{self._n:05d}"),
            archetype="mule" if illicit else "transient",
            script_type=script,
            ips=[self.space.issue(asn) for _ in range(int(self.rng.integers(1, 3)))],
            asn=asn.number, asn_type=kind, country=asn.country,
            tz_offset_min=asn.tz_offset_min,
            os_family=draw_os(self.rng),
            illicit=illicit, typology=typology or None,
        )
        m.addresses = [make_address(self.rng, script) for _ in range(int(self.rng.integers(1, 4)))]
        self.mules.append(m)
        self.lg.actors[m.eid] = m
        for a in m.addresses:
            self.lg.register(m, a)
        return m

    def _pay(self, src: Actor, dst: Actor, amount: int, ts: int, typ: str,
             campaign: str, hop: int) -> Tx | None:
        addr = self.lg.receiving_address(dst)
        return self.lg.spend(src, [(addr, amount)], ts, illicit=True, typology=typ,
                             campaign=campaign, hop=hop)

    # -- proceeds ---------------------------------------------------------
    def fund_campaign(self, src: Actor, victims: list[Actor], ts: int,
                      typ: str, campaign: str) -> list[Tx]:
        """Crime proceeds arriving before the laundering starts.

        Without this the source has nothing to launder and campaigns silently
        collapse. The inbound *shape* is archetype-specific and is itself a
        detection signal - "sudden large inflow followed by immediate layering"
        is a feature (time_to_first_outflow), not a coincidence.

        Victims stay licit. Being paid by a criminal does not make you one, and a
        generator that labelled them illicit would teach the model to flag
        bystanders.
        """
        # LEAK DISCIPLINE. Proceeds are drawn from the SAME payment-size
        # distribution as ordinary licit traffic, scaled off the paying victim's
        # own balance - because that is literally what they are: a payment from a
        # normal wallet. Using fixed absolute BTC ranges here made illicit money
        # systematically larger than licit money, and the leak test caught the
        # model learning "big = bad" from it at 1.7x baseline.
        #
        # The archetype controls the COUNT and the DISPERSION of the payments,
        # never their absolute scale. That keeps the shape of a campaign
        # detectable while leaving raw amount uninformative.
        from .simulate import payment_fraction

        if src.archetype == "extortion":
            # Many payers, one near-fixed demanded sum: low dispersion is the tell.
            n = int(self.rng.integers(18, 70))
            dispersion = 0.03
            spread = 86400 * 3
        elif src.archetype == "ransomware":
            # Few payers, individually negotiated: high dispersion.
            n = int(self.rng.integers(1, 5))
            dispersion = 0.45
            spread = 86400 * 2
        else:  # darknet market: many payers, ordinary market pricing
            n = int(self.rng.integers(12, 45))
            dispersion = 0.8
            spread = 86400 * 6

        out: list[Tx] = []
        if not victims:
            return out
        # One campaign-level "price", then per-payment variation around it.
        anchor = payment_fraction(self.rng)
        start = max(self.t0, ts - spread)
        for _ in range(n):
            v = victims[int(self.rng.integers(len(victims)))]
            bal = v.total_balance()
            if bal <= DUST * 20:
                continue
            frac = anchor * float(self.rng.lognormal(0.0, dispersion))
            amt = int(min(bal * 0.85, bal * frac))
            if amt <= DUST * 4:
                continue
            t = self.lg.spend(
                v, [(self.lg.receiving_address(src), amt)],
                int(self.rng.integers(start, max(start + 60, ts))),
                illicit=True, typology=typ, campaign=campaign, hop=None)
            if t is not None:
                out.append(t)
        return out

    # -- typologies -------------------------------------------------------
    def peel_chain(self, src: Actor, ts: int, campaign: str) -> list[Tx]:
        """Long chain; each hop peels a small amount off and forwards the rest.

        The classic cash-out ladder. Signature: high chain depth, small and
        consistent peel ratios, a long tail of one-hop-only side wallets.
        """
        p = self.cfg["typologies"]["peel_chain"]
        hops = int(self.rng.integers(*p["hops"]))
        lo, hi = p["peel_fraction"]
        out: list[Tx] = []
        holder = src
        amount = int(holder.total_balance() * float(self.rng.uniform(0.35, 0.8)))
        if amount <= DUST * 10:
            return out
        nxt = self.spawn_mule("peel_chain", campaign)
        tx = self._pay(holder, nxt, amount, ts, "peel_chain", campaign, 0)
        if tx is None:
            return out
        out.append(tx)
        holder = nxt
        for h in range(1, hops):
            ts += int(self.rng.exponential(3600 * 5))
            if ts > self.t1:
                break
            bal = holder.total_balance()
            if bal <= DUST * 20:
                break
            peel = int(bal * float(self.rng.uniform(lo, hi)))
            # The peel is the cash-out: it leaves for an exchange deposit address.
            # Only the remainder continues down the chain.
            sink_addr = self._cashout_addr()
            if sink_addr is None:
                sink_addr = self.lg.receiving_address(self.spawn_mule("peel_chain", campaign))
            nxt = self.spawn_mule("peel_chain", campaign)
            tx = self.lg.spend(
                holder,
                [(sink_addr, peel),
                 (self.lg.receiving_address(nxt), bal - peel - 50_000)],
                ts, illicit=True, typology="peel_chain", campaign=campaign, hop=h)
            if tx is None:
                break
            out.append(tx)
            holder = nxt
        return out

    def fan_out_in(self, src: Actor, ts: int, campaign: str) -> list[Tx]:
        """Split across many wallets, let them settle, then reconverge.

        Signature: a burst of high out-degree followed by high in-degree on a
        single collector k hops later. Reconvergence ratio is the giveaway.
        """
        p = self.cfg["typologies"]["fan_out_in"]
        n = int(self.rng.integers(*p["split"]))
        khops = int(self.rng.integers(*p["reconverge_hops"]))
        out: list[Tx] = []
        total = int(src.total_balance() * float(self.rng.uniform(0.4, 0.85)))
        each = total // n
        if each <= DUST * 4:
            return out
        legs = [self.spawn_mule("fan_out_in", campaign) for _ in range(n)]
        tx = self.lg.spend(src, [(self.lg.receiving_address(m), each) for m in legs], ts,
                           illicit=True, typology="fan_out_in", campaign=campaign, hop=0)
        if tx is None:
            return out
        out.append(tx)

        # Intermediate hops shuffle value WITHIN the same mule network rather than
        # minting a fresh wallet per leg per hop. Real mule networks are a fixed
        # roster being reused; spawning new entities every hop would both inflate
        # the illicit population and hand the model an unrealistically clean signal.
        layer = legs
        for h in range(1, khops):
            ts += int(self.rng.exponential(3600 * 8))
            perm = list(self.rng.permutation(len(layer)))
            for i, m in enumerate(layer):
                bal = m.total_balance()
                if bal <= DUST * 4:
                    continue
                dst = layer[perm[i]]
                if dst is m:
                    continue
                t = self._pay(m, dst, bal - 30_000, ts + int(self.rng.integers(0, 3600)),
                              "fan_out_in", campaign, h)
                if t is not None:
                    out.append(t)

        collector = self.spawn_mule("fan_out_in", campaign, kind="hosting")
        ts += int(self.rng.exponential(3600 * 6))
        for m in layer:
            bal = m.total_balance()
            if bal <= DUST * 4:
                continue
            t = self._pay(m, collector, bal - 30_000, ts + int(self.rng.integers(0, 7200)),
                          "fan_out_in", campaign, khops)
            if t is not None:
                out.append(t)
        # Reconverged value leaves for an exchange - the point of the exercise.
        addr = self._cashout_addr()
        bal = collector.total_balance()
        if addr and bal > DUST * 8:
            t = self.lg.spend(collector, [(addr, bal - 40_000)],
                              ts + int(self.rng.exponential(3600 * 12)),
                              illicit=True, typology="fan_out_in", campaign=campaign,
                              hop=khops + 1)
            if t is not None:
                out.append(t)
        return out

    def rapid_layering(self, src: Actor, ts: int, campaign: str) -> list[Tx]:
        """Many hops in a short window with almost no dwell time.

        Signature: chain depth similar to a peel chain but compressed into
        minutes. Burstiness and mean inter-transaction gap separate the two.
        """
        p = self.cfg["typologies"]["rapid_layering"]
        hops = int(self.rng.integers(*p["hops"]))
        dlo, dhi = p["dwell_minutes"]
        out: list[Tx] = []
        holder = src
        amount = int(holder.total_balance() * float(self.rng.uniform(0.5, 0.9)))
        if amount <= DUST * 10:
            return out
        for h in range(hops):
            nxt = self.spawn_mule("rapid_layering", campaign)
            bal = amount if h == 0 else holder.total_balance() - 40_000
            if bal <= DUST * 4:
                break
            tx = self._pay(holder, nxt, bal, ts, "rapid_layering", campaign, h)
            if tx is None:
                break
            out.append(tx)
            holder = nxt
            ts += int(self.rng.uniform(dlo, dhi) * 60)
            if ts > self.t1:
                break
        return out

    def mixer_passthrough(self, src: Actor, ts: int, campaign: str,
                          mixer: Actor | None = None) -> list[Tx]:
        """Deposit into a mixer, withdraw as equal-value outputs to fresh wallets.

        Signature: output-value entropy collapses to near zero (identical
        amounts), address reuse stops, and ownership breaks at the mixer.
        """
        p = self.cfg["typologies"]["mixer_passthrough"]
        n = int(self.rng.integers(*p["participants"]))
        out: list[Tx] = []
        if mixer is None:
            return out
        amount = int(src.total_balance() * float(self.rng.uniform(0.4, 0.8)))
        if amount <= DUST * 20:
            return out
        tx = self._pay(src, mixer, amount, ts, "mixer_passthrough", campaign, 0)
        if tx is None:
            return out
        out.append(tx)
        ts += int(self.rng.exponential(3600 * 3))
        legs = [self.spawn_mule("mixer_passthrough", campaign) for _ in range(n)]
        each = int(amount * 0.97) // n
        if each <= DUST * 2:
            return out
        t = self.lg.equal_split(mixer, legs, each, ts, illicit=True,
                                typology="mixer_passthrough", campaign=campaign, hop=1)
        if t is not None:
            out.append(t)
        return out

    # ---- HELD OUT: never present in the training split -------------------
    def dormancy_burst(self, src: Actor, ts: int, campaign: str) -> list[Tx]:
        """Funds sit untouched for weeks, then move all at once.

        HELD OUT. Its signature is almost purely temporal - dormancy ratio and a
        single enormous inter-transaction gap - which is exactly why a model
        trained on the four topological typologies struggles with it.
        """
        p = self.cfg["typologies"]["dormancy_burst"]
        dormant = int(self.rng.integers(*p["dormant_days"])) * 86400
        n_burst = int(self.rng.integers(*p["burst_txs"]))
        wake = ts + dormant
        if wake > self.t1:
            wake = self.t1 - int(self.rng.integers(3600, 86400 * 2))
        out: list[Tx] = []
        pool = [self.spawn_mule("dormancy_burst", campaign)
                for _ in range(int(self.rng.integers(2, 5)))]
        holder = src
        for h in range(n_burst):
            bal = holder.total_balance()
            if bal <= DUST * 8:
                break
            nxt = pool[h % len(pool)]
            if nxt is holder:
                nxt = pool[(h + 1) % len(pool)]
            amt = int(bal * float(self.rng.uniform(0.5, 0.9)))
            t = self._pay(holder, nxt, amt, wake + h * int(self.rng.exponential(900)),
                          "dormancy_burst", campaign, h)
            if t is None:
                break
            out.append(t)
            if self.rng.random() < 0.5:
                holder = nxt
        addr = self._cashout_addr()
        if addr:
            for m in pool:
                bal = m.total_balance()
                if bal > DUST * 8:
                    t = self.lg.spend(m, [(addr, bal - 30_000)],
                                      wake + int(self.rng.exponential(86400)),
                                      illicit=True, typology="dormancy_burst",
                                      campaign=campaign, hop=n_burst)
                    if t is not None:
                        out.append(t)
        return out

    def cross_asn_structuring(self, src: Actor, ts: int, campaign: str) -> list[Tx]:
        """Tranches kept below a round threshold, deliberately spread across ASNs.

        HELD OUT. This is the only typology whose signature is primarily in the
        NETWORK layer - the same value, moved by wallets that are careful never
        to share an autonomous system. A chain-only detector is blind to it, which
        makes it the sharpest test of whether fusion actually earns its keep.
        """
        p = self.cfg["typologies"]["cross_asn_structuring"]
        n = int(self.rng.integers(*p["tranches"]))
        thresh = int(p["threshold_sats"])
        spread = int(self.rng.integers(*p["asn_spread"]))
        kinds = list(self.rng.choice(["residential", "hosting", "mobile", "vpn"],
                                     size=spread, replace=True))
        # One account per autonomous system, reused across tranches. Structuring
        # spreads value over a handful of deliberately-separated accounts; it does
        # not open a fresh wallet for every payment.
        accounts = [self.spawn_mule("cross_asn_structuring", campaign, kind=k) for k in kinds]
        out: list[Tx] = []
        for i in range(n):
            bal = src.total_balance()
            if bal <= DUST * 20:
                break
            # Just under the threshold: the structuring tell.
            amt = int(thresh * float(self.rng.uniform(0.86, 0.985)))
            amt = min(amt, int(bal * 0.9))
            if amt <= DUST * 4:
                break
            m = accounts[i % len(accounts)]
            t = self._pay(src, m, amt, ts + i * int(self.rng.exponential(3600 * 4)),
                          "cross_asn_structuring", campaign, i)
            if t is not None:
                out.append(t)
        # Each account cashes out separately - never together, which is the whole
        # point of separating them across networks in the first place.
        for j, m in enumerate(accounts):
            addr = self._cashout_addr()
            bal = m.total_balance()
            if addr and bal > DUST * 8:
                t = self.lg.spend(m, [(addr, bal - 30_000)],
                                  ts + int(self.rng.exponential(86400 * 2)) + j * 3600,
                                  illicit=True, typology="cross_asn_structuring",
                                  campaign=campaign, hop=n + j)
                if t is not None:
                    out.append(t)
        return out

    def run(self, name: str, src: Actor, ts: int, campaign: str,
            mixer: Actor | None = None) -> list[Tx]:
        if name == "mixer_passthrough":
            return self.mixer_passthrough(src, ts, campaign, mixer)
        return getattr(self, name)(src, ts, campaign)
