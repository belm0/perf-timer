# PerfTimer

An indispensable performance timer for Python

## Background
### Taxonomy
Three general tools should be employed to to
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
call count and average execution time of a function or piece
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
utilities.  Implementations can be found in public repos and snippets, PyPi,
and there's even a Python feature request.  That's not counting all the
proprietary and one-off instances.

Features of this library:

  * **flexible** - use as a context manager or function decorator;
  pluggable logging and timer functions
  * **low overhead** (typically a few microseconds) - it means you can have
  instrumentation enabled on production code
  * **async/await support** (Trio only) - first of it's kind!  Periods when a task is
  is sleeping, blocked by I/O, etc. will not be counted.
  * (coming soon) **percentile durations** - e.g. find median and 90 percentile
  execution time of the instrumented code.  Implementated with a bounded-memory,
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
timer "process thumbnail": average 73.1 usec, max 320.5 usec in 292 runs
```

A custom logging function may be passed to the `PerfTimer`
constructor:

```python
import logging

_logger = logging.getLogger()
_timer = PerfTimer('process thumbnail', log_fn=_logger.debug)
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
module, trio_perf_counter() provides high resolution timing of a Trio task's
execution time, excluding periods where it's sleeping or blocked on I/O.
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

## TODO
  * features
    * HistogramObserver (bounded memory and fast)
    * more async/await support: asyncio, curio, etc.
      * [asyncio hint which no longer works](https://stackoverflow.com/revisions/34827291/3)
  * project infrastructure
    * continuous integration
    * publish docs
    * overhead benchmark
    * type annotations and check
