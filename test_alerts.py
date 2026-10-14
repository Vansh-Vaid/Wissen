import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from decimal import Decimal

from alerts import InputError, crossing_days, level_differences, ma_differences, read_prices, read_rules

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(HERE, "samples")


def series(*closes):
    return [(date(2026, 9, i + 1), Decimal(str(c))) for i, c in enumerate(closes)]


def sept(day):
    return date(2026, 9, day)


def run_tool(prices_path, rules_path):
    return subprocess.run([sys.executable, os.path.join(HERE, "alerts.py"), prices_path, rules_path],
                          capture_output=True, text=True)


class TestCrossings(unittest.TestCase):
    def test_level_crosses_below(self):
        values = level_differences(series("1520.50", "1534.10", "1498.00"), Decimal(1500))
        self.assertEqual(crossing_days(values, "below"), [sept(3)])

    def test_staying_below_does_not_fire_again(self):
        values = level_differences(series(1510, 1490, 1480, 1470), Decimal(1500))
        self.assertEqual(crossing_days(values, "below"), [sept(2)])

    def test_first_day_never_fires(self):
        values = level_differences(series(1490, 1480), Decimal(1500))
        self.assertEqual(crossing_days(values, "below"), [])

    def test_touching_the_level_is_not_a_cross(self):
        values = level_differences(series(1510, 1500, 1510), Decimal(1500))
        self.assertEqual(crossing_days(values, "below"), [])

    def test_from_the_level_to_below_is_a_cross(self):
        values = level_differences(series(1500, "1499.99"), Decimal(1500))
        self.assertEqual(crossing_days(values, "below"), [sept(2)])

    def test_ma_cross_worked_by_hand(self):
        # MA2 - MA3 from day 3: -0.5, -0.5, +1.5
        values = ma_differences(series(10, 10, 7, 10, 13), 2, 3)
        self.assertEqual(crossing_days(values, "above"), [sept(5)])

    def test_ma_is_undefined_until_the_long_window_is_full(self):
        values = ma_differences(series(10, 10, 7, 10, 13), 2, 3)
        self.assertEqual([v is None for _, v in values], [True, True, False, False, False])

    def test_ma_needs_one_more_day_than_the_long_window(self):
        self.assertEqual(crossing_days(ma_differences(series(1, 1, 100), 2, 3), "above"), [])
        self.assertEqual(crossing_days(ma_differences(series(10, 10, 7, 20), 2, 3), "above"), [sept(4)])

    def test_ma_exact_tie_is_not_a_cross(self):
        # MA2 and MA4 are both exactly 1675.805 on the last day; floats disagree.
        closes = ["2000", "1854.05", "1497.56", "1275.19", "2076.42"]
        self.assertEqual(crossing_days(ma_differences(series(*closes), 2, 4), "above"), [])


class TestReadingFiles(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def write(self, name, text):
        path = os.path.join(self.folder.name, name)
        with open(path, "w", newline="") as f:
            f.write(text)
        return path

    def test_rows_are_sorted_by_date(self):
        path = self.write("p.csv", "date,instrument,close\n2026-09-02,INFY,2\n2026-09-01,INFY,1\n")
        self.assertEqual(read_prices(path)["INFY"], series(1, 2))

    def test_conflicting_duplicate_is_an_error(self):
        path = self.write("p.csv", "date,instrument,close\n2026-09-01,INFY,1520\n2026-09-01,INFY,1530\n")
        with self.assertRaises(InputError):
            read_prices(path)

    def test_missing_column_is_an_error(self):
        path = self.write("p.csv", "date,instrument,price\n2026-09-01,INFY,1520\n")
        with self.assertRaises(InputError):
            read_prices(path)

    def test_invalid_rules_are_errors(self):
        good = {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}
        bad_rules = [
            [dict(good, type="percent")],
            [dict(good, direction="up")],
            [dict(good, level="1500")],
            [dict(good, level=True)],
            [{"id": "m", "instrument": "TCS", "type": "ma_cross", "short": 20, "long": 5, "direction": "above"}],
            [{"id": "m", "instrument": "TCS", "type": "ma_cross", "short": 20, "long": 20, "direction": "above"}],
            [{"id": "m", "instrument": "TCS", "type": "ma_cross", "short": 5.5, "long": 20, "direction": "above"}],
            [good, good],
            good,
        ]
        for rules in bad_rules:
            with self.subTest(rules=rules):
                path = self.write("r.json", json.dumps(rules))
                with self.assertRaises(InputError):
                    read_rules(path)


class TestSamples(unittest.TestCase):
    def test_every_sample_gives_its_expected_output(self):
        for name in sorted(os.listdir(SAMPLES)):
            folder = os.path.join(SAMPLES, name)
            with self.subTest(sample=name):
                result = run_tool(os.path.join(folder, "prices.csv"), os.path.join(folder, "rules.json"))
                with open(os.path.join(folder, "expected.txt")) as f:
                    self.assertEqual(result.stdout, f.read())
                self.assertNotIn("Traceback", result.stderr)

    def test_invalid_rule_sample_exits_with_2(self):
        folder = os.path.join(SAMPLES, "10_invalid_rule")
        result = run_tool(os.path.join(folder, "prices.csv"), os.path.join(folder, "rules.json"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("rule 'bad'", result.stderr)

    def test_messy_sample_warns_about_each_bad_row(self):
        folder = os.path.join(SAMPLES, "08_messy_csv")
        result = run_tool(os.path.join(folder, "prices.csv"), os.path.join(folder, "rules.json"))
        self.assertEqual(result.stderr.count("warning"), 6)


if __name__ == "__main__":
    unittest.main()
