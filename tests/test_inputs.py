"""Parsing and validation of the prices CSV and the rules JSON."""

import contextlib
import io
import unittest
from datetime import date
from decimal import Decimal

from alerts import AlertError, LevelRule, MaCrossRule, load_prices, load_rules
from tests.helpers import TempFiles

HEADER = "date,instrument,close\n"


class PricesTest(TempFiles, unittest.TestCase):
    def load(self, text, encoding="utf-8"):
        """Load prices; return (series, warnings printed to stderr)."""
        path = self.write("prices.csv", text, encoding)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            result = load_prices(path)
        return result, err.getvalue()

    def test_out_of_order_rows_are_sorted_per_instrument(self):
        prices, _ = self.load(HEADER + "2026-09-03,INFY,3\n2026-09-01,TCS,10\n2026-09-01,INFY,1\n2026-09-02,INFY,2\n")
        self.assertEqual([c for _, c in prices["INFY"]], [Decimal(1), Decimal(2), Decimal(3)])
        self.assertEqual(prices["TCS"], [(date(2026, 9, 1), Decimal(10))])

    def test_closes_are_exact_decimals(self):
        prices, _ = self.load(HEADER + "2026-09-01,INFY,1520.50\n")
        self.assertEqual(prices["INFY"][0][1], Decimal("1520.50"))

    def test_header_variations_bom_spaces_case_order_extra_columns_crlf(self):
        text = "﻿ Close ,Volume,INSTRUMENT, Date \r\n1520.5,100,INFY,2026-09-01\r\n"
        prices, warnings = self.load(text)
        self.assertEqual(prices, {"INFY": [(date(2026, 9, 1), Decimal("1520.5"))]})
        self.assertEqual(warnings, "")

    def test_whitespace_and_case_in_values_are_normalised(self):
        prices, _ = self.load(HEADER + " 2026-09-01 , infy , 1520.50 \n")
        self.assertIn("INFY", prices)

    def test_blank_lines_are_ignored_silently(self):
        prices, warnings = self.load(HEADER + "\n2026-09-01,INFY,1\n\n,,\n2026-09-02,INFY,2\n")
        self.assertEqual(len(prices["INFY"]), 2)
        self.assertEqual(warnings, "")

    def test_bad_rows_are_skipped_with_line_number(self):
        bad_rows = [
            "2026-09-02,INFY,",            # empty close
            "2026-09-03,INFY,N/A",         # non-numeric
            "2026-09-04,INFY,NaN",         # Decimal parses NaN; must be rejected
            "2026-09-05,INFY,Infinity",
            "2026-09-06,INFY,-5",          # negative price
            "2026-09-07,INFY,0",
            '2026-09-08,INFY,"1,520.50"',  # thousands separator: ambiguous, rejected
            "2026-02-30,INFY,10",          # impossible date
            "03/09/2026,INFY,10",          # non-ISO date
            ",INFY,10",                    # missing date
            "2026-09-09,,10",              # missing instrument
            "2026-09-10,INFY",             # too few fields
            "2026-09-11,INFY,1e-1000000",  # absurd magnitude would make huge integers
            "2026-09-12,INFY,1E+20",       # more than 15 integer digits
            "2026-09-13,INFY,1." + "0" * 31,  # more than 30 decimal places
        ]
        text = HEADER + "2026-09-01,INFY,1\n" + "\n".join(bad_rows) + "\n"
        prices, warnings = self.load(text)
        self.assertEqual(prices["INFY"], [(date(2026, 9, 1), Decimal(1))])
        lines = warnings.strip().splitlines()
        self.assertEqual(len(lines), len(bad_rows))
        for n, line in enumerate(lines, start=3):
            self.assertIn(f"line {n}:", line)

    def test_plausible_extremes_are_accepted(self):
        text = HEADER + "2026-09-01,A,0.000001\n2026-09-01,B,999999999999999\n2026-09-01,C,1.5E3\n" \
               "2026-09-01,D,1." + "0" * 29 + "1\n"
        prices, warnings = self.load(text)
        self.assertEqual(sorted(prices), ["A", "B", "C", "D"])
        self.assertEqual(warnings, "")

    def test_exact_duplicate_row_is_dropped_with_warning(self):
        prices, warnings = self.load(HEADER + "2026-09-01,INFY,1520.5\n2026-09-01,INFY,1520.50\n")
        self.assertEqual(len(prices["INFY"]), 1)
        self.assertIn("duplicate", warnings)

    def test_conflicting_duplicate_is_fatal(self):
        with self.assertRaisesRegex(AlertError, "conflicting closes"):
            self.load(HEADER + "2026-09-01,INFY,1520\n2026-09-01,INFY,1530\n")

    def test_header_only_gives_no_series(self):
        prices, _ = self.load(HEADER)
        self.assertEqual(prices, {})

    def test_empty_file_is_fatal(self):
        with self.assertRaisesRegex(AlertError, "empty"):
            self.load("")

    def test_missing_column_is_fatal(self):
        with self.assertRaisesRegex(AlertError, "missing column.*close"):
            self.load("date,instrument,price\n2026-09-01,INFY,1\n")

    def test_missing_file_is_fatal(self):
        with self.assertRaisesRegex(AlertError, "cannot read"):
            load_prices("/no/such/prices.csv")


class RulesTest(TempFiles, unittest.TestCase):
    def load(self, rules):
        return load_rules(self.write("rules.json", rules))

    def assertRejected(self, rule, message):
        with self.assertRaisesRegex(AlertError, message):
            self.load([rule])

    LEVEL = {"id": "r1", "instrument": "INFY", "type": "level", "direction": "below", "level": 1500}
    MA = {"id": "r2", "instrument": "TCS", "type": "ma_cross", "short": 5, "long": 20, "direction": "above"}

    def test_brief_rules_parse(self):
        level, ma = self.load([self.LEVEL, self.MA])
        self.assertEqual(level, LevelRule("r1", "INFY", "below", Decimal(1500), "1500"))
        self.assertEqual(ma, MaCrossRule("r2", "TCS", "above", 5, 20))

    def test_fractional_level_is_exact_and_printed_as_written(self):
        (rule,) = self.load('[{"id": "a", "instrument": "X", "type": "level", '
                            '"direction": "above", "level": 1500.50}]')
        self.assertEqual(rule.level, Decimal("1500.50"))
        self.assertEqual(rule.describe(), "level above 1500.50")

    def test_empty_list_is_valid(self):
        self.assertEqual(self.load([]), [])

    def test_extra_fields_are_ignored(self):
        self.load([dict(self.LEVEL, note="ignored")])

    def test_invalid_rules(self):
        cases = [
            (dict(self.LEVEL, type="percent"), "unknown rule type"),
            (dict(self.LEVEL, direction="up"), "direction"),
            (dict(self.LEVEL, level="1500"), "'level' must be a number"),
            (dict(self.LEVEL, level=True), "'level' must be a number"),
            ({k: v for k, v in self.LEVEL.items() if k != "level"}, "'level' must be a number"),
            (dict(self.LEVEL, id=""), "'id'"),
            (dict(self.LEVEL, id=7), "'id'"),
            (dict(self.LEVEL, instrument=None), "'instrument'"),
            (dict(self.MA, short=0), "'short' must be a positive integer"),
            (dict(self.MA, short=5.5), "'short' must be a positive integer"),
            (dict(self.MA, short="5"), "'short' must be a positive integer"),
            (dict(self.MA, short=True), "'short' must be a positive integer"),
            (dict(self.MA, long=-20), "'long' must be a positive integer"),
            (dict(self.MA, short=20, long=20), "must be less than"),
            (dict(self.MA, short=30, long=20), "must be less than"),
            ("not an object", "expected an object"),
        ]
        for rule, message in cases:
            with self.subTest(rule=rule):
                self.assertRejected(rule, message)

    def test_duplicate_ids_rejected(self):
        with self.assertRaisesRegex(AlertError, "duplicate rule id 'r1'"):
            self.load([self.LEVEL, dict(self.MA, id="r1")])

    def test_not_a_list_rejected(self):
        with self.assertRaisesRegex(AlertError, "JSON list"):
            self.load(self.LEVEL)

    def test_invalid_json_rejected(self):
        with self.assertRaisesRegex(AlertError, "not valid JSON"):
            self.load('[{"id": "r1",]')


if __name__ == "__main__":
    unittest.main()
