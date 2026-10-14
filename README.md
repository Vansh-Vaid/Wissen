# Price Alert Tool

Give it daily closing prices and alert rules, and it tells you which alerts fired on which day. You need Python 3.9 or newer; there is nothing to install.

## Running it
```
python alerts.py prices.csv rules.json
python -m unittest
```
`prices.csv` and `rules.json` are the brief's example: only `r1` fires, since TCS has 2 days (`samples/01_brief_example` adds history and gives both lines).

## How it works
Both rules boil down to one question: *did a number cross zero today?*

**Level rule.** I look at `close - level` each day. `below 1500` fires on the day the close drops under 1500 after being at 1500 or more the day before. It won't fire again while the price stays down. Sitting exactly on 1500 isn't a cross, and a stock's first day can't fire (there's no day before it).

**Moving average rule.** A 5-day average is the average of the last 5 closes. `5/20 above` fires on the day the 5-day average climbs over the 20-day one. The 20-day average only exists from day 20, and I need the day before too, so the earliest alert is day 21. Prices are `Decimal`, not float, and I compare `short_sum * long` with `long_sum * short`, so equal averages stay exactly equal.

```
close   10   10    7   10   13
MA2      -   10  8.5  8.5 11.5
MA3      -    -    9    9   10     MA2 climbs over MA3 on day 5 -> alert
```

**Output.** One line per alert, sorted by date, then rule id (as text, so `r10` comes before `r2`), lined up like the brief's example. Quiet days print nothing.

```
2026-09-03  r1  INFY  level below 1500
2026-09-24  r2  TCS   ma_cross 5/20 above
```

**Messy data.** Rows can be in any order. A bad date, an unreadable ticker or a price that isn't a positive number gets a warning and the row is skipped (`2026-9-1` is fine). Two different prices for the same stock and day, or a broken rule, stop the tool rather than guess.

## How I used the AI assistant
It wrote most of the code and tests. I asked it, roughly, to plan a build as a senior engineer, test it against the PDF's edge cases, check it on 100 generated cases, review it as an interviewer, and make it readable. What it got wrong, and what changed:

1. It printed single spaces between columns. The brief's output is lined up, so I padded them.
2. It blamed dividing for unequal averages; the real cause is adding floats, so prices are `Decimal`.
3. Its hand calculation expected an alert a day early, but the averages were tied, so I fixed the test.
