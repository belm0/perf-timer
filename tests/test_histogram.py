import random

import numpy as np
import pytest
from pytest import approx

from perf_timer._histogram import ApproximateHistogram


def test_histogram_exact():
    random.seed(0)
    max_bins = 50
    h = ApproximateHistogram(max_bins=max_bins)
    points = []

    for _ in range(max_bins):
        p = random.expovariate(1/5)
        points.append(p)
        h.add(p)

    q = [i / 100 for i in range(101)]
    assert h.quantile(q) == approx(np.quantile(points, q))
    assert h.mean() == approx(np.mean(points))
    assert h.std() == approx(np.std(points))
    assert h.sum() == approx(np.sum(points))
    assert h.min == min(points)
    assert h.max == max(points)
    assert h.count == max_bins


@pytest.mark.parametrize("max_bins,num_points,expected_error", [
    (50, 50, 1e-6),
    (100, 150, 1.5),
    (100, 1000, 1),
    (250, 1000, .5),
])
def test_histogram_approx(max_bins, num_points, expected_error):
    random.seed(0)
    h = ApproximateHistogram(max_bins=max_bins)
    points = []

    for _ in range(num_points):
        p = random.expovariate(1/5)
        points.append(p)
        h.add(p)

    q = [i / 100 for i in range(101)]
    err_sum = 0  # avg percent error across samples
    for p, b, b_np, b_np_min, b_np_max in zip(
            q,
            h.quantile(q),
            np.quantile(points, q),
            np.quantile(points, [0] * 7 + q),
            np.quantile(points, q[7:] + [1] * 7)):
        err_denom = b_np_max - b_np_min
        err_sum += abs(b - b_np) / err_denom
    assert err_sum <= expected_error
    assert h.mean() == approx(np.mean(points))
    assert h.std() == approx(np.std(points), rel=.05)
    assert h.sum() == approx(np.sum(points))
    assert h.min == min(points)
    assert h.max == max(points)
    assert h.count == num_points
