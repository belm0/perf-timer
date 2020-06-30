"""Measure and report overhead of the perf-timer variants.

The typical observation duration is reported for each case.

Synopsis:
    $ python overhead.py
    compare observers:
        PerfTimer(observer=AverageObserver):         1.5 µs
        PerfTimer(observer=StdDevObserver):          1.8 µs  (default)
        PerfTimer(observer=HistogramObserver):       6.0 µs

    compare types:
        PerfTimer(observer=StdDevObserver):          1.8 µs
        ThreadPerfTimer(observer=StdDevObserver):    9.8 µs
        TrioPerfTimer(observer=StdDevObserver):      4.8 µs
"""

from functools import partial

import trio

from perf_timer import (PerfTimer, ThreadPerfTimer, TrioPerfTimer,
                        AverageObserver, StdDevObserver, HistogramObserver,
                        measure_overhead)
from perf_timer._impl import _format_duration


async def main():
    _format = partial(_format_duration, precision=2)
    default_observer = StdDevObserver
    print('compare observers:')
    timer_type = PerfTimer
    for observer in (AverageObserver, StdDevObserver, HistogramObserver):
        duration = measure_overhead(partial(timer_type, observer=observer))
        item = f'{timer_type.__name__}(observer={observer.__name__}):'
        print(f'    {item:45s}{_format(duration)}'
              f'{"  (default)" if observer is default_observer else ""}')

    print()
    print('compare types:')
    observer = default_observer
    for timer_type in (PerfTimer, ThreadPerfTimer, TrioPerfTimer):
        duration = measure_overhead(partial(timer_type, observer=observer))
        item = f'{timer_type.__name__}(observer={observer.__name__}):'
        print(f'    {item:45s}{_format(duration)}')


if __name__ == '__main__':
    trio.run(main)
