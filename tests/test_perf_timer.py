from functools import partial
from unittest.mock import Mock

import pytest

from perf_timer import PerfTimer, ThreadPerfTimer, \
    AverageObserver, StdDevObserver, HistogramObserver, \
    measure_overhead


def test_perf_timer():
    # time_fn is called on enter and exit of each with block
    time_fn = Mock(side_effect=[10, 15,
                                15, 25])
    log_fn = Mock()
    timer = PerfTimer('foo', time_fn=time_fn, log_fn=log_fn)

    for _ in range(2):
        with timer:
            pass

    assert timer._count == 2
    assert timer._duration == 15
    assert timer._max == 10
    del timer
    assert 'in 2 runs' in log_fn.call_args_list[0][0][0]


def test_perf_timer_decorator():
    time_fn = Mock(side_effect=[10, 15,
                                15, 25])
    timer = PerfTimer('foo', time_fn=time_fn)

    @timer
    def foo():
        pass

    for _ in range(2):
        foo()

    assert timer._count == 2
    assert timer._duration == 15
    assert timer._max == 10
    del timer


def test_perf_timer_one_run():
    log_fn = Mock()
    timer = PerfTimer('foo', log_fn=log_fn)

    with timer:
        pass

    assert timer._count == 1
    del timer
    assert ' in ' not in log_fn.call_args_list[0][0][0]


def test_perf_timer_non_reentrant():
    timer = PerfTimer('foo')
    with timer:
        with pytest.raises(RuntimeError):
            with timer:
                pass


def test_thread_perf_timer_lock():
    lock_count = 0

    class MockLock:
        def __enter__(self):
            pass
        def __exit__(self, *args):
            nonlocal lock_count
            lock_count += 1

    timer = ThreadPerfTimer('foo')
    timer._lock = MockLock()

    with timer:
        pass
    with timer:
        pass
    del timer

    assert lock_count == 2


def test_perf_timer_type():
    # since metaclass is used, ensure type is cached
    assert type(PerfTimer('foo')) is type(PerfTimer('bar'))


def test_measure_overhead():
    assert measure_overhead(partial(PerfTimer, observer=AverageObserver)) < \
           measure_overhead(partial(PerfTimer, observer=StdDevObserver)) < \
           measure_overhead(partial(PerfTimer, observer=HistogramObserver))
