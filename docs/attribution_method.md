# Attribution method

The component that answers the PS's load-bearing verb — *correlates*. Given an on-chain
entity, which network identity is behind it, and how sure are we?

## Pipeline

```
announcements
  ① entity × IP co-occurrence matrix
  ② propagation-tree roots, per transaction     ← diffusion.py
  ③ hypergeometric significance vs a null model ← significance.py
  ④ infrastructure classification and penalty   ← infra.py
  ⑤ behavioural timezone inference              ← behaviour.py
  ⑥ confidence, interval, counterfactuals       ← confidence.py
```

## ② Diffusion — the credibility step

Naive first-relay attribution says "whoever we saw announce it first is the originator".
Koshy et al. (FC 2014) and Biryukov et al. (CCS 2014) demonstrated that P2P relay patterns
leak origin, and Bitcoin Core responded: modern diffusion applies an **independent
randomised delay per peer**, so the first announcement a given collector observes is
frequently a relay, not the source. Dandelion++ (BIP-156) was proposed to strengthen this
and never merged.

We model the defence rather than ignoring it:

- **Propagation-tree roots.** `src_ip → dst_ip` edges with timestamps reconstruct who
  announced to whom per transaction. A node that announces but is never announced *to*
  within that transaction is a root — materially stronger evidence than "seen first".
  Where no candidate survives, the transaction contributes no root evidence at all.
  Most designs ignore `dst_ip` entirely and cannot do this.
- **Single observations are weak by construction.** Evidence weight saturates as
  `1 − exp(−n/4)`: one sighting earns ~22% of full weight, eight earn ~86%. One sighting
  can never on its own produce a confident attribution.

## ③ Significance

Co-occurrence counts alone mislead: a busy relay co-occurs heavily with everyone. The
question is whether the association is stronger than chance **given how much traffic that
address carries and how many transactions that entity made**. A hypergeometric survival
test answers exactly that, with PPMI supplying magnitude alongside the p-value.

**Benjamini–Hochberg FDR control** is applied across the whole pair set. Testing hundreds
of thousands of pairs at an uncorrected p < 0.01 would hand back thousands of spurious
links.

## ④ Infrastructure penalty

Two sources, because either alone is exploitable: the **declared** ASN type from the
bundled GeoIP database, and the **observed** number of distinct entities seen announcing
from that address in this capture. An ASN labelled residential that carries 400 entities
is a shared box whatever the database says.

| Class | Multiplier |
|---|---|
| residential | 1.00 |
| mobile | 0.90 (CGNAT) |
| hosting | 0.72 |
| CDN | 0.30 |
| VPN | 0.22 |
| Tor exit | 0.12 |

## ⑤ Behavioural timezone

People keep hours. Taking an entity's activity histogram and asking which UTC offset makes
it look most like a human waking, working and sleeping gives an estimate of where the
operator physically is — derived from **behaviour, not from the GeoIP database**. When the
two independent methods agree, that is real corroboration. `diurnality` guards against
nonsense: a flat 24/7 histogram fits every offset equally, and is reported as such.

## ⑥ Confidence and abstention

```
confidence = statistical strength
           × repeat-observation weight
           × propagation-root bonus
           × infrastructure penalty
           × timezone corroboration
```

**Where every candidate is shared infrastructure, attribution is suppressed rather than
reported at a confidence that would mislead.** An attribution engine that always produces
an answer is not an attribution engine. 195 abstentions on demo (624 on bulk), and they are
scored separately from errors — declining to answer is not the same as answering wrongly.

Counterfactuals are computed by re-running this model with one input changed, so they are
a property of the model rather than authored text.

## Measured performance

| Metric | demo | **bulk** |
|---|---|---|
| Top-1 accuracy | 0.9052 | **0.9243** |
| Random-choice baseline | 0.3449 (mean 3.58 candidates) | 0.3378 (mean 3.64 candidates) |
| Top-3 · MRR | 0.9064 · 0.9058 | 0.9251 · 0.9247 |
| Attempt rate · abstentions | 98.6% · 195 | 98.9% · 624 |
| Pairs tested → significant at FDR α 0.01 | 66,534 → 64,807 | 290,787 → 280,911 |
| Attributions suppressed as shared infrastructure | 5,694 | 28,661 |

### Degradation with observation coverage (demo sweep)

| Coverage | Top-1 | Chance |
|---|---|---|
| 5% | 0.593 | **0.740** |
| 10% | 0.671 | 0.585 |
| 20% | 0.781 | 0.396 |
| 35% | 0.862 | 0.284 |
| 100% | 0.901 | 0.200 |

**Below ~10% coverage the engine is worse than guessing** — it is mostly seeing relays and
picking among them confidently. Reported rather than hidden: a single accuracy number at
an unstated coverage would be exactly the overclaim this module exists to avoid.
