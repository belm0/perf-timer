"""Measure and report overhead of the perf-timer variants.

The typical observation duration is reported for each case.

Synopsis:
    $ python overhead.py
    compare observers:
        PerfTimer(observer=AverageObserver):         1.44 µs
        PerfTimer(observer=StdDevObserver):          1.75 µs
        PerfTimer(observer=HistogramObserver):       5.91 µs

    compare types:
        PerfTimer(observer=AverageObserver):         1.43 µs
        ThreadPerfTimer(observer=AverageObserver):   9.21 µs
        TrioPerfTimer(observer=AverageObserver):     4.36 µs
"""

from functools import partial

import trio

from perf_timer import (PerfTimer, ThreadPerfTimer, TrioPerfTimer,
                        AverageObserver, StdDevObserver, HistogramObserver,
                        measure_overhead)
from perf_timer._impl import _format_duration


async def main():
    _format = partial(_format_duration, precision=2)
    print('compare observers:')
    timer_type = PerfTimer
    for observer in (AverageObserver, StdDevObserver, HistogramObserver):
        duration = measure_overhead(partial(timer_type, observer=observer))
        item = f'{timer_type.__name__}(observer={observer.__name__}):'
        print(f'    {item:45s}{_format(duration)}'
              f'{"  (default)" if observer is StdDevObserver else ""}')

    print()
    print('compare types:')
    observer = AverageObserver
    for timer_type in (PerfTimer, ThreadPerfTimer, TrioPerfTimer):
        duration = measure_overhead(partial(timer_type, observer=observer))
        item = f'{timer_type.__name__}(observer={observer.__name__}):'
        print(f'    {item:45s}{_format(duration)}')


if __name__ == '__main__':
    trio.run(main)
