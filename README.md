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
These examples walk through **exactly** what the pipeline computes for a specific ID: counts → denominators → proportions → time pieces → trend/frequency → named vector → suitability. The LaTeX below **matches the paper** notation.

### Example 1 — `00173d8423`
**Offense Lists (active for this run)**  
- Violent: `['187', '211', '245']`  
- Nonviolent: `['459', '484', '10851']`

**Inputs**
- Current offense rows found: **11**  
- Prior offense rows found: **6**

**Counts by Category**
- Current: `{'violent': 1, 'nonviolent': 1, 'other': 9, 'clash': 0}`  
- Prior:   `{'violent': 0, 'nonviolent': 4, 'other': 2, 'clash': 0}`

**Time Pieces**
- `current_sentence_months = 10000.000`  
- `completed_months = 330.000`  
- `past_time_months = NA`  
- `childhood_months = 0.000`  
- `pct_current_completed = 3.300`  
- `time_outside_months = 0.000`

**Formulas + Numeric Plug-ins**
- **Proportion of non‑violent (current)**  

$$
\mathrm{desc}^{\mathrm{nonvio}}_{i,t_d}
= \frac{\mathrm{conv}^{\mathrm{nonvio}}_{i,t_d}}{\mathrm{conv}^{(\mathrm{vio+nonvio})}_{i,t_d}}
$$

$= \tfrac{1}{2} = \mathbf{0.500}$

- **Proportion of non‑violent (past)**  

$$
\mathrm{desc}^{\mathrm{nonvio}}_{i,\,t \lt t_d}
= \frac{\mathrm{conv}^{\mathrm{nonvio}}_{i,\,t \lt t_d}}
        {\mathrm{conv}^{\mathrm{vio+nonvio}}_{i,\,t \lt t_d}}
$$

$= \frac{4}{4} = \mathbf{1.000}$

- **Violent proportions (for trend)**  

$$
\mathrm{desc}^{\mathrm{vio}}_{i,\,t_d} = 0.500
\mathrm{desc}^{\mathrm{vio}}_{i,\,t \lt t_d} = 0.000
$$

- **Severity trend**  

$$
\mathrm{severity\_trend} =
\mathrm{clip}_{[0,1]}\left(
  \frac{\mathrm{desc}^{\text{vio}}_{i,\, t \lt t_d}
        - \mathrm{desc}^{\text{vio}}_{i,\, t_d}}{\mathrm{years}+1}
  \cdot \frac{1}{2} + \frac{1}{2}
\right)
$$

$= \mathbf{0.477} \quad (\mathrm{years\_elapsed}=10)$

- **Frequency (raw rates per month outside)**  

violent\_total \(= 1\); total\_conv \(= 6\); time\_outside \(= 0.000\).  
Raw rates undefined; normalized **SKIPPED** (requires \( \text{time\_outside} > 0 \) and bounds).

- **Age (min–max)**  

$$
\mathrm{age}_{i, t_d} =
\mathrm{norm}\left(\mathrm{age}^{\text{raw}}_{i, t_d},\,k\right)
$$

$= \mathbf{0.278} \quad (\text{raw}=38,\ \text{min}=18,\ \text{max}=90)$

**Final Metric Vector (named)**  
Order: `desc_nonvio_curr`, `desc_nonvio_past`, `age`, `freq_violent`, `freq_total`, `severity_trend`, `edu_general`, `edu_advanced`, `rehab_general`, `rehab_advanced`  
Values: `[0.500, 1.000, 0.278, SKIPPED, SKIPPED, 0.477, SKIPPED, SKIPPED, SKIPPED, SKIPPED]`

**Suitability (with METRIC_WEIGHTS):** **1.977**



### Example 2 — `0029029e5b`
**Offense Lists (active for this run)**  
- Violent: `['187', '211', '245']`  
- Nonviolent: `['459', '484', '10851']`

**Inputs**
- Current offense rows found: **1**  
- Prior offense rows found: **2**

**Counts by Category**
- Current: `{'violent': 1, 'nonviolent': 0, 'other': 0, 'clash': 0}`  
- Prior:   `{'violent': 2, 'nonviolent': 0, 'other': 0, 'clash': 0}`

**Time Pieces**
- `current_sentence_months = 84.000`  
- `completed_months = 67.200`  
- `past_time_months = NA`  
- `childhood_months = 0.000`  
- `pct_current_completed = 80.000`  
- `time_outside_months = 0.000`

**Formulas + Numeric Plug-ins**
- **Proportion of non‑violent (current)**  

$$
\mathrm{desc}^{\mathrm{nonvio}}_{i,t_d}
= \frac{\mathrm{conv}^{\mathrm{nonvio}}_{i,t_d}}{\mathrm{conv}^{(\mathrm{vio+nonvio})}_{i,t_d}}
$$

$= \tfrac{0}{1} = \mathbf{0.000}$

- **Proportion of non‑violent (past)**  

$$
\mathrm{desc}^{\mathrm{nonvio}}_{i,\,t \lt t_d}
= \frac{\mathrm{conv}^{\mathrm{nonvio}}_{i,\,t \lt t_d}}
       {\mathrm{conv}^{\mathrm{vio+nonvio}}_{i,\,t \lt t_d}}
$$

$= \frac{0}{2} = \mathbf{0.000}$

- **Violent proportions (for trend)**  

$$
\mathrm{desc}^{\mathrm{vio}}_{i,\,t_d} = 1.000
\mathrm{desc}^{\mathrm{vio}}_{i,\,t \lt t_d} = 1.000
$$

- **Severity trend**  

$$
\mathrm{severity\_trend} =
\mathrm{clip}_{[0,1]}\left(
  \frac{\mathrm{desc}^{\text{vio}}_{i,\, t \lt t_d}
        - \mathrm{desc}^{\text{vio}}_{i,\, t_d}}{\mathrm{years}+1}
  \cdot \frac{1}{2} + \frac{1}{2}
\right)
$$

$= \mathbf{0.500} \quad (\mathrm{years\_elapsed}=10)$

- **Frequency**  
  violent\_total \(= 3\); total\_conv \(= 3\); time\_outside \(= 0.000\).  
  Raw rates undefined; normalized **SKIPPED**.

- **Age (min–max)**  

$$
\mathrm{age}_{i, t_d} =
\mathrm{norm}\left(\mathrm{age}^{\text{raw}}_{i, t_d},\,k\right)
$$

$= \mathbf{0.278} \quad (\text{raw}=38,\ \text{min}=18,\ \text{max}=90)$

**Final Metric Vector (named)**  
Order: `desc_nonvio_curr`, `desc_nonvio_past`, `age`, `freq_violent`, `freq_total`, `severity_trend`, `edu_general`, `edu_advanced`, `rehab_general`, `rehab_advanced`  
Values: `[0.000, 0.000, 0.278, SKIPPED, SKIPPED, 0.500, SKIPPED, SKIPPED, SKIPPED, SKIPPED]`

**Suitability (with METRIC_WEIGHTS):** **0.500**

### Re‑generate these examples
**macOS/Linux**
```bash
CFG_PROFILE=DEV python docs_1/make_worked_example.py --uid "0029029e5b" --violent "187,211,245" --nonviolent "459,484,10851" --age-years 38 --exposure-months 480 --freq-bounds "0,0.05" --out docs_1/README_worked_example_0029029e5b.md
CFG_PROFILE=DEV python docs_1/make_worked_example.py --uid "00173d8423" --violent "187,211,245" --nonviolent "459,484,10851" --age-years 38 --exposure-months 480 --freq-bounds "0,0.05" --out docs_1/README_worked_example_00173d8423.md
```
**Windows PowerShell**
```powershell
$env:CFG_PROFILE="DEV"
python docs_1\make_worked_example.py --uid "0029029e5b" --violent "187,211,245" --nonviolent "459,484,10851" --age-years 38 --exposure-months 480 --freq-bounds "0,0.05" --out "docs_1\README_worked_example_0029029e5b.md"
python docs_1\make_worked_example.py --uid "00173d8423" --violent "187,211,245" --nonviolent "459,484,10851" --age-years 38 --exposure-months 480 --freq-bounds "0,0.05" --out "docs_1\README_worked_example_00173d8423.md"
```

## Formulas implemented (LaTeX)
- **Descriptive proportions:**

$$
\mathrm{desc}^{\mathrm{nonvio}}_{i,t_d}
= \frac{\mathrm{conv}^{\mathrm{nonvio}}_{i,t_d}}{\mathrm{conv}^{(\mathrm{vio+nonvio})}_{i,t_d}},
\qquad
\mathrm{desc}^{\mathrm{nonvio}}_{i,t<t_d}
= \frac{\mathrm{conv}^{\mathrm{nonvio}}_{i,t<t_d}}{\mathrm{conv}^{(\mathrm{vio+nonvio})}_{i,t<t_d}}
$$

- **Violent proportions (used in trend):**  
  
$$
\mathrm{desc}^{\mathrm{vio}}_{i,t_d}
  = \frac{\mathrm{conv}^{\mathrm{vio}}_{i,t_d}}{\mathrm{conv}^{(\mathrm{vio+nonvio})}_{i,t_d}},
  \qquad
  \mathrm{desc}^{\mathrm{vio}}_{i,t<t_d}
  = \frac{\mathrm{conv}^{\mathrm{vio}}_{i,t<t_d}}{\mathrm{conv}^{(\mathrm{vio+nonvio})}_{i,t<t_d}}
$$

- **Severity trend:**  
  
$$
\mathrm{severity\_trend}
= \mathrm{clip}_{[0,1]}\left(
    \frac{\mathrm{desc}^{\mathrm{vio}}_{i,t<t_d}-\mathrm{desc}^{\mathrm{vio}}_{i,t_d}}{\mathrm{years}+1}\cdot\frac{1}{2}
      +\frac{1}{2}
    \right)
$$

- **Frequency (per month outside; min–max normalize if bounds are set):**  
Raw rates:
  
$$
r_v = \frac{\mathrm{violent\_total}}{\mathrm{time\_outside}},
\qquad
r_t = \frac{\mathrm{conv\_total}}{\mathrm{time\_outside}}
$$

Normalized:

$$
\hat r = \mathrm{clip}_{[0,1]}\left(\frac{r-\text{min}}{\text{max}-\text{min}}\right)
$$

- **Age (min–max):** 

$$
\mathrm{age}_{i,\,t_d} = \mathrm{norm}\big(\mathrm{age}^{\mathrm{raw}}_{i,\,t_d},\,k\big)
$$

- **Suitability (name‑based, present features only):**  

$$
\text{score}=\sum_{k\in\text{present}} w_k\, m_k
$$

> **Notes:**  
> • Proportion metrics are computed **only** when denominators \(> 0\); otherwise the metric is **SKIPPED**.  
> • Frequency requires **both** `time_outside > 0` **and** configured `freq_min_rate`/`freq_max_rate`.  
> • Rehab/education are per‑month‑inside, then min–max normalized **only if** inputs and bounds are provided; otherwise **omitted**.

## Validation checklist
- Proportion metrics are computed **only** when denominators \(> 0\); otherwise the metric is **SKIPPED**.
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
