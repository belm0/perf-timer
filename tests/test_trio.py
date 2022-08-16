import time
from unittest.mock import Mock

import pytest
import trio
try:
    import trio.lowlevel as trio_lowlevel
except ImportError:
    import trio.hazmat as trio_lowlevel

from perf_timer import trio_perf_counter, _trio, TrioPerfTimer, AverageObserver


async def test_descheduled_time_instrument():
    time_fn = Mock(side_effect=[5, 10, 10, 20])
    instrument = _trio._DescheduledTimeInstrument(time_fn=time_fn)
    trio_lowlevel.add_instrument(instrument)

    # Only tasks referenced by get_elapsed_descheduled_time() will be tracked,
    # so instrument is not tracking the current task.
    await trio.sleep(0)
    assert not time_fn.called

    async with trio.open_nursery() as nursery:
        @nursery.start_soon
        async def _tracked_child():
            # calling get_elapsed_descheduled_time() initiates tracking
            task = trio_lowlevel.current_task()
            assert instrument.get_elapsed_descheduled_time(task) == 0
            await trio.sleep(0)
            assert instrument.get_elapsed_descheduled_time(task) == 10 - 5
            await trio.sleep(0)
            assert instrument.get_elapsed_descheduled_time(task) == 20 - 5
            # time function is called twice for each deschedule
            assert time_fn.call_count == 4

    # the sole tracked task exited, so instrument is automatically removed
    with pytest.raises(KeyError):
        trio_lowlevel.remove_instrument(instrument)


async def test_descheduled_time_instrument_exclude_children():
    time_fn = Mock(side_effect=[5, 10])
    instrument = _trio._DescheduledTimeInstrument(time_fn=time_fn)
    trio_lowlevel.add_instrument(instrument)

    task = trio_lowlevel.current_task()
    assert instrument.get_elapsed_descheduled_time(task) == 0

    async with trio.open_nursery() as nursery:
        @nursery.start_soon
        async def _untracked_child():
            await trio.sleep(0)

    assert instrument.get_elapsed_descheduled_time(task) == 10 - 5
    assert time_fn.call_count == 2  # 2 x 1 deschedule (due to nursery)

    # our task is still alive, so instrument remains active
    trio_lowlevel.remove_instrument(instrument)


async def test_trio_perf_counter_time_sleep():
    # NOTE: subject to false pass due to reliance on wall time
    t0 = trio_perf_counter()
    time.sleep(.01)
    dt = trio_perf_counter() - t0
    assert dt == pytest.approx(.01, rel=.2)


class _TaskHierarchyTimeInstrument(trio.abc.Instrument):
    def __init__(self, time_fn=time.perf_counter):
        self._time_fn = time_fn
        self._root_task = trio_lowlevel.current_task()
        self._hierarchy_tasks = {self._root_task}
        self._descheduled_start = 0.
        self._descheduled_elapsed = 0.

        # populate existing child tasks of the root
        nurseries = set(self._root_task.child_nurseries)
        while nurseries:
            nursery: trio.Nursery = nurseries.pop()
            for child_task in nursery.child_tasks:
                self._hierarchy_tasks.add(child_task)
                nurseries.update(child_task.child_nurseries)

    def task_spawned(self, task: trio_lowlevel.Task):
        if task.parent_nursery and task.parent_nursery.parent_task in self._hierarchy_tasks:
            self._hierarchy_tasks.add(task)

    def task_exited(self, task: trio_lowlevel.Task):
        self._hierarchy_tasks.discard(task)

    def after_task_step(self, task: trio_lowlevel.Task):
        if task in self._hierarchy_tasks:
            self._descheduled_start = self._time_fn()

    def before_task_step(self, task: trio_lowlevel.Task):
        if task in self._hierarchy_tasks:
            self._descheduled_elapsed += self._time_fn() - self._descheduled_start

    def _finalize(self):
        assert self._hierarchy_tasks == {self._root_task}

    def get_elapsed_descheduled_time(self):
        return self._descheduled_elapsed


async def _work(duration, count=1):
    for _ in range(count):
        time.sleep(duration)
        await trio.sleep(0)


async def test_trio_perf_counter_child():
    instrument = _TaskHierarchyTimeInstrument()
    trio_lowlevel.add_instrument(instrument)
    t0 = time.perf_counter() - instrument.get_elapsed_descheduled_time()
    try:
        async with trio.open_nursery() as nursery:
            await _work(.05, 3)

            @nursery.start_soon
            async def _child():
                async with trio.open_nursery() as nursery2:
                    @nursery2.start_soon
                    async def _child_child():
                        await _work(.05, 5)

                    await _work(.05, 5)

            @nursery.start_soon
            async def _child_2():
                await _work(.05, 10)
    finally:
        trio_lowlevel.remove_instrument(instrument)
        instrument._finalize()
        dt = (time.perf_counter() - instrument.get_elapsed_descheduled_time()) - t0
        print('total time:', round(dt, 2))
        assert dt == pytest.approx(1.15, rel=.1)


async def test_trio_perf_counter_child_partial():
    try:
        async with trio.open_nursery() as nursery:
            @nursery.start_soon
            async def _child():
                async with trio.open_nursery() as nursery2:
                    @nursery2.start_soon
                    async def _child_child():
                        await _work(.1, 5)

                    await _work(.1, 5)

            await trio.sleep(.5)

            instrument = _TaskHierarchyTimeInstrument()
            trio_lowlevel.add_instrument(instrument)
            t0 = time.perf_counter() - instrument.get_elapsed_descheduled_time()

            @nursery.start_soon
            async def _child_2():
                await _work(.1, 10)

    finally:
        trio.lowlevel.remove_instrument(instrument)
        instrument._finalize()
        dt = (time.perf_counter() - instrument.get_elapsed_descheduled_time()) - t0
        print('total time:', round(dt, 2))
        assert dt == pytest.approx(1.5, rel=.1)


async def test_trio_perf_counter_unregister():
    async def perf_counter_with_trio_sleep():
        trio_perf_counter()
        await trio.sleep(0)
        trio_perf_counter()

    async with trio.open_nursery() as nursery:
        nursery.start_soon(perf_counter_with_trio_sleep)
        nursery.start_soon(perf_counter_with_trio_sleep)

    # Since all tasks using task_perf_counter() have exited, we expected
    # the Trio instrumentation to no longer be active (so remove call
    # will fail).
    with pytest.raises(KeyError):
        trio_lowlevel.remove_instrument(_trio._instrument)


async def test_trio_perf_timer(autojump_clock):
    # time_fn is called on enter and exit of each with block
    time_fn = Mock(side_effect=[10, 15,
                                15, 25])
    timer = TrioPerfTimer('foo', observer=AverageObserver, time_fn=time_fn)

    for _ in range(2):
        with timer:
            await trio.sleep(1)

    assert timer._count == 2
    assert timer._sum == 15
    assert timer._max == 10
    del timer


async def test_trio_perf_timer_decorator(autojump_clock):
    time_fn = Mock(side_effect=[10, 15,
                                15, 25])
    timer = TrioPerfTimer('foo', observer=AverageObserver, time_fn=time_fn)

    @timer
    async def foo():
        await trio.sleep(1)

    for _ in range(2):
        await foo()

    assert timer._count == 2
    assert timer._sum == 15
    assert timer._max == 10
    del timer
