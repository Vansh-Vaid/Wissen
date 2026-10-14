# Price Alert Tool

```
python alerts.py examples/prices.csv examples/rules.json   # run
python -m unittest                                          # 138 tests
```
Nothing to install: Python 3.9+ standard library (tests pass on 3.9 to 3.13). Alerts go to stdout, warnings to stderr; exit 0 = success, 2 = fatal error. Step-by-step instructions are in **[GUIDE.md](GUIDE.md)**.

## Decisions where the brief is open
- **Level** fires on *every* crossing (the day the close moves to the target side), not while it stays there. Equal to the level is *not* crossed. The first row of an instrument never fires.
- **MA** windows count the instrument's own trading rows, not calendar days. Both today's and yesterday's MAs must exist, so the earliest alert is row `long+1`. A tie is not a cross.
- **"Previous day"** means the previous trading row, even across missing dates. Skipped bad rows don't count towards MA windows.
- **Precision:** exact arithmetic, never `float`, which turns exact ties into false crosses. Prices are parsed as `Decimal`; MA sums are scaled to integers (1520.50 → 152050), which is exact and faster.
- **Output** matches the brief byte for byte: columns separated by two spaces, id and instrument padded to the widest value (measured from the PDF). Sorted by date, then rule id as a string (`r10` before `r2`).
- **Names:** tickers trimmed and case-insensitive; `type`/`direction` case-insensitive.

## Bad data
- **Bad row** (bad or non-ISO date, empty, non-numeric, NaN, ≤0 or `"1,520.50"` close, missing fields, repeated header) → warning with line number, skipped.
- **Exact duplicate** → kept once. **Same instrument and date with different closes** → fatal: guessing would give silently wrong alerts.
- **Invalid rule** (unknown type, `short ≥ long`, `true` or `5.5` window, duplicate id, bad JSON) → fatal, naming the rule.
- **Rule for an instrument with no prices** → warning.
- **Accepted:** BOM, CRLF, quotes, any header case or column order, extra or missing trailing columns. Non-UTF-8 is read as Latin-1 with a warning.

## Verification
- **Tests,** split by focus: `test_engine` (crossing logic; 500 random series, some with 33-digit prices, against a naive `Fraction` reference), `test_inputs` (each bad-data case), `test_cli` (end to end), `test_brief_scenarios` (grouped by sentence of the brief), `test_properties` (random-data invariants: same alerts after rupee→paise scaling, price shifts, mirroring, row order), `test_more_edge_cases`, and `test_interviewer_rules` (150 random rules files with any values, run through the real command and compared line for line with an independent implementation).
- **Brief fixture:** `fixtures/brief_full_prices.csv` keeps the brief's five rows and adds history, so the tool prints **exactly the brief's two output lines**: r2 on 09-24, with a near-miss on 09-23 (MA5 3911.0 vs MA20 3911.0625).
- **Mutation check:** across two rounds I planted 29 typical bugs (firing every day, `>=`, MA window off by one, floats, wrong sort, single spaces, …); the tests fail for each.
- **By hand:** MA values checked for the example alerts.
- **Performance:** 500k rows with 150 rules run in about 5s, down from 12s, with byte-identical output.

## How I used the AI assistant
Prompts in brief: *"come up with a build idea as a senior engineer"* (design, edge cases), *"act as a senior engineer"* (code, tests), *"test with edge cases matching the PDF"* (scenarios, exact format), *"check against the PDF, improve performance, add a guide"* (profiling, GUIDE.md).

**What it got wrong, and what changed:**
1. It claimed `Decimal` division could break MA ties, with an example that wasn't a tie. The real risk is float *addition*; the test now shows a concrete float failure.
2. That float test passed vacuously on Python 3.12+, whose `sum()` compensates rounding. It now adds left to right explicitly.
3. The ordering test used ids already in date order, so a wrong sort key passed. The mutation check caught it, and the data was changed.
4. Output used single spaces, because PDF text extraction collapses them. Measured word positions showed padded columns, and the output was fixed.
5. A hand calculation expected an MA cross on day 6. It was an exact tie (MA2 = MA3 = 10), so the cross is day 7. The tool was right and the test was wrong.
6. It checked a Windows-console crash using `python -I`, which ignores `PYTHONIOENCODING`, so the check proved nothing. Rerun properly, the crash was confirmed; a test now guards the fix.
