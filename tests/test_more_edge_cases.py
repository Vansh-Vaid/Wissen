"""More edge cases for the files and command line, beyond the brief's examples."""

import os
import subprocess
import sys
import unittest

from tests.helpers import TempFiles

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "alerts.py")
HEADER = "date,instrument,close\n"
RULE = [{"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}]
FIRES = "2026-09-02  r1  INFY  level below 1500\n"


def run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)


class PriceFileEdgeCases(TempFiles, unittest.TestCase):
    def run_prices(self, text, rules=RULE):
        return run(self.write("prices.csv", text), self.write("rules.json", rules))

    def test_no_newline_at_end_of_file(self):
        result = self.run_prices(HEADER + "2026-09-01,INFY,1510\n2026-09-02,INFY,1490")
        self.assertEqual((result.stdout, result.stderr), (FIRES, ""))

    def test_number_spellings_that_are_valid(self):
        # "+1510", "1490." and ".5"-style values are ordinary numbers; all accepted.
        result = self.run_prices(HEADER + "2026-09-01,INFY,+1510\n2026-09-02,INFY,1490.\n2026-09-03,X,.5\n")
        self.assertEqual((result.stdout, result.stderr), (FIRES, ""))

    def test_currency_symbol_and_units_rejected(self):
        # "1_490" and Arabic-Indic digits are accepted by Python's Decimal() but are not CSV prices.
        for close in ("₹1490", "1490 INR", "$1490", "1490%", "1_490", "١٤٩٠", "0x5D2", "1490-"):
            with self.subTest(close=close):
                result = self.run_prices(HEADER + f"2026-09-01,INFY,1510\n2026-09-02,INFY,{close}\n")
                self.assertEqual(result.stdout, "")
                self.assertIn("bad close", result.stderr)

    def test_timestamp_in_date_column_rejected(self):
        for d in ("2026-09-02 00:00:00", "2026-09-02T09:15", "20260902", "2026/09/02", "02-09-2026"):
            with self.subTest(date=d):
                result = self.run_prices(HEADER + f"2026-09-01,INFY,1510\n{d},INFY,1490\n")
                self.assertEqual(result.stdout, "")
                self.assertIn("bad date", result.stderr)

    def test_single_digit_month_and_day_accepted(self):
        result = self.run_prices(HEADER + "2026-9-1,INFY,1510\n2026-09-2,INFY,1490\n")
        self.assertEqual(result.stdout, FIRES)

    def test_tab_separated_file_is_fatal(self):
        result = self.run_prices("date\tinstrument\tclose\n2026-09-01\tINFY\t1510\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("missing column", result.stderr)

    def test_whitespace_only_file_is_fatal(self):
        result = self.run_prices("   \n\n")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_quoted_field_with_comma_in_instrument_name(self):
        rules = [{"id": "r1", "instrument": "NIFTY, 50", "type": "level", "direction": "below", "level": 100}]
        result = self.run_prices(HEADER + '2026-09-01,"NIFTY, 50",110\n2026-09-02,"NIFTY, 50",90\n', rules)
        self.assertEqual(result.stdout, "2026-09-02  r1  NIFTY, 50  level below 100\n")

    def test_duplicate_in_shuffled_file_reports_both_lines(self):
        result = self.run_prices(HEADER + "2026-09-02,INFY,1490\n2026-09-01,INFY,1510\n2026-09-02,INFY,1495\n")
        self.assertEqual(result.returncode, 2)
        self.assertIn("lines 2 and 4", result.stderr)

    def test_same_close_written_differently_is_an_exact_duplicate(self):
        result = self.run_prices(HEADER + "2026-09-01,INFY,1510\n2026-09-01,INFY,1510.000\n2026-09-02,INFY,1490\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, FIRES)

    def test_huge_gap_between_dates(self):
        # Years apart: still "the previous day" for this instrument.
        result = self.run_prices(HEADER + "1999-12-31,INFY,1510\n2026-09-02,INFY,1490\n")
        self.assertEqual(result.stdout, FIRES)

    def test_many_instruments_one_row_each_never_fire(self):
        rows = "".join(f"2026-09-01,T{i},{1000 + i}\n" for i in range(200))
        rules = [{"id": f"r{i}", "instrument": f"T{i}", "type": "level", "direction": "below", "level": 5000}
                 for i in range(200)]
        result = self.run_prices(HEADER + rows, rules)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))


class RulesFileEdgeCases(TempFiles, unittest.TestCase):
    PRICES = HEADER + "2026-09-01,INFY,1510\n2026-09-02,INFY,1490\n2026-09-03,INFY,1510\n"

    def run_rules(self, rules):
        return run(self.write("prices.csv", self.PRICES), self.write("rules.json", rules))

    def test_rules_wrapped_in_an_object_is_fatal(self):
        result = self.run_rules({"rules": RULE})
        self.assertEqual(result.returncode, 2)
        self.assertIn("JSON list", result.stderr)

    def test_instrument_given_as_a_list_is_fatal(self):
        result = self.run_rules([dict(RULE[0], instrument=["INFY"])])
        self.assertEqual(result.returncode, 2)
        self.assertIn("'instrument'", result.stderr)

    def test_negative_and_zero_levels_are_valid_but_never_cross_positive_prices(self):
        rules = [dict(RULE[0], id="neg", level=-5), dict(RULE[0], id="zero", level=0)]
        result = self.run_rules(rules)
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_huge_integer_level(self):
        result = self.run_rules([dict(RULE[0], direction="above", level=10 ** 30)])
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_level_and_ma_rules_with_identical_settings_but_different_ids(self):
        rules = [dict(RULE[0], id="b"), dict(RULE[0], id="a")]
        self.assertEqual(self.run_rules(rules).stdout,
                         "2026-09-02  a  INFY  level below 1500\n2026-09-02  b  INFY  level below 1500\n")

    def test_ids_differing_only_in_case_are_distinct_and_sorted_by_code_point(self):
        rules = [dict(RULE[0], id="r1"), dict(RULE[0], id="R1")]
        self.assertEqual([l.split()[1] for l in self.run_rules(rules).stdout.splitlines()], ["R1", "r1"])

    def test_ma_window_of_zero_length_series_and_huge_window(self):
        rules = [{"id": "m", "instrument": "INFY", "type": "ma_cross", "short": 1, "long": 100000,
                  "direction": "above"}]
        result = self.run_rules(rules)
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_ma_short_one_long_two_alternates_every_day(self):
        prices = HEADER + "".join(f"2026-09-{d:02d},INFY,{c}\n" for d, c in
                                  zip(range(1, 8), [10, 12, 10, 12, 10, 12, 10]))
        rules = [{"id": "up", "instrument": "INFY", "type": "ma_cross", "short": 1, "long": 2, "direction": "above"},
                 {"id": "dn", "instrument": "INFY", "type": "ma_cross", "short": 1, "long": 2, "direction": "below"}]
        out = run(self.write("p.csv", prices), self.write("r.json", rules)).stdout.split("\n")
        # close - MA2 from day 2: +1, -1, +1, -1, +1, -1 -> crosses from day 3 on, alternating.
        self.assertEqual([l.split()[1] for l in out if l], ["dn", "up", "dn", "up", "dn"])


class CommandLineEdgeCases(TempFiles, unittest.TestCase):
    def test_too_many_arguments_prints_usage(self):
        p = self.write("p.csv", HEADER)
        result = run(p, p, p)
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage", result.stderr)

    def test_help_flag_prints_usage_not_a_traceback(self):
        result = run("--help")
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage", result.stderr)

    def test_directory_instead_of_file(self):
        result = run(self._tmp.name, self.write("r.json", RULE))
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot read prices file", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_missing_rules_file(self):
        result = run(self.write("p.csv", HEADER), os.path.join(self._tmp.name, "nope.json"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot read rules file", result.stderr)

    def test_paths_with_spaces_and_unicode(self):
        p = self.write("my prices ₹.csv", HEADER + "2026-09-01,INFY,1510\n2026-09-02,INFY,1490\n")
        r = self.write("my rules.json", RULE)
        self.assertEqual(run(p, r).stdout, FIRES)

    def test_relative_paths_from_project_folder(self):
        result = subprocess.run(
            [sys.executable, "alerts.py", "tests/fixtures/brief_full_prices.csv", "tests/fixtures/brief_rules.json"],
            capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stdout.splitlines()), 2)

    def test_same_file_twice_gives_same_output(self):
        p = self.write("p.csv", HEADER + "2026-09-01,INFY,1510\n2026-09-02,INFY,1490\n")
        r = self.write("r.json", RULE)
        self.assertEqual(run(p, r).stdout, run(p, r).stdout)


if __name__ == "__main__":
    unittest.main()
