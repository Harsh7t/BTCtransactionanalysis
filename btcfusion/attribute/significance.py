"""Is this entity<->IP link stronger than chance?

Co-occurrence counts alone are misleading: a busy relay announces a great many
entities' transactions, so it will co-occur heavily with all of them without
being any of them. The question that matters is not "how often" but "more often
than we would expect given how much traffic this IP carries and how many
transactions this entity made".

TWO STATISTICS, computed against the same null model:

  * HYPERGEOMETRIC SURVIVAL. Draw n announcements (this entity's) from a
    population of N (all announcements) containing K from this IP; how surprising
    is it to see k or more? This is sampling without replacement, which is what
    the situation actually is.

  * POSITIVE POINTWISE MUTUAL INFORMATION. log( P(e,i) / (P(e)P(i)) ), floored at
    zero. Gives a magnitude to sit alongside the p-value, and is stable when
    counts are small.

Both are computed vectorised over the sparse entity x IP matrix. A per-pair
Python loop over ~90k entities would take minutes for a stage budgeted at 15s.
"""
from __future__ import annotations

import numpy as np
from scipy.sparse import csr_matrix
from scipy.stats import hypergeom


def cooccurrence_significance(m: csr_matrix, min_count: int = 2
                              ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Score every observed entity x IP pair.

    Returns (rows, cols, p_values, ppmi) for pairs meeting min_count. Only
    observed pairs are scored - the matrix is sparse and the zeros are not
    evidence of anything.
    """
    coo = m.tocoo()
    keep = coo.data >= min_count
    rows, cols, k = coo.row[keep], coo.col[keep], coo.data[keep].astype(np.int64)
    if len(k) == 0:
        e = np.array([], dtype=np.int64)
        return e, e, np.array([]), np.array([])

    N = int(m.sum())
    entity_tot = np.asarray(m.sum(axis=1)).ravel()     # n: this entity's announcements
    ip_tot = np.asarray(m.sum(axis=0)).ravel()         # K: this IP's announcements

    n = entity_tot[rows].astype(np.int64)
    K = ip_tot[cols].astype(np.int64)

    # P(X >= k) under the null that the entity's announcements were drawn at
    # random from all announcements.
    p = hypergeom.sf(k - 1, N, K, n)
    p = np.clip(p, 1e-300, 1.0)

    # PPMI on the same counts.
    with np.errstate(divide="ignore", invalid="ignore"):
        pmi = np.log((k * N) / np.maximum(n * K, 1e-12))
    ppmi = np.maximum(np.nan_to_num(pmi), 0.0)

    return rows, cols, p, ppmi


def benjamini_hochberg(p: np.ndarray, alpha: float = 0.01) -> np.ndarray:
    """FDR control across the whole pair set.

    We test hundreds of thousands of entity x IP pairs at once, so an uncorrected
    p < 0.01 would hand back thousands of spurious links. Benjamini-Hochberg
    controls the expected proportion of false discoveries, which is the right
    guarantee for a lead-generation tool: the analyst can be told what fraction of
    the list is expected to be noise.
    """
    n = len(p)
    if n == 0:
        return np.array([], dtype=bool)
    order = np.argsort(p)
    ranked = p[order]
    thresh = alpha * (np.arange(1, n + 1) / n)
    passed = ranked <= thresh
    if not passed.any():
        return np.zeros(n, dtype=bool)
    cutoff_rank = np.max(np.where(passed)[0])
    out = np.zeros(n, dtype=bool)
    out[order[:cutoff_rank + 1]] = True
    return out
