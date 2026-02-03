#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compute_metrics.py — parameterized, raw-data–oriented feature computation (no CLI)

Pipeline:
  read → parse → classify(offenses) → time → features

Relies on:
  - config.py: PATHS, COLS, DEFAULTS, OFFENSE_LISTS, OFFENSE_POLICY
  - sentencing_math.py: pure math helpers (imported as sm)
  - offense_helpers.py: classify_offense (uses OFFENSE_LISTS/OFFENSE_POLICY)

Design notes:
  • Missing numerics remain NaN (configurable via DEFAULTS["missing_numeric"]).
  • Time fields are unit-aware by column name: "...year..."→*12, "...day..."→/30, else months.
  • STRICT SKIP-IF-MISSING: features are ONLY added when inputs are valid.
  • Frequency exposure window (months) uses DEFAULTS["months_elapsed_for_frequency"] if provided,
    else computes a per-person exposure window (dob/reference_date if available).
  • Severity trend horizon (years) is computed from commitments (first prior → last current),
    optionally overridden by DEFAULTS["years_elapsed_for_trend"] when use_default_trend_years=True.
"""


from __future__ import annotations
from typing import Any, Dict, Optional, Tuple

import math
import numpy as np
import pandas as pd
from pandas.tseries.offsets import DateOffset

import config as CFG
import sentencing_math as sm
from offense_helpers import classify_offense


# Small config helpers

def _cfg_col(name: str) -> Optional[str]:
    """Return configured column name (or None) for a logical field."""
    return getattr(CFG, "COLS", {}).get(name)


def _cfg_default(key: str, fallback: Any) -> Any:
    """Return configured default for a key (with fallback)."""
    return getattr(CFG, "DEFAULTS", {}).get(key, fallback)


# I/O helpers

def _to_raw_github_url(path: str) -> str:
    """Allow GitHub 'blob' URLs in config by converting them to 'raw' URLs."""
    if not isinstance(path, str):
        return path
    if "github.com" not in path:
        return path
    return (
        path.replace("https://github.com/", "https://raw.githubusercontent.com/")
        .replace("/blob/", "/")
    )


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


# Parsing helpers

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


# Offense counting utilities

def count_offenses_by_category(
    df: pd.DataFrame,
    id_col: str,
    uid: str,
    offense_col: str,
    lists: Dict[str, Any],
) -> Dict[str, int]:
    """Return counts by category for all rows matching an ID."""
    out = {"violent": 0, "nonviolent": 0, "other": 0, "clash": 0}
    if df is None or offense_col not in df.columns or id_col not in df.columns:
        return out
    sub = df.loc[df[id_col].astype(str) == str(uid)]
    for _, row in sub.iterrows():
        label = classify_offense(row[offense_col], lists)
        out[label] += 1
    return out


# Time + Age extract

def extract_time_inputs(demo_row: Optional[pd.Series]) -> Optional[sm.TimeInputs]:
    """
    Build sm.TimeInputs from the demographics row using configured columns.
    Requires at least the fields listed in DEFAULTS['require_time_fields'].
    """
    if demo_row is None:
        return None

    cur_col = _cfg_col("current_sentence")
    com_col = _cfg_col("completed_time")
    pas_col = _cfg_col("past_time")

    cur = to_months(demo_row.get(cur_col), cur_col)
    com = to_months(demo_row.get(com_col), com_col)

    pas = (
        to_months(demo_row.get(pas_col), pas_col)
        if pas_col else _cfg_default("missing_numeric", np.nan)
    )

    req = tuple(_cfg_default("require_time_fields", ("current_sentence", "completed_time")))
    need_cur = "current_sentence" in req
    need_com = "completed_time" in req
    if (need_cur and np.isnan(cur)) or (need_com and np.isnan(com)):
        return None

    return sm.TimeInputs(
        current_sentence_months=cur,
        completed_months=com,
        past_time_months=pas,
        childhood_months=float(_cfg_default("childhood_months", 0.0)),
    )


def extract_age_years(demo_row: Optional[pd.Series]) -> Optional[float]:
    """Return age in years if present; else None (caller will skip age feature)."""
    if demo_row is None:
        return None
    col = _cfg_col("age_years")
    if col and (col in demo_row) and pd.notna(demo_row[col]):
        v = _to_float_or_nan(demo_row[col])
        return None if np.isnan(v) else float(v)
    return None


# Exposure / elapsed time

def _months_between(start: pd.Timestamp, end: pd.Timestamp) -> Optional[float]:
    """Return months between two timestamps (≈ days/30) or None if either is NaT."""
    if pd.isna(start) or pd.isna(end):
        return None
    days = (end - start).days
    return max(0.0, days / 30.0)


def _years_between(start: pd.Timestamp, end: pd.Timestamp) -> Optional[float]:
    """Return years between two timestamps (≈ days/365.25) or None if either is NaT."""
    if pd.isna(start) or pd.isna(end):
        return None
    days = (end - start).days
    return max(0.0, days / 365.25)


def years_elapsed_prior_curr_commitments(
    uid: str,
    current_df: pd.DataFrame,
    prior_df: pd.DataFrame,
) -> Optional[float]:
    """
    Calculate elapsed years between:
        first recorded PRIOR commitment date -> last recorded CURRENT commitment date.

    Uses optional config columns:
        COLS["prior_commit_date"], COLS["current_commit_date"]

    Returns None if required columns/dates are missing for this uid.
    """
    id_col = _cfg_col("id")
    prior_date_col = _cfg_col("prior_commit_date")
    current_date_col = _cfg_col("current_commit_date")

    if id_col is None or prior_date_col is None or current_date_col is None:
        return None
    if prior_df is None or current_df is None:
        return None
    if (
        id_col not in prior_df.columns
        or id_col not in current_df.columns
        or prior_date_col not in prior_df.columns
        or current_date_col not in current_df.columns
    ):
        return None

    prior_sub = prior_df.loc[prior_df[id_col].astype(str) == str(uid)]
    curr_sub = current_df.loc[current_df[id_col].astype(str) == str(uid)]
    if prior_sub.empty or curr_sub.empty:
        return None

    prior_dates = pd.to_datetime(prior_sub[prior_date_col], errors="coerce")
    curr_dates = pd.to_datetime(curr_sub[current_date_col], errors="coerce")
    if prior_dates.notna().sum() == 0 or curr_dates.notna().sum() == 0:
        return None

    first_prior = prior_dates.min()
    last_current = curr_dates.max()
    return _years_between(first_prior, last_current)


# Feature computation API

def compute_features(
    uid: str,
    demo: pd.DataFrame,
    current_df: pd.DataFrame,
    prior_df: pd.DataFrame,
    lists: Dict[str, Any],
    use_default_trend_years: bool = True,
) -> Tuple[Dict[str, float], Dict[str, Any]]:
    """
    Compute name-keyed metrics for a single ID.

    Returns:
        feats: name→value dictionary (features are ONLY added when inputs are valid).
        aux:   auxiliary info for QA/debugging.
    """
    cols = CFG.COLS
    row = get_row_by_id(demo, cols["id"], uid)

    feats: Dict[str, float] = {}
    aux: Dict[str, Any] = {}


    # Frequency exposure (MONTHS)
    
    per_person_exposure = _cfg_default("months_elapsed_for_frequency", None)

    if per_person_exposure is None and row is not None:
        dob_col, ref_col = _cfg_col("dob"), _cfg_col("reference_date")
        if dob_col and ref_col and (dob_col in row) and (ref_col in row):
            dob = pd.to_datetime(row.get(dob_col), errors="coerce")
            ref = pd.to_datetime(row.get(ref_col), errors="coerce")
            adulthood = (dob + DateOffset(years=18)) if pd.notna(dob) else pd.NaT
            start = adulthood if pd.notna(adulthood) else dob
            per_person_exposure = _months_between(start, ref)

    aux["months_elapsed_for_frequency"] = per_person_exposure

    
    # Time (pct/outside)
    
    t = extract_time_inputs(row)
    if t is not None:
        aux["time_inputs"] = t
        _, pct_completed, time_outside = sm.compute_time_vars(t, per_person_exposure)
        aux["pct_completed"] = pct_completed
        aux["time_outside"] = time_outside
    else:
        aux["pct_completed"] = np.nan
        aux["time_outside"] = np.nan

    
    # Age (optional)
    
    age_val = extract_age_years(row)
    if age_val is not None:
        feats["age"] = sm.score_age_norm(
            age_val,
            _cfg_default("age_min", None),
            _cfg_default("age_max", None),
        )
        aux["age_value"] = age_val
    else:
        aux["age_value"] = np.nan

    
    # Convictions (current & prior)
    
    cur = count_offenses_by_category(current_df, cols["id"], uid, cols["current_offense_text"], lists)
    pri = count_offenses_by_category(prior_df, cols["id"], uid, cols["prior_offense_text"], lists)
    aux["counts_by_category"] = {"current": cur, "prior": pri}

    conv = sm.Convictions(
        curr_nonviolent=cur["nonviolent"],
        curr_violent=cur["violent"],
        past_nonviolent=pri["nonviolent"],
        past_violent=pri["violent"],
    )

    # Descriptive proportions
    if conv.curr_total > 0:
        feats["desc_nonvio_curr"] = sm.score_desc_nonvio_curr(conv.curr_nonviolent, conv.curr_total)
    if conv.past_total > 0:
        feats["desc_nonvio_past"] = sm.score_desc_nonvio_past(conv.past_nonviolent, conv.past_total)

    
    # Frequency metrics
    
    minr, maxr = _cfg_default("freq_min_rate", None), _cfg_default("freq_max_rate", None)
    time_outside = aux["time_outside"]
    have_bounds = (minr is not None and maxr is not None and float(maxr) > float(minr))

    if (
        isinstance(time_outside, (int, float))
        and not np.isnan(time_outside)
        and time_outside > 0
        and have_bounds
    ):
        feats["freq_violent"] = sm.score_freq_violent(conv.violent_total, time_outside, minr, maxr)
        feats["freq_total"] = sm.score_freq_total(conv.total, time_outside, minr, maxr)
    # else: skip both freq_* features

    
    # Severity trend
    
    if conv.curr_total > 0 and conv.past_total > 0:
        yrs_from_commits = years_elapsed_prior_curr_commitments(uid, current_df, prior_df)
        aux["years_elapsed_prior_curr_commitments"] = yrs_from_commits

        yrs_elapsed_for_trend = yrs_from_commits

        # Only ONE override knob, from DEFAULTS
        override_years = _cfg_default("years_elapsed_for_trend", None)
        if use_default_trend_years and override_years is not None:
            try:
                yrs_elapsed_for_trend = float(override_years)
            except Exception:
                pass  # keep computed value if override is invalid

        aux["years_elapsed_for_trend"] = yrs_elapsed_for_trend

        if yrs_elapsed_for_trend is not None:
            feats["severity_trend"] = sm.score_severity_trend(
                conv.curr_violent_prop,
                conv.past_violent_prop,
                yrs_elapsed_for_trend,
            )

    return feats, aux
