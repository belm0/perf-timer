import random
from unittest.mock import Mock

import numpy

from perf_timer import AverageObserver, StdDevObserver, HistogramObserver


def test_average_observer():
    name = 'foo'
    n = 100
    log_fn = Mock()
    observer = AverageObserver(name, log_fn=log_fn)
    points = []
    for _ in range(n):
        x = random.expovariate(1/5)  # expected average is 5s
        observer._observe(x)
        points.append(x)
    del observer
    # timer "foo": avg 11.9 ms, max 12.8 ms in 10 runs
    log_fn.assert_called_once_with(
        f'timer "{name}": '
        f'avg {sum(points)/n:.2f} s, '
        f'max {max(points):.1f} s '
        f'in {n} runs')


def test_std_dev_observer():
    name = 'foo'
    n = 100
    log_fn = Mock()
    observer = StdDevObserver(name, log_fn=log_fn)
    points = []
    for _ in range(n):
        x = random.expovariate(1/5)  # expected average is 5s
        observer._observe(x)
        points.append(x)
    del observer
    # timer "foo": avg 11.9 ms ± 961 µs, max 12.8 ms in 10 runs
    log_fn.assert_called_once_with(
        f'timer "{name}": '
        f'avg {sum(points)/n:.2f} s ± {numpy.std(points):.2f} s, '
        f'max {max(points):.1f} s '
        f'in {n} runs')


def test_histogram_observer():
    name = 'foo'
    # cheating to allow a simple string compare:
    #   * requested quantiles and distribution are such that output precision is fixed
    #   * since n < max bins of the approximate histogram, quantile output will be exact
    quantiles = (.4, .5, .6)
    n = 50
    log_fn = Mock()
    observer = HistogramObserver(name, quantiles=quantiles, log_fn=log_fn)
    points = []
    for _ in range(n):
        x = random.expovariate(1/5)  # expected average is 5s
        observer._observe(x)
        points.append(x)
    del observer
    q_expected = numpy.quantile(points, quantiles)
    # timer "foo": avg 11.9ms ± 961µs, 50% ≤ 12.6ms, 90% ≤ 12.7ms in 10 runs
    log_fn.assert_called_once_with(
        f'timer "{name}": '
        f'avg {sum(points)/n:.2f}s ± {numpy.std(points):.2f}s, '
        f'{", ".join(f"{q:.0%} ≤ {out:.2f}s" for q, out in zip(quantiles, q_expected))} '
        f'in {n} runs')
