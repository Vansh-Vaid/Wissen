import unittest
from datetime import date, timedelta
from decimal import Decimal

from alerts import crossing_days, level_signals


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


if __name__ == "__main__":
    unittest.main()
