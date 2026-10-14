"""Price alert tool.

Usage: python alerts.py prices.csv rules.json

Reads daily closes, applies alert rules, prints one line per fired alert
ordered by date then rule id. Alerts go to stdout; warnings and errors go to
stderr. Exit code 0 on success (even with warnings), 2 on a fatal error.
"""

import csv
import io
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

DIRECTIONS = ("above", "below")


class AlertError(Exception):
    """A problem that makes the output untrustworthy; the tool stops."""


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LevelRule:
    id: str
    instrument: str
    direction: str
    level: Decimal
    level_text: str  # the level exactly as written in the JSON, for output

    def describe(self) -> str:
        return f"level {self.direction} {self.level_text}"


@dataclass(frozen=True)
class MaCrossRule:
    id: str
    instrument: str
    direction: str
    short: int
    long: int

    def describe(self) -> str:
        return f"ma_cross {self.short}/{self.long} {self.direction}"


def _warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


def _read_text(path: str, what: str) -> str:
    """Read a file as UTF-8 (BOM allowed); fall back to Latin-1 so a file
    saved by Excel on Windows still loads instead of crashing."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        raise AlertError(f"cannot read {what} file: {e}")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        _warn(f"{what} file is not valid UTF-8; reading it as Latin-1")
        return data.decode("latin-1")


def _is_int(value) -> bool:
    # bool is a subclass of int in Python; `"short": true` must not mean 1.
    return isinstance(value, int) and not isinstance(value, bool)


def _keyword(value):
    """'Below ' -> 'below'; non-strings are returned unchanged and fail validation."""
    return value.strip().lower() if isinstance(value, str) else value


def parse_rule(raw, index: int):
    where = f"rule #{index + 1}"
    if not isinstance(raw, dict):
        raise AlertError(f"{where}: expected an object, got {type(raw).__name__}")

    rule_id = raw.get("id")
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise AlertError(f"{where}: 'id' must be a non-empty string")
    rule_id = rule_id.strip()
    where = f"rule '{rule_id}'"

    instrument = raw.get("instrument")
    if not isinstance(instrument, str) or not instrument.strip():
        raise AlertError(f"{where}: 'instrument' must be a non-empty string")
    instrument = instrument.strip()

    direction = _keyword(raw.get("direction"))
    if direction not in DIRECTIONS:
        raise AlertError(f"{where}: 'direction' must be 'above' or 'below', got {direction!r}")

    rule_type = _keyword(raw.get("type"))
    if rule_type == "level":
        level = raw.get("level")
        # JSON is loaded with parse_float=Decimal, so a level is an int or a Decimal.
        if _is_int(level):
            level = Decimal(level)
        if not isinstance(level, Decimal) or not level.is_finite():
            raise AlertError(f"{where}: 'level' must be a number, got {raw.get('level')!r}")
        return LevelRule(rule_id, instrument, direction, level, str(raw["level"]))

    if rule_type == "ma_cross":
        short, long_ = raw.get("short"), raw.get("long")
        for name, value in (("short", short), ("long", long_)):
            if not _is_int(value) or value < 1:
                raise AlertError(f"{where}: '{name}' must be a positive integer, got {value!r}")
        if short >= long_:
            raise AlertError(f"{where}: 'short' ({short}) must be less than 'long' ({long_})")
        return MaCrossRule(rule_id, instrument, direction, short, long_)

    raise AlertError(f"{where}: unknown rule type {rule_type!r}")


def load_rules(path: str) -> list:
    text = _read_text(path, "rules")
    try:
        raw = json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError as e:
        raise AlertError(f"rules file is not valid JSON: {e}")
    if not isinstance(raw, list):
        raise AlertError("rules file must contain a JSON list of rules")

    rules = [parse_rule(r, i) for i, r in enumerate(raw)]
    seen = set()
    for rule in rules:
        if rule.id in seen:
            raise AlertError(f"duplicate rule id '{rule.id}'")
        seen.add(rule.id)
    return rules


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------

Series = List[Tuple[date, Decimal]]  # one instrument, sorted by date


def load_prices(path: str) -> Dict[str, Series]:
    """Return {INSTRUMENT: [(date, close), ...] sorted by date}.

    Bad rows are skipped with a warning. Exact duplicate rows are dropped.
    Two different closes for the same instrument and date are fatal: we cannot
    know which is right, and guessing would produce wrong alerts silently.
    Instrument names are matched case-insensitively (stored upper-case).
    """
    text = _read_text(path, "prices")

    by_key: Dict[Tuple[str, date], Tuple[Decimal, int]] = {}
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader, None)
    if header is None:
        raise AlertError("prices file is empty")
    columns = [h.strip().lower() for h in header]
    missing = [c for c in ("date", "instrument", "close") if c not in columns]
    if missing:
        raise AlertError(f"prices file is missing column(s): {', '.join(missing)}")
    i_date, i_inst, i_close = (columns.index(c) for c in ("date", "instrument", "close"))
    needed = max(i_date, i_inst, i_close) + 1  # trailing optional columns may be absent

    while True:
        try:
            row = next(reader, None)
        except csv.Error as e:
            raise AlertError(f"prices line {reader.line_num}: unreadable CSV ({e})")
        if row is None:
            break
        line = reader.line_num
        if not any(cell.strip() for cell in row):
            continue  # blank line
        if len(row) < needed:
            _warn(f"prices line {line}: expected {len(columns)} fields, got {len(row)}; skipped")
            continue

        raw_date, raw_inst, raw_close = row[i_date].strip(), row[i_inst].strip(), row[i_close].strip()
        try:
            day = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError:
            _warn(f"prices line {line}: bad date {raw_date!r} (expected YYYY-MM-DD); skipped")
            continue
        if not raw_inst:
            _warn(f"prices line {line}: empty instrument; skipped")
            continue
        try:
            close = Decimal(raw_close)
        except InvalidOperation:
            close = None
        # Decimal happily parses "NaN" and "Infinity"; a price must be finite and positive.
        if close is None or not close.is_finite() or close <= 0:
            _warn(f"prices line {line}: bad close {raw_close!r}; skipped")
            continue

        key = (raw_inst.upper(), day)
        if key in by_key:
            prev_close, prev_line = by_key[key]
            if prev_close == close:
                _warn(f"prices line {line}: duplicate of line {prev_line}; ignored")
                continue
            raise AlertError(
                f"prices lines {prev_line} and {line}: conflicting closes for "
                f"{raw_inst} on {day} ({prev_close} vs {close})"
            )
        by_key[key] = (close, line)

    series: Dict[str, Series] = {}
    for (inst, day), (close, _) in by_key.items():
        series.setdefault(inst, []).append((day, close))
    for points in series.values():
        points.sort()
    return series


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def crossing_days(signals: List[Tuple[date, Optional[Decimal]]], direction: str) -> List[date]:
    """Days on which a signal moves onto the `direction` side of zero.

    `signals` is [(day, value)] in date order; value None means "not defined
    yet" (e.g. moving average window not full). "above" means value > 0,
    "below" means value < 0; exactly zero counts as not-yet-crossed. A day
    fires only if both it and the previous day are defined, the previous day
    was not on the target side, and this day is.
    """
    def on_side(v: Decimal) -> bool:
        return v > 0 if direction == "above" else v < 0

    fired = []
    prev = None
    for day, value in signals:
        if value is not None and prev is not None and not on_side(prev) and on_side(value):
            fired.append(day)
        prev = value
    return fired


def level_signals(series: Series, rule: LevelRule):
    return [(day, close - rule.level) for day, close in series]


def ma_signals(series: Series, rule: MaCrossRule):
    """Signal whose sign is sign(MA_short - MA_long), None until `long` days exist.

    Prices are Decimal, so sums are exact (floats are not: see the tie test).
    Comparing sum_short * long with sum_long * short avoids division entirely.
    """
    # prefix[k] = sum of the first k closes, so any window sum is one subtraction.
    prefix = [Decimal(0)]
    for _, close in series:
        prefix.append(prefix[-1] + close)
    out = []
    for i, (day, _) in enumerate(series):
        end = i + 1  # number of rows up to and including today
        if end < rule.long:
            out.append((day, None))
            continue
        sum_short = prefix[end] - prefix[end - rule.short]
        sum_long = prefix[end] - prefix[end - rule.long]
        out.append((day, sum_short * rule.long - sum_long * rule.short))
    return out


def evaluate(series_by_instrument: Dict[str, Series], rules: list) -> List[Tuple[str, str, str, str]]:
    """Return fired alerts as (date, rule_id, instrument, description), sorted by date then rule id."""
    alerts = []
    for rule in rules:
        series = series_by_instrument.get(rule.instrument.upper())
        if series is None:
            _warn(f"rule '{rule.id}': no prices for instrument {rule.instrument}")
            continue
        signals = level_signals(series, rule) if isinstance(rule, LevelRule) else ma_signals(series, rule)
        for day in crossing_days(signals, rule.direction):
            alerts.append((day.isoformat(), rule.id, rule.instrument, rule.describe()))
    alerts.sort(key=lambda a: (a[0], a[1]))
    return alerts


def format_alerts(alerts) -> List[str]:
    """Columns separated by two spaces; rule id and instrument padded to the widest value.

    This reproduces the brief's example byte for byte:
        2026-09-03  r1  INFY  level below 1500
        2026-09-24  r2  TCS   ma_cross 5/20 above
    """
    id_width = max((len(a[1]) for a in alerts), default=0)
    inst_width = max((len(a[2]) for a in alerts), default=0)
    return [f"{d}  {rid.ljust(id_width)}  {inst.ljust(inst_width)}  {desc}" for d, rid, inst, desc in alerts]


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: python alerts.py PRICES.csv RULES.json", file=sys.stderr)
        return 2
    try:
        rules = load_rules(argv[1])
        prices = load_prices(argv[0])
        lines = format_alerts(evaluate(prices, rules))
    except AlertError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
