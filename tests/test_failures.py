"""Three cases we get wrong, with reasons. Credibility, not decoration."""
import numpy as np
import polars as pl

from btcfusion.eval.failures import failure_gallery


def _fm():
    return pl.DataFrame({
        "entity": ["E1", "E2", "E3", "E4"],
        "max_n_outputs": [40.0, 2.0, 3.0, 1.0],
        "dormancy_ratio": [0.1, 0.9, 0.2, 0.1],
        "shared_infra_frac": [0.0, 0.0, 1.0, 0.0],
    })


def _labels():
    return pl.DataFrame({
        "entity": ["E1", "E2", "E3", "E4"],
        "archetype": ["exchange", "mule", "mule", "retail"],
        "typology": ["", "dormancy_burst", "peel_chain", ""],
    })


def test_gallery_finds_the_worst_false_positive():
    y = np.array([0, 1, 1, 0])
    s = np.array([0.95, 0.10, 0.20, 0.05])     # E1 wrongly high
    g = failure_gallery(["E1", "E2", "E3", "E4"], y, s, _fm(), _labels(), 0.5)
    fps = [x for x in g if x["kind"] == "false_positive"]
    assert fps and fps[0]["entity"] == "E1"


def test_gallery_finds_the_worst_false_negative():
    y = np.array([0, 1, 1, 0])
    s = np.array([0.95, 0.10, 0.20, 0.05])
    g = failure_gallery(["E1", "E2", "E3", "E4"], y, s, _fm(), _labels(), 0.5)
    fns = [x for x in g if x["kind"] == "false_negative"]
    assert fns and fns[0]["entity"] == "E2"     # lowest-scoring true positive


def test_every_entry_carries_a_reason():
    y = np.array([0, 1, 1, 0])
    s = np.array([0.95, 0.10, 0.20, 0.05])
    for x in failure_gallery(["E1", "E2", "E3", "E4"], y, s, _fm(), _labels(), 0.5):
        assert x["why"] and len(x["why"]) > 20
