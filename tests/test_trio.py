import time
from unittest.mock import Mock

import pytest
import trio
try:
    import trio.lowlevel as trio_lowlevel
except ImportError:
    import trio.hazmat as trio_lowlevel

from perf_timer import trio_perf_counter, _trio, TrioPerfTimer, AverageObserver, trio_hierarchy_perf_counter


async def _work(duration, count=1):
    for _ in range(count):
        time.sleep(duration)
        await trio.sleep(0)


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
    await _work(.1, 5)
    dt = trio_perf_counter() - t0
    assert dt == pytest.approx(.5, rel=.15)


async def test_trio_perf_counter_child():
    t0 = trio_hierarchy_perf_counter()
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

    dt = trio_hierarchy_perf_counter() - t0
    assert dt == pytest.approx(1.15, rel=.15)


async def test_trio_hierarchy_perf_counter_active_children():
    # trio_hierarchy_perf_counter() should work even if the task already has children
    async with trio.open_nursery() as nursery:
        @nursery.start_soon
        async def _child():
            async with trio.open_nursery() as nursery2:
                @nursery2.start_soon
                async def _child_child():
                    await _work(.1, 5)

                await _work(.1, 5)

        await trio.sleep(.5)
        t0 = trio_hierarchy_perf_counter()

        @nursery.start_soon
        async def _child_2():
            await _work(.1, 10)

    dt = trio_hierarchy_perf_counter() - t0
    assert dt == pytest.approx(1.5, rel=.15)


@pytest.mark.parametrize('counter_fn, instrument', [
    (trio_perf_counter, _trio._instrument),
    (trio_hierarchy_perf_counter, _trio._hierarchy_instrument),
])
async def test_trio_perf_counter_unregister(counter_fn, instrument: trio.abc.Instrument):
    async def perf_counter_with_trio_sleep():
        counter_fn()
        await trio.sleep(0)
        counter_fn()

    async with trio.open_nursery() as nursery:
        nursery.start_soon(perf_counter_with_trio_sleep)
        nursery.start_soon(perf_counter_with_trio_sleep)

    # Since all tasks using task_perf_counter() have exited, we expected
    # the Trio instrumentation to no longer be active (so remove call
    # will fail).
    with pytest.raises(KeyError):
        trio_lowlevel.remove_instrument(instrument)


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


# TODO: test nested perf timers on the same task
# async def _foo():
#     with TrioPerfTimer('timer1'):
#         async with trio.open_nursery() as nursery:
#             @nursery.start_soon
#             async def _child_1():
#                 pass  # do work
#
#             # do work
#
#             with TrioPerfTimer('timer2'):
#                 @nursery.start_soon
#                 async def _child_2():
#                     pass  # do work
