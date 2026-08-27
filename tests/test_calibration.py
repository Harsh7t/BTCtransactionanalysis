"""Calibration must mean ONE thing everywhere.

A confidence score is the product's central claim. If the training path and the
scoring path compute it differently, the Model panel and the alert queue are
describing different systems.
"""
import numpy as np
import pytest

from btcfusion.detect.fuse import Calibrator


def _fitted() -> Calibrator:
    rng = np.random.default_rng(0)
    raw = rng.random(2000)
    y = (rng.random(2000) < raw * 0.4).astype(int)
    return Calibrator().fit(raw, y)


def test_transform_is_pure_and_repeatable():
    """Same input, same output, every time - no hidden state."""
    cal = _fitted()
    raw = np.linspace(0, 1, 500)
    a = cal.transform(raw)
    b = cal.transform(raw)
    assert np.array_equal(a, b)


def test_transform_does_not_mutate_the_calibrator():
    """api/main.py runs pipeline jobs in threads; a mutating transform races."""
    cal = _fitted()
    before = {k: v for k, v in vars(cal).items() if isinstance(v, (int, float))}
    cal.transform(np.linspace(0, 1, 200))
    after = {k: v for k, v in vars(cal).items() if isinstance(v, (int, float))}
    assert before == after


def test_transform_takes_no_adjust_prior_kwarg():
    """One calibration path, not two. The kwarg is what let them diverge."""
    cal = _fitted()
    with pytest.raises(TypeError):
        cal.transform(np.linspace(0, 1, 10), adjust_prior=True)


def test_output_is_always_a_valid_probability():
    cal = _fitted()
    out = cal.transform(np.array([-5.0, 0.0, 0.5, 1.0, 5.0]))
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_estimate_prior_recovers_a_known_positive_rate():
    cal = _fitted()
    p = np.concatenate([np.full(100, 0.9), np.full(900, 0.02)])
    assert cal.estimate_prior(p) == pytest.approx(0.108, abs=0.05)
