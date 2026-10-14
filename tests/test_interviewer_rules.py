"""The interviewer writes their own rules: same keys, any values.

Generates random but valid rules files (random ids, instruments, levels,
windows, directions, key order, letter case) and random price files, runs the
real command, and compares its output line for line with an independent,
deliberately simple implementation written here from the brief's wording.
"""

import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "alerts.py")
RUNS = 150


# ---------------------------------------------------------------------------
# Independent reference, straight from the brief
# ---------------------------------------------------------------------------

def reference_output(price_rows, rules):
    by_inst = {}
    for d, inst, close in price_rows:
        by_inst.setdefault(inst.strip().upper(), []).append((d, Fraction(close)))
    for points in by_inst.values():
        points.sort()

    alerts = []
    for rule in rules:
        points = by_inst.get(rule["instrument"].strip().upper(), [])
        direction = rule["direction"].strip().lower()
        kind = rule["type"].strip().lower()
        for i in range(1, len(points)):
            if kind == "level":
                lvl = Fraction(str(rule["level"]))
                prev, cur = points[i - 1][1] - lvl, points[i][1] - lvl
            else:
                s, l = rule["short"], rule["long"]
                if i < l:  # yesterday (row i-1) needs a full long window: i-1 >= l-1
                    continue
                closes = [c for _, c in points]

                def ma(end, n):
                    return sum(closes[end - n + 1:end + 1]) / n
                prev, cur = ma(i - 1, s) - ma(i - 1, l), ma(i, s) - ma(i, l)
            crossed = (prev <= 0 < cur) if direction == "above" else (prev >= 0 > cur)
            if crossed:
                if kind == "level":
                    what = f"level {direction} {rule['level']}"
                else:
                    what = f"ma_cross {rule['short']}/{rule['long']} {direction}"
                alerts.append((points[i][0].isoformat(), rule["id"].strip(), rule["instrument"].strip(), what))

    alerts.sort(key=lambda a: (a[0], a[1]))
    w_id = max((len(a[1]) for a in alerts), default=0)
    w_inst = max((len(a[2]) for a in alerts), default=0)
    return "".join(f"{d}  {i.ljust(w_id)}  {n.ljust(w_inst)}  {w}\n" for d, i, n, w in alerts)


# ---------------------------------------------------------------------------
# Random interviewer-style inputs
# ---------------------------------------------------------------------------

TICKERS = ["INFY", "TCS", "HDFCBANK", "RELIANCE", "M&M", "WIPRO", "BAJAJ-AUTO", "ITC"]


def random_prices(rng):
    rows = []
    for inst in rng.sample(TICKERS, rng.randint(1, 4)):
        d = date(2026, rng.randint(1, 12), rng.randint(1, 28))
        price = rng.randint(100, 4000)
        for _ in range(rng.randint(0, 60)):
            d += timedelta(days=rng.choice([1, 1, 1, 1, 3]))  # weekends and holidays
            price = max(1, price + rng.randint(-40, 40))
            paise = rng.choice([0, 0, rng.randint(0, 99)])
            rows.append((d, inst, f"{price}.{paise:02d}"))
    rng.shuffle(rows)  # "dates may be out of order"
    return rows


def random_case(rng, word):
    return rng.choice([word, word.upper(), word.capitalize(), f" {word} "])


def random_level(rng, rows):
    choice = rng.random()
    if rows and choice < 0.3:
        # Exactly equal to a real close, to force "touching is not crossing" cases.
        close = rng.choice(rows)[2]
        return int(close.split(".")[0]) if close.endswith(".00") and rng.random() < 0.5 else float(close)
    if choice < 0.6:
        return rng.randint(50, 4100)
    return round(rng.uniform(50, 4100), rng.randint(1, 4))


def random_rules(rng, rows):
    instruments = sorted({r[1] for r in rows}) or ["INFY"]
    rules, used_ids = [], set()
    for n in range(rng.randint(0, 8)):
        rule_id = rng.choice([f"r{n}", f"R{n}", f"alert-{n}", f"rule_{rng.randint(0, 999)}_{n}", f"{n}"])
        if rule_id in used_ids:
            continue
        used_ids.add(rule_id)
        inst = "UNKNOWN" if rng.random() < 0.1 else rng.choice(instruments)  # 10%: no prices
        inst = rng.choice([inst, inst.lower(), f" {inst}"])
        if rng.random() < 0.5:
            rule = {"id": rule_id, "instrument": inst, "type": random_case(rng, "level"),
                    "direction": random_case(rng, rng.choice(["above", "below"])),
                    "level": random_level(rng, rows)}
        else:
            short = rng.randint(1, 10)
            rule = {"id": rule_id, "instrument": inst, "type": random_case(rng, "ma_cross"),
                    "short": short, "long": rng.randint(short + 1, 30),
                    "direction": random_case(rng, rng.choice(["above", "below"]))}
        if rng.random() < 0.3:
            rule["note"] = "extra keys are ignored"
        items = list(rule.items())
        rng.shuffle(items)  # key order must not matter
        rules.append(dict(items))
    return rules


def rule_for_reference(rule, raw_json_rule):
    """The reference prints the level exactly as written in the JSON text."""
    out = dict(rule)
    if "level" in rule:
        out["level"] = raw_json_rule["level"]
    return out


class InterviewerRulesTest(unittest.TestCase):
    def test_random_rules_files_match_the_reference(self):
        rng = random.Random(2026)
        with tempfile.TemporaryDirectory() as tmp:
            prices_path = os.path.join(tmp, "prices.csv")
            rules_path = os.path.join(tmp, "rules.json")
            for run in range(RUNS):
                rows = random_prices(rng)
                rules = random_rules(rng, rows)
                with open(prices_path, "w", newline="") as f:
                    f.write("date,instrument,close\n")
                    f.writelines(f"{d},{inst},{c}\n" for d, inst, c in rows)
                text = json.dumps(rules, indent=rng.choice([None, 2]))
                with open(rules_path, "w") as f:
                    f.write(text)

                # Levels as the JSON text spells them (e.g. 1500.5, not 1500.50).
                raw = json.loads(text, parse_float=str, parse_int=str)
                expected = reference_output(rows, [rule_for_reference(r, w) for r, w in zip(rules, raw)])

                result = subprocess.run([sys.executable, SCRIPT, prices_path, rules_path],
                                        capture_output=True, text=True)
                with self.subTest(run=run, rules=text):
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, expected)


if __name__ == "__main__":
    unittest.main()
