# Price Alert Tool

```
python alerts.py examples/prices.csv examples/rules.json   # run
python -m unittest                                          # 51 tests
```
**Install:** nothing. Python 3.9+ standard library only (developed and tested on 3.13).
Alerts go to **stdout**; warnings to **stderr**. Exit `0` = success (even with warnings), `2` = fatal error.

## Decisions where the brief is open
| Question | Decision |
|---|---|
| Level rule: fire once ever, or on every crossing? | Every crossing. It fires on the day the close moves to the target side, not on the days it stays there. |
| Close exactly equal to the level | Not crossed. `below` means `close < level`; `1510 → 1500 → 1510` never fires. |
| First day of an instrument | Never fires: there is no previous day to be "on the other side". |
| MA window | The instrument's own trading rows sorted by date (not calendar days). Defined only after `long` rows. Both today's and yesterday's MAs must exist, so the earliest alert is row `long + 1`. |
| MA tie (`short == long`) | Not crossed. `above` fires when yesterday `short ≤ long` and today `short > long`. |
| Number precision | `Decimal`, never `float`. Floats turn exact ties into false crosses (see `test_exact_tie_that_floats_get_wrong`). |
| Output order | Date, then rule id as a plain string (so `r10` sorts before `r2`). |
| Instrument names | Whitespace trimmed, matched case-insensitively; output uses the rule's spelling. |

## Bad data policy
- **Bad price row** (bad date, non-ISO date, empty / non-numeric / NaN / Infinity / ≤0 close, `"1,520.50"`, missing fields) → warning with line number, row skipped, run continues.
- **Exact duplicate row** → warning, kept once. **Same instrument and date with different closes** → fatal: the tool can't know which is right, and guessing would produce wrong alerts silently.
- **Invalid rules** (unknown type or direction, non-integer or `true` windows, `short ≥ long`, duplicate ids, bad JSON) → fatal, with a message naming the rule.
- **Rule for an instrument with no prices** → warning; other rules still run.
- **Headers:** BOM, CRLF, extra spaces, any case, any column order and extra columns are accepted.

## Verification
- `tests/test_engine.py`: crossing logic per rule type, including hand-computed MA examples (worked out in comments) and 300 random series checked against a deliberately naive reference implementation using exact `Fraction`s.
- `tests/test_inputs.py`: every bad-data case listed above.
- `tests/test_cli.py`: end-to-end runs, including the brief's exact example, shuffled input, ordering, exit codes, and no tracebacks.
- **Mutation check:** I planted 9 typical bugs one at a time and confirmed the suite fails for each: firing every day below, `>=` for crossing, firing on the first day, no date sort, float prices, MA before the window is full, accepting NaN, wrong sort key, accepting `true` as a window.
- The bundled example's `r2` alert (2026-10-05: MA5 = 3850 > MA20 = 3833.5, previous day 3827.2 < 3832.3) was checked by hand.

## How I used the AI assistant
Prompts in brief: *"understand the problem statement and come up with a build idea as a senior software engineer"*, which produced the design and the edge-case list; then *"act as a senior engineer"*, which produced the implementation, tests and README.

**What it got wrong, and what changed:**
1. **A false claim about ties.** It wrote a test and a docstring saying `Decimal` division could turn an exact MA tie into a false cross. The test case wasn't even a tie (MA1 = 10 vs MA3 = 16/3). On checking, correctly rounded division maps equal values to the same result, so the claim was false. The real risk is **float addition**, so the test was replaced with a concrete float failure (1675.805 vs 1675.8049999999998).
2. **That float test then failed**, because Python 3.12+ `sum()` uses compensated summation and hides the error. The test now adds left to right explicitly, as a normal loop would.
3. **The ordering test couldn't catch a wrong sort key.** Rule ids happened to be in date order, so sorting by id first also passed. The mutation check found this, and the test data was changed so the two orders differ.
