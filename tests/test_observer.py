import random
from unittest.mock import Mock

import numpy
import pytest

from perf_timer import AverageObserver, StdDevObserver, HistogramObserver


@pytest.mark.parametrize('n', (0, 1, 100))
def test_average_observer(n):
    name = 'foo'
    log_fn = Mock()
    observer = AverageObserver(name, log_fn=log_fn)
    points = []
    for _ in range(n):
        x = random.expovariate(1/5)  # expected average is 5s
        observer._observe(x)
        points.append(x)
    del observer
    if n > 1:
        # timer "foo": avg 11.9 ms, max 12.8 ms in 10 runs
        log_fn.assert_called_once_with(
            f'timer "{name}": '
            f'avg {sum(points)/n:.2f} s, '
            f'max {max(points):.1f} s '
            f'in {n} runs')
    elif n > 0:
        # timer "foo": 12.8 ms
        log_fn.assert_called_once_with(
            f'timer "{name}": '
            f'{points[0]:.1f} s')
    else:
        log_fn.assert_not_called()


@pytest.mark.parametrize('n', (0, 1, 100))
def test_std_dev_observer(n):
    name = 'foo'
    log_fn = Mock()
    observer = StdDevObserver(name, log_fn=log_fn)
    points = []
    for _ in range(n):
        x = random.expovariate(1/5)  # expected average is 5s
        observer._observe(x)
        points.append(x)
    del observer
    if n > 1:
        # timer "foo": avg 11.9 ms ± 961 µs, max 12.8 ms in 10 runs
        log_fn.assert_called_once_with(
            f'timer "{name}": '
            f'avg {sum(points)/n:.2f} s ± {numpy.std(points):.2f} s, '
            f'max {max(points):.1f} s '
            f'in {n} runs')
    elif n > 0:
        # timer "foo": 12.8 ms
        log_fn.assert_called_once_with(
            f'timer "{name}": '
            f'{points[0]:.1f} s')
    else:
        log_fn.assert_not_called()


@pytest.mark.parametrize('n', (0, 1, 50))
def test_histogram_observer(n):
    name = 'foo'
    # cheating to allow a simple string compare:
    #   * requested quantiles and distribution are such that output precision is fixed
    #   * since n < max bins of the approximate histogram, quantile output will be exact
    quantiles = (.4, .5, .6)
    log_fn = Mock()
    observer = HistogramObserver(name, quantiles=quantiles, log_fn=log_fn)
    points = []
    for _ in range(n):
        x = random.expovariate(1/5)  # expected average is 5s
        observer._observe(x)
        points.append(x)
    del observer
    if n > 1:
        q_expected = numpy.quantile(points, quantiles)
        # timer "foo": avg 11.9ms ± 961µs, 50% ≤ 12.6ms, 90% ≤ 12.7ms in 10 runs
        log_fn.assert_called_once_with(
            f'timer "{name}": '
            f'avg {sum(points)/n:.2f}s ± {numpy.std(points):.2f}s, '
            f'{", ".join(f"{q:.0%} ≤ {out:.2f}s" for q, out in zip(quantiles, q_expected))} '
            f'in {n} runs')
    elif n > 0:
        # timer "foo": 12.8 ms
        log_fn.assert_called_once_with(
            f'timer "{name}": '
            f'{points[0] * 1000:.1f} ms')
    else:
        log_fn.assert_not_called()


def test_histogram_observer_bad_input():
    with pytest.raises(ValueError):
        HistogramObserver('foo', quantiles=(.5, 2))
    with pytest.raises(ValueError):
        HistogramObserver('foo', quantiles=(.6, .5))
