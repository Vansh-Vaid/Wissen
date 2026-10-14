"""Price alert tool, built step by step."""


def crossing_days(signals, direction):
    """Return the days on which a value crosses zero in the given direction.

    signals:   list of (day, value) in date order. value is None when it is
               not known yet (e.g. a moving average without enough days).
    direction: "above" means crossing to > 0, "below" means crossing to < 0.

    A day fires when today is on the target side and yesterday was not.
    Exactly zero counts as "not crossed yet".
    """
    fired = []
    yesterday = None
    for day, today in signals:
        if today is not None and yesterday is not None:
            if direction == "above" and yesterday <= 0 and today > 0:
                fired.append(day)
            if direction == "below" and yesterday >= 0 and today < 0:
                fired.append(day)
        yesterday = today
    return fired


def level_signals(series, level):
    """Turn a level rule into a signal that crosses zero when the close crosses the level.

    series: list of (date, close) sorted by date, closes as Decimal.
    level:  the rule's level as Decimal.
    """
    return [(day, close - level) for day, close in series]


def ma_signals(series, short, long):
    """Turn an ma_cross rule into a signal that crosses zero when MA_short crosses MA_long.

    The signal has the same sign as MA_short - MA_long, but is computed as
    sum_short * long - sum_long * short, which needs no division (no rounding).
    It is None until `long` days exist: an average needs a full window.
    """
    closes = [close for _, close in series]
    signals = []
    for i, (day, _) in enumerate(series):
        days_so_far = i + 1
        if days_so_far < long:
            signals.append((day, None))  # long window not full yet
            continue
        sum_short = sum(closes[days_so_far - short:days_so_far])  # last `short` closes
        sum_long = sum(closes[days_so_far - long:days_so_far])    # last `long` closes
        signals.append((day, sum_short * long - sum_long * short))
    return signals
