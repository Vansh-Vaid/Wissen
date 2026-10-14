import csv
import json
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation


class InputError(Exception):
    pass


def warn(message):
    print(f"warning: {message}", file=sys.stderr)


def read_prices(path):
    prices = {}
    seen = {}

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = [name.strip().lower() for name in next(reader, [])]
        for column in ("date", "instrument", "close"):
            if column not in header:
                raise InputError(f"prices file has no '{column}' column")
        date_col = header.index("date")
        instrument_col = header.index("instrument")
        close_col = header.index("close")

        for row in reader:
            line = reader.line_num
            if not "".join(row).strip():
                continue

            try:
                day = datetime.strptime(row[date_col].strip(), "%Y-%m-%d").date()
                instrument = row[instrument_col].strip().upper()
                close = Decimal(row[close_col].strip())
            except (IndexError, ValueError, InvalidOperation):
                warn(f"line {line}: cannot read {','.join(row)!r}, skipped")
                continue

            if not instrument or not close.is_finite() or close <= 0:
                warn(f"line {line}: invalid row {','.join(row)!r}, skipped")
                continue

            key = (instrument, day)
            if key in seen:
                if seen[key] != close:
                    raise InputError(f"line {line}: two different closes for {instrument} on {day}")
                warn(f"line {line}: duplicate row, skipped")
                continue

            seen[key] = close
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
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise InputError(f"rule {rule!r} has no id")
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

    checked = {"id": rule_id, "instrument": instrument.strip(), "direction": direction}
    rule_type = str(rule.get("type", "")).strip().lower()

    if rule_type == "level":
        level = rule.get("level")
        if not (is_whole_number(level) or isinstance(level, Decimal)):
            raise InputError(f"rule '{rule_id}': level must be a number")
        checked.update(type="level", level=Decimal(level), level_text=str(level))

    elif rule_type == "ma_cross":
        short, long = rule.get("short"), rule.get("long")
        if not (is_whole_number(short) and is_whole_number(long) and 0 < short < long):
            raise InputError(f"rule '{rule_id}': short and long must be whole numbers with 0 < short < long")
        checked.update(type="ma_cross", short=short, long=long)

    else:
        raise InputError(f"rule '{rule_id}': unknown type {rule.get('type')!r}")

    return checked


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
        series = prices.get(rule["instrument"].upper())
        if series is None:
            warn(f"rule '{rule['id']}': no prices for {rule['instrument']}")
            continue

        if rule["type"] == "level":
            values = level_differences(series, rule["level"])
            text = f"level {rule['direction']} {rule['level_text']}"
        else:
            values = ma_differences(series, rule["short"], rule["long"])
            text = f"ma_cross {rule['short']}/{rule['long']} {rule['direction']}"

        for day in crossing_days(values, rule["direction"]):
            alerts.append((day.isoformat(), rule["id"], rule["instrument"], text))

    alerts.sort(key=lambda alert: (alert[0], alert[1]))
    return alerts


def format_alerts(alerts):
    id_width = max((len(a[1]) for a in alerts), default=0)
    instrument_width = max((len(a[2]) for a in alerts), default=0)
    return [
        f"{day}  {rule_id.ljust(id_width)}  {instrument.ljust(instrument_width)}  {text}"
        for day, rule_id, instrument, text in alerts
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
