# Release history

## perf-timer 0.2.0 (2020-07-01)
### Added
- perf-timer classes now support tracking various statistics
  including standard deviation and percentiles.  The options are
  `AverageObserver`, `StdDevObserver` (default), and `HistogramObserver`.
  E.g. `PerfTimer(..., observer=HistogramObserver)`.
- Benchmark overhead of the various observer and timer types

## perf-timer 0.1.1 (2020-06-05)
### Fixed
- Support rename of trio.hazmat to trio.lowlevel
- Expose docs to help()

## perf-timer 0.1.0 (2019-07-31)
Initial version
