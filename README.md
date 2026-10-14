# Price Alert Tool

## How to run
Python 3.9 or newer, nothing to install.
```
python alerts.py prices.csv rules.json
python -m unittest
```
The tests check the logic on hand-worked examples and run the 10 cases in `samples/` (prices, rules and expected output; each folder name says which edge case it covers).

## How it works
**Level rule.** For each day the tool looks at `close - level`. `below 1500` fires on the day the close drops under 1500 when the day before was 1500 or more; `above` is the reverse. It fires on each crossing, not on every day it stays below. A close exactly at the level is not a cross, and a stock's first day never fires (there is no day before it).

**Moving average rule.** A 5-day average is the average of the last 5 closes. `ma_cross 5/20 above` fires on the day the 5-day average goes over the 20-day average when the day before it was equal or under. An average needs a full window, so the 20-day average starts on day 20 and the earliest alert is day 21. Prices are `Decimal`, not float, and the averages are compared as `short_sum * long` against `long_sum * short`, so equal averages stay exactly equal.

```
close   10   10    7   10   13
MA2      -   10  8.5  8.5 11.5
MA3      -    -    9    9   10     MA2 goes over MA3 on day 5 -> alert
```

**Output.** One line per alert, sorted by date then rule id (as text, so `r10` comes before `r2`), tickers in capitals, columns lined up as in the brief. Days with no alerts print nothing.
```
2026-09-03  r1  INFY  level below 1500
2026-09-24  r2  TCS   ma_cross 5/20 above
```

**Bad input.** Rows may be in any order. Dates are `YYYY-MM-DD` (`2026-9-1` is also accepted). A row with a bad date, an unreadable ticker or a price that is not a positive number is skipped with a warning. Two different prices for the same stock and day, or an invalid rule, stop the tool with an error.

## Use of the AI assistant
Prompts, in brief: "design a build as a senior engineer", "build and test it against the PDF", "add edge cases", "rewrite it simply".

What it got wrong, what I changed and why:

1. It printed single spaces between columns; I padded them because the brief's output is lined up.
2. It blamed dividing for unequal averages; the real cause is adding floats, so prices are `Decimal`.
3. A hand calculation expected an alert a day early; the averages were tied, so I fixed the test.
