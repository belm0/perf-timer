from bisect import bisect_right
from itertools import accumulate
from math import inf, sqrt
from numbers import Number


class ApproximateHistogram:
    """
    Streaming, approximate histogram

    Based on http://jmlr.org/papers/volume11/ben-haim10a/ben-haim10a.pdf

    Performance of adding a point is about 5x faster than
    https://github.com/carsonfarmer/streamhist (unmaintained).

    The output of quantile() will match numpy.quantile() exactly until
    the number of points reaches max_bins, and then gracefully transition
    to an approximation.
    """

    def __init__(self, max_bins):
        self._max_bins = max_bins
        self._bins = []  # (point, count)
        self._costs = []  # item i is _bins[i+1].point - _bins[i].point
        self._count = 0
        # TODO: maintain min/max as bin entries with infinite merge cost
        self._min = inf
        self._max = -inf

    @staticmethod
    def _update_costs(costs, l, i, val):
        """update costs array to reflect l.insert(i, val)"""
        if i > 0:
            new_cost = val[0] - l[i - 1][0]
            costs.insert(i - 1, new_cost)
            if i < len(costs):
                costs[i] = l[i + 1][0] - val[0]
        elif len(l) > 1:
            costs.insert(0, l[1][0] - val[0])
        # assert costs == approx([b - a for (a, _), (b, _) in zip(l, l[1:])], rel=1e-4)

    @staticmethod
    def _update_costs_for_merge(costs, l, i, val):
        """update costs array to reflect l[i:i+2] = (val, )"""
        # TODO: combine with update_costs()
        if 0 < i < len(costs) - 1:
            costs[i - 1:i + 2] = val[0] - l[i - 1][0], l[i + 1][0] - val[0]
        elif i > 0:
            costs[i - 1:i + 1] = (val[0] - l[i - 1][0], )
        else:
            costs[i:i + 2] = (l[i + 1][0] - val[0], )
        # assert costs == approx([b - a for (a, _), (b, _) in zip(l, l[1:])], rel=1e-4)

    @classmethod
    def _insert_with_cost(cls, costs, l, val):
        i = bisect_right(l, val)
        l.insert(i, val)
        cls._update_costs(costs, l, i, val)

    def add(self, point):
        """Add point to histogram"""
        # optimization:  maintain cost array
        self._count += 1
        self._min = min(self._min, point)
        self._max = max(self._max, point)
        bins = self._bins
        costs = self._costs
        self._insert_with_cost(costs, bins, (point, 1))
        if len(bins) > self._max_bins:
            i = costs.index(min(costs))
            (q0, k0), (q1, k1) = bins[i:i+2]
            _count = k0 + k1
            median = (q0 * k0 + q1 * k1) / _count
            bins[i:i+2] = ((median, _count), )
            self._update_costs_for_merge(costs, bins, i, (median, _count))

    @property
    def count(self):
        """Return number of points represented by this histogram."""
        return self._count

    @property
    def min(self):
        """Return minimum point represented by this histogram"""
        return self._min

    @property
    def max(self):
        """Return maximum point represented by this histogram"""
        return self._max

    def mean(self):
        """Return mean;  O(max_bins) complexity."""
        return sum(p * count for p, count in self._bins) / self._count

    def std(self):
        """Return standard deviation;  O(max_bins) complexity."""
        mean = self.mean()
        sum_squares = sum((p - mean) ** 2 * count for p, count in self._bins)
        return sqrt(sum_squares / self._count)

    def _quantile(self, sums, q):
        if q <= 0:
            return self._min
        if q >= 1:
            return self._max
        bins = self._bins
        target_sum = q * (self._count - 1) + 1
        i = bisect_right(sums, target_sum) - 1
        left = bins[i] if i >= 0 else (self._min, 0)
        right = bins[i+1] if i+1 < len(bins) else (self._max, 0)
        l0, r0 = left[0], right[0]
        l1, r1 = left[1], right[1]
        s = target_sum - (sums[i] if i >= 0 else 1)
        if l1 <= 1 and r1 <= 1:
            # We have exact info at this quantile.  Match linear interpolation
            # strategy of numpy.quantile().
            b = l0 + (r0 - l0) * s / r1 if r1 > 0 else l0
        else:
            if r1 == 1:
                # For exact bin on RHS, compensate for trapezoid interpolation using
                # only half of count.
                r1 = 2
            if l1 == r1:
                bp_ratio = s / l1
            else:
                bp_ratio = (l1 - (l1 ** 2 - 2 * s * (l1 - r1)) ** .5) / (l1 - r1)
                assert bp_ratio.imag == 0
            b = bp_ratio * (r0 - l0) + l0
        return b

    def sum(self):
        """Return sum of points;  O(max_bins) complexity."""
        return sum(x * count for x, count in self._bins)

    def quantile(self, q):
        """Return list of values at given quantile fraction(s);  O(max_bins) complexity."""
        # Deviation from Ben-Haim sum strategy:
        #     * treat count 1 bins as "exact" rather than dividing the count at the point
        #     * for neighboring exact bins, use simple linear interpolation matching
        #       numpy.quantile()
        if isinstance(q, Number):
            q = (q, )
        bins = self._bins
        sums = [x - (y/2 if y > 1 else 0) for x, (_, y) in \
                zip(accumulate(bin[1] for bin in bins), bins)]
        return list(self._quantile(sums, q_item) for q_item in q)
