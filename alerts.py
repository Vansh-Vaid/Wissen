import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import MAX_PREC, Decimal, InvalidOperation, localcontext
from typing import Optional


class InputError(Exception):
    pass


@dataclass
class Rule:
    id: str
    instrument: str
    direction: str
    type: str
    level: Optional[Decimal] = None
    level_text: str = ""
    short: int = 0
    long: int = 0


def warn(message):
    print(f"warning: {message}", file=sys.stderr)


def find_columns(header):
    names = [name.strip().lower() for name in header]
    for column in ("date", "instrument", "close"):
        if column not in names:
            raise InputError(f"prices file has no '{column}' column")
    return names.index("date"), names.index("instrument"), names.index("close")


def parse_row(row, columns):
    date_col, instrument_col, close_col = columns
    try:
        day = datetime.strptime(row[date_col].strip(), "%Y-%m-%d").date()
        instrument = row[instrument_col].strip().upper()
        close = Decimal(row[close_col].strip())
    except (IndexError, ValueError, InvalidOperation):
        return None
    if not instrument or "\ufffd" in instrument or not close.is_finite() or close <= 0:
        return None
    return instrument, day, close


def read_prices(path):
    prices = {}
    seen = {}

    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            raise InputError("prices file is empty")
        columns = find_columns(header)

        for row in reader:
            if not "".join(row).strip():
                continue
            line = reader.line_num

            parsed = parse_row(row, columns)
            if parsed is None:
                warn(f"line {line}: bad row {','.join(row)!r}, skipped")
                continue

            instrument, day, close = parsed
            if (instrument, day) in seen:
                if seen[(instrument, day)] != close:
                    raise InputError(f"line {line}: two different closes for {instrument} on {day}")
                warn(f"line {line}: duplicate row, skipped")
                continue

            seen[(instrument, day)] = close
            prices.setdefault(instrument, []).append((day, close))

    for series in prices.values():
        series.sort()
    return prices


def is_whole_number(value):
    return isinstance(value, int) and not isinstance(value, bool)


def check_rule(rule, used_ids):
    if not isinstance(rule, dict):
        raise InputError(f"rule {rule!r} is not an object")

    rule_id = rule.get("id")
    if is_whole_number(rule_id):
        rule_id = str(rule_id)
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise InputError(f"rule {rule!r} needs an id (text or a whole number)")
    rule_id = rule_id.strip()
    if rule_id in used_ids:
        raise InputError(f"rule id '{rule_id}' is used twice")
    used_ids.add(rule_id)

    instrument = rule.get("instrument")
    if not isinstance(instrument, str) or not instrument.strip():
        raise InputError(f"rule '{rule_id}' has no instrument")

    direction = str(rule.get("direction", "")).strip().lower()
    if direction not in ("above", "below"):
        raise InputError(f"rule '{rule_id}': direction must be 'above' or 'below'")

    rule_type = str(rule.get("type", "")).strip().lower()

    if rule_type == "level":
        level = rule.get("level")
        if not (is_whole_number(level) or isinstance(level, Decimal)):
            raise InputError(f"rule '{rule_id}': level must be a number")
        level = Decimal(level)
        return Rule(rule_id, instrument.strip(), direction, "level", level=level, level_text=f"{level:f}")

    if rule_type == "ma_cross":
        short, long = rule.get("short"), rule.get("long")
        if not (is_whole_number(short) and is_whole_number(long) and 0 < short < long):
            raise InputError(f"rule '{rule_id}': short and long must be whole numbers with 0 < short < long")
        return Rule(rule_id, instrument.strip(), direction, "ma_cross", short=short, long=long)

    raise InputError(f"rule '{rule_id}': unknown type {rule.get('type')!r}")


def read_rules(path):
    with open(path, encoding="utf-8-sig") as f:
        try:
            raw = json.load(f, parse_float=Decimal)
        except json.JSONDecodeError as e:
            raise InputError(f"rules file is not valid JSON ({e})")

    if not isinstance(raw, list):
        raise InputError("rules file must contain a list of rules")

    used_ids = set()
    return [check_rule(rule, used_ids) for rule in raw]


def level_differences(series, level):
    return [(day, close - level) for day, close in series]


def ma_differences(series, short, long):
    # sign of (short_sum / short - long_sum / long), without dividing
    with localcontext() as context:
        context.prec = MAX_PREC  # no rounding, however many digits the prices have
        totals = [0]
        for _, close in series:
            totals.append(totals[-1] + close)

        values = []
        for count, (day, _) in enumerate(series, start=1):
            if count < long:
                values.append((day, None))
                continue
            short_sum = totals[count] - totals[count - short]
            long_sum = totals[count] - totals[count - long]
            values.append((day, short_sum * long - long_sum * short))
    return values


def crossing_days(values, direction):
    days = []
    for (_, before), (day, now) in zip(values, values[1:]):
        if before is None or now is None:
            continue
        if direction == "above" and before <= 0 < now:
            days.append(day)
        if direction == "below" and before >= 0 > now:
            days.append(day)
    return days


def find_alerts(prices, rules):
    alerts = []
    for rule in rules:
        series = prices.get(rule.instrument.upper())
        if series is None:
            warn(f"rule '{rule.id}': no prices for {rule.instrument}")
            continue

        if rule.type == "level":
            values = level_differences(series, rule.level)
            text = f"level {rule.direction} {rule.level_text}"
        else:
            values = ma_differences(series, rule.short, rule.long)
            text = f"ma_cross {rule.short}/{rule.long} {rule.direction}"

        for day in crossing_days(values, rule.direction):
            alerts.append((day.isoformat(), rule.id, rule.instrument.upper(), text))

    alerts.sort(key=lambda alert: (alert[0], alert[1]))
    return alerts


def format_alerts(alerts):
    id_width = max((len(rule_id) for _, rule_id, _, _ in alerts), default=0)
    name_width = max((len(name) for _, _, name, _ in alerts), default=0)
    return [
        f"{day}  {rule_id.ljust(id_width)}  {name.ljust(name_width)}  {text}"
        for day, rule_id, name, text in alerts
    ]


def main(args):
    if len(args) != 2:
        print("usage: python alerts.py prices.csv rules.json", file=sys.stderr)
        return 2

    try:
        rules = read_rules(args[1])
        prices = read_prices(args[0])
    except (InputError, OSError, UnicodeDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    for line in format_alerts(find_alerts(prices, rules)):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
