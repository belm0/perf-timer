import pytest

from perf_timer._impl import _format_duration


@pytest.mark.parametrize('in_, expected', [
    ((      12, 3), '12.0 s' ),
    ((     120, 3), '120 s'  ),
    ((  .05071, 3), '50.7 ms'),
    ((  .05071, 2), '51 ms'  ),
    ((12.34e-6, 3), '12.3 µs'),
    ((1.234e-9, 3), '1.23 ns'),
    ((   .5e-9, 3), '0.500 ns' ),
    ((     120, 3, 'X'), '120Xs'),
])
def test_format_duration(in_, expected):
    assert _format_duration(*in_) == expected
