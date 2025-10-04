# population_metrics
Batch runner to compute **population-level sentencing metrics** and **suitability scores** for all individuals, writing a flat file (CSV/Parquet). The pipeline is strict about missing inputs: metrics are **skipped** when their prerequisites aren’t present (no fabricated values). Metrics are **named and extensible**; new metrics can be added without changing positional order.

## Repo contents
- `config.py` — Paths (DEV/PROD), column map (`COLS`), defaults (`DEFAULTS`), offense lists (`OFFENSE_LISTS`), and metric weights (`METRIC_WEIGHTS`).
- `compute_metrics.py` — Library functions to read raw tables and compute **named features** for a single ID (skip-if-missing).
- `sentencing_math.py` — Pure math (no I/O): time decomposition, proportions, frequency/trend, rehab, and name-based suitability.
- `run.py` — CLI to iterate over the cohort and export results (CSV or Parquet).

## Install
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -U pip pandas numpy openpyxl tqdm pyarrow
```

## Configure
Edit `config.py`:
- `CFG_PROFILE`: `DEV` uses local files; default `PROD` can read GitHub raw URLs.
- `PATHS`: set `demographics`, `current_commitments`, `prior_commitments` (CSV/XLSX).
- `COLS`: map canonical fields (any `None` disables that field/metric).
- `OFFENSE_LISTS`: explicit code lists; unlisted → `other` (no implicit fallback).
- `METRIC_WEIGHTS`: **dict by name**; only present features contribute to the score.
- Optional: set `DEFAULTS["months_elapsed_total"]` and `DEFAULTS["freq_min_rate"/"freq_max_rate"]` if you want frequency metrics to appear without per-person exposure inference.

## Quick start
```bash
# CSV (auto format by extension)
python run.py --out population_metrics.csv

# Parquet
python run.py --out population_metrics.parquet --format parquet

# Subset of IDs (CSV with a column named as config.COLS['id'])
python run.py --out subset_metrics.csv --ids-csv ids_subset.csv

# Quick smoke test
python run.py --out sample.csv --limit 500
```

## Useful flags
- `--include-aux` : adds diagnostics like `age_value`, `% completed`, `time_outside`, and flattened offense counts (`counts_current_...`, `counts_prior_...`).
- `--print-every N` : also prints progress every N rows (besides tqdm).
- `--fail-fast` : aborts on first error (default: continue and log per-ID error).

## Output
- Main file: CSV/Parquet with one row per ID, including named metrics and `score` (suitability).
- Errors (if any): `*.errors.jsonl` with `{id, error}` records.
- Console preview prints the first rows/columns for a quick check.

## Worked examples (from scratch)
These examples walk through **exactly** what the pipeline computes for a specific ID: counts → denominators → proportions → time pieces → trend/frequency → named vector → suitability, with the LaTeX used in code.

### Example 1 — `00009164d5`
**Offense Lists (active for this run)**  
- Violent: `['211', '245']`  
- Nonviolent: `['484', '10851', '459']`

**Inputs**
- Current offense rows found: **4**  
- Prior offense rows found: **1**

**Counts by Category**
- Current: `{'violent': 0, 'nonviolent': 0, 'other': 4, 'clash': 0}`  
- Prior:   `{'violent': 0, 'nonviolent': 0, 'other': 1, 'clash': 0}`

**Time Pieces**
- `current_sentence_months = 372.000`  
- `completed_months = 79.200`  
- `past_time_months = NA`  
- `childhood_months = 0.000`  
- `pct_current_completed = 21.290`  
- `time_outside_months = 0.000`

**Formulas + Numeric Plug-ins**
- **Proportion of non-violent (current)**  
  \( \mathrm{desc\_nonvio\_curr}=\dfrac{\mathrm{nonvio_{curr}}}{\mathrm{total_{curr}}} \)  
  `0/0` → **SKIPPED**

- **Proportion of non-violent (past)**  
  \( \mathrm{desc\_nonvio\_past}=\dfrac{\mathrm{nonvio_{past}}}{\mathrm{total_{past}}} \)  
  `0/0` → **SKIPPED**

- **Violent proportions (for trend)**  
  `prop_violent_curr = NA`  
  `prop_violent_past = NA`

- **Severity trend**  
  \( \mathrm{severity\_trend}=\left(\dfrac{\mathrm{prop_{vio,past}}-\mathrm{prop_{vio,curr}}}{\mathrm{years}+1}+1\right)/2 \)  
  = **SKIPPED**  (`years_elapsed=10.000`)

- **Frequency (raw rates per month outside)**  
  `violent_total = 0; total_conv = 0; time_outside = 0.000`  
  `raw_freq_violent = NA; raw_freq_total = NA`  
  **normalized:** **SKIPPED** (requires `time_outside>0` and `freq_min_rate/max_rate`).

- **Age (min–max)**  
  \( \mathrm{age}=\mathrm{clip}_{[0,1]}\!\left(\dfrac{\text{age\_years}-\text{age\_min}}{\text{age\_max}-\text{age\_min}}\right) \)  
  = **0.333**  (`raw=42.000`, `min=18.000`, `max=90.000`)

**Final Metric Vector (named)**  
Order: `desc_nonvio_curr, desc_nonvio_past, age, freq_violent, freq_total, severity_trend, edu_general, edu_advanced, rehab_general, rehab_advanced`  
Values: `[SKIPPED, SKIPPED, 0.333, SKIPPED, SKIPPED, SKIPPED, SKIPPED, SKIPPED, SKIPPED, SKIPPED]`  
**Suitability (with METRIC_WEIGHTS):** **0.000**

### Example 2 — `2cf2a233c4`
**Offense Lists (active for this run)**  
- Violent: `['187', '211', '245']`  
- Nonviolent: `['459', '484', '10851']`

**Inputs**
- Current offense rows found: **1**  
- Prior offense rows found: **13**

**Counts by Category**
- Current: `{'violent': 0, 'nonviolent': 1, 'other': 0, 'clash': 0}`  
- Prior:   `{'violent': 0, 'nonviolent': 2, 'other': 11, 'clash': 0}`

**Time Pieces**
- `current_sentence_months = 32.000`  
- `completed_months = 31.200`  
- `past_time_months = NA`  
- `childhood_months = 0.000`  
- `pct_current_completed = 97.500`  
- `time_outside_months = 0.000`

**Formulas + Numeric Plug-ins**
- **Proportion of non-violent (current)**  
  \( \mathrm{desc\_nonvio\_curr}=\dfrac{\mathrm{nonvio_{curr}}}{\mathrm{total_{curr}}} \)  
  `1/1` → **1.000**

- **Proportion of non-violent (past)**  
  \( \mathrm{desc\_nonvio\_past}=\dfrac{\mathrm{nonvio_{past}}}{\mathrm{total_{past}}} \)  
  `2/2` → **1.000**

- **Violent proportions (for trend)**  
  `prop_violent_curr = 0.000`  
  `prop_violent_past = 0.000`

- **Severity trend**  
  \( \mathrm{severity\_trend}=\left(\dfrac{\mathrm{prop_{vio,past}}-\mathrm{prop_{vio,curr}}}{\mathrm{years}+1}+1\right)/2 \)  
  = **0.500**  (`years_elapsed=10.000`)

- **Frequency (raw rates per month outside)**  
  `violent_total = 0; total_conv = 3; time_outside = 0.000`  
  `raw_freq_violent = NA; raw_freq_total = NA`  
  **normalized:** **SKIPPED** (requires `time_outside>0` and `freq_min_rate/max_rate`).

- **Age:** **SKIPPED** (no age column configured or value missing)

**Final Metric Vector (named)**  
Order: `desc_nonvio_curr, desc_nonvio_past, age, freq_violent, freq_total, severity_trend, edu_general, edu_advanced, rehab_general, rehab_advanced`  
Values: `[1.000, 1.000, SKIPPED, SKIPPED, SKIPPED, 0.500, SKIPPED, SKIPPED, SKIPPED, SKIPPED]`  
**Suitability (with METRIC_WEIGHTS):** **2.500**

### Re‑generate these examples
**macOS/Linux**
```bash
CFG_PROFILE=DEV python docs/make_worked_example.py --uid "2cf2a233c4" --out docs/README_worked_example_2cf2a233c4.md
CFG_PROFILE=DEV python docs/make_worked_example.py --uid "00009164d5" --out docs/README_worked_example_00009164d5.md
```
**Windows PowerShell**
```powershell
$env:CFG_PROFILE="DEV"
python docs\make_worked_example.py --uid "2cf2a233c4" --out docs\README_worked_example_2cf2a233c4.md
python docs\make_worked_example.py --uid "00009164d5" --out docs\README_worked_example_00009164d5.md
```

## Formulas implemented (LaTeX)
- **Proportion of non‑violent (current):**  
  \( \mathrm{desc\_nonvio\_curr}=\dfrac{\mathrm{nonvio_{curr}}}{\mathrm{total_{curr}}} \)

- **Proportion of non‑violent (past):**  
  \( \mathrm{desc\_nonvio\_past}=\dfrac{\mathrm{nonvio_{past}}}{\mathrm{total_{past}}} \)

- **Violent proportions (definitions used by trend):**  
  \( \mathrm{prop_{vio,curr}}=\dfrac{\mathrm{vio_{curr}}}{\mathrm{total_{curr}}},\quad
     \mathrm{prop_{vio,past}}=\dfrac{\mathrm{vio_{past}}}{\mathrm{total_{past}}} \)

- **Severity trend (higher = shift toward non‑violence; clipped to \([0,1]\)):**  
  \( \mathrm{severity\_trend}=\mathrm{clip}_{[0,1]}\!\left(
      \dfrac{\mathrm{prop_{vio,past}}-\mathrm{prop_{vio,curr}}}{\mathrm{years}+1}\cdot\dfrac{1}{2}
      + \dfrac{1}{2}
    \right) \)

- **Frequency (per month outside; min–max normalize if bounds are set):**  
  Raw rates: \( r_v=\dfrac{\text{violent\_total}}{\text{time\_outside}},\quad
               r_t=\dfrac{\text{conv\_total}}{\text{time\_outside}} \)  
  Normalized: \( \hat r=\mathrm{clip}_{[0,1]}\!\left(\dfrac{r-\text{min}}{\text{max}-\text{min}}\right) \)

- **Age (min–max):**  
  \( \mathrm{age}=\mathrm{clip}_{[0,1]}\!\left(\dfrac{\text{age\_years}-\text{age\_min}}{\text{age\_max}-\text{age\_min}}\right) \)

- **Suitability (name‑based, present features only):**  
  \( \text{score}=\sum_{k\in\text{present}} w_k\, m_k \)

> **Notes:**  
> • Proportion metrics are computed **only** when denominators \(>\,0\); otherwise the metric is **SKIPPED**.  
> • Frequency requires **both** `time_outside > 0` **and** configured `freq_min_rate`/`freq_max_rate`.  
> • Rehab/education are per‑month‑inside, then min–max normalized **only if** inputs and bounds are provided; otherwise **omitted**.

## Validation checklist
- Proportion metrics are computed **only** when denominators \(>\,0\); otherwise the metric is **SKIPPED**.
- Frequency requires **both** `time_outside > 0` **and** `freq_min_rate`/`freq_max_rate` in `config.py`.
- Offense classification uses only `OFFENSE_LISTS`; anything unlisted → **other** (and does not contribute to denominators).
- Suitability uses **only present (gated)** features with explicit `METRIC_WEIGHTS` (no hidden zero‑weights).
- When comparing individuals (similarity), compute on the **intersection of present features** and require a minimum shared‑dimension count (e.g., ≥3). Consider also Euclidean or Tanimoto for sensitivity analysis.

## Programmatic example
```python
import config as CFG, compute_metrics as cm, sentencing_math as sm
import pandas as pd

demo = cm.read_table(CFG.PATHS["demographics"])
cur  = cm.read_table(CFG.PATHS["current_commitments"])
pri  = cm.read_table(CFG.PATHS["prior_commitments"])

ids = demo[CFG.COLS["id"]].astype(str).unique().tolist()[:3]
rows = []
for uid in ids:
    feats, aux = cm.compute_features(uid, demo, cur, pri, CFG.OFFENSE_LISTS)
    score = sm.suitability_score_named(feats, CFG.METRIC_WEIGHTS)
    rows.append({CFG.COLS["id"]: uid, **feats, "score": score})
df = pd.DataFrame(rows)
print(df.head())
```

## Troubleshooting
- **No computable features**: verify `COLS` names and required time fields in `DEFAULTS['require_time_fields']`.
- **All similarities/metrics look constant**: set meaningful `freq_min_rate`/`freq_max_rate` and ensure exposure window is computed.
- **XLSX read errors**: `pip install openpyxl`.
- **Parquet write errors**: `pip install pyarrow`.

## License
MIT
