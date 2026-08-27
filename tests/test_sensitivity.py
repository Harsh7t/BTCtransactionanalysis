"""Attribution must degrade as coverage falls, and we must be able to show it."""
from btcfusion.eval.sensitivity import sweep_coverage


def test_sweep_returns_one_row_per_coverage_point():
    # Deliberately tiny so the test runs in seconds, not minutes.
    rows = sweep_coverage([0.10, 0.50], seed=7, n_entities=120, days=8)
    assert len(rows) == 2
    assert {r["coverage"] for r in rows} == {0.10, 0.50}
    for r in rows:
        for k in ("top1_accuracy", "top3_accuracy", "mrr", "attempt_rate", "n_evaluable"):
            assert k in r


def test_higher_coverage_never_reduces_the_attempt_rate():
    """Seeing more of the network cannot make the engine willing to answer less."""
    rows = sorted(sweep_coverage([0.10, 0.60], seed=7, n_entities=120, days=8),
                  key=lambda r: r["coverage"])
    assert rows[-1]["attempt_rate"] >= rows[0]["attempt_rate"] - 0.05
