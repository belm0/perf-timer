import functools
import math
from _contextvars import ContextVar
from inspect import iscoroutinefunction
from multiprocessing import Lock
from time import perf_counter, thread_time

_start_time_by_instance = ContextVar('start_time', default={})


def _format_duration(duration, precision=3):
    """Returns human readable duration.

    >>> _format_duration(.0507)
    '50.7 ms'
    """
    units = (('s', 1), ('ms', 1e3), ('µs', 1e6), ('ns', 1e9))
    i = len(units) - 1
    if duration > 0:
        i = min(-int(math.floor(math.log10(duration)) // 3), i)
    symbol, scale = units[i]
    return f'{duration * scale:.{precision}g} {symbol}'


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

    def __init__(self, name, *, time_fn=perf_counter, log_fn=print):
        """
        :param name: string used to annotate the timer output
        :param time_fn: optional function which returns the current time
        :param log_fn: optional function which records the output string
        """
        self.name = name
        self._time_fn = time_fn
        self._log_fn = log_fn
        self._startTimeByInstance = _start_time_by_instance.get()

    def _observe(self, duration):
        pass

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


class _AverageObserver(_PerfTimerBase):
    """Mixin which outputs mean and max"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._count = 0
        self._duration = 0
        self._max = -math.inf

    def _observe(self, duration):
        self._count += 1
        self._duration += duration
        self._max = max(self._max, duration)

    def __del__(self):
        if self._count > 1:
            mean = self._duration / self._count
            self._log_fn(f'timer "{self.name}": '
                         f'average {_format_duration(mean)}, '
                         f'max {_format_duration(self._max)} '
                         f'in {self._count} runs')
        elif self._count > 0:
            self._log_fn(f'timer "{self.name}": '
                         f'{_format_duration(self._duration)} ')


class _ObservationLock(_PerfTimerBase):
    """Mixin which wraps _observe() in a lock"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = Lock()

    def _observe(self, duration):
        with self._lock:
            super()._observe(duration)


class PerfTimer(_AverageObserver, _PerfTimerBase):
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


class ThreadPerfTimer(_ObservationLock, _AverageObserver, _PerfTimerBase):
    """Variant of PerfTimer which measures CPU time of the current thread"""

    def __init__(self, name, time_fn=thread_time, **kwargs):
        super().__init__(name, time_fn=time_fn, **kwargs)
