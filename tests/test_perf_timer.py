from functools import partial
from unittest.mock import Mock, patch

import pytest

from perf_timer import PerfTimer, ThreadPerfTimer, \
    AverageObserver, StdDevObserver, HistogramObserver, \
    measure_overhead
from perf_timer import _impl


class _Containing:
    """Argument matcher for Mock"""

    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return self.value in other

    def __repr__(self):
        return f'{self.__class__.__name__}("{self.value}")'


class _NotContaining:
    """Argument matcher for Mock"""

    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return self.value not in other

    def __repr__(self):
        return f'{self.__class__.__name__}("{self.value}")'


def test_perf_timer():
    # time_fn is called on enter and exit of each with block
    time_fn = Mock(side_effect=[10, 15,
                                15, 25])
    log_fn = Mock()
    timer = PerfTimer('foo', observer=AverageObserver, time_fn=time_fn,
                      log_fn=log_fn)

    for _ in range(2):
        with timer:
            pass

    assert timer._count == 2
    assert timer._sum == 15
    assert timer._max == 10
    timer._report()
    log_fn.assert_called_once_with(_Containing('in 2 runs'))


def test_perf_timer_decorator():
    time_fn = Mock(side_effect=[10, 15,
                                15, 25])
    log_fn = Mock()

    @PerfTimer('foo', time_fn=time_fn, log_fn=log_fn)
    def foo():
        pass

    for _ in range(2):
        foo()

    del foo
    log_fn.assert_called_once_with(_Containing('in 2 runs'))


def test_perf_timer_one_run():
    log_fn = Mock()
    timer = PerfTimer('foo', log_fn=log_fn)

    with timer:
        pass

    assert timer._count == 1
    timer._report()
    log_fn.assert_called_once_with(_NotContaining(' in '))


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
    timer._report()

    assert lock_count == 2


def test_perf_timer_type():
    # since metaclass is used, ensure type is cached
    assert type(PerfTimer('foo')) is type(PerfTimer('bar'))


def test_perf_timer_not_implemented():
    with pytest.raises(NotImplementedError):
        PerfTimer('foo', time_fn=None)


@patch.object(PerfTimer, '_report_once')
def test_perf_timer_atexit_and_del(_report_once):
    # atexit and del each cause 1 call to _report_once()
    timer = PerfTimer('foo')
    _impl._atexit()
    del timer
    assert _report_once.call_count == 2


@patch.object(PerfTimer, '_report_once')
def test_perf_timer_atexit_is_weak(_report_once):
    # atexit doesn't trigger _report_once() if object already finalized
    timer = PerfTimer('foo')
    del timer
    _impl._atexit()
    assert _report_once.call_count == 1


def test_perf_timer_report():
    # multiple calls to _report_once() cause only one report
    log_fn = Mock()
    timer = PerfTimer('foo', log_fn=log_fn)
    with timer:
        pass
    timer._report_once()
    timer._report_once()
    log_fn.assert_called_once()


def test_measure_overhead():
    assert measure_overhead(partial(PerfTimer, observer=AverageObserver)) < \
           measure_overhead(partial(PerfTimer, observer=StdDevObserver)) < \
           measure_overhead(partial(PerfTimer, observer=HistogramObserver))
