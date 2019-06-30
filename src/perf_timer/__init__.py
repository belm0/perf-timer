from ._impl import PerfTimer, ThreadPerfTimer
try:
    from ._trio import trio_perf_counter, TrioPerfTimer
except ImportError:
    pass
from ._version import __version__
