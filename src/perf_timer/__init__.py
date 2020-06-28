from ._impl import (PerfTimer, ThreadPerfTimer, AverageObserver,
                    StdDevObserver, HistogramObserver, measure_overhead)
try:
    from ._trio import trio_perf_counter, TrioPerfTimer
except ImportError:
    pass
from ._version import __version__

def _metadata_fix():
    # don't do this for Sphinx case because it breaks "bysource" member ordering
    import sys  # pylint: disable=import-outside-toplevel
    if 'sphinx' in sys.modules:
        return

    for name, value in globals().items():
        if not name.startswith('_'):
            value.__module__ = __name__

_metadata_fix()
