# Introduction
Batch runner to compute **population-level sentencing metrics** and **suitability scores** for all individuals, writing a flat file (CSV/Parquet). The pipeline is strict about missing inputs:
when nothing can be evaluated for a person, we emit NaNs instead of 0 so the case can be flagged,
metrics are **skipped** when their prerequisites aren’t present (no fabricated values). Metrics are **named and extensible**; new metrics can be added without changing positional order.

## Contents
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
- `DEFAULT_TIME_ELAPSED_YEARS` and `SEVERITY_DECAY_RATE`:
  control the time horizon and exponential decay in `severity_trend`.
  If `DEFAULT_TIME_ELAPSED_YEARS` is not `None`, it overrides the computed
  years elapsed; `SEVERITY_DECAY_RATE` is the λ in
  `severity = Δv · exp(−λ · years_elapsed)`.

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
- If an ID has no evaluable metrics (e.g. all offenses → other, or required denominators are 0), the runner now writes:
     score = NaN
     score_out_of = NaN
     score_ratio = NaN
     evaluated = 0
This allows downstream tools to tell “not evaluated / insufficient data” apart from “evaluated and low score.
- If `--include-aux` is used, the file also includes `time_outside_months`
  (the paper’s `outᵢᵗ`), representing total months spent outside prison
  across all convictions.
- Errors (if any): `*.errors.jsonl` with `{id, error}` records.
- Console preview prints the first rows/columns for a quick check.

## Worked Examples
These examples walk through **exactly** what the pipeline computes for a specific ID: counts → denominators → proportions → time pieces → trend/frequency → named vector → suitability. The LaTeX below **matches the paper** notation.

### Example 1
**CDCR ID:** `00173d8423`<br>

**Offense Lists (active for this run)**
- Violent: `['187', '211', '245']`
- Nonviolent: `['459', '484', '10851']`

#### Inputs
- Current offense rows found: **11**
- Prior offense rows found: **6**

#### Counts by Category
- Current: {'violent': 1, 'nonviolent': 1, 'other': 9, 'clash': 0}
- Prior:   {'violent': 0, 'nonviolent': 4, 'other': 2, 'clash': 0}

#### Time Pieces
- `current_sentence_months` = 10000.000
- `completed_months` = 330.000
- `past_time_months` = NA 
- `pct_current_completed` = 3.300
- `time_outside_months` = 0.000

**Definition:**

$$
\mathrm{out}^t_i = t_d - \mathrm{in}^{(\mathrm{vio+nonvio}),t}_i - \text{childhood}.
$$

#### Calculations

- `desc_nonvio_curr = 1/2 = 0.500` (see Eq. **DESC-NONVIO-CURR**)
- `desc_nonvio_past = 4/4 = 1.000` (see Eq. **DESC-NONVIO-PAST**)

- Violent proportions for trend:
  - `desc_vio_curr = 1/2 = 0.500` (see Eq. **DESC-VIO-CURR**)
  - `desc_vio_past = 0/4 = 0.000` (see Eq. **DESC-VIO-PAST**)

- Severity trend:
  - `severity_trend = 0.500 * exp(-0.150 * 10.0) = 0.112` (see Eq. **SEVERITY-TREND**;  `severity_trend = Δv * exp(-λ * T)`)

- Frequency (per month outside):
  - `raw_freq_violent = NA; raw_freq_total = NA`
  - `normalized: **SKIPPED**` (requires `time_outside > 0`, `freq_min_rate` and `freq_max_rate`)
     (see Eqs. **FREQ-VIO**, **FREQ-TOTAL**)

- Age (min–max):
  - `age_raw = 38.000`, `min = 18.000`, `max = 90.000` → `age = 0.278` (see Eq. **AGE-NORM**)

#### Final Metric Vector
Order: `desc_nonvio_curr, desc_nonvio_past, age, freq_violent, freq_total, severity_trend, edu_general, edu_advanced, rehab_general, rehab_advanced`  
Values: `[0.500, 1.000, 0.278, SKIPPED, SKIPPED, 0.112, SKIPPED, SKIPPED, SKIPPED, SKIPPED]`

**Score:** `1.889` (out of `3.000`) — **63.0% of maximum**    
**Contributing metrics:** `age, desc_nonvio_curr, desc_nonvio_past, severity_trend`


### Example 2 
**CDCR ID:** `0029029e5b`<br>

**Offense Lists (active for this run)**
- Violent: `['187', '211', '245']`
- Nonviolent: `['459', '484', '10851']`

#### Inputs
- Current offense rows found: **1**
- Prior offense rows found: **2**

#### Counts by Category
- Current: {'violent': 1, 'nonviolent': 0, 'other': 0, 'clash': 0}
- Prior:   {'violent': 2, 'nonviolent': 0, 'other': 0, 'clash': 0}


#### Time Pieces
- `current_sentence_months` = 84.000
- `completed_months` = 67.200
- `past_time_months` = NA
- `pct_current_completed` = 80.000
- `time_outside_months` = 0.000

**Definition:**

$$
\mathrm{out}^t_i = t_d - \mathrm{in}^{(\mathrm{vio+nonvio}),t}_i - \text{childhood}.
$$

#### Calculations

- `desc_nonvio_curr = 0/1 = 0.000` (see Eq. **DESC-NONVIO-CURR**)
- `desc_nonvio_past = 0/2 = 0.000` (see Eq. **DESC-NONVIO-PAST**)

- Violent proportions for trend:
  - `desc_vio_curr = 1/1 = 1.000` (see Eq. **DESC-VIO-CURR**)
  - `desc_vio_past = 2/2 = 1.000` (see Eq. **DESC-VIO-PAST**)

- Severity trend:
  - `severity_trend = 0.000` (Δv = 0.000, so severity trend is 0; see Eq. **SEVERITY-TREND**, `severity_trend = Δv * exp(-λ * T)`)

- Frequency (per month outside):
  - `violent_total = 3; total_conv = 3; time_outside = 0.000`
  - `raw_freq_violent = NA; raw_freq_total = NA`
  - `normalized: **SKIPPED**` (requires `time_outside > 0`, `freq_min_rate` and `freq_max_rate`)
    (see Eqs. **FREQ-VIO**, **FREQ-TOTAL**)

- Age (min–max):
  - `age_raw = 38.000`, `min = 18.000`, `max = 90.000` → `age = 0.278` (see Eq. **AGE-NORM**)

#### Final Metric Vector
Order: `desc_nonvio_curr, desc_nonvio_past, age, freq_violent, freq_total, severity_trend, edu_general, edu_advanced, rehab_general, rehab_advanced`  
Values: `[0.000, 0.000, 0.278, SKIPPED, SKIPPED, 0.000, SKIPPED, SKIPPED, SKIPPED, SKIPPED]`

**Score:** `0.278` (out of `3.000`) — **9.3% of maximum**   
**Contributing metrics:** `age, desc_nonvio_curr, desc_nonvio_past, severity_trend`

### Re‑generate Examples
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

## Formulas Implemented
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

- **Severity trend (updated exponential form):**  

We first define the change in violent share between past and current.
Let $v_i^{\text{curr}}$ and $v_i^{\text{past}}$ be the current and past violent proportions for person $i$.

$$
\Delta v_i = \max\bigl(0, v_i^{\text{curr}} - v_i^{\text{past}}\bigr),
\qquad \Delta v_i \in [0,1].
$$

Only **increases** in violent share are penalized (if the violent share does not increase, 
Δv<sub>i</sub> = 0).

Let \(\lambda > 0\) be the decay rate (configured as `SEVERITY_DECAY_RATE` in `config.py`), and let
$T_i \ge 0$ be the time horizon in years (computed from first prior → last current commitment,
optionally overridden by `DEFAULT_TIME_ELAPSED_YEARS`).

The implemented severity trend is:

$$
\mathrm{severity\_trend}_i
=\Delta v_i \cdot \exp\bigl(-\lambda \, T_i\bigr),
\qquad \mathrm{severity\_trend}_i \in [0,1].
$$

Properties:

- The **ideal value** is \(0\) (no recent worsening in severity).
- Larger values correspond to **more recent increases** in violent share.
- The exponential term down-weights very old changes.


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


>**Notes:**  
> • Proportion metrics are computed **only** when denominators \(> 0\); otherwise the metric is **SKIPPED**.  
> • Frequency requires **both** `time_outside > 0` **and** configured `freq_min_rate`/`freq_max_rate`.  
> • Rehab/education are per‑month‑inside, then min–max normalized **only if** inputs and bounds are provided; otherwise **omitted**.

## Validation Checklist
- Proportion metrics are computed **only** when denominators \(> 0\); otherwise the metric is **SKIPPED**.
- Frequency requires **both** `time_outside > 0` **and** `freq_min_rate`/`freq_max_rate` in `config.py`.
- Offense classification uses only `OFFENSE_LISTS`; anything unlisted → **other** (and does not contribute to denominators).
- Suitability uses **only present (gated)** features with explicit `METRIC_WEIGHTS` (no hidden zero‑weights).
- When comparing individuals (similarity), compute on the **intersection of present features** and require a minimum shared‑dimension count (e.g., ≥3). Consider also Euclidean or Tanimoto for sensitivity analysis.
- If no metrics pass the gating (denominators 0, missing exposure, missing age, etc.), the scorer returns NaN (or None, depending on runner) and sets evaluated = 0. This is intentional and we do not fabricate zeros for unevaluable people.

## Programmatic Example
```python
import math
import config as CFG
import compute_metrics as cm
import sentencing_math as sm
import pandas as pd

# load source tables
demo = cm.read_table(CFG.PATHS["demographics"])
cur  = cm.read_table(CFG.PATHS["current_commitments"])
pri  = cm.read_table(CFG.PATHS["prior_commitments"])

# take a few IDs for the demo
ids = demo[CFG.COLS["id"]].astype(str).dropna().unique().tolist()[:3]

rows = []
for uid in ids:
    feats, aux = cm.compute_features(uid, demo, cur, pri, CFG.OFFENSE_LISTS)

    # name-based suitability; may return NaN/None if no evaluable metrics
    score_ratio, num, den = sm.suitability_score_named(
        feats,
        weights=CFG.METRIC_WEIGHTS,
        directions=getattr(CFG, "METRIC_DIRECTIONS", {}),
        return_parts=True,
    )  # score_ratio == (num / den) when den > 0

    # NaN / “not evaluated” safe handling
    no_denom = (
        den is None
        or den == 0
        or (isinstance(den, float) and math.isnan(den))
    )
    if no_denom:
        score_ratio_safe = math.nan
        num_safe = math.nan
        den_safe = math.nan
        evaluated = 0
    else:
        score_ratio_safe = float(score_ratio)
        num_safe = float(num)
        den_safe = float(den)
        evaluated = 1

    # Optional: expose time_outside if present in aux
    time_outside_months = aux.get("time_outside")
    pct_completed = aux.get("pct_completed")

    rows.append(
        {
            CFG.COLS["id"]: uid,
            **feats,                     # all computed named metrics
            "score": num_safe,           # numerator (Σ w·m)
            "score_out_of": den_safe,    # denominator (Σ w·x*)
            "score_ratio": score_ratio_safe,
            "evaluated": evaluated,      # 1 = evaluated, 0 = not evaluable
            "time_outside_months": time_outside_months,
            "pct_completed": pct_completed,
        }
    )

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
