[![Build status](https://img.shields.io/circleci/build/github/belm0/perf-timer)](https://circleci.com/gh/belm0/perf-timer)
[![Package version](https://img.shields.io/pypi/v/perf-timer.svg)](https://pypi.org/project/perf-timer)
[![Supported Python versions](https://img.shields.io/pypi/pyversions/perf-timer.svg)](https://pypi.org/project/perf-timer)

# PerfTimer

An indispensable performance timer for Python

## Background
### Taxonomy
Three general tools should be employed to
understand the CPU performance of your Python code:
  1. **sampling profiler** - measures the relative
  distribution of time spent among function or
  lines of code during a program session.  Limited by
  sampling resolution.  Does not provide call counts,
  and results cannot be easily compared between sessions.
  2. **microbenchmark timer** (timeit) - accurately
  times a contrived code snippet by running it repeatedly
  3. **instrumenting timer** - accurately times a specific
  function or section of your code during a program
  session

_PerfTimer_ is a humble instance of #3.  It's the easiest
way (least amount of fuss and effort) to get insight into
call count and execution time of a function or piece
of code during a real session of your program.

Use cases include:
  * check the effects of algorithm tweaks, new implementations, etc.
  * confirm the performance of a library you are considering under
  actual use by your app (as opposed to upstream's artificial
  benchmarks)
  * measure CPU overhead of networking or other asynchronous I/O
  (currently supported: OS threads, Trio async/await)

### Yet another code timer?

It seems everyone has tried their hand at writing one of these timer
utilities.  Implementations can be found in public repos, snippets, and PyPi—
there's even a Python feature request.  That's not counting all the
proprietary and one-off instances.

Features of this library:

  * **flexible** - use as a context manager or function decorator;
  pluggable logging, timer, and observer functions
  * **low overhead** (typically a few microseconds) - can be
  employed in hot code paths or even enabled on production deployments
  * **async/await support** (Trio only) - first of its kind!  Periods when a task is
  is sleeping, blocked by I/O, etc. will not be counted.
  * **percentile durations** - e.g. report the median and 90th percentile
  execution time of the instrumented code.  Implemented with a bounded-memory,
  streaming histogram.

## Usage

Typical usage is to create a `PerfTimer` instance at the global
scope, so that aggregate execution time is reported at program termination:

```python
from perf_timer import PerfTimer

_timer = PerfTimer('process thumbnail')

def get_thumbnail_image(path):
    img = cache.get_thumbnail(path)
    if not thumbnail:
        img = read_image(path)
        with _timer:
            img.decode()
            img.resize(THUMBNAIL_SIZE)
        cache.set_thumbnail(img)
    return img
```

When the program exits, assuming `get_thumbnail_image` was called
several times, execution stats will be reported to stdout as
follows:

```
timer "process thumbnail": avg 73.1 µs ± 18.0 µs, max 320.5 µs in 292 runs
```

A custom logging function may be passed to the `PerfTimer`
constructor:

```python
import logging

_logger = logging.getLogger()
_timer = PerfTimer('process thumbnail', log_fn=_logger.debug)
```

By default `PerfTimer` will track the average, standard deviation, and maximum
of observed values.  Other available observers include `HistogramObserver`,
which reports (customizable) percentiles:

```python
import random
import time
from perf_timer import PerfTimer, HistogramObserver

_timer = PerfTimer('test', observer=HistogramObserver, quantiles=(.5, .9))
for _ in range(50):
    with _timer:
        time.sleep(random.expovariate(1/.1))

del _timer
```
output:
```
timer "test": avg 117ms ± 128ms, 50% ≤ 81.9ms, 90% ≤ 243ms in 50 runs
```

To minimize overhead, `PerfTimer` assumes single-thread access.  Use
`ThreadPerfTimer` in multi-thread scenarios:

```python
from perf_timer import ThreadPerfTimer

_timer = ThreadPerfTimer('process thumbnail')
```

To instrument an entire function or class method, use `PerfTimer`
as a decorator:

```python
@PerfTimer('get thumbnail')
def get_thumbnail_image(path):
    ...
```

In this example however, timing the entire function will include file
I/O time since `PerfTimer` measures wall time by default.  For programs
which happen to do I/O via the Trio async/await library, you
can use `TrioPerfTimer` which measures time only when the current task
is executing:

```python
from perf_timer import TrioPerfTimer

@TrioPerfTimer('get thumbnail')
async def get_thumbnail_image(path):
    img = cache.get_thumbnail(path)
    if not thumbnail:
        img = await read_image(path)
        img.decode()
        img.resize(THUMBNAIL_SIZE)
        cache.set_thumbnail(img)
    return img
```

(Open challenge: support other async/await libraries)

### trio_perf_counter()

This module also provides the `trio_perf_counter()` primitive.
Following the semantics of the various performance counters in Python's `time`
module, `trio_perf_counter()` provides high resolution measurement of a Trio
task's execution time, excluding periods where it's sleeping or blocked on I/O.
(`TrioPerfTimer` uses this internally.)

```python
from perf_timer import trio_perf_counter

async def get_remote_object():
    t0 = trio_perf_counter()
    msg = await read_network_bytes()
    obj = parse(msg)
    print('task CPU usage (seconds):', trio_perf_counter() - t0)
    return obj
```

## Installation

```shell
pip install perf-timer
```

## Measurement overhead

Measurement overhead is important.  The smaller the timer's overhead, the
less it interferes with the normal timing of your program, and the tighter
the code loop it can be applied to.

The values below represent the typical overhead of one observation, as measured
on ye old laptop (2014 MacBook Air 11 1.7GHz i7).

```
$ pip install -r test-requirements.txt
$ python benchmarks/overhead.py
compare observers:
    PerfTimer(observer=AverageObserver):         1.5 µs
    PerfTimer(observer=StdDevObserver):          1.8 µs  (default)
    PerfTimer(observer=HistogramObserver):       6.0 µs

compare types:
    PerfTimer(observer=StdDevObserver):          1.8 µs
    ThreadPerfTimer(observer=StdDevObserver):    9.8 µs
    TrioPerfTimer(observer=StdDevObserver):      4.8 µs
```

## TODO
  * features
    * faster HistogramObserver
    * more async/await support: asyncio, curio, etc.
      * [asyncio hint which no longer works](https://stackoverflow.com/revisions/34827291/3)
  * project infrastructure
    * code coverage integration
    * publish docs
    * type annotations and check
