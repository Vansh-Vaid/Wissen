"""End-to-end: run alerts.py as a user would and check stdout, stderr, exit code."""

import os
import subprocess
import sys
import unittest

from tests.helpers import TempFiles

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "alerts.py")

BRIEF_PRICES = """date,instrument,close
2026-09-01,INFY,1520.50
2026-09-01,TCS,3890.00
2026-09-02,INFY,1534.10
2026-09-02,TCS,3902.25
2026-09-03,INFY,1498.00
"""

BRIEF_RULES = [
    {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500},
    {"id": "r2", "instrument": "TCS", "type": "ma_cross", "short": 5, "long": 20, "direction": "above"},
]


def run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)


class CliTest(TempFiles, unittest.TestCase):
    def run_tool(self, prices, rules):
        return run(self.write("prices.csv", prices), self.write("rules.json", rules))

    def test_brief_example(self):
        # TCS has only 2 days, so its 5/20 averages are never defined.
        result = self.run_tool(BRIEF_PRICES, BRIEF_RULES)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "2026-09-03  r1  INFY  level below 1500\n")
        self.assertEqual(result.stderr, "")

    def test_shuffled_input_gives_identical_output(self):
        header, *rows = BRIEF_PRICES.strip().splitlines()
        shuffled = "\n".join([header] + rows[::-1]) + "\n"
        self.assertEqual(self.run_tool(shuffled, BRIEF_RULES).stdout, self.run_tool(BRIEF_PRICES, BRIEF_RULES).stdout)

    def test_ordering_by_date_then_rule_id(self):
        prices = "date,instrument,close\n" + "\n".join([
            "2026-09-02,AAA,90", "2026-09-01,BBB,110", "2026-09-01,AAA,110", "2026-09-02,BBB,90",
            "2026-09-03,AAA,110",
        ]) + "\n"
        # Rule "a" fires last by date, so sorting by id first would put it on top.
        rules = [
            {"id": "c", "instrument": "BBB", "type": "level", "direction": "below", "level": 100},
            {"id": "a", "instrument": "AAA", "type": "level", "direction": "above", "level": 100},
            {"id": "b", "instrument": "AAA", "type": "level", "direction": "below", "level": 100},
        ]
        self.assertEqual(self.run_tool(prices, rules).stdout.splitlines(), [
            "2026-09-02  b  AAA  level below 100",
            "2026-09-02  c  BBB  level below 100",
            "2026-09-03  a  AAA  level above 100",
        ])

    def test_rule_ids_sort_as_strings(self):
        # Documented choice: plain string order, so "r10" sorts before "r2".
        prices = "date,instrument,close\n2026-09-01,X,110\n2026-09-02,X,90\n"
        rules = [{"id": i, "instrument": "X", "type": "level", "direction": "below", "level": 100}
                 for i in ("r2", "r10")]
        self.assertEqual([l.split()[1] for l in self.run_tool(prices, rules).stdout.splitlines()], ["r10", "r2"])

    def test_one_instrument_missing_a_day_does_not_shift_another(self):
        # AAA lacks 09-02; its 1/2 MA uses its own rows only. BBB is unaffected.
        prices = "date,instrument,close\n" + "\n".join([
            "2026-09-01,AAA,10", "2026-09-03,AAA,8", "2026-09-04,AAA,12",
            "2026-09-01,BBB,10", "2026-09-02,BBB,10", "2026-09-03,BBB,8", "2026-09-04,BBB,12",
        ]) + "\n"
        rules = [{"id": n, "instrument": n, "type": "ma_cross", "short": 1, "long": 2, "direction": "above"}
                 for n in ("AAA", "BBB")]
        self.assertEqual(self.run_tool(prices, rules).stdout.splitlines(), [
            "2026-09-04  AAA  AAA  ma_cross 1/2 above",
            "2026-09-04  BBB  BBB  ma_cross 1/2 above",
        ])

    def test_rule_for_unknown_instrument_warns_and_continues(self):
        rules = BRIEF_RULES + [{"id": "r3", "instrument": "WIPRO", "type": "level", "direction": "above", "level": 1}]
        result = self.run_tool(BRIEF_PRICES, rules)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "2026-09-03  r1  INFY  level below 1500\n")
        self.assertIn("WIPRO", result.stderr)

    def test_bad_price_row_warns_but_stdout_stays_clean(self):
        result = self.run_tool(BRIEF_PRICES + "2026-09-04,INFY,oops\n", BRIEF_RULES)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "2026-09-03  r1  INFY  level below 1500\n")
        self.assertIn("line 7", result.stderr)

    def test_no_alerts_prints_nothing(self):
        result = self.run_tool("date,instrument,close\n2026-09-01,INFY,1\n", BRIEF_RULES)
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_fatal_errors_exit_2_without_traceback(self):
        cases = [
            (BRIEF_PRICES, "{broken"),
            (BRIEF_PRICES, [{"id": "x"}]),
            ("date,instrument,close\n2026-09-01,INFY,1\n2026-09-01,INFY,2\n", BRIEF_RULES),
        ]
        for prices, rules in cases:
            with self.subTest(rules=rules):
                result = self.run_tool(prices, rules)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.startswith("error: "), result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_wrong_argument_count_prints_usage(self):
        result = run()
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage", result.stderr)

    def test_missing_file(self):
        result = run("/no/such.csv", self.write("rules.json", BRIEF_RULES))
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot read prices file", result.stderr)

    def test_bundled_example(self):
        result = run(os.path.join(ROOT, "examples", "prices.csv"), os.path.join(ROOT, "examples", "rules.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], "2026-09-03  r1  INFY  level below 1500")
        # Hand-checked: on 2026-10-05 MA5 = 3850 > MA20 = 3833.5; the day before 3827.2 < 3832.3.
        self.assertEqual([l for l in lines if " r2 " in l], ["2026-10-05  r2  TCS   ma_cross 5/20 above"])


if __name__ == "__main__":
    unittest.main()
