"""Attribution is the differentiator. An unmeasured differentiator is a claim.

Grading is not trivial here: our resolved entity IDs are not the generator's, so
truth has to be joined through the label map, and a system that answers rarely
but correctly must not score the same as one that answers always and wrongly.
"""
import polars as pl

from btcfusion.attribute.engine import Attribution
from btcfusion.eval.attribution_eval import evaluate_attribution


def _truth() -> pl.DataFrame:
    return pl.DataFrame({
        "eid": ["T-1", "T-2", "T-3"],
        "ips": ["198.18.0.1|198.18.0.2", "198.18.0.9", ""],
    })


def _labels() -> pl.DataFrame:
    return pl.DataFrame({
        "entity": ["ENT-A", "ENT-B", "ENT-C"],
        "true_eid": ["T-1", "T-2", "T-3"],
    })


def _attr(entity, ips, status="ok"):
    return Attribution(entity=entity,
                       candidates=[{"ip": ip, "confidence": 0.9} for ip in ips],
                       status=status)


def test_top1_hit_is_counted():
    got = evaluate_attribution(
        {"ENT-A": _attr("ENT-A", ["198.18.0.1", "10.0.0.1"])}, _truth(), _labels())
    assert got["top1_accuracy"] == 1.0
    assert got["mrr"] == 1.0


def test_rank_three_hit_scores_top3_not_top1():
    got = evaluate_attribution(
        {"ENT-A": _attr("ENT-A", ["10.0.0.1", "10.0.0.2", "198.18.0.2"])},
        _truth(), _labels())
    assert got["top1_accuracy"] == 0.0
    assert got["top3_accuracy"] == 1.0
    assert round(got["mrr"], 3) == round(1 / 3, 3)


def test_wrong_attribution_scores_zero_but_still_counts_as_attempted():
    got = evaluate_attribution(
        {"ENT-B": _attr("ENT-B", ["203.0.113.1"])}, _truth(), _labels())
    assert got["top1_accuracy"] == 0.0
    assert got["n_attempted"] == 1


def test_suppressed_entities_are_not_counted_as_attempts():
    """Declining to answer must not be scored as a wrong answer."""
    got = evaluate_attribution(
        {"ENT-A": _attr("ENT-A", [], status="suppressed")}, _truth(), _labels())
    assert got["n_attempted"] == 0
    assert got["attempt_rate"] == 0.0


def test_entities_with_no_truth_ips_are_not_evaluable():
    """T-3 has no IPs, so ENT-C cannot be graded either way."""
    got = evaluate_attribution(
        {"ENT-C": _attr("ENT-C", ["198.18.0.1"])}, _truth(), _labels())
    assert got["n_evaluable"] == 0
