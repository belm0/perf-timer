from collections import defaultdict
from dataclasses import dataclass
from time import perf_counter

import trio
try:
    import trio.lowlevel as trio_lowlevel
except ImportError:
    import trio.hazmat as trio_lowlevel

from ._impl import PerfTimer


@dataclass
class _TimeInfo:
    deschedule_start: float = 0
    elapsed_descheduled: float = 0


class _DescheduledTimeInstrument(trio.abc.Instrument):
    """Trio instrument tracking elapsed descheduled time of selected tasks"""

    def __init__(self, time_fn=perf_counter):
        self._time_fn = time_fn
        self._info_by_task = defaultdict(_TimeInfo)

    def after_task_step(self, task):
        info = self._info_by_task.get(task)
        if info:
            info.deschedule_start = self._time_fn()

    def before_task_step(self, task):
        info = self._info_by_task.get(task)
        if info:
            info.elapsed_descheduled += self._time_fn() - info.deschedule_start

    def task_exited(self, task):
        # unregister instrument if there are no more traced tasks
        if self._info_by_task.pop(task, None) and not self._info_by_task:
            trio_lowlevel.remove_instrument(self)

    def get_elapsed_descheduled_time(self, task):
        """
        Return elapsed descheduled time in seconds since the given task was
        first referenced by this method.  The initial reference always returns 0.
        """
        return self._info_by_task[task].elapsed_descheduled


_instrument = _DescheduledTimeInstrument()


def trio_perf_counter():
    """Trio task-local equivalent of time.perf_counter().

    For the current Trio task, return the value (in fractional seconds) of a
    performance counter, i.e. a clock with the highest available resolution to
    measure a short duration.  It includes time elapsed during time.sleep,
    but not trio.sleep.  The reference point of the returned value is
    undefined, so that only the difference between the results of consecutive
    calls is valid.

    Performance note: calling this function installs instrumentation on the
    Trio scheduler which may affect application performance.  The
    instrumentation is automatically removed when the corresponding tasks
    have exited.
    """
    trio_lowlevel.add_instrument(_instrument)
    task = trio_lowlevel.current_task()
    return perf_counter() - _instrument.get_elapsed_descheduled_time(task)


class _HierarchyDescheduledTimeInstrument(trio.abc.Instrument):
    """Trio instrument tracking elapsed descheduled time of given task and children

    The implementation is similar to _DescheduledTimeInstrument, except on task
    steps we walk up the task tree to find tracked tasks.  This probably has
    significant overhead since it must be done even for untracked hierarchies.
    """

    def __init__(self, time_fn=perf_counter):
        self._time_fn = time_fn
        self._info_by_root_task = defaultdict(_TimeInfo)

    def _parents_info(self, task: trio_lowlevel.Task, time_fn):
        t = 0
        while True:
            info = self._info_by_root_task.get(task)
            if info:
                t = t or time_fn()
                yield info, t
            parent_nursery = task.parent_nursery
            if parent_nursery:
                task = parent_nursery.parent_task
            else:
                break

    def task_exited(self, task: trio_lowlevel.Task):
        if self._info_by_root_task.pop(task, None) and not self._info_by_root_task:
            trio_lowlevel.remove_instrument(self)

    def after_task_step(self, task: trio_lowlevel.Task):
        # TODO: maintain global "tracked tasks" to provide a fast path?
        for info, t in self._parents_info(task, self._time_fn):
            info.deschedule_start = t

    def before_task_step(self, task: trio_lowlevel.Task):
        for info, t in self._parents_info(task, self._time_fn):
            info.elapsed_descheduled += t - info.deschedule_start

    def get_elapsed_descheduled_time(self, task: trio_lowlevel.Task):
        return self._info_by_root_task[task].elapsed_descheduled


_hierarchy_instrument = _HierarchyDescheduledTimeInstrument()


def trio_hierarchy_perf_counter():
    trio_lowlevel.add_instrument(_hierarchy_instrument)
    task = trio_lowlevel.current_task()
    return perf_counter() - _hierarchy_instrument.get_elapsed_descheduled_time(task)


class TrioPerfTimer(PerfTimer):
    """Variant of PerfTimer which measures Trio task time

    Use to measure performance of the current Trio tasks within a block
    of code.  The object will log performance stats when it is destroyed.

    Measured time includes time.sleep, but not trio.sleep or other async
    blocking (due to I/O, child tasks, etc).

        perf_timer = PerfTimer('my code')
        ...
        async def foo():
            ...
            with perf_timer:
                # code under test
                await trio.sleep(1)
                ...

    It can also be used as a function decorator:

        @PerfTimer('my function')
        async def foo():
            ...
    """

    def __init__(self, name, time_fn=trio_perf_counter, **kwargs):
        super().__init__(name, time_fn=time_fn, **kwargs)


# TODO: The shorter trio_perf_counter and TrioPerfTimer names should include
#  hierarchy, and non-hierarchy variants relegated to longer names.
class TrioHierarchyPerfTimer(TrioPerfTimer):
    def __init__(self, name, time_fn=trio_hierarchy_perf_counter, **kwargs):
        super().__init__(name, time_fn=time_fn, **kwargs)
