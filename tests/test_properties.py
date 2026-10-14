"""Property and metamorphic tests on random data.

Instead of hand-picked examples, these check facts that must hold for *any*
input: changing the input in a way that should not matter must not change the
alerts, and the output must always have the brief's shape.
"""

import random
import re
import unittest
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

from alerts import (LevelRule, MaCrossRule, crossing_days, evaluate, format_alerts,
                    level_signals, ma_signals)

RUNS = 200


def make_series(closes, start=date(2026, 1, 1)):
    return [(start + timedelta(days=i), Decimal(str(c))) for i, c in enumerate(closes)]


def random_closes(rng, n=None, low=95, high=105):
    """Paise prices in a narrow band, so crossings and exact ties are common."""
    n = rng.randint(0, 40) if n is None else n
    return [f"{rng.randint(low * 100, high * 100) / 100:.2f}" for _ in range(n)]


def level_fires(closes, direction, lvl):
    rule = LevelRule("r", "X", direction, Decimal(str(lvl)), str(lvl))
    return crossing_days(level_signals(make_series(closes), rule), direction)


def ma_fires(closes, direction, short, long_):
    rule = MaCrossRule("r", "X", direction, short, long_)
    return crossing_days(ma_signals(make_series(closes), rule), direction)


def reference_level(closes, direction, lvl):
    """Brief's wording, implemented as literally as possible with exact fractions."""
    lvl = Fraction(str(lvl))
    fired = []
    for i in range(1, len(closes)):
        prev, cur = Fraction(closes[i - 1]), Fraction(closes[i])
        if direction == "below" and not prev < lvl and cur < lvl:
            fired.append(date(2026, 1, 1) + timedelta(days=i))
        if direction == "above" and not prev > lvl and cur > lvl:
            fired.append(date(2026, 1, 1) + timedelta(days=i))
    return fired


class LevelAgainstReferenceTest(unittest.TestCase):
    def test_random_series_match_reference(self):
        rng = random.Random(2024)
        for _ in range(RUNS):
            closes = random_closes(rng)
            lvl = rng.choice([100, "100.00", "99.5", "100.25", rng.randint(9500, 10500) / 100])
            direction = rng.choice(["above", "below"])
            with self.subTest(closes=closes, level=lvl, direction=direction):
                self.assertEqual(level_fires(closes, direction, lvl), reference_level(closes, direction, lvl))


class MetamorphicTest(unittest.TestCase):
    """Transform the input in a way that must not change which days fire."""

    def test_converting_rupees_to_paise_changes_nothing(self):
        # Multiplying every price (and the level) by 100 keeps every comparison the same.
        rng = random.Random(1)
        for _ in range(RUNS):
            closes = random_closes(rng)
            scaled = [str(Decimal(c) * 100) for c in closes]
            direction = rng.choice(["above", "below"])
            short = rng.randint(1, 4)
            long_ = rng.randint(short + 1, 8)
            with self.subTest(closes=closes):
                self.assertEqual(level_fires(closes, direction, 100), level_fires(scaled, direction, 10000))
                self.assertEqual(ma_fires(closes, direction, short, long_), ma_fires(scaled, direction, short, long_))

    def test_adding_a_constant_to_all_prices_does_not_change_ma_crosses(self):
        # Both averages shift by the same amount, so their difference is unchanged.
        rng = random.Random(2)
        for _ in range(RUNS):
            closes = random_closes(rng)
            shifted = [str(Decimal(c) + Decimal("1234.56")) for c in closes]
            short = rng.randint(1, 4)
            long_ = rng.randint(short + 1, 8)
            direction = rng.choice(["above", "below"])
            with self.subTest(closes=closes):
                self.assertEqual(ma_fires(closes, direction, short, long_),
                                 ma_fires(shifted, direction, short, long_))

    def test_mirroring_prices_swaps_above_and_below(self):
        # Reflect around 200: p -> 400 - p. Crossing below 100 becomes crossing above 300.
        rng = random.Random(3)
        for _ in range(RUNS):
            closes = random_closes(rng)
            mirrored = [str(400 - Decimal(c)) for c in closes]
            short = rng.randint(1, 4)
            long_ = rng.randint(short + 1, 8)
            with self.subTest(closes=closes):
                self.assertEqual(level_fires(closes, "below", 100), level_fires(mirrored, "above", 300))
                self.assertEqual(ma_fires(closes, "above", short, long_), ma_fires(mirrored, "below", short, long_))

    def test_trailing_zeros_and_number_spelling_do_not_matter(self):
        rng = random.Random(4)
        for _ in range(RUNS):
            closes = random_closes(rng)
            respelled = [rng.choice([c, c + "000", str(Decimal(c).normalize())]) for c in closes]
            with self.subTest(closes=closes):
                self.assertEqual(ma_fires(closes, "above", 2, 5), ma_fires(respelled, "above", 2, 5))
                self.assertEqual(level_fires(closes, "below", 100), level_fires(respelled, "below", 100))

    def test_a_long_window_never_fires_before_row_long_plus_one(self):
        rng = random.Random(5)
        for _ in range(RUNS):
            closes = random_closes(rng)
            short = rng.randint(1, 5)
            long_ = rng.randint(short + 1, 12)
            first_allowed = date(2026, 1, 1) + timedelta(days=long_)  # row long+1 (0-based index long)
            for d in ma_fires(closes, rng.choice(["above", "below"]), short, long_):
                self.assertGreaterEqual(d, first_allowed)


def random_portfolio(rng):
    """Several instruments with random gaps, plus random rules over them."""
    instruments = rng.sample(["INFY", "TCS", "HDFCBANK", "M&M", "WIPRO", "BAJAJ-AUTO"], rng.randint(1, 4))
    series = {}
    for inst in instruments:
        d, points = date(2026, 1, 1), []
        for _ in range(rng.randint(0, 35)):
            d += timedelta(days=rng.choice([1, 1, 1, 3]))  # weekends / holidays
            points.append((d, Decimal(f"{rng.randint(9500, 10500) / 100:.2f}")))
        series[inst] = points
    rules = []
    for i in range(rng.randint(0, 6)):
        inst = rng.choice(instruments)
        direction = rng.choice(["above", "below"])
        if rng.random() < 0.5:
            rules.append(LevelRule(f"r{i}", inst, direction, Decimal(100), "100"))
        else:
            short = rng.randint(1, 4)
            rules.append(MaCrossRule(f"r{i}", inst, direction, short, rng.randint(short + 1, 8)))
    return series, rules


LINE = re.compile(r"^\d{4}-\d{2}-\d{2}  \S.*$")


class PortfolioPropertiesTest(unittest.TestCase):
    def test_output_is_sorted_aligned_unique_and_well_formed(self):
        rng = random.Random(6)
        for _ in range(RUNS):
            series, rules = random_portfolio(rng)
            alerts = evaluate(series, rules)
            lines = format_alerts(alerts)
            with self.subTest(rules=rules):
                self.assertEqual(alerts, sorted(alerts, key=lambda a: (a[0], a[1])))
                self.assertEqual(len(lines), len(set(lines)))
                for line in lines:
                    self.assertRegex(line, LINE)
                    self.assertEqual(line, line.rstrip())  # no trailing spaces
                # The description column starts at the same position on every line.
                starts = {len(l) - len(a[3]) for l, a in zip(lines, alerts)}
                self.assertLessEqual(len(starts), 1)

    def test_each_rule_is_evaluated_independently(self):
        # Running all rules together gives exactly the union of running each alone.
        rng = random.Random(7)
        for _ in range(RUNS):
            series, rules = random_portfolio(rng)
            together = evaluate(series, rules)
            alone = sorted((a for r in rules for a in evaluate(series, [r])), key=lambda a: (a[0], a[1]))
            self.assertEqual(together, alone)

    def test_other_instruments_data_does_not_affect_an_instrument(self):
        rng = random.Random(8)
        for _ in range(RUNS):
            series, rules = random_portfolio(rng)
            for inst in series:
                own_rules = [r for r in rules if r.instrument == inst]
                with self.subTest(instrument=inst):
                    self.assertEqual(evaluate(series, own_rules), evaluate({inst: series[inst]}, own_rules))

    def test_duplicating_a_rule_under_a_new_id_duplicates_its_alerts(self):
        rng = random.Random(9)
        for _ in range(RUNS):
            series, rules = random_portfolio(rng)
            if not rules:
                continue
            original = rules[0]
            twin = type(original)(**{**original.__dict__, "id": "zz-twin"})
            days = [a[0] for a in evaluate(series, [original])]
            self.assertEqual([a[0] for a in evaluate(series, [twin])], days)


if __name__ == "__main__":
    unittest.main()
