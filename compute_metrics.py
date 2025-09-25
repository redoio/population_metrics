#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compute_metrics.py — config-driven, raw-data–oriented (library only)

Pipeline (library functions):
  read → parse → classify → time → features
Scoring/printing should be handled by a separate runner (e.g., run_compute_metrics.py).

Relies on:
  - config.py: PATHS, COLS, DEFAULTS, OFFENSE_LISTS, METRIC_WEIGHTS (or WEIGHTS_10D)
  - sentencing_math.py: pure math helpers (imported as sm)

Design notes:
  • Missing numerics remain NaN (configurable via DEFAULTS["missing_numeric"]).
  • Time fields are unit-aware by column name: "...year..."→*12, "...day..."→/30, else months.
  • Convictions are handled via sm.Convictions (single class).
  • Weights are NAME-BASED and should be applied outside this module.
  • Exposure window: uses DEFAULTS["months_elapsed_total"] if provided; otherwise
    computes per-person exposure as months from (DOB+18y) to reference_date.
"""

from __future__ import annotations
from typing import Any, Dict, Optional, Tuple
import re

import numpy as np
import pandas as pd
from pandas.tseries.offsets import DateOffset

import config as CFG
import sentencing_math as sm



# Small config helpers


def _cfg_col(name: str) -> Optional[str]:
    """Return configured column name (or None) for a logical field."""
    return getattr(CFG, "COLS", {}).get(name)

def _cfg_default(key: str, fallback: Any) -> Any:
    """Return configured default for a key (with fallback)."""
    return getattr(CFG, "DEFAULTS", {}).get(key, fallback)



# I/O (CSV/XLSX via pandas)


def _to_raw_github_url(path: str) -> str:
    """Allow GitHub 'blob' URLs in config by converting them to 'raw' URLs."""
    if not isinstance(path, str):
        return path
    if "github.com" not in path:
        return path
    return path.replace("https://github.com/", "https://raw.githubusercontent.com/").replace("/blob/", "/")

def read_table(path: str) -> pd.DataFrame:
    """Read CSV/XLSX from local path or HTTP(S)."""
    path = _to_raw_github_url(path)
    p = (path or "").lower()
    if p.startswith(("http://", "https://")):
        if p.endswith((".xlsx", ".xls")):
            return pd.read_excel(path)
        return pd.read_csv(path)
    if p.endswith((".xlsx", ".xls")):
        return pd.read_excel(path)
    return pd.read_csv(path)

def get_row_by_id(df: pd.DataFrame, id_col: str, uid: str) -> Optional[pd.Series]:
    """Return first row matching the given id value (or None if missing)."""
    if df is None or id_col not in df.columns:
        return None
    sub = df.loc[df[id_col].astype(str) == str(uid)]
    return None if sub.empty else sub.iloc[0]



# Parsing (NaN-honest)


def _to_float_or_nan(x: Any) -> float:
    """Parse numeric strings safely; return NaN if missing/invalid."""
    try:
        if pd.isna(x):
            return np.nan
        return float(str(x).replace(",", ""))
    except Exception:
        return np.nan

def to_months(val: Any, colname: Optional[str]) -> float:
    """
    Unit-aware parse to months using the column name:
      - contains 'year' → multiply by 12
      - contains 'day'  → divide by 30
      - otherwise → assume already months
    """
    x = _to_float_or_nan(val)
    if np.isnan(x):
        return np.nan
    nm = (colname or "").lower()
    if "year" in nm:
        return x * 12.0
    if "day" in nm:
        return x / 30.0
    return x



# Offense classification


_PENAL_RE = re.compile(r"[0-9]{2,5}(?:\.[0-9]+)?")

def classify_offense(code_or_text: Any, lists: Dict[str, Any]) -> str:
    """
    Map offense text/code to one of: 'violent', 'nonviolent', 'other', 'clash'.

    Rules:
      • If OFFENSE_LISTS['nonviolent'] == 'rest', anything not in 'violent' → 'nonviolent'
      • If a code is in both lists → 'clash'
      • Otherwise → 'other'
    """
    if code_or_text is None or (isinstance(code_or_text, float) and pd.isna(code_or_text)):
        return "other"
    s = str(code_or_text).strip().lower()
    m = _PENAL_RE.search(s)
    norm = m.group(0) if m else s

    vio = (lists.get("violent") or [])
    non = lists.get("nonviolent")

    is_v = norm in vio
    is_n = isinstance(non, list) and (norm in non)

    if is_v and is_n:
        return "clash"
    if is_v:
        return "violent"
    if isinstance(non, list):
        return "nonviolent" if is_n else "other"
    if non == "rest":
        return "nonviolent"
    return "other"

def count_offenses_by_category(df: pd.DataFrame, id_col: str, uid: str,
                               offense_col: str, lists: Dict[str, Any]) -> Dict[str, int]:
    """Return counts by category for all rows matching an ID."""
    out = {"violent": 0, "nonviolent": 0, "other": 0, "clash": 0}
    if df is None or offense_col not in df.columns or id_col not in df.columns:
        return out
    sub = df.loc[df[id_col].astype(str) == str(uid)]
    for _, row in sub.iterrows():
        out[classify_offense(row[offense_col], lists)] += 1
    return out



# Time + Age extractors


def extract_time_inputs(demo_row: Optional[pd.Series]) -> Optional[sm.TimeInputs]:
    """
    Build sm.TimeInputs from the demographics row using configured columns.
    Requires at least the two fields in DEFAULTS['require_time_fields'].
    """
    if demo_row is None:
        return None

    cur = to_months(demo_row.get(_cfg_col("current_sentence")), _cfg_col("current_sentence"))
    com = to_months(demo_row.get(_cfg_col("completed_time")),  _cfg_col("completed_time"))
    pas = to_months(demo_row.get(_cfg_col("past_time")),       _cfg_col("past_time")) if _cfg_col("past_time") else _cfg_default("missing_numeric", np.nan)

    req = tuple(_cfg_default("require_time_fields", ("current_sentence", "completed_time")))
    need_cur = "current_sentence" in req
    need_com = "completed_time"   in req
    if (need_cur and np.isnan(cur)) or (need_com and np.isnan(com)):
        return None

    # Childhood months come from config (no hard-coding)
    return sm.TimeInputs(
        current_sentence_months=cur,
        completed_months=com,
        past_time_months=pas,
        childhood_months=float(_cfg_default("childhood_months", 0.0)),
    )

def extract_age_years(demo_row: Optional[pd.Series]) -> Optional[float]:
    """Return age in years if present; else None (caller will use fallback)."""
    if demo_row is None:
        return None
    col = _cfg_col("age_years")
    if col and (col in demo_row) and pd.notna(demo_row[col]):
        return _to_float_or_nan(demo_row[col])
    return None



# Exposure helpers

def _months_between(start: pd.Timestamp, end: pd.Timestamp) -> Optional[float]:
    """Return months between two timestamps (≈ days/30) or None if either is NaT."""
    if pd.isna(start) or pd.isna(end):
        return None
    days = (end - start).days
    return max(0.0, days / 30.0)


# Feature computation (public API)

def compute_features(uid: str,
                     demo: pd.DataFrame,
                     current_df: pd.DataFrame,
                     prior_df: pd.DataFrame,
                     lists: Dict[str, Any]) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """
    Compute named metrics for a single ID.

    Returns:
        feats: name→value dictionary (may include NaN if inputs are missing).
        aux:   auxiliary info useful for debugging/QA (time pieces, raw counts, etc.).
    """
    cols = CFG.COLS
    row  = get_row_by_id(demo, cols["id"], uid)

    feats: Dict[str, float] = {}
    aux:   Dict[str, Any]   = {}

    # Determine exposure window (months)
    # Prefer global config; else compute per-person as months from (DOB+18y) → reference_date
    per_person_exposure = _cfg_default("months_elapsed_total", None)
    if per_person_exposure is None and row is not None:
        dob_col, ref_col = _cfg_col("dob"), _cfg_col("reference_date")
        if dob_col and ref_col and (dob_col in row) and (ref_col in row):
            dob = pd.to_datetime(row.get(dob_col), errors="coerce")
            ref = pd.to_datetime(row.get(ref_col), errors="coerce")
            adulthood = (dob + DateOffset(years=18)) if pd.notna(dob) else pd.NaT
            start = adulthood if pd.notna(adulthood) else dob  # fall back to dob if adulthood missing
            per_person_exposure = _months_between(start, ref)

    # Time
    t = extract_time_inputs(row)
    if t:
        aux["time_inputs"] = t
        _, pct_completed, time_outside = sm.compute_time_vars(t, per_person_exposure)
        aux["pct_completed"] = pct_completed
        aux["time_outside"]  = time_outside
    else:
        aux["pct_completed"] = np.nan
        aux["time_outside"]  = np.nan

    # Age (normalized)
    age_val = extract_age_years(row)
    if age_val is None or np.isnan(age_val):
        age_val = _cfg_default("age_fallback_years", np.nan)
    feats["age"] = sm.score_age_norm(
        age_val,
        _cfg_default("age_min", None),
        _cfg_default("age_max", None)
    )
    aux["age_value"] = age_val

    # Convictions (current & prior)
    cur = count_offenses_by_category(current_df, cols["id"], uid, cols["current_offense_text"], lists)
    pri = count_offenses_by_category(prior_df,   cols["id"], uid, cols["prior_offense_text"],   lists)
    aux["counts_by_category"] = {"current": cur, "prior": pri}

    conv = sm.Convictions(
        curr_nonviolent=cur["nonviolent"], curr_violent=cur["violent"],
        past_nonviolent=pri["nonviolent"], past_violent=pri["violent"],
    )

    # Descriptive proportions
    feats["desc_nonvio_curr"] = sm.score_desc_nonvio_curr(conv.curr_nonviolent, conv.curr_total)
    feats["desc_nonvio_past"] = sm.score_desc_nonvio_past(conv.past_nonviolent,  conv.past_total)

    # Frequency & trend
    minr, maxr  = _cfg_default("freq_min_rate", None), _cfg_default("freq_max_rate", None)
    yrs_elapsed = _cfg_default("trend_years_elapsed", 0.0)
    time_outside = aux["time_outside"]

    feats["freq_violent"] = sm.score_freq_violent(conv.violent_total, time_outside, minr, maxr)
    feats["freq_total"]   = sm.score_freq_total(  conv.total,         time_outside, minr, maxr)

    feats["severity_trend"] = sm.score_severity_trend(
        conv.curr_violent_prop, conv.past_violent_prop, yrs_elapsed
    )

    # Note: Rehabilitation/education metrics are not computed here.
    # If available, construct sm.RehabInputs and sm.VectorInputs and pass them
    # to sm.build_metrics_named(...) to obtain all 10 metrics.

    return feats, aux
