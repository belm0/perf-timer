from collections import defaultdict
from dataclasses import dataclass, field
from time import perf_counter
from typing import Set

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


@dataclass
class _HierarchyTimeInfo:
    hierarchy_tasks: Set[trio_lowlevel.Task] = field(default_factory=set)
    deschedule_start: float = 0
    elapsed_descheduled: float = 0


class _HierarchyDescheduledTimeInstrument(trio.abc.Instrument):
    """Trio instrument tracking elapsed descheduled time of given task and children"""

    def __init__(self, time_fn=perf_counter):
        self._time_fn = time_fn
        self._info_by_root_task = defaultdict(_HierarchyTimeInfo)

    def task_spawned(self, task: trio_lowlevel.Task):
        # TODO: Maintain a global tree rather than a set per root, avoiding O(N)
        #  on task spawn and exit.  (But then task steps are O(N)...)
        if task.parent_nursery:
            parent_task = task.parent_nursery.parent_task
            for info in self._info_by_root_task.values():
                if parent_task in info.hierarchy_tasks:
                    info.hierarchy_tasks.add(task)

    def task_exited(self, task: trio_lowlevel.Task):
        for info in self._info_by_root_task.values():
            info.hierarchy_tasks.discard(task)

        root_info = self._info_by_root_task.pop(task, None)
        if root_info:
            assert not root_info.hierarchy_tasks
            if not self._info_by_root_task:
                trio_lowlevel.remove_instrument(self)

    def after_task_step(self, task: trio_lowlevel.Task):
        for info in self._info_by_root_task.values():
            if task in info.hierarchy_tasks:
                info.descheduled_start = self._time_fn()

    def before_task_step(self, task: trio_lowlevel.Task):
        for info in self._info_by_root_task.values():
            if task in info.hierarchy_tasks:
                info.elapsed_descheduled += self._time_fn() - info.descheduled_start

    def get_elapsed_descheduled_time(self, task: trio_lowlevel.Task):
        info = self._info_by_root_task[task]
        hierarchy_tasks = info.hierarchy_tasks

        if not hierarchy_tasks:  # newly tracked root
            hierarchy_tasks.add(task)
            # populate existing child tasks of the root
            nurseries = set(task.child_nurseries)
            while nurseries:
                nursery: trio.Nursery = nurseries.pop()
                for child_task in nursery.child_tasks:
                    hierarchy_tasks.add(child_task)
                    nurseries.update(child_task.child_nurseries)

        return info.elapsed_descheduled


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
