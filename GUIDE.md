# Price Alert Tool: Run Guide

A step-by-step guide to installing, running, testing and demonstrating the tool.
The one-page summary of design decisions is in [README.md](README.md).

---

## 1. Requirements

| | |
|---|---|
| **Python** | 3.9 or newer. The tests pass on 3.9, 3.10, 3.11, 3.12 and 3.13. |
| **Packages** | None. Standard library only, so no `pip install` and no virtual environment. |
| **OS** | Windows, macOS, Linux. |

Check your Python:

```bash
python --version      # Windows (or: py --version)
python3 --version     # macOS / Linux
```

No Python? Install it from <https://www.python.org/downloads/>. On Windows, tick **"Add python.exe to PATH"** in the installer.

> On macOS/Linux, type `python3` wherever this guide says `python`.
> On Windows, `py` works if `python` is not found.

---

## 2. Get the code

**Option A, git:**
```bash
git clone https://github.com/Vansh-Vaid/Wissen.git
cd Wissen
```

**Option B, zip:** download the repository zip from GitHub, unzip it, and open a terminal in the unzipped folder (the folder that contains `alerts.py`).

---

## 3. Run it (one command)

```bash
python alerts.py PRICES.csv RULES.json
```

Try it with the bundled files:

```bash
# The brief's own scenario: prints exactly the brief's two output lines
python alerts.py tests/fixtures/brief_full_prices.csv tests/fixtures/brief_rules.json
```
```
2026-09-03  r1  INFY  level below 1500
2026-09-24  r2  TCS   ma_cross 5/20 above
```

```bash
# A longer example: three rules, 30 trading days, shuffled rows
python alerts.py examples/prices.csv examples/rules.json
```

Windows paths work with either slash: `python alerts.py examples\prices.csv examples\rules.json`.

### Reading the output
```
2026-09-24  r2  TCS   ma_cross 5/20 above
└─ date ─┘  id  instr └─ what fired ──────┘
```
- One line per alert, sorted by **date, then rule id**.
- Columns are separated by two spaces; id and instrument are padded so the columns line up.
- A day with no alerts prints nothing. If nothing fires at all, the output is empty.

### Warnings, errors and exit codes
Alerts go to **stdout**. Problems go to **stderr**, so you can separate them:

```bash
python alerts.py prices.csv rules.json > alerts.txt     # alerts.txt holds only alert lines
python alerts.py prices.csv rules.json 2> problems.txt  # problems.txt holds warnings/errors
```

| Exit code | Meaning | Examples |
|---|---|---|
| `0` | Success. There may be `warning:` lines for skipped rows. | bad price row, duplicate row, rule for an unknown instrument |
| `2` | Fatal `error:`. No alerts are printed. | missing file, invalid JSON, invalid rule, conflicting duplicate prices, missing CSV column |

Check the exit code with `echo $?` (macOS/Linux), `echo %ERRORLEVEL%` (Windows cmd) or `echo $LASTEXITCODE` (PowerShell).

---

## 4. Writing your own input files

### Prices: CSV
```csv
date,instrument,close
2026-09-01,INFY,1520.50
2026-09-01,TCS,3890.00
```
- **Required columns:** `date`, `instrument`, `close`, in any order and any case. Extra columns are ignored.
- **`date`:** `YYYY-MM-DD`. Rows may be in any order; the tool sorts them.
- **`close`:** a positive number such as `1520.50`. Don't use thousands separators.
- **Rows the tool skips, with a `warning:` naming the line:** a bad date, a non-numeric (including `₹1490` or `1_490`), empty, `NaN`, zero or negative close, an implausible close (more than 15 integer digits or 30 decimal places), or a missing instrument.
- **Duplicates:** an exact duplicate row is used once. Two *different* closes for the same instrument and date stop the tool (exit 2), because it can't know which one is right.

### Rules: JSON list
```json
[
  {"id": "r1", "instrument": "INFY", "type": "level",
   "direction": "below", "level": 1500},
  {"id": "r2", "instrument": "TCS", "type": "ma_cross",
   "short": 5, "long": 20, "direction": "above"}
]
```
| Field | Rule type | Allowed values |
|---|---|---|
| `id` | all | non-empty string, unique |
| `instrument` | all | ticker (case-insensitive) |
| `type` | all | `level` or `ma_cross` |
| `direction` | all | `above` or `below` |
| `level` | level | a number (`1500` or `1500.50`) |
| `short`, `long` | ma_cross | whole numbers, `1 ≤ short < long` |

### When does a rule fire?
- **level below 1500:** fires on a day when yesterday's close was **≥ 1500** and today's is **< 1500**. It fires again only after the price goes back to 1500 or above and then drops below again. `above` is the mirror image.
- **ma_cross 5/20 above:** fires on a day when yesterday the 5-day average was **≤** the 20-day average and today it is **>**. Averages use the instrument's last N *trading rows*, so the first possible alert is on its 21st row.
- An instrument's first row never fires, because it has no "yesterday".

---

## 5. Run the tests

```bash
python -m unittest            # all 138 tests, about 15 s
python -m unittest -v         # list every test by name
python -m unittest tests.test_brief_scenarios   # just one file
```

| File | What it checks |
|---|---|
| `tests/test_brief_scenarios.py` | Each sentence of the brief, the exact brief output, and real-world file problems |
| `tests/test_engine.py` | Crossing logic, ties, precision, and 500 random series checked against an independent reference implementation |
| `tests/test_inputs.py` | Every kind of bad CSV row and invalid rule |
| `tests/test_cli.py` | Running the real command: output, exit codes, no tracebacks |
| `tests/test_properties.py` | Facts that must hold for any input (alerts unchanged by rescaling, shifting, mirroring or reordering; output always sorted and aligned), plus a level-rule reference check |
| `tests/test_interviewer_rules.py` | 150 random rules files (same keys, any values: ids, stocks, levels, windows, letter case, key order) run through the real command and compared with an independent implementation |
| `tests/test_more_edge_cases.py` | Missing final newline, number spellings, currency symbols, timestamps, tab files, odd rule files, odd command lines |

---

## 6. Performance

The tool reads 500,000 price rows (50 instruments × 10,000 days, 150 rules including 50/200 averages) in about **5 seconds**. Where the speed comes from:
- **Running totals:** each moving average is one subtraction per day, computed once per instrument and shared by all its rules.
- **Exact integer arithmetic:** closes are scaled to whole numbers (1520.50 → 152050), which is faster than `Decimal` and still exact.
- **Date caching:** each distinct date string is parsed once, not once per row.

The output is byte-identical to the earlier, slower version (about 12 s on the same file).

---

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `python: command not found` | Use `python3` (macOS/Linux) or `py` (Windows), or install Python (section 1). |
| `can't open file 'alerts.py'` | You're not in the project folder. `cd` into the folder that contains `alerts.py`. |
| `error: prices file is missing column(s)` | The first line must be a header with `date,instrument,close`. A `;`-separated file must be re-saved as comma-separated. |
| Many `bad date` warnings | Dates must be `YYYY-MM-DD`. Excel often saves `01/09/2026`; reformat the column before saving. |
| `warning: ... not valid UTF-8; reading it as Latin-1` | The file was saved by older Excel. It's handled; re-save as "CSV UTF-8" to silence the warning. |
| A rule never fires | Check stderr for `no prices for instrument`. For `ma_cross`, the instrument needs at least `long + 1` rows. |

---

## 8. Demo script for the presentation (6 + 6 minutes)

1. **Show the brief's result:**
   `python alerts.py tests/fixtures/brief_full_prices.csv tests/fixtures/brief_rules.json`
2. **Show messy data being handled:** append a bad row and rerun.
   ```bash
   cp examples/prices.csv demo.csv            # Windows: copy examples\prices.csv demo.csv
   echo 2026-09-31,INFY,abc >> demo.csv
   python alerts.py demo.csv examples/rules.json
   ```
   Point out the warning names the line, the alerts are unchanged, and the exit code is 0.
3. **Show a fatal error:** a rule with `"short": 20, "long": 5` gives a clear `error:` and exit code 2.
4. **Show the tests:** `python -m unittest`. Then open `tests/test_brief_scenarios.py` and walk through one group.
5. **One thing the assistant got wrong:** see README, "What it got wrong".

During the questions, predict the output before pressing Enter.

---

## 9. Brief compliance checklist

| Requirement in the brief | Where it's met | Verified by |
|---|---|---|
| CLI that reads daily prices for several instruments | `alerts.py`, `load_prices` | `test_inputs.PricesTest` |
| Applies alert rules from a config file | `load_rules`, `evaluate` | `test_inputs.RulesTest` |
| Prices CSV `date,instrument,close`, dates may be out of order | sorted per instrument | `test_brief_fixture_any_row_order_gives_same_output` |
| Rules JSON, any number of rules | 0 to 500 rules tested | `RulesFiles.test_zero_rules`, `test_many_rules` |
| Level fires on the first day it crosses (other side the previous day) | `crossing_days` | `LevelRuleTest`, `LevelScenarios` |
| ma_cross fires on the day short crosses long | `ma_signals` | `MaCrossRuleTest`, the random reference test |
| Moving averages need a full window | first `long - 1` rows undefined | `test_exactly_long_rows_can_never_fire` |
| Output format as in the example | `format_alerts`, byte-exact | `test_reproduces_brief_output_byte_for_byte` |
| Ordered by date, then rule id | `evaluate` sort | `test_ordering_by_date_then_rule_id` |
| Print nothing on days with no alerts | no blank lines | `test_no_blank_lines_and_nothing_printed_when_nothing_fires` |
| Runs from a clean download with one command; say what to install | nothing to install | fresh clone tested; Python 3.9 to 3.13 tested |
| Includes tests; think about real data | 138 tests | `RealWorldPriceFiles`, `test_inputs` |
| README of at most one page: run, prompts, what the AI got wrong, what changed | `README.md` | |
| Submitted as a zip or repository link by 14:00 | see below | |

**Making a zip for submission** (from the project folder):
```bash
git archive --format=zip -o price-alert-tool.zip HEAD
```
