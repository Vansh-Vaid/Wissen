"""Scenario tests, grouped by the sentence of the brief each one checks.

Each test runs the real CLI on a small, readable prices file, the way the
evaluators will run it on theirs.
"""

import os
import random
import subprocess
import sys
import time
import unittest

from tests.helpers import TempFiles

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "alerts.py")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")

# The brief's expected output, byte for byte (column spacing measured from the PDF).
BRIEF_OUTPUT = (
    "2026-09-03  r1  INFY  level below 1500\n"
    "2026-09-24  r2  TCS   ma_cross 5/20 above\n"
)

HEADER = "date,instrument,close\n"


def csv_rows(*rows):
    return HEADER + "".join(r + "\n" for r in rows)


def level(rule_id, instrument, direction, value):
    return {"id": rule_id, "instrument": instrument, "type": "level", "direction": direction, "level": value}


def ma(rule_id, instrument, direction, short, long_):
    return {"id": rule_id, "instrument": instrument, "type": "ma_cross",
            "short": short, "long": long_, "direction": direction}


def daily(instrument, closes, start_day=1):
    """Rows for consecutive September 2026 dates (fine for tests: rows, not calendar, matter)."""
    from datetime import date, timedelta
    d0 = date(2026, 9, start_day)
    return [f"{d0 + timedelta(days=i)},{instrument},{c}" for i, c in enumerate(closes)]


class Scenario(TempFiles, unittest.TestCase):
    def run_cli(self, prices, rules, prices_encoding="utf-8"):
        p = prices if os.path.isabs(prices) else self.write("prices.csv", prices, prices_encoding)
        r = rules if isinstance(rules, str) and os.path.isabs(rules) else self.write("rules.json", rules)
        return subprocess.run([sys.executable, SCRIPT, p, r], capture_output=True, text=True)

    def alerts(self, prices, rules):
        """Run and return stdout lines with column padding collapsed, asserting a clean exit."""
        result = self.run_cli(prices, rules)
        self.assertEqual(result.returncode, 0, result.stderr)
        return [" ".join(line.split()) for line in result.stdout.splitlines()]


# ---------------------------------------------------------------------------
# "Output: ... One line per alert, ordered by date then rule id.
#  Print nothing for days on which no rule fires."
# ---------------------------------------------------------------------------

class OutputMatchesBrief(Scenario):
    BRIEF_PRICES = os.path.join(FIXTURES, "brief_full_prices.csv")
    BRIEF_RULES = os.path.join(FIXTURES, "brief_rules.json")

    def test_reproduces_brief_output_byte_for_byte(self):
        # Fixture: the brief's five price rows verbatim, plus TCS history from
        # August (a 5/20 cross needs >= 21 rows) and INFY staying below 1500.
        result = self.run_cli(self.BRIEF_PRICES, self.BRIEF_RULES)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, BRIEF_OUTPUT)
        self.assertEqual(result.stderr, "")

    def test_brief_fixture_near_miss_day_before_the_cross(self):
        # 2026-09-23: MA5 = 3911.0 vs MA20 = 3911.0625, so short is still just below.
        # Firing a day early here would mean the comparison or window is off by one.
        self.assertNotIn("2026-09-23", self.run_cli(self.BRIEF_PRICES, self.BRIEF_RULES).stdout)

    def test_brief_fixture_any_row_order_gives_same_output(self):
        with open(self.BRIEF_PRICES) as f:
            header, *rows = f.read().splitlines()
        rng = random.Random(42)
        for _ in range(3):
            rng.shuffle(rows)
            path = self.write("shuffled.csv", "\n".join([header] + rows) + "\n")
            self.assertEqual(self.run_cli(path, self.BRIEF_RULES).stdout, BRIEF_OUTPUT)

    def test_no_blank_lines_and_nothing_printed_when_nothing_fires(self):
        result = self.run_cli(csv_rows(*daily("INFY", [1600, 1610, 1620])), [level("r1", "INFY", "below", 1500)])
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_columns_stay_aligned_with_long_ids_and_tickers(self):
        prices = csv_rows(*daily("BAJFINANCE", [110, 90]), *daily("TCS", [110, 90]))
        rules = [level("r1", "TCS", "below", 100), level("drop-alert", "BAJFINANCE", "below", 100)]
        out = self.run_cli(prices, rules).stdout.splitlines()
        self.assertEqual(out, [
            "2026-09-02  drop-alert  BAJFINANCE  level below 100",
            "2026-09-02  r1          TCS         level below 100",
        ])

    def test_same_rule_firing_on_many_days_each_gets_a_line(self):
        prices = csv_rows(*daily("INFY", [1510, 1490, 1510, 1490, 1510, 1490]))
        self.assertEqual(self.alerts(prices, [level("r1", "INFY", "below", 1500)]), [
            "2026-09-02 r1 INFY level below 1500",
            "2026-09-04 r1 INFY level below 1500",
            "2026-09-06 r1 INFY level below 1500",
        ])

    def test_many_rules_same_day_sorted_by_id_regardless_of_rule_file_order(self):
        prices = csv_rows(*daily("INFY", [1510, 1490]))
        rules = [level(i, "INFY", "below", 1500) for i in ("r3", "r1", "r2")]
        self.assertEqual([l.split()[1] for l in self.alerts(prices, rules)], ["r1", "r2", "r3"])

    def test_level_printed_as_written_in_rules(self):
        prices = csv_rows(*daily("INFY", ["1500.60", "1500.40"]))
        rules = '[{"id":"r1","instrument":"INFY","type":"level","direction":"below","level":1500.50}]'
        self.assertEqual(self.alerts(prices, rules), ["2026-09-02 r1 INFY level below 1500.50"])


# ---------------------------------------------------------------------------
# "A level rule fires on the first day the close crosses the level in the
#  given direction (it was on the other side the previous day)."
# ---------------------------------------------------------------------------

class LevelScenarios(Scenario):
    def test_big_gap_through_level_fires_once(self):
        prices = csv_rows(*daily("INFY", [1600, 1400, 1300, 1200]))
        self.assertEqual(self.alerts(prices, [level("r1", "INFY", "below", 1500)]),
                         ["2026-09-02 r1 INFY level below 1500"])

    def test_previous_day_means_previous_trading_row_across_missing_dates(self):
        # No INFY row for 09-02..09-06 (holiday / missing data): 09-07 is compared with 09-01.
        prices = csv_rows("2026-09-01,INFY,1510", "2026-09-07,INFY,1490")
        self.assertEqual(self.alerts(prices, [level("r1", "INFY", "below", 1500)]),
                         ["2026-09-07 r1 INFY level below 1500"])

    def test_opposite_rules_on_one_instrument_alternate(self):
        prices = csv_rows(*daily("INFY", [1510, 1490, 1510, 1490]))
        rules = [level("dn", "INFY", "below", 1500), level("up", "INFY", "above", 1500)]
        self.assertEqual(self.alerts(prices, rules), [
            "2026-09-02 dn INFY level below 1500",
            "2026-09-03 up INFY level above 1500",
            "2026-09-04 dn INFY level below 1500",
        ])

    def test_resting_exactly_on_level_then_breaking_fires_on_the_break(self):
        prices = csv_rows(*daily("INFY", [1510, 1500, 1500, 1500, 1499]))
        self.assertEqual(self.alerts(prices, [level("r1", "INFY", "below", 1500)]),
                         ["2026-09-05 r1 INFY level below 1500"])

    def test_paise_precision(self):
        prices = csv_rows(*daily("INFY", ["1500.01", "1500.00", "1499.99"]))
        self.assertEqual(self.alerts(prices, [level("r1", "INFY", "below", 1500)]),
                         ["2026-09-03 r1 INFY level below 1500"])

    def test_starting_below_never_fires_until_it_goes_back_above_and_down_again(self):
        prices = csv_rows(*daily("INFY", [1490, 1480, 1510, 1495]))
        self.assertEqual(self.alerts(prices, [level("r1", "INFY", "below", 1500)]),
                         ["2026-09-04 r1 INFY level below 1500"])

    def test_level_out_of_range_never_fires(self):
        prices = csv_rows(*daily("INFY", [1510, 1490]))
        self.assertEqual(self.alerts(prices, [level("r1", "INFY", "above", 99999)]), [])


# ---------------------------------------------------------------------------
# "An ma_cross rule fires on the day the short moving average crosses the long
#  one in the given direction. Moving averages need a full window of days."
# ---------------------------------------------------------------------------

class MaCrossScenarios(Scenario):
    # short=2, long=3. MA2 - MA3 from day 3: -0.5, -0.5, +1.5  -> cross above on day 5.
    CROSS_UP = [10, 10, 7, 10, 13]

    def test_cross_with_exactly_long_plus_one_rows(self):
        prices = csv_rows(*daily("TCS", [10, 10, 7, 20]))  # 4 rows, long = 3
        self.assertEqual(self.alerts(prices, [ma("r2", "TCS", "above", 2, 3)]),
                         ["2026-09-04 r2 TCS ma_cross 2/3 above"])

    def test_exactly_long_rows_can_never_fire(self):
        prices = csv_rows(*daily("TCS", [1, 1, 100]))  # MA3 exists only on the last day
        self.assertEqual(self.alerts(prices, [ma("r2", "TCS", "above", 2, 3)]), [])

    def test_fewer_rows_than_long_window_is_silent(self):
        result = self.run_cli(csv_rows(*daily("TCS", [1, 2, 3])), [ma("r2", "TCS", "above", 5, 20)])
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_hand_computed_cross_up_and_down_with_two_rules(self):
        prices = csv_rows(*daily("TCS", self.CROSS_UP + [7, 4]))
        # Continue: day6 MA2 = (13+7)/2 = 10, MA3 = (10+13+7)/3 = 10 -> exact tie, not below yet.
        #           day7 MA2 = (7+4)/2 = 5.5, MA3 = (13+7+4)/3 = 8 -> below: fires on day 7.
        rules = [ma("up", "TCS", "above", 2, 3), ma("dn", "TCS", "below", 2, 3)]
        self.assertEqual(self.alerts(prices, rules), [
            "2026-09-05 up TCS ma_cross 2/3 above",
            "2026-09-07 dn TCS ma_cross 2/3 below",
        ])

    def test_windows_count_trading_rows_not_calendar_days(self):
        # Same closes as CROSS_UP but spread over weekends: alert lands on the 5th row's date.
        dates = ["2026-09-03", "2026-09-04", "2026-09-07", "2026-09-08", "2026-09-09"]
        prices = csv_rows(*[f"{d},TCS,{c}" for d, c in zip(dates, self.CROSS_UP)])
        self.assertEqual(self.alerts(prices, [ma("r2", "TCS", "above", 2, 3)]),
                         ["2026-09-09 r2 TCS ma_cross 2/3 above"])

    def test_skipped_bad_row_does_not_count_towards_the_window(self):
        # The "oops" row is dropped, so the remaining 5 rows behave exactly like CROSS_UP.
        rows = daily("TCS", self.CROSS_UP)
        rows.insert(2, "2026-09-02T12,TCS,oops")
        result = self.run_cli(csv_rows(*rows), [ma("r2", "TCS", "above", 2, 3)])
        self.assertEqual(result.stdout.split(), "2026-09-05 r2 TCS ma_cross 2/3 above".split())
        self.assertIn("line 4", result.stderr)

    def test_two_window_sizes_on_one_instrument_are_independent(self):
        prices = csv_rows(*daily("TCS", self.CROSS_UP))
        rules = [ma("a", "TCS", "above", 2, 3), ma("b", "TCS", "above", 3, 5)]
        # 3/5 needs 6 rows to fire; only 5 exist.
        self.assertEqual(self.alerts(prices, rules), ["2026-09-05 a TCS ma_cross 2/3 above"])

    def test_short_window_of_one_is_the_close_itself(self):
        prices = csv_rows(*daily("TCS", [10, 10, 9, 12]))  # close vs MA2: 0, -0.5, +1.5
        self.assertEqual(self.alerts(prices, [ma("r", "TCS", "above", 1, 2)]),
                         ["2026-09-04 r TCS ma_cross 1/2 above"])

    def test_brief_windows_on_flat_then_rising_prices(self):
        # 20 flat days: MA5 == MA20 (a tie, not a cross). Day 21 rises: fires on day 21.
        prices = csv_rows(*daily("TCS", [3900] * 20 + [3901]))
        self.assertEqual(self.alerts(prices, [ma("r2", "TCS", "above", 5, 20)]),
                         ["2026-09-21 r2 TCS ma_cross 5/20 above"])


# ---------------------------------------------------------------------------
# "Prices file (CSV, one row per instrument per trading day, dates may be out
#  of order)" + "a prices file we bring, which will contain conditions you
#  have not seen". Real-world file problems.
# ---------------------------------------------------------------------------

class RealWorldPriceFiles(Scenario):
    RULE = [level("r1", "INFY", "below", 1500)]
    EXPECTED = ["2026-09-02 r1 INFY level below 1500"]

    def test_excel_style_file(self):
        # BOM, CRLF, quoted fields, capitalised header with spaces, extra column.
        text = '﻿"Date","Instrument","Close","Volume"\r\n' \
               '"2026-09-01","INFY","1510.00","100"\r\n"2026-09-02","INFY","1490.00","120"\r\n'
        self.assertEqual(self.alerts(text, self.RULE), self.EXPECTED)

    def test_latin1_file_still_loads_with_warning(self):
        text = "date,instrument,close,note\n2026-09-01,INFY,1510,caf\xe9\n2026-09-02,INFY,1490,\n"
        result = self.run_cli(text, self.RULE, prices_encoding="latin-1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(), self.EXPECTED[0].split())
        self.assertIn("not valid UTF-8", result.stderr)

    def test_concatenated_files_with_repeated_header(self):
        text = csv_rows("2026-09-01,INFY,1510") + csv_rows("2026-09-02,INFY,1490")
        result = self.run_cli(text, self.RULE)
        self.assertEqual(result.stdout.split(), self.EXPECTED[0].split())
        self.assertIn("line 3", result.stderr)  # the repeated header row is reported, then skipped

    def test_trailing_commas_and_missing_optional_trailing_column(self):
        text = "date,instrument,close,volume\n2026-09-01,INFY,1510,\n2026-09-02,INFY,1490\n"
        result = self.run_cli(text, self.RULE)
        self.assertEqual((result.stdout.split(), result.stderr), (self.EXPECTED[0].split(), ""))

    def test_lowercase_and_padded_tickers_match_the_rule(self):
        text = csv_rows("2026-09-01, infy ,1510", "2026-09-02,Infy,1490")
        self.assertEqual(self.alerts(text, self.RULE), self.EXPECTED)

    def test_same_day_in_two_spellings_is_a_duplicate(self):
        result = self.run_cli(csv_rows("2026-09-01,INFY,1510", "2026-09-01,infy,1510.00"), self.RULE)
        self.assertEqual(result.returncode, 0)
        self.assertIn("duplicate", result.stderr)

    def test_year_boundary_and_leap_day_sorting(self):
        text = csv_rows("2028-03-01,INFY,1480", "2027-12-31,INFY,1510", "2028-02-29,INFY,1490",
                        "2028-01-03,INFY,1520")
        self.assertEqual(self.alerts(text, self.RULE), ["2028-02-29 r1 INFY level below 1500"])

    def test_invalid_calendar_date_skipped(self):
        result = self.run_cli(csv_rows("2026-09-01,INFY,1510", "2026-02-29,INFY,1400", "2026-09-02,INFY,1490"),
                              self.RULE)
        self.assertEqual(result.stdout.split(), self.EXPECTED[0].split())
        self.assertIn("bad date", result.stderr)

    def test_tickers_with_symbols_and_spaces(self):
        text = csv_rows(*daily("M&M", [110, 90]), *daily("NIFTY 50", [110, 90]), *daily("BAJAJ-AUTO", [110, 90]))
        rules = [level("a", "M&M", "below", 100), level("b", "NIFTY 50", "below", 100),
                 level("c", "BAJAJ-AUTO", "below", 100)]
        out = self.run_cli(text, rules).stdout.splitlines()
        self.assertEqual([l.split("  ")[0:3] for l in out][0], ["2026-09-02", "a", "M&M"])
        self.assertIn("NIFTY 50", out[1])
        self.assertEqual(len(out), 3)

    def test_instruments_without_rules_are_ignored(self):
        text = csv_rows(*daily("INFY", [1510, 1490]), *daily("WIPRO", [1, 2, 3]))
        self.assertEqual(self.alerts(text, self.RULE), self.EXPECTED)

    def test_every_row_bad_gives_warnings_and_no_alerts(self):
        result = self.run_cli(csv_rows("x,INFY,1", "2026-09-01,INFY,abc"), self.RULE)
        self.assertEqual((result.returncode, result.stdout), (0, ""))
        self.assertEqual(result.stderr.count("warning"), 3)  # 2 bad rows + no prices for INFY

    def test_no_header_row_is_fatal_with_clear_message(self):
        result = self.run_cli("2026-09-01,INFY,1510\n", self.RULE)
        self.assertEqual(result.returncode, 2)
        self.assertIn("missing column", result.stderr)

    def test_semicolon_delimited_file_is_fatal_with_clear_message(self):
        result = self.run_cli("date;instrument;close\n2026-09-01;INFY;1510\n", self.RULE)
        self.assertEqual(result.returncode, 2)
        self.assertIn("missing column", result.stderr)

    def test_large_file_runs_quickly(self):
        # 20 instruments x 3000 days with 50/200 averages; must stay interactive.
        from datetime import date, timedelta
        rng = random.Random(9)
        rows = []
        for k in range(20):
            p = 1000.0
            for i in range(3000):
                p = max(1.0, p * (1 + rng.gauss(0, 0.01)))
                rows.append(f"{date(2010, 1, 1) + timedelta(days=i)},I{k},{p:.2f}")
        rng.shuffle(rows)
        rules = [ma(f"m{k}", f"I{k}", "above", 50, 200) for k in range(20)]
        started = time.monotonic()
        result = self.run_cli(csv_rows(*rows), rules)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(time.monotonic() - started, 15)
        self.assertGreater(len(result.stdout.splitlines()), 0)


# ---------------------------------------------------------------------------
# "Rules file (JSON, any number of rules)"
# ---------------------------------------------------------------------------

class RulesFiles(Scenario):
    PRICES = csv_rows(*daily("INFY", [1510, 1490]))

    def test_zero_rules(self):
        self.assertEqual(self.alerts(self.PRICES, []), [])

    def test_many_rules(self):
        rules = [level(f"r{i:04d}", "INFY", "below", 1500) for i in range(500)]
        out = self.alerts(self.PRICES, rules)
        self.assertEqual(len(out), 500)
        self.assertEqual(out[0], "2026-09-02 r0000 INFY level below 1500")

    def test_keywords_tolerate_case_and_spaces(self):
        rules = [{"id": "r1", "instrument": "infy", "type": " Level", "direction": "BELOW ", "level": 1500}]
        self.assertEqual(self.alerts(self.PRICES, rules), ["2026-09-02 r1 infy level below 1500"])

    def test_brief_rules_file_layout_with_bom(self):
        with open(os.path.join(FIXTURES, "brief_rules.json"), encoding="utf-8") as f:
            text = "﻿" + f.read()
        path = self.write("rules.json", text)
        self.assertEqual(self.alerts(self.PRICES, path), ["2026-09-02 r1 INFY level below 1500"])

    def test_empty_rules_file_is_fatal(self):
        result = self.run_cli(self.PRICES, "")
        self.assertEqual(result.returncode, 2)
        self.assertIn("not valid JSON", result.stderr)

    def test_one_bad_rule_rejects_the_file_and_names_the_rule(self):
        rules = [level("r1", "INFY", "below", 1500), ma("r2", "TCS", "above", 20, 5)]
        result = self.run_cli(self.PRICES, rules)
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("rule 'r2'", result.stderr)


if __name__ == "__main__":
    unittest.main()
