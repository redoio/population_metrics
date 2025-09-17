# compute_metrics.py

from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
import argparse, re
import numpy as np
import pandas as pd

import config as CFG
import sentencing_math as sm


# Small config helpers

def _cfg_col(name: str) -> Optional[str]:
    return getattr(CFG, "COLS", {}).get(name)

def _cfg_default(key: str, fallback: Any) -> Any:
    return getattr(CFG, "DEFAULTS", {}).get(key, fallback)


# I/O (CSV/XLSX via pandas)


# 5-line helper: accept GitHub "blob" URLs in config by converting to raw
def _to_raw_github_url(path: str) -> str:
    if not isinstance(path, str): return path
    if "github.com" not in path:  return path
    return path.replace("https://github.com/", "https://raw.githubusercontent.com/").replace("/blob/", "/")

def read_table(path: str) -> pd.DataFrame:
    path = _to_raw_github_url(path)
    p = (path or "").lower()
    if p.startswith(("http://", "https://")):
        if p.endswith((".xlsx", ".xls")): return pd.read_excel(path)
        return pd.read_csv(path)
    if p.endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    return pd.read_csv(path)

def get_row_by_id(df: pd.DataFrame, id_col: str, uid: str) -> Optional[pd.Series]:
    if df is None or id_col not in df.columns:
        return None
    sub = df.loc[df[id_col].astype(str) == str(uid)]
    return None if sub.empty else sub.iloc[0]


# Parsing (NaN-honest)

def _to_float_or_nan(x: Any) -> float:
    try:
        if pd.isna(x): return np.nan
        return float(str(x).replace(",", ""))
    except Exception:
        return np.nan

def to_months(val: Any, colname: Optional[str]) -> float:
    """Unit-aware: infer months from the column name."""
    x = _to_float_or_nan(val)
    if np.isnan(x): return np.nan
    nm = (colname or "").lower()
    if "year" in nm: return x * 12.0
    if "day"  in nm: return x / 30.0
    return x  # assume already months


# Offense classification

_PENAL_RE = re.compile(r"[0-9]{2,5}(?:\.[0-9]+)?")

def classify_offense(code_or_text: Any, lists: Dict[str, Any]) -> str:
    if code_or_text is None or (isinstance(code_or_text, float) and pd.isna(code_or_text)):
        return "other"
    s = str(code_or_text).strip().lower()
    m = _PENAL_RE.search(s)
    norm = m.group(0) if m else s

    vio = (lists.get("violent") or [])
    non = lists.get("nonviolent")

    is_v = norm in vio
    is_n = isinstance(non, list) and (norm in non)

    if is_v and is_n: return "clash"
    if is_v:          return "violent"
    if isinstance(non, list): return "nonviolent" if is_n else "other"
    if non == "rest": return "nonviolent"
    return "other"

def count_offenses_by_category(df: pd.DataFrame, id_col: str, uid: str,
                               offense_col: str, lists: Dict[str, Any]) -> Dict[str, int]:
    out = {"violent": 0, "nonviolent": 0, "other": 0, "clash": 0}
    if df is None or offense_col not in df.columns or id_col not in df.columns:
        return out
    sub = df.loc[df[id_col].astype(str) == str(uid)]
    for _, row in sub.iterrows():
        out[classify_offense(row[offense_col], lists)] += 1
    return out


# Time + Age extractors

def extract_time_inputs(demo_row: Optional[pd.Series]) -> Optional[sm.TimeInputs]:
    if demo_row is None: return None

    cur = to_months(demo_row.get(_cfg_col("current_sentence")), _cfg_col("current_sentence"))
    com = to_months(demo_row.get(_cfg_col("completed_time")),  _cfg_col("completed_time"))
    pas = to_months(demo_row.get(_cfg_col("past_time")),       _cfg_col("past_time")) if _cfg_col("past_time") else _cfg_default("missing_numeric", np.nan)

    # require current + completed by default
    req = tuple(_cfg_default("require_time_fields", ("current_sentence", "completed_time")))
    need_cur = "current_sentence" in req
    need_com = "completed_time"   in req
    if (need_cur and np.isnan(cur)) or (need_com and np.isnan(com)):
        return None

    return sm.TimeInputs(
        current_sentence_months=cur,
        completed_months=com,
        past_time_months=pas,
        childhood_months=float(_cfg_default("childhood_months", 0.0)),
    )

def extract_age_years(demo_row: Optional[pd.Series]) -> Optional[float]:
    if demo_row is None: return None
    col = _cfg_col("age_years")
    if col and (col in demo_row) and pd.notna(demo_row[col]):
        return _to_float_or_nan(demo_row[col])
    return None


# Feature computation

def compute_features(uid: str,
                     demo: pd.DataFrame,
                     current_df: pd.DataFrame,
                     prior_df: pd.DataFrame,
                     lists: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """Returns (features, auxiliary_info). Features may contain NaN."""
    cols = CFG.COLS
    row  = get_row_by_id(demo, cols["id"], uid)

    feats: Dict[str, float] = {}
    aux:   Dict[str, Any]   = {}

    # Time
    t = extract_time_inputs(row)
    if t:
        aux["time_inputs"] = t
        _, pct_completed, time_outside = sm.compute_time_vars(t, None)
        aux["pct_completed"] = pct_completed
        aux["time_outside"]  = time_outside
    else:
        aux["pct_completed"] = np.nan
        aux["time_outside"]  = np.nan

    # Age → normalized
    age_val = extract_age_years(row)
    if age_val is None or np.isnan(age_val):
        age_val = _cfg_default("age_fallback_years", np.nan)
    feats["age"] = sm.score_age_norm(age_val, _cfg_default("age_min", None), _cfg_default("age_max", None))
    aux["age_value"] = age_val

    # Convictions
    cur = count_offenses_by_category(current_df, cols["id"], uid, cols["current_offense_text"], lists)
    pri = count_offenses_by_category(prior_df,   cols["id"], uid, cols["prior_offense_text"],   lists)
    aux["counts_by_category"] = {"current": cur, "prior": pri}

    conv = sm.ConvictionCounts(
        curr_nonviolent=cur["nonviolent"], curr_violent=cur["violent"],
        past_nonviolent=pri["nonviolent"], past_violent=pri["violent"],
    )
    curr_total = conv.curr_nonviolent + conv.curr_violent
    past_total = conv.past_nonviolent + conv.past_violent

    # Descriptive proportions
    feats["desc_nonvio_curr"] = sm.score_desc_nonvio_curr(conv.curr_nonviolent, curr_total)
    feats["desc_nonvio_past"] = sm.score_desc_nonvio_past(conv.past_nonviolent, past_total)

    # Frequency + trend (use NaN-friendly helpers)
    conv_total   = curr_total + past_total
    violent_total= conv.curr_violent + conv.past_violent
    minr, maxr   = _cfg_default("freq_min_rate", None), _cfg_default("freq_max_rate", None)
    yrs_elapsed  = _cfg_default("trend_years_elapsed", 0.0)

    time_outside = aux["time_outside"]
    feats["freq_violent"] = sm.score_freq_violent(violent_total, time_outside, minr, maxr)
    feats["freq_total"]   = sm.score_freq_total(  conv_total,   time_outside, minr, maxr)

    desc_vio_curr = sm.clip01(sm.safe_div(conv.curr_violent, curr_total))
    desc_vio_past = sm.clip01(sm.safe_div(conv.past_violent, past_total))
    feats["severity_trend"] = sm.score_severity_trend(desc_vio_curr, desc_vio_past, yrs_elapsed)

    return feats, aux


# Scoring

def aligned_linear_score(weights: Dict[str, float], feats: Dict[str, float]) -> float:
    keys = [k for k in feats if k in weights]
    vals = [weights[k] * feats[k] for k in keys]
    return float(np.nansum(vals))   # NaN contributes 0; change to sum(vals) to propagate NaN


# CLI

def _round_or_nan(x):
    try: return float(np.round(x, 3))
    except Exception: return x

def main():
    ap = argparse.ArgumentParser(description="Compute sentencing metrics for a single ID.")
    ap.add_argument("--cdcr-id", required=True)
    args = ap.parse_args()

    demo = read_table(CFG.PATHS["demographics"])
    cur  = read_table(CFG.PATHS["current_commitments"])
    pri  = read_table(CFG.PATHS["prior_commitments"])

    lists   = getattr(CFG, "OFFENSE_LISTS", {"violent": [], "nonviolent": "rest"})
    weights = getattr(CFG, "WEIGHTS_10D", {
        "desc_nonvio_curr": 1.0, "desc_nonvio_past": 1.0, "age": 1.0,
        "freq_violent": 0.0, "freq_total": 0.0, "severity_trend": 0.0,
        "edu_general": 0.0, "edu_advanced": 0.0, "rehab_general": 0.0, "rehab_advanced": 0.0,
    })

    feats, aux = compute_features(args.cdcr_id, demo, cur, pri, lists)
    score = aligned_linear_score(weights, feats)

    print("\n Sentencing Metrics")
    print("CDCR ID:", args.cdcr_id)
    print("Features:", {k: _round_or_nan(v) for k, v in feats.items()})
    print("Linear score:", _round_or_nan(score))
    if "counts_by_category" in aux:
        print("Counts (current):", aux["counts_by_category"]["current"])
        print("Counts (prior):",   aux["counts_by_category"]["prior"])
    print("Age used:", aux.get("age_value"))
    print("Pct completed:", _round_or_nan(aux.get("pct_completed")))
    print("Time outside (months):", _round_or_nan(aux.get("time_outside")))

if __name__ == "__main__":
    main()
