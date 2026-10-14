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
