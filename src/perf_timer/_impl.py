import atexit
import functools
import math
import timeit
from weakref import WeakSet

from contextvars import ContextVar
from inspect import iscoroutinefunction
from multiprocessing import Lock
from time import perf_counter
try:
    from time import thread_time
except ImportError:
    # thread_time is not available in some OS X environments
    thread_time = None

from perf_timer._histogram import ApproximateHistogram

_start_time_by_instance = ContextVar('start_time', default={})
_timers = WeakSet()


def _format_duration(duration, precision=3, delimiter=' '):
    """Returns human readable duration.

    >>> _format_duration(.0507)
    '50.7 ms'
    """
    units = (('s', 1), ('ms', 1e3), ('µs', 1e6), ('ns', 1e9))
    i = len(units) - 1
    if duration > 0:
        i = min(-int(math.floor(math.log10(duration)) // 3), i)
    symbol, scale = units[i]
    # constant precision, keeping trailing zeros but don't end in decimal point
    value = f'{duration * scale:#.{precision}g}'.rstrip('.')
    return f'{value}{delimiter}{symbol}'


class _BetterContextDecorator:
    """
    Equivalent to contextlib.ContextDecorator but supports decorating async
    functions.  The context manager itself it still non-async.
    """

    def _recreate_cm(self):
        return self

    def __call__(self, func):
        if iscoroutinefunction(func):
            @functools.wraps(func)
            async def inner(*args, **kwargs):
                with self._recreate_cm():  # pylint: disable=not-context-manager
                    return await func(*args, **kwargs)
        else:
            @functools.wraps(func)
            def inner(*args, **kwargs):
                with self._recreate_cm():  # pylint: disable=not-context-manager
                    return func(*args, **kwargs)
        return inner


class _PerfTimerBase(_BetterContextDecorator):

    # NOTE: `observer` is handled by the metaclass, and `quantiles` is handled
    #   by HistogramObserver.  They're included here only for documentation.
    def __init__(self, name, *, time_fn=perf_counter, log_fn=print,
                 observer=None, quantiles=None):
        """
        :param name: string used to annotate the timer output
        :param time_fn: optional function which returns the current time.
            (A None value will raise NotImplementedError.)
        :param log_fn: optional function which records the output string
        :param observer: mixin class to observe and summarize samples
            (AverageObserver|StdDevObserver|HistogramObserver, default StdDevObserver)
        :param quantiles: for HistogramObserver, a sequence of quantiles to report.
            Values must be in range [0..1] and monotonically increasing.
            (default: (0.5, 0.9, 0.98))
        """
        if not time_fn:
            raise NotImplementedError
        self.name = name
        self._time_fn = time_fn
        self._log_fn = log_fn
        self._startTimeByInstance = _start_time_by_instance.get()
        self._reported = False
        _timers.add(self)

    def _observe(self, duration):
        """called for each observed duration"""

    def _report(self):
        """called to report observation results"""

    def _report_once(self):
        if not self._reported:
            self._report()
            self._reported = True

    def __del__(self):
        self._report_once()

    def __enter__(self):
        if self in self._startTimeByInstance:
            raise RuntimeError('PerfTimer is not re-entrant')
        self._startTimeByInstance[self] = self._time_fn()

    def __exit__(self, exc_type, exc_value, traceback):
        current_time = self._time_fn()
        start_time = self._startTimeByInstance.pop(self)
        if exc_type is None:
            duration = current_time - start_time
            self._observe(duration)


class AverageObserver(_PerfTimerBase):
    """Mixin which outputs mean and max

    output synopsis:
        timer "foo": avg 11.9 ms, max 12.8 ms in 10 runs
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._count = 0
        self._sum = 0
        self._max = -math.inf

    def _observe(self, duration):
        self._count += 1
        self._sum += duration
        self._max = max(self._max, duration)

    def _report(self):
        if self._count > 1:
            mean = self._sum / self._count
            self._log_fn(f'timer "{self.name}": '
                         f'avg {_format_duration(mean)}, '
                         f'max {_format_duration(self._max)} '
                         f'in {self._count} runs')
        elif self._count > 0:
            self._log_fn(f'timer "{self.name}": '
                         f'{_format_duration(self._sum)}')


class StdDevObserver(_PerfTimerBase):
    """Mixin which outputs mean, stddev, and max

    15 - 20% slower than _AverageObserver.
    https://en.wikipedia.org/wiki/Algorithms_for_calculating_variance#Welford's_online_algorithm

    output synopsis:
        timer "foo": avg 11.9 ms ± 961 µs, max 12.8 ms in 10 runs
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._count = 0
        self._mean = 0
        self._m2 = 0
        self._max = -math.inf

    def _observe(self, duration):
        self._count += 1
        delta = duration - self._mean
        self._mean += delta / self._count
        self._m2 += delta * (duration - self._mean)
        self._max = max(self._max, duration)

    def _report(self):
        if self._count > 1:
            std = math.sqrt(self._m2 / self._count)
            self._log_fn(f'timer "{self.name}": '
                         f'avg {_format_duration(self._mean)} '
                         f'± {_format_duration(std)}, '
                         f'max {_format_duration(self._max)} '
                         f'in {self._count} runs')
        elif self._count > 0:
            self._log_fn(f'timer "{self.name}": '
                         f'{_format_duration(self._mean)}')


class HistogramObserver(_PerfTimerBase):
    """Mixin which outputs mean, standard deviation, and percentiles

    output synopsis:
        timer "foo": avg 11.9ms ± 961µs, 50% ≤ 12.6ms, 90% ≤ 12.7ms in 10 runs
    """

    def __init__(self, *args, quantiles=(.5, .9, .98), max_bins=64, **kwargs):
        super().__init__(*args, **kwargs)
        if not all(0 <= x <= 1 for x in quantiles):
            raise ValueError('quantile values must be in the range [0, 1]')
        if not all(a < b for a, b in zip(quantiles, quantiles[1:])):
            raise ValueError('quantiles must be monotonically increasing')
        self._quantiles = quantiles
        self._hist = ApproximateHistogram(max_bins=max_bins)

    def _observe(self, duration):
        self._hist.add(duration)

    def _report(self):
        if self._hist.count > 1:
            _format = functools.partial(_format_duration, delimiter='')
            hist_quantiles = self._hist.quantile(self._quantiles)
            percentiles = [f"{pct * 100:.0f}% ≤ {_format(val)}"
                           for pct, val in zip(self._quantiles, hist_quantiles)]
            self._log_fn(f'timer "{self.name}": '
                         f'avg {_format(self._hist.mean())} '
                         f'± {_format(self._hist.std())}, '
                         f'{", ".join(percentiles)} '
                         f'in {self._hist.count} runs')
        elif self._hist.count > 0:
            self._log_fn(f'timer "{self.name}": '
                         f'{_format_duration(self._hist.sum())}')


class _ObservationLock(_PerfTimerBase):
    """Mixin which wraps _observe() in a lock"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = Lock()

    def _observe(self, duration):
        with self._lock:
            super()._observe(duration)


class _MixinMeta(type):
    """Metaclass which injects an observer mixin based on constructor arg"""

    @staticmethod
    @functools.lru_cache(maxsize=None)
    def _get_cls(observer, cls):
        # NOTE: bases ordering allows _ObservationLock to override the observer
        return type(cls.__name__, (cls, observer), {})

    def __call__(cls, *args, observer=StdDevObserver, **kwargs):
        out_cls = _MixinMeta._get_cls(observer, cls)
        return type.__call__(out_cls, *args, **kwargs)


class PerfTimer(_PerfTimerBase, metaclass=_MixinMeta):
    """Performance timer

    Use to measure performance of a block of code.  The object will log
    performance stats when it is destroyed.

        perf_timer = PerfTimer('my code')
        ...
        def foo():
            ...
            with perf_timer:
                # code under test
            ...

    It can also be used as a function decorator:

        @PerfTimer('my function')
        def foo():
            ...

    This implementation is not thread safe.  For a multi-threaded scenario,
    use `ThreadPerfTimer`.
    """


class ThreadPerfTimer(_ObservationLock, PerfTimer):
    """Variant of PerfTimer which measures CPU time of the current thread

    (Implemented with time.thread_time by default, which may not be available
    in some OS X environments.)
    """

    def __init__(self, name, time_fn=thread_time, **kwargs):
        super().__init__(name, time_fn=time_fn, **kwargs)


def measure_overhead(timer_factory):
    """Measure the overhead of a timer instance from the given factory.

    :param timer_factory: callable which returns a new timer instance
    :return: the average duration of one observation, in seconds
    """
    timeit_timer = timeit.Timer(
        globals={'timer': timer_factory('foo', log_fn=lambda x: x)},
        stmt='with timer: pass'
    )
    n, duration = timeit_timer.autorange()
    min_duration = min([duration] + timeit_timer.repeat(number=n))
    return min_duration / n


@atexit.register
def _atexit():
    while _timers:
        _timers.pop()._report_once()
