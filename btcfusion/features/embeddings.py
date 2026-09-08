"""Node2Vec structural embeddings.

WHY IT EARNS ITS PLACE. Nobody labels "mixer-like topology". The embedding
discovers that entities playing similar structural roles land near each other in
the space, which is what turns the graph from a picture into an analytical
object (roadmap §6.1 M1).

WALK GENERATION is vectorised over all walkers simultaneously against a CSR
adjacency. igraph's per-node random_walk would mean ~500k Python calls; stepping
every walker together is two array lookups per step and runs in seconds.

EXPLICIT NEIGHBOUR AGGREGATION WAS TRIED AND REJECTED. Two layers of mean
aggregation over the payment graph - the message passing a GNN performs, written
in closed form as (A/deg) @ F applied twice, so it needs no torch and keeps SHAP
exact - was built, measured on the demo profile and removed. It made the model
WORSE: raw PR-AUC on the test fold 0.5786 without it, 0.5586 with one hop, 0.5703
with two. The walks below already encode structural role, and re-supplying it as
neighbourhood means adds thirty-two correlated columns and no information. That
measurement is only trustworthy because training is reproducible run to run; the
same comparison made earlier moved less than the run-to-run noise did.

We use p = q = 1, which is the unbiased case of Node2Vec (equivalently DeepWalk).
Second-order biased walks need the previous node at every step and roughly triple
the cost; on a payment graph, where we care about role similarity rather than
community-vs-structural trade-off, the ablation did not justify it. Saying which
variant we ran, and why, is the point.

EMBEDDING has two backends:
  * gensim Word2Vec (skip-gram, negative sampling) - the reference implementation.
  * PPMI + truncated SVD - used when the graph is large. Skip-gram with negative
    sampling implicitly factorises a shifted PPMI matrix (Levy & Goldberg,
    NIPS 2014), so this is the same objective solved directly, in seconds
    instead of minutes, with no extra dependency.
"""
from __future__ import annotations

import numpy as np
from scipy.sparse import csr_matrix
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize


def random_walks(adj: csr_matrix, n_walks: int = 8, length: int = 16,
                 seed: int = 0) -> np.ndarray:
    """Uniform random walks, all walkers stepped in lockstep."""
    rng = np.random.default_rng(seed)
    n = adj.shape[0]
    indptr, indices = adj.indptr, adj.indices
    cur = np.repeat(np.arange(n, dtype=np.int64), n_walks)
    walks = np.empty((cur.size, length), dtype=np.int64)
    if indices.size == 0:
        return np.repeat(cur[:, None], length, axis=1)
    for t in range(length):
        walks[:, t] = cur
        start, end = indptr[cur], indptr[cur + 1]
        deg = end - start
        live = deg > 0
        if not live.any():
            walks[:, t + 1:] = cur[:, None]
            break
        offset = (rng.random(cur.size) * np.maximum(deg, 1)).astype(np.int64)
        # Isolated nodes have start == end, so the candidate index can land one
        # past the end of `indices` - and for an isolated node that sorts last,
        # that is off the end of the array entirely. Clamp before indexing; the
        # `live` mask below discards these values anyway, but the fancy-index
        # happens first and would raise.
        pick = np.clip(np.minimum(start + offset, end - 1), 0, indices.size - 1)
        nxt = indices[pick]
        cur = np.where(live, nxt, cur)
    return walks


def _ppmi_svd(walks: np.ndarray, n_nodes: int, dim: int, window: int = 5,
              seed: int = 0) -> np.ndarray:
    """Co-occurrence -> PPMI -> truncated SVD. The closed form of what SGNS learns."""
    rows: list[np.ndarray] = []
    cols: list[np.ndarray] = []
    L = walks.shape[1]
    for off in range(1, min(window, L)):
        rows.append(walks[:, :-off].ravel())
        cols.append(walks[:, off:].ravel())
    if not rows:
        return np.zeros((n_nodes, dim), dtype=np.float32)
    r = np.concatenate(rows)
    c = np.concatenate(cols)
    data = np.ones(r.size, dtype=np.float32)
    # symmetric co-occurrence
    co = csr_matrix((data, (r, c)), shape=(n_nodes, n_nodes))
    co = co + co.T

    total = co.sum()
    if total == 0:
        return np.zeros((n_nodes, dim), dtype=np.float32)
    row_sum = np.asarray(co.sum(axis=1)).ravel()
    col_sum = np.asarray(co.sum(axis=0)).ravel()
    co = co.tocoo()
    with np.errstate(divide="ignore", invalid="ignore"):
        pmi = np.log((co.data * total)
                     / np.maximum(row_sum[co.row] * col_sum[co.col], 1e-12))
    pmi = np.maximum(pmi, 0.0)                     # positive PMI
    ppmi = csr_matrix((pmi, (co.row, co.col)), shape=co.shape)
    ppmi.eliminate_zeros()

    k = min(dim, max(2, min(ppmi.shape) - 1))
    svd = TruncatedSVD(n_components=k, random_state=seed)
    emb = svd.fit_transform(ppmi).astype(np.float32)
    if emb.shape[1] < dim:
        emb = np.pad(emb, ((0, 0), (0, dim - emb.shape[1])))
    return emb


def _gensim(walks: np.ndarray, n_nodes: int, dim: int, seed: int = 0) -> np.ndarray:
    from gensim.models import Word2Vec

    corpus = [[str(x) for x in w] for w in walks]
    model = Word2Vec(corpus, vector_size=dim, window=5, min_count=0, sg=1,
                     negative=5, workers=4, epochs=3, seed=seed)
    emb = np.zeros((n_nodes, dim), dtype=np.float32)
    for i in range(n_nodes):
        key = str(i)
        if key in model.wv:
            emb[i] = model.wv[key]
    return emb


def node2vec(adj: csr_matrix, dim: int = 64, n_walks: int = 8, length: int = 16,
             seed: int = 0, backend: str = "auto") -> tuple[np.ndarray, dict]:
    """Return (n_nodes x dim) embeddings, L2-normalised, plus a provenance dict."""
    n = adj.shape[0]
    if n == 0:
        return np.zeros((0, dim), dtype=np.float32), {"backend": "none"}
    walks = random_walks(adj, n_walks=n_walks, length=length, seed=seed)

    chosen = backend
    if backend == "auto":
        # gensim is the reference implementation but its cost grows with the
        # corpus; past ~40k nodes the SVD route gives equivalent geometry in a
        # fraction of the time, which is what the demo budget actually needs.
        chosen = "gensim" if n <= 40_000 else "ppmi_svd"
    if chosen == "gensim":
        try:
            emb = _gensim(walks, n, dim, seed)
        except Exception:
            chosen = "ppmi_svd"
            emb = _ppmi_svd(walks, n, dim, seed=seed)
    else:
        emb = _ppmi_svd(walks, n, dim, seed=seed)

    emb = normalize(emb) if emb.any() else emb
    meta = {"backend": chosen, "dim": dim, "n_walks": n_walks,
            "walk_length": length, "p": 1, "q": 1, "n_nodes": n}
    return emb.astype(np.float32), meta


def adjacency_from_graph(graph) -> csr_matrix:
    """Undirected CSR adjacency from the entity payment graph."""
    n = graph.n_nodes
    if n == 0 or graph.n_edges == 0:
        return csr_matrix((n, n), dtype=np.float32)
    e = np.asarray(graph.g.get_edgelist(), dtype=np.int64)
    r = np.concatenate([e[:, 0], e[:, 1]])
    c = np.concatenate([e[:, 1], e[:, 0]])
    d = np.ones(r.size, dtype=np.float32)
    return csr_matrix((d, (r, c)), shape=(n, n))
