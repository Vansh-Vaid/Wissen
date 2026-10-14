# Price Alert Tool

```
python alerts.py prices.csv rules.json
python -m unittest
```
Needs Python 3.9 or newer, nothing to install. Alerts are printed to stdout, warnings and errors to stderr. Exit code 0 on success, 2 on an error.

## How it works
Both rule types become a number that crosses zero:
- level rule: `close - level`
- ma_cross rule: `MA_short - MA_long`, compared as `short_sum * long - long_sum * short` so nothing is divided

A rule fires on a day when that number is on the target side and was not on the previous day. Prices are read as `Decimal`, not float, so exact ties stay exact.

## Decisions
- A level rule fires every time the price crosses, not only the first time. Equal to the level is not a cross.
- The first day of an instrument never fires, since there is no previous day.
- Moving averages use the instrument's own rows, not calendar days. With a 5/20 rule the earliest alert is on the 21st row.
- Output columns are padded to line up, matching the example in the brief. Lines are sorted by date, then rule id.
- A bad price row (bad date, non-number, zero or negative price) is skipped with a warning.
- Two different closes for the same instrument and date stop the tool, since there is no way to know which is right. An exact duplicate is skipped.
- An invalid rule (unknown type or direction, short not less than long, duplicate id) stops the tool with a message naming the rule.

## Samples
Each folder in `samples/` has `prices.csv`, `rules.json` and `expected.txt`. `python -m unittest` runs all of them.

| Sample | What it checks |
|---|---|
| 01_brief_example | The brief's data and rules give the brief's exact output |
| 02_level_lowered_and_raised | Same prices, levels at 1490, 1500 and 1550; touching 1500 is not a cross |
| 03_level_first_day_and_staying | Starting on the target side, staying there, levels never reached |
| 04_ma_windows_increased | 2/3, 3/5 and 5/10 windows on the same prices; a tie before a cross |
| 05_ma_full_window_boundary | 20 rows cannot fire a 5/20 rule, 21 can; 5/21 needs 22 |
| 06_ma_exact_tie | An exact MA tie that floats would report as a cross |
| 07_unordered_and_gaps | Shuffled rows, weekends and a missing week |
| 08_messy_csv | BOM, Windows line endings, odd header, blank, bad and duplicate rows |
| 09_ordering_and_alignment | Several alerts on one day, id order, long tickers, unknown stock |
| 10_invalid_rule | A rule with short > long stops the tool with exit code 2 |

## Verification
- The samples' expected outputs were worked out by hand first, then matched against an earlier, separately written version of the tool.
- I broke the code on purpose in 14 ways (firing every day, off-by-one windows, floats, wrong sort order, and so on) and checked that the tests fail each time. One gap was found this way: `short == long` was not tested, so I added it.
- Tests pass on Python 3.9, 3.11, 3.12 and 3.13.

## Use of the AI assistant
I used an AI assistant to plan the edge cases, write the code and tests, and generate the samples. I asked it to design the tool, test it against the brief, add edge cases, and finally rewrite everything in a simpler style.

What it got wrong:
1. It printed single spaces between columns, because copying text out of the PDF collapses spaces. Measuring the PDF showed the columns are padded. Fixed.
2. It claimed dividing Decimals could break exact ties. It was wrong: the real problem is adding floats. The tie test now uses a real float failure.
3. One of its hand calculations expected an MA cross a day early. Rechecking showed an exact tie on that day. The code was right and the test was wrong.
4. Some of its own checks were flawed: once it edited a comment instead of the code, and once Python ran an old cached copy of the file. Both were caught and the checks were redone.
