import time
from unittest.mock import Mock

import pytest
import trio

from perf_timer import trio_perf_counter, _trio, TrioPerfTimer


async def test_descheduled_time_instrument():
    time_fn = Mock(side_effect=[5, 10, 10, 20])
    instrument = _trio._DescheduledTimeInstrument(time_fn=time_fn)
    trio.hazmat.add_instrument(instrument)

    # Only tasks referenced by get_elapsed_descheduled_time() will be tracked,
    # so instrument is not tracking the current task.
    await trio.sleep(0)
    assert not time_fn.called

    async with trio.open_nursery() as nursery:
        @nursery.start_soon
        async def _tracked_child():
            # calling get_elapsed_descheduled_time() initiates tracking
            task = trio.hazmat.current_task()
            assert instrument.get_elapsed_descheduled_time(task) == 0
            await trio.sleep(0)
            assert instrument.get_elapsed_descheduled_time(task) == 10 - 5
            await trio.sleep(0)
            assert instrument.get_elapsed_descheduled_time(task) == 20 - 5
            # time function is called twice for each deschedule
            assert time_fn.call_count == 4

    # the sole tracked task exited, so instrument is automatically removed
    with pytest.raises(KeyError):
        trio.hazmat.remove_instrument(instrument)


async def test_descheduled_time_instrument_exclude_children():
    time_fn = Mock(side_effect=[5, 10])
    instrument = _trio._DescheduledTimeInstrument(time_fn=time_fn)
    trio.hazmat.add_instrument(instrument)

    task = trio.hazmat.current_task()
    assert instrument.get_elapsed_descheduled_time(task) == 0

    async with trio.open_nursery() as nursery:
        @nursery.start_soon
        async def _untracked_child():
            await trio.sleep(0)

    assert instrument.get_elapsed_descheduled_time(task) == 10 - 5
    assert time_fn.call_count == 2  # 2 x 1 deschedule (due to nursery)

    # our task is still alive, so instrument remains active
    trio.hazmat.remove_instrument(instrument)


async def test_trio_perf_counter_time_sleep():
    # NOTE: subject to false pass due to reliance on wall time
    t0 = trio_perf_counter()
    time.sleep(.01)
    dt = trio_perf_counter() - t0
    assert dt > .008


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
        trio.hazmat.remove_instrument(_trio._instrument)


async def test_trio_perf_timer(autojump_clock):
    # time_fn is called on enter and exit of each with block
    time_fn = Mock(side_effect=[10, 15,
                                15, 25])
    timer = TrioPerfTimer('foo', time_fn=time_fn)

    for _ in range(2):
        with timer:
            await trio.sleep(1)

    assert timer._count == 2
    assert timer._duration == 15
    assert timer._max == 10
    del timer


async def test_trio_perf_timer_decorator(autojump_clock):
    time_fn = Mock(side_effect=[10, 15,
                                15, 25])
    timer = TrioPerfTimer('foo', time_fn=time_fn)

    @timer
    async def foo():
        await trio.sleep(1)

    for _ in range(2):
        await foo()

    assert timer._count == 2
    assert timer._duration == 15
    assert timer._max == 10
    del timer
