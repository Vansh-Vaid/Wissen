"""Crossing logic for level and ma_cross rules, independent of file parsing."""

import random
import unittest
from fractions import Fraction

from alerts import LevelRule, MaCrossRule, crossing_days, level_signals, ma_signals
from tests.helpers import day, series


def level_rule(direction, level):
    from decimal import Decimal
    return LevelRule("r", "X", direction, Decimal(str(level)), str(level))


def fires_level(closes, direction, level):
    s = series(*closes)
    return crossing_days(level_signals(s, level_rule(direction, level)), direction)


def fires_ma(closes, direction, short, long_):
    s = series(*closes)
    return crossing_days(ma_signals(s, MaCrossRule("r", "X", direction, short, long_)), direction)


class LevelRuleTest(unittest.TestCase):
    def test_brief_example(self):
        self.assertEqual(fires_level([1520.50, 1534.10, 1498.00], "below", 1500), [day(2)])

    def test_fires_only_on_crossing_day_not_while_staying_below(self):
        self.assertEqual(fires_level([1510, 1490, 1480, 1470], "below", 1500), [day(1)])

    def test_fires_again_after_recovering_and_crossing_again(self):
        self.assertEqual(fires_level([1510, 1490, 1510, 1490], "below", 1500), [day(1), day(3)])

    def test_first_day_already_below_does_not_fire(self):
        # No previous day, so nothing was "on the other side".
        self.assertEqual(fires_level([1490, 1480], "below", 1500), [])

    def test_touching_the_level_is_not_crossing(self):
        self.assertEqual(fires_level([1510, 1500, 1510], "below", 1500), [])

    def test_from_exactly_level_to_below_fires(self):
        self.assertEqual(fires_level([1500, 1499.99], "below", 1500), [day(1)])

    def test_through_the_level_via_equal_fires_once(self):
        self.assertEqual(fires_level([1510, 1500, 1490, 1500, 1490], "below", 1500), [day(2), day(4)])

    def test_above_mirrors_below(self):
        self.assertEqual(fires_level([1490, 1510, 1520, 1490, 1500, 1501], "above", 1500), [day(1), day(5)])

    def test_decimal_precision_no_float_error(self):
        # 0.1 + 0.2 style issues: 1500.10 vs level 1500.1 must be equal, not above.
        self.assertEqual(fires_level(["1499.9", "1500.10"], "above", "1500.1"), [])

    def test_single_day_and_empty_series(self):
        self.assertEqual(fires_level([1490], "below", 1500), [])
        self.assertEqual(fires_level([], "below", 1500), [])


class MaCrossRuleTest(unittest.TestCase):
    def test_hand_computed_cross_above(self):
        # short=2, long=3. Day:      0   1   2   3   4
        # closes                    10  10   7  10  13
        # MA2 (from day 1)              10 8.5 8.5 11.5
        # MA3 (from day 2)                  9   9  10
        # MA2 - MA3 (from day 2)          -0.5 -0.5 1.5  -> crosses above on day 4
        self.assertEqual(fires_ma([10, 10, 7, 10, 13], "above", 2, 3), [day(4)])

    def test_hand_computed_cross_below(self):
        self.assertEqual(fires_ma([10, 10, 13, 10, 7], "below", 2, 3), [day(4)])

    def test_wrong_direction_does_not_fire(self):
        self.assertEqual(fires_ma([10, 10, 13, 10, 7], "above", 2, 3), [])

    def test_no_alert_before_long_window_is_full(self):
        # A sharp rise inside the first `long` days cannot fire: MA_long undefined.
        self.assertEqual(fires_ma([1, 1, 100], "above", 2, 3), [])

    def test_earliest_possible_fire_is_day_long_plus_one(self):
        # Day 2 is the first day MA3 exists; the first possible crossing is day 3.
        self.assertEqual(fires_ma([10, 10, 7, 20], "above", 2, 3), [day(3)])

    def test_already_above_when_first_defined_does_not_fire(self):
        self.assertEqual(fires_ma([1, 2, 3, 4, 5, 6], "above", 2, 3), [])

    def test_exact_tie_then_above_fires(self):
        # Flat prices make MA2 == MA3 exactly; the first real move above fires.
        self.assertEqual(fires_ma([10, 10, 10, 10, 11], "above", 2, 3), [day(4)])

    def test_one_signal_per_row_undefined_until_long_rows(self):
        s = series(10, 10, 7, 10, 13)
        signals = ma_signals(s, MaCrossRule("r", "X", "above", 2, 3))
        self.assertEqual([d for d, _ in signals], [d for d, _ in s])
        self.assertEqual([v is None for _, v in signals], [True, True, False, False, False])

    def test_exact_tie_that_floats_get_wrong(self):
        # On the last day MA2 == MA4 == 1675.805 exactly, so nothing may fire.
        # With floats, MA2 = 1675.805 but MA4 = 1675.8049999999998: a false cross.
        closes = ["2000", "1854.05", "1497.56", "1275.19", "2076.42"]
        # Left-to-right addition, as a hand-written loop does. (Python 3.12+ sum()
        # uses compensated summation for floats and happens to hide this case.)
        f = [float(c) for c in closes]
        self.assertGreater((f[3] + f[4]) / 2, (f[1] + f[2] + f[3] + f[4]) / 4)  # the float trap is real
        self.assertEqual(fires_ma(closes, "above", 2, 4), [])


def reference_ma_cross(closes, direction, short, long_):
    """Deliberately naive re-implementation with exact fractions, for cross-checking."""
    def ma(i, n):
        return sum(Fraction(str(c)) for c in closes[i - n + 1:i + 1]) / n

    fired = []
    for i in range(long_, len(closes)):
        prev = ma(i - 1, short) - ma(i - 1, long_)
        cur = ma(i, short) - ma(i, long_)
        if direction == "above" and prev <= 0 < cur:
            fired.append(day(i))
        if direction == "below" and prev >= 0 > cur:
            fired.append(day(i))
    return fired


def random_close(rng):
    """Mostly paise prices; sometimes whole numbers or very long decimals."""
    kind = rng.random()
    if kind < 0.6:
        return f"{rng.randint(9500, 10500) / 100:.2f}"
    if kind < 0.8:
        return str(rng.randint(95, 105))
    return f"100.{rng.randint(0, 10**30):030d}"  # 33 significant digits


class MaCrossAgainstReferenceTest(unittest.TestCase):
    def test_random_series_match_reference(self):
        rng = random.Random(1234)
        for _ in range(300):
            short = rng.randint(1, 6)
            long_ = rng.randint(short + 1, 12)
            # Small integer range on purpose: produces many exact ties.
            closes = [rng.randint(95, 105) for _ in range(rng.randint(0, 40))]
            direction = rng.choice(["above", "below"])
            with self.subTest(closes=closes, short=short, long=long_, direction=direction):
                self.assertEqual(
                    fires_ma(closes, direction, short, long_),
                    reference_ma_cross(closes, direction, short, long_),
                )

    def test_mixed_and_very_long_decimal_places_match_reference(self):
        rng = random.Random(99)
        for _ in range(200):
            short = rng.randint(1, 5)
            long_ = rng.randint(short + 1, 10)
            closes = [random_close(rng) for _ in range(rng.randint(0, 30))]
            direction = rng.choice(["above", "below"])
            with self.subTest(closes=closes, short=short, long=long_, direction=direction):
                self.assertEqual(
                    fires_ma(closes, direction, short, long_),
                    reference_ma_cross(closes, direction, short, long_),
                )

    def test_tie_hidden_beyond_28_significant_digits(self):
        # MA1 vs MA2 differ only in the 31st significant digit on the last day:
        # 100.000...0002 vs (100.000...0001 + 100.000...0002) / 2. Must still fire.
        a, b = "100." + "0" * 29 + "1", "100." + "0" * 29 + "2"
        self.assertEqual(fires_ma([a, a, b], "above", 1, 2), [day(2)])


if __name__ == "__main__":
    unittest.main()
