import unittest
from datetime import date, timedelta
from decimal import Decimal

from alerts import crossing_days, level_signals, ma_signals


def prices(*closes):
    """Build [(date, Decimal close), ...] for consecutive days from Sep 1, 2026."""
    start = date(2026, 9, 1)
    return [(start + timedelta(days=i), Decimal(str(c))) for i, c in enumerate(closes)]


def level_alerts(closes, direction, level):
    return crossing_days(level_signals(prices(*closes), Decimal(str(level))), direction)


class CrossingDaysTest(unittest.TestCase):
    # Each signal is (day, value). Think of value as "close - level".

    def test_fires_on_the_day_it_crosses_below(self):
        signals = [("d1", 20), ("d2", 34), ("d3", -2)]
        self.assertEqual(crossing_days(signals, "below"), ["d3"])

    def test_does_not_fire_again_while_it_stays_below(self):
        signals = [("d1", 10), ("d2", -10), ("d3", -20), ("d4", -30)]
        self.assertEqual(crossing_days(signals, "below"), ["d2"])

    def test_fires_again_after_going_back_and_crossing_again(self):
        signals = [("d1", 10), ("d2", -10), ("d3", 10), ("d4", -10)]
        self.assertEqual(crossing_days(signals, "below"), ["d2", "d4"])

    def test_first_day_never_fires_because_there_is_no_yesterday(self):
        signals = [("d1", -10), ("d2", -20)]
        self.assertEqual(crossing_days(signals, "below"), [])

    def test_touching_zero_is_not_crossing(self):
        signals = [("d1", 10), ("d2", 0), ("d3", 10)]
        self.assertEqual(crossing_days(signals, "below"), [])

    def test_from_zero_to_negative_is_crossing(self):
        signals = [("d1", 0), ("d2", -1)]
        self.assertEqual(crossing_days(signals, "below"), ["d2"])

    def test_above_is_the_mirror_image(self):
        signals = [("d1", -10), ("d2", 10), ("d3", 20), ("d4", -5), ("d5", 5)]
        self.assertEqual(crossing_days(signals, "above"), ["d2", "d5"])

    def test_undefined_values_never_fire(self):
        # None means "not known yet", like a moving average without enough days.
        signals = [("d1", None), ("d2", None), ("d3", -5), ("d4", 5)]
        self.assertEqual(crossing_days(signals, "above"), ["d4"])


class LevelRuleTest(unittest.TestCase):
    def test_brief_example_fires_on_sep_3(self):
        # The PDF: INFY 1520.50, 1534.10, 1498.00 with "below 1500" fires on 2026-09-03.
        self.assertEqual(level_alerts(["1520.50", "1534.10", "1498.00"], "below", 1500), [date(2026, 9, 3)])

    def test_signal_is_close_minus_level(self):
        signals = level_signals(prices("1520.50", "1498.00"), Decimal(1500))
        self.assertEqual(signals, [(date(2026, 9, 1), Decimal("20.50")), (date(2026, 9, 2), Decimal("-2.00"))])

    def test_close_exactly_on_the_level_is_not_crossed(self):
        self.assertEqual(level_alerts([1510, 1500, 1510], "below", 1500), [])

    def test_one_paisa_below_the_level_is_crossed(self):
        self.assertEqual(level_alerts(["1500.00", "1499.99"], "below", 1500), [date(2026, 9, 2)])

    def test_same_number_written_differently_is_equal(self):
        # 1500.10 and 1500.1 are the same price: no crossing above 1500.1.
        self.assertEqual(level_alerts(["1499.90", "1500.10"], "above", "1500.1"), [])

    def test_above_rule(self):
        self.assertEqual(level_alerts([1490, 1510, 1520], "above", 1500), [date(2026, 9, 2)])

    def test_empty_and_single_day(self):
        self.assertEqual(level_alerts([], "below", 1500), [])
        self.assertEqual(level_alerts([1400], "below", 1500), [])


def day(n):
    """The n-th day (1-based) of a series built by prices()."""
    return date(2026, 9, n)


def ma_alerts(closes, direction, short, long_):
    return crossing_days(ma_signals(prices(*closes), short, long_), direction)


class MovingAverageRuleTest(unittest.TestCase):
    def test_hand_computed_cross_above(self):
        # Day:   1   2   3    4    5
        # close 10  10   7   10   13
        # MA2    -  10  8.5  8.5 11.5
        # MA3    -   -   9    9   10    -> MA2 - MA3: -0.5, -0.5, +1.5 -> fires day 5
        self.assertEqual(ma_alerts([10, 10, 7, 10, 13], "above", 2, 3), [day(5)])

    def test_cross_below(self):
        self.assertEqual(ma_alerts([10, 10, 13, 10, 7], "below", 2, 3), [day(5)])

    def test_wrong_direction_does_not_fire(self):
        self.assertEqual(ma_alerts([10, 10, 7, 10, 13], "below", 2, 3), [])

    def test_one_signal_per_day_and_none_until_the_long_window_is_full(self):
        signals = ma_signals(prices(10, 10, 7, 10, 13), 2, 3)
        self.assertEqual([d for d, _ in signals], [day(1), day(2), day(3), day(4), day(5)])
        self.assertEqual([v is None for _, v in signals], [True, True, False, False, False])

    def test_exactly_long_days_can_never_fire(self):
        # MA3 first exists on day 3, but day 3 has no defined yesterday.
        self.assertEqual(ma_alerts([1, 1, 100], "above", 2, 3), [])

    def test_earliest_alert_is_day_long_plus_one(self):
        self.assertEqual(ma_alerts([10, 10, 7, 20], "above", 2, 3), [day(4)])

    def test_brief_windows_flat_then_rising(self):
        # 20 flat days: MA5 == MA20 exactly (a tie is not a cross). Day 21 rises: fires.
        self.assertEqual(ma_alerts([3900] * 20 + [3901], "above", 5, 20), [day(21)])

    def test_signals_are_exact_numbers_never_floats(self):
        # Floats can turn exact ties into false alerts, and newer Pythons hide some
        # float errors (sum() compensates since 3.12), so test the promise directly.
        for _, value in ma_signals(prices("1854.05", "1497.56", "1275.19", "2076.42", "1500"), 2, 4):
            if value is not None:
                self.assertIsInstance(value, Decimal)

    def test_exact_tie_that_floats_get_wrong(self):
        closes = ["2000", "1854.05", "1497.56", "1275.19", "2076.42"]
        # Last day: MA2 = (1275.19 + 2076.42) / 2 = 1675.805
        #           MA4 = (1854.05 + 1497.56 + 1275.19 + 2076.42) / 4 = 1675.805  -> a tie
        f = [float(c) for c in closes]
        float_ma2 = (f[3] + f[4]) / 2
        float_ma4 = (f[1] + f[2] + f[3] + f[4]) / 4
        self.assertGreater(float_ma2, float_ma4)  # floats wrongly say MA2 is above
        self.assertEqual(ma_alerts(closes, "above", 2, 4), [])  # exact maths: no alert


if __name__ == "__main__":
    unittest.main()
