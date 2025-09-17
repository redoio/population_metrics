# compute_metrics_v2.py

# Config-driven sentencing metrics. No auto-detection, skip-if-missing.

from __future__ import annotations
import argparse, re
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd

import config as CFG
from sentencing_math import (
    TimeInputs, ConvictionCounts,
    compute_time_vars, clip01, safe_div,
    score_desc_nonvio_curr, score_desc_nonvio_past,
    score_age_norm, score_freq_violent, score_freq_total,
    score_severity_trend,
)

# I/O 
def _read(path: str) -> pd.DataFrame:
    p = path.lower()
    if p.endswith(".xlsx") or p.endswith(".xls"):
        return pd.read_excel(path)
    return pd.read_csv(path)

def _get_row(df: pd.DataFrame, id_col: str, uid: str) -> Optional[pd.Series]:
    sub = df.loc[df[id_col].astype(str) == str(uid)]
    if sub.empty:
        return None
    return sub.iloc[0]

def _to_float(x) -> Optional[float]:
    try:
        if pd.isna(x): return None
        return float(str(x).replace(",", ""))
    except Exception:
        return None

def _months_unit_aware(val: Any, colname: str) -> Optional[float]:
    if val is None: return None
    name = (colname or "").lower()
    x = _to_float(val)
    if x is None: return None
    if "year" in name: return x * 12.0
    if "day" in name:  return x / 30.0
    return x

# Offense classification 
def classify_offense(code_or_text: str, lists: Dict[str, Any]) -> str:
    if not code_or_text: return "other"
    s = str(code_or_text).strip()

    # normalize penal code digits
    m = re.search(r"[0-9]{2,5}(?:\.[0-9]+)?", s)
    norm = m.group(0) if m else s

    vio_list = lists.get("violent", [])
    nonvio_list = lists.get("nonviolent", [])

    # Check clashes
    is_vio = norm in vio_list
    is_nonvio = isinstance(nonvio_list, list) and norm in nonvio_list
    if is_vio and is_nonvio:
        return "clash"

    # Case 1: violent match
    if is_vio:
        return "violent"

    # Case 2: nonviolent list is explicit
    if isinstance(nonvio_list, list):
        if is_nonvio:
            return "nonviolent"
        else:
            return "other"  # leftover

    # Case 3: nonviolent == "rest"
    if nonvio_list == "rest":
        return "nonviolent"

    return "other"

def count_by_category(df: pd.DataFrame, id_col: str, uid: str,
                      offense_col: str, cat_col: Optional[str],
                      lists: Dict[str, Any]) -> Dict[str, int]:
    out = {"violent": 0, "nonviolent": 0, "other": 0, "clash": 0}
    sub = df.loc[df[id_col].astype(str) == str(uid)]
    if sub.empty: return out

    for _, row in sub.iterrows():
        val = row[offense_col] if offense_col in row else None
        cat = classify_offense(val, lists)
        out[cat] += 1
    return out

# Feature computation 
def maybe_time_inputs(row: Optional[pd.Series]) -> Optional[TimeInputs]:
    if row is None: return None
    c = CFG.COLS
    cur = _months_unit_aware(row.get(c["current_sentence"]), c["current_sentence"])
    com = _months_unit_aware(row.get(c["completed_time"]),  c["completed_time"])
    pas = _months_unit_aware(row.get(c["past_time"]),       c["past_time"]) if c["past_time"] else 0.0
    if cur is None or com is None:
        return None
    return TimeInputs(
        current_sentence_months=float(cur or 0.0),
        completed_months=float(com or 0.0),
        past_time_months=float(pas or 0.0),
        childhood_months=float(CFG.DEFAULTS["childhood_months"] or 0.0),
    )

def maybe_age(row: Optional[pd.Series]) -> Optional[float]:
    c = CFG.COLS
    if row is None: return None
    if c["age_years"] and c["age_years"] in row and pd.notna(row[c["age_years"]]):
        return _to_float(row[c["age_years"]])
    return None

def compute_features(uid: str,
                     demo: pd.DataFrame,
                     current_df: pd.DataFrame,
                     prior_df: pd.DataFrame,
                     lists: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, Any]]:
    cols = CFG.COLS
    row = _get_row(demo, cols["id"], uid)

    feats: Dict[str, float] = {}
    aux:  Dict[str, Any] = {}

    # Time
    tinputs = maybe_time_inputs(row)
    if tinputs:
        aux["time_inputs"] = tinputs
        _, pct_completed, time_outside = compute_time_vars(tinputs, None)
        aux["pct_completed"] = pct_completed
        aux["time_outside"]  = time_outside
    else:
        time_outside = None

    # Age
    age_val = maybe_age(row)
    if age_val is None:
        age_val = CFG.DEFAULTS["age_fallback_years"]
    feats["age"] = score_age_norm(age_val, CFG.DEFAULTS["age_min"], CFG.DEFAULTS["age_max"])
    aux["age_value"] = age_val

    # Convictions
    cur_counts = count_by_category(current_df, cols["id"], uid, cols["current_offense_text"], cols["current_category_text"], lists)
    pri_counts = count_by_category(prior_df, cols["id"], uid, cols["prior_offense_text"], cols["prior_category_text"], lists)
    aux["counts_by_category"] = {"current": cur_counts, "prior": pri_counts}

    conv = ConvictionCounts(
        curr_nonviolent=cur_counts["nonviolent"],
        curr_violent=cur_counts["violent"],
        past_nonviolent=pri_counts["nonviolent"],
        past_violent=pri_counts["violent"],
    )

    conv_curr_total = conv.curr_nonviolent + conv.curr_violent
    conv_past_total = conv.past_nonviolent + conv.past_violent
    feats["desc_nonvio_curr"] = score_desc_nonvio_curr(conv.curr_nonviolent, conv_curr_total)
    feats["desc_nonvio_past"] = score_desc_nonvio_past(conv.past_nonviolent, conv_past_total)

    # Frequency & trend
    if tinputs is not None:
        conv_total = conv_curr_total + conv_past_total
        conv_violent_total = conv.curr_violent + conv.past_violent
        feats["freq_violent"] = score_freq_violent(conv_violent_total, time_outside,
                                                   CFG.DEFAULTS["freq_min_rate"], CFG.DEFAULTS["freq_max_rate"])
        feats["freq_total"]   = score_freq_total(conv_total, time_outside,
                                                 CFG.DEFAULTS["freq_min_rate"], CFG.DEFAULTS["freq_max_rate"])
        desc_vio_curr = clip01(safe_div(conv.curr_violent, conv_curr_total))
        desc_vio_past = clip01(safe_div(conv.past_violent, conv_past_total))
        feats["severity_trend"] = score_severity_trend(desc_vio_curr, desc_vio_past,
                                                       CFG.DEFAULTS["trend_years_elapsed"])

    return feats, aux

def aligned_linear_score(weights: Dict[str, float], feats: Dict[str, float]) -> float:
    keys = [k for k in feats.keys() if k in weights]
    return sum(weights[k] * feats[k] for k in keys)

# CLI 
def main():
    ap = argparse.ArgumentParser(description="Config-driven sentencing metrics (single ID).")
    ap.add_argument("--cdcr-id", required=True)
    args = ap.parse_args()

    demo = _read(CFG.PATHS["demographics"])
    cur  = _read(CFG.PATHS["current_commitments"])
    pri  = _read(CFG.PATHS["prior_commitments"])

    lists = CFG.OFFENSE_LISTS

    feats, aux = compute_features(args.cdcr_id, demo, cur, pri, lists)
    score = aligned_linear_score(CFG.WEIGHTS_10D, feats)

    print("\n Sentencing Metrics (config-driven) ")
    print("CDCR ID:", args.cdcr_id)
    print("Features:", {k: round(v, 3) for k, v in feats.items()})
    print("Linear score:", round(score, 3))
    print("Counts (current):", aux["counts_by_category"]["current"])
    print("Counts (prior):", aux["counts_by_category"]["prior"])
    print("Age used:", aux.get("age_value"))

if __name__ == "__main__":
    main()
