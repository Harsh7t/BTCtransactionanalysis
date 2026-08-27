# Generator parameters

Every distribution the synthetic generator draws from, what it models, and where the
value came from.

> **Values marked _assumption_ are engineering defaults chosen to make the two-layer
> fusion thesis exercisable. They are not measured from the literature.** No absolute
> detection-rate claim should be made on their basis until they are replaced with sourced
> values. What the current numbers support is a claim about the *method and the system*.

## Payment sizes — the leak firewall

| Parameter | Models | Value | Source |
|---|---|---|---|
| `PAYMENT_LOG_MEAN` | payment size as a share of payer balance | −3.0 | _assumption_ |
| `PAYMENT_LOG_SIGMA` | spread of payment sizes | 1.9 | _assumption_ — deliberately wide so licit and illicit payments span the same range |

**One distribution serves both licit traffic and crime proceeds.** This is the single most
important property in the file. An earlier version drew proceeds from fixed absolute BTC
ranges, which made illicit money systematically larger; the leak test caught the model
learning "big = bad" at 1.7× baseline. The archetype now controls the *count* and
*dispersion* of payments, never their absolute scale.

## Fees

| Parameter | Models | Value | Source |
|---|---|---|---|
| `base_sat_per_vb` | network fee pressure | 12.0 | _assumption_ |
| `diurnal_amplitude` | daily mempool congestion cycle | 0.35 | _assumption_ |
| `noise_sigma` | lognormal multiplicative noise | 0.30 | _assumption_ |

Fee is `f(vsize, congestion at timestamp)` and nothing else. It never depends on who is
spending. This is enforced by the strict tier of the leak test
(`mean_feerate_sat_vb` measured at 1.145× baseline).

## Network layer

| Parameter | Models | Value | Source |
|---|---|---|---|
| `peer_delay_mean_s` | Bitcoin Core's randomised per-peer relay delay | 2.0 | The **mechanism** is documented — Koshy et al. FC 2014, Biryukov et al. CCS 2014, and the Dandelion++ proposal (BIP-156, Fanti et al. 2018) that was never merged. The **constant** is an _assumption_ |
| `fanout_peers` | peers an originating node announces to | 8 | _assumption_, order-of-magnitude consistent with Core's default outbound peer count |
| `relay_depth` | further re-announcement hops simulated | 2 | _assumption_ |
| `observation_coverage` | fraction of the P2P network the collector monitors | 0.25 | _assumption_ — **swept end-to-end**, see below |
| `churn_prob_residential` | daily chance a residential IP rotates | 0.06 | _assumption_ |
| `shared_pool_size` | VPN/Tor exit addresses shared across entities | 60 | _assumption_ |

**Coverage is modelled per-vantage-point, not per-event.** A real collector monitors a set
of nodes and sees an announcement iff its destination is one of them. Sampling events
independently at random would make attribution far too easy and flatter every downstream
number.

## Wallet behaviour

| Parameter | Models | Value | Source |
|---|---|---|---|
| `CHANGE_SCRIPT_MISMATCH` | wallets returning change to a different script type | 0.09 | _assumption_ — deliberately non-zero so the change heuristic has a realistic error rate instead of being exact by construction |
| `OS_PROBS` | host OS mix (drives ephemeral port range) | 0.55 / 0.38 / 0.07 | _assumption_. **Drawn identically for every actor** — mules once used a different distribution, and the leak test detected it as 1.2× lift on port features |
| CoinJoin output script type | uniform across all outputs | — | **Real**: Wasabi and JoinMarket require every output in a round to use the same script type; mixed types would defeat the point |

## Typologies

Six laundering patterns; `dormancy_burst` and `cross_asn_structuring` are held entirely
out of training. `n_licit_passthrough` (320) generates **legitimate** multi-hop chains of
short-lived wallets — wallet migrations, hot-wallet rotation, custody handoffs. Without
them, "short-lived wallet forwarding one chunk" is a perfect illicit predictor and the
model never has to learn laundering at all.

## Sensitivity

`observation_coverage` is the parameter our central claim is most sensitive to, so it is
swept rather than asserted. See `artifacts/v1/sensitivity.json` and the Model panel: top-1
attribution runs from 0.593 at 5% coverage to 0.901 at 100%, and **crosses below the
random-choice baseline under ~10%**.

## Known class-balance deviation

The generated capture carries a higher illicit entity rate than a real-world base rate
(3.3% in the test fold). This is a deliberate trade: enough positives to train and
evaluate at all. It means precision figures are more favourable than deployment would be,
and it is why PR-AUC is always reported against the fold's own base rate.
