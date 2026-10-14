import unittest

from alerts import crossing_days


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


if __name__ == "__main__":
    unittest.main()
