# Price Alert Tool

Reads daily closing prices and alert rules, and prints which alert fired on which day.

## How to run
Needs Python 3.9 or newer. Nothing to install.

```
python alerts.py prices.csv rules.json
python -m unittest
```

Example:
```
python alerts.py samples/01_brief_example/prices.csv samples/01_brief_example/rules.json
```

## How it works

### Level rule
A level rule watches `close - level` for each day.

- `below 1500` fires on the day the close goes under 1500, when the day before it was 1500 or more.
- `above 1500` fires on the day the close goes over 1500, when the day before it was 1500 or less.

```
date    close    close - 1500
Sep 1   1520.50   +20.50
Sep 2   1534.10   +34.10
Sep 3   1498.00    -2.00   <- crossed below, alert
```

It fires each time the price crosses, not on every day it stays below. A close exactly at the level does not count as crossing. The first day of a stock never fires, because there is no day before it.

### Moving average rule
A moving average of N days is the average of the last N closes. With `short 5, long 20`, the tool compares the 5-day average with the 20-day average every day.

- `above` fires on the day the short average goes over the long one, when the day before it was equal or under.
- `below` is the opposite.

An average needs a full window, so the 20-day average exists only from the 20th day. Because the day before must also have it, the earliest possible alert for 5/20 is the 21st day.

```
close   10   10    7   10   13
MA2      -   10  8.5  8.5 11.5
MA3      -    -    9    9   10
                            ^ MA2 goes over MA3, alert on day 5
```

The two averages are compared as `short_sum * long` against `long_sum * short`, which gives the same answer without dividing. Prices are read as `Decimal` instead of float, so equal averages stay exactly equal.

### Output
One line per alert: date, rule id, stock, and what fired. Lines are sorted by date, then rule id, and the columns are lined up as in the brief:

```
2026-09-03  r1  INFY  level below 1500
2026-09-24  r2  TCS   ma_cross 5/20 above
```

Days with no alerts print nothing.

### Bad input
- Rows can be in any order; each stock is sorted by date.
- A row with a bad date or a price that is not a positive number is skipped with a warning.
- Two different prices for the same stock and day stop the tool, because there is no way to know which is right.
- An invalid rule (unknown type or direction, short not smaller than long, repeated id) stops the tool with an error.

## Tests
`test_alerts.py` checks the level and moving-average logic on small hand-worked examples, the file reading, and the 10 cases in `samples/`. Each sample has `prices.csv`, `rules.json` and the `expected.txt` output, and covers one situation: the brief's example, raised and lowered levels, longer averages, a full window, exact ties, shuffled rows, a messy file, sort order, and an invalid rule.

## Use of the AI assistant
Prompts in brief: design the tool as a senior engineer; build and test it against the brief; add edge cases; rewrite it simply.

What it got wrong, and what I changed:
1. It printed single spaces between columns. The brief's example has the columns lined up, so I fixed the output.
2. It said dividing could make two equal averages look different. The real problem is adding floats, so prices are read as `Decimal`, and a test uses a real case where floats are wrong.
3. One of its hand calculations expected an alert a day early. The averages were exactly equal that day, so the code was right and the test was fixed.
