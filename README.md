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
- Main file: CSV/Parquet with one row per ID, including named metrics, `score` (suitability), and `score_out_of` (sum of absolute weights for present metrics).
- If `--include-aux` is used, the file also includes `time_outside_months` ( \( \mathrm{out}^t_i \) ), representing total months spent outside prison across all convictions.
- Errors (if any): `*.errors.jsonl` with `{id, error}` records.
- Console preview prints the first rows/columns for a quick check.

## Worked examples (from scratch)
These examples walk through **exactly** what the pipeline computes for a specific ID: counts → denominators → proportions → time pieces → trend/frequency → named vector → suitability. The LaTeX below **matches the paper** notation.

# Worked Example (REAL DATA)

**CDCR ID:** `00173d8423`
**Offense Lists (active for this run)**
- Violent: `['187', '211', '245']`
- Nonviolent: `['459', '484', '10851']`

## Inputs
- Current offense rows found: **11**
- Prior offense rows found: **6**

### Counts by Category
- Current: {'violent': 1, 'nonviolent': 1, 'other': 9, 'clash': 0}
- Prior:   {'violent': 0, 'nonviolent': 4, 'other': 2, 'clash': 0}

### Time Pieces
- current_sentence_months = 10000.000
- completed_months = 330.000
- past_time_months = NA
- childhood_months = 0.000
- pct_current_completed = 3.300
- time_outside_months = 0.000

### Calculations (refer to LaTeX section for formulas)

- `desc_nonvio_curr = 1/2 = 0.500` (see Eq. **DESC-NONVIO-CURR**)
- `desc_nonvio_past = 4/4 = 1.000` (see Eq. **DESC-NONVIO-PAST**)

- Violent proportions for trend:
  - `desc_vio_curr = 1/2 = 0.500` (see Eq. **DESC-VIO-CURR**)
  - `desc_vio_past = 0/4 = 0.000` (see Eq. **DESC-VIO-PAST**)

- Severity trend:
  - `severity_trend = ((0.000 − 0.500)/10.000 + 1)/2 = 0.477` (see Eq. **SEVERITY-TREND**)

- Frequency (per month outside):
  - `time_outside_months = 0.000` → **SKIPPED** (requires `time_outside > 0` and bounds)  
    (see Eqs. **FREQ-VIO**, **FREQ-TOTAL**)

- Age (min–max):
  - `age_raw = 38.000`, `min = 18.000`, `max = 90.000` → `age = 0.278` (see Eq. **AGE-NORM**)

## Final Metric Vector (named)
Order: `desc_nonvio_curr, desc_nonvio_past, age, freq_violent, freq_total, severity_trend, edu_general, edu_advanced, rehab_general, rehab_advanced`  
Values: `[0.500, 1.000, 0.278, SKIPPED, SKIPPED, 0.477, SKIPPED, SKIPPED, SKIPPED, SKIPPED]`

**Score:** `0.659` (out of `3.000`) — **22.0% of maximum**  
“Out-of” is computed as described in Eq. **OUT-OF**.  
**Contributing metrics:** `age, desc_nonvio_curr, desc_nonvio_past, severity_trend`


### Example 2 
**CDCR ID:** `0029029e5b`

**Offense Lists (active for this run)**
- Violent: `['187', '211', '245']`
- Nonviolent: `['459', '484', '10851']`

## Inputs
- Current offense rows found: **1**
- Prior offense rows found: **2**

### Counts by Category
- Current: {'violent': 1, 'nonviolent': 0, 'other': 0, 'clash': 0}
- Prior:   {'violent': 2, 'nonviolent': 0, 'other': 0, 'clash': 0}


### Time Pieces
- current_sentence_months = 84.000
- completed_months = 67.200
- past_time_months = NA
- childhood_months = 0.000
- pct_current_completed = 80.000
- time_outside_months = 0.000

### Calculations (refer to LaTeX section for formulas)

- `desc_nonvio_curr = 0/1 = 0.000` (see Eq. **DESC-NONVIO-CURR**)
- `desc_nonvio_past = 0/2 = 0.000` (see Eq. **DESC-NONVIO-PAST**)

- Violent proportions for trend:
  - `desc_vio_curr = 1/1 = 1.000` (see Eq. **DESC-VIO-CURR**)
  - `desc_vio_past = 2/2 = 1.000` (see Eq. **DESC-VIO-PAST**)

- Severity trend:
  - `severity_trend = ((1.000 − 1.000)/10.000 + 1)/2 = 0.500` (see Eq. **SEVERITY-TREND**)

- Frequency (per month outside):
  - `time_outside_months = 0.000` → **SKIPPED** (requires `time_outside > 0` and bounds)  
    (see Eqs. **FREQ-VIO**, **FREQ-TOTAL**)

- Age (min–max):
  - `age_raw = 38.000`, `min = 18.000`, `max = 90.000` → `age = 0.278` (see Eq. **AGE-NORM**)

## Final Metric Vector (named)
Order: `desc_nonvio_curr, desc_nonvio_past, age, freq_violent, freq_total, severity_trend, edu_general, edu_advanced, rehab_general, rehab_advanced`  
Values: `[0.000, 0.000, 0.278, SKIPPED, SKIPPED, 0.500, SKIPPED, SKIPPED, SKIPPED, SKIPPED]`

**Score:** `0.167` (out of `3.000`) — **5.6% of maximum**  
“Out-of” is computed as described in Eq. **OUT-OF**.  
**Contributing metrics:** `age, desc_nonvio_curr, desc_nonvio_past, severity_trend`

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
severity_i^{\mathrm{trend},t_d}
=\frac{\dfrac{\mathrm{desc}_i^{\mathrm{vio},t< t_d}-\mathrm{desc}_i^{\mathrm{vio},t_d}}{\text{years elapsed}}+1}{2},\qquad \in [0,1]
$$


- **Frequency (per month outside; min–max normalize if bounds are set):**  

Normalized:

$$
\mathrm{freq}_{i}^{\mathrm{vio,score},t}
=\frac{\left(\dfrac{\mathrm{conv}_{i}^{\mathrm{vio},t}}{\mathrm{out}_{i}^{t}}\right)-
\min_{\forall\,k\in N}\left(\dfrac{\mathrm{conv}_{k}^{(\mathrm{vio+nonvio}),t}}{\mathrm{out}_{k}^{t}}\right)}{\max_{\forall\,k\in N}\left(\dfrac{\mathrm{conv}_{k}^{(\mathrm{vio+nonvio}),t}}{\mathrm{out}_{k}^{t}}\right)-\min_{\forall\,k\in N}\left(\dfrac{\mathrm{conv}_{k}^{(\mathrm{vio+nonvio}),t}}{\mathrm{out}_{k}^{t}}\right)
},
\quad \in (0,1].
$$

$$
\mathrm{freq}_{i}^{(\mathrm{vio+nonvio}),\mathrm{score},t}
=\mathrm{norm}\left(\frac{\mathrm{conv}_{i}^{(\mathrm{vio+nonvio}),t}}{\mathrm{out}_{i}^{t}},k
\right),
\quad \in (0,1].
$$


- **Age (min–max):** 

$$
\mathrm{age}_{i,t_d}=\mathrm{norm}\big(\mathrm{age}^{\mathrm{raw}}_{i,t_d},k\big)
$$

- **Suitability (weighted dot product of available normalized metrics):**

$$
\mathrm{score}_i=\sum_{k \in K_{\mathrm{present}}} w_k m_{k,i},\qquad
K_{\mathrm{present}} \subseteq K_{\mathrm{all}}.
$$

**Out of:**

$$
\mathrm{out of}_i = \sum_{k \in K_{\mathrm{present}}} w_k \, x_k^{\star}, 
\qquad x_k^{\star} \in \{0, 1\}
$$

**Direction:**  

We encode orientation using `d_k ∈ {+1, −1}`:

- `d_k = +1` → higher metric value `m_{k,i}` **increases** suitability  
- `d_k = −1` → higher metric value `m_{k,i}` **decreases** suitability  

Weights `w_k ≥ 0` represent magnitudes only.  
The numerator uses `w_k * m_{k,i}` and the “out-of” denominator uses `w_k * x_k*`,  
where `x_k* = 1` for `d_k = +1` (positive-direction metrics)  
and `x_k* = 0` for `d_k = −1` (negative-direction metrics).


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

    # Compute suitability score (directional dot product)
    present = feats.keys() & CFG.METRIC_WEIGHTS.keys()
    score = sm.suitability_score_named(feats, CFG.METRIC_WEIGHTS)
    score_out_of = sum(abs(CFG.METRIC_WEIGHTS[k]) for k in present)

    # Optional: expose time_outside if present in aux
    time_outside = aux.get("time_outside", None)

    rows.append({
        CFG.COLS["id"]: uid,
        **feats,
        "score": score,
        "score_out_of": score_out_of,
        "time_outside": time_outside
    })
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
