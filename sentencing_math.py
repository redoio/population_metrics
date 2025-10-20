#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sentencing_math.py — PURE math/metrics (no I/O)
• Policy-sensitive defaults come from the CALLER (or optional config helpers).
• Name-based metrics; weights are dict-based, not positional.
• STRICTLY PURE: no pandas, no file access, no CLI, no similarity metrics.
Author: Taufia Hussain
License: MIT
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Optional

# Optional config hook (safe)
try:
    import config as CFG  # type: ignore
except Exception:
    CFG = None  # type: ignore

# Utilities
def safe_div(n: float, d: float) -> float:
    """0-safe division; returns 0.0 if d is 0/None."""
    if d is None or d == 0:
        return 0.0
    return float(n) / float(d)

def clip01(x: float) -> float:
    """Clamp to [0,1]."""
    return max(0.0, min(1.0, float(x)))

def minmax_norm_scalar(x: float, lo: Optional[float], hi: Optional[float]) -> float:
    """
    Min–max normalize to [0,1]; if lo/hi invalid → 1.0 (constant-series behavior).
    (Callers should gate features so this is only used when bounds are meaningful.)
    """
    if lo is None or hi is None or hi == lo:
        return 1.0
    return clip01((float(x) - float(lo)) / (float(hi) - float(lo)))

# Time Variables
@dataclass
class TimeInputs:
    current_sentence_months: float
    completed_months: float
    past_time_months: float
    childhood_months: Optional[float] = None  # pass explicitly or read via helper

def _get_childhood_months_from_cfg() -> float:
    if CFG is None:
        raise RuntimeError("config.py not available; pass childhood_months explicitly.")
    try:
        return float(CFG.DEFAULTS["childhood_months"])
    except Exception as e:
        raise RuntimeError("DEFAULTS['childhood_months'] missing in config.py") from e

def compute_time_vars(t: TimeInputs, months_elapsed_total: Optional[float]) -> tuple[float, float, float]:
    """
    Return (time_inside_months, pct_current_completed, time_outside_months).
    Caller should pass months_elapsed_total; if None, time_outside is 0.0.
    """
    cm = t.childhood_months if t.childhood_months is not None else _get_childhood_months_from_cfg()
    time_inside = float(t.past_time_months) + float(t.completed_months)
    pct_completed = 100.0 * safe_div(t.completed_months, t.current_sentence_months)
    if months_elapsed_total is None:
        time_outside = 0.0
    else:
        time_outside = max(0.0, float(months_elapsed_total) - time_inside - float(cm))
    return time_inside, pct_completed, time_outside

# Convictions (consolidated)
@dataclass
class Convictions:
    curr_nonviolent: float
    curr_violent: float
    past_nonviolent: float
    past_violent: float

    # Totals
    @property
    def curr_total(self) -> float: return float(self.curr_nonviolent) + float(self.curr_violent)

    @property
    def past_total(self) -> float: return float(self.past_nonviolent) + float(self.past_violent)

    @property
    def total(self) -> float: return self.curr_total + self.past_total

    # Totals by type
    @property
    def violent_total(self) -> float: return float(self.curr_violent) + float(self.past_violent)

    @property
    def nonviolent_total(self) -> float: return float(self.curr_nonviolent) + float(self.past_nonviolent)

    # Proportions (clipped)
    @property
    def curr_nonviolent_prop(self) -> float: return clip01(safe_div(self.curr_nonviolent, self.curr_total))

    @property
    def past_nonviolent_prop(self) -> float: return clip01(safe_div(self.past_nonviolent, self.past_total))

    @property
    def curr_violent_prop(self) -> float: return clip01(safe_div(self.curr_violent, self.curr_total))

    @property
    def past_violent_prop(self) -> float: return clip01(safe_div(self.past_violent, self.past_total))

# Descriptive Scoring
def score_desc_nonvio_curr(curr_nonviolent: float, conv_curr_total: float) -> float:
    return clip01(safe_div(curr_nonviolent, conv_curr_total))

def score_desc_nonvio_past(past_nonviolent: float, conv_past_total: float) -> float:
    return clip01(safe_div(past_nonviolent, conv_past_total))

def score_age_norm(age_value: float, age_min: Optional[float], age_max: Optional[float]) -> float:
    return minmax_norm_scalar(age_value, age_min, age_max)

# Frequency & Trend
def score_freq_violent(conv_violent_total: float, time_outside_months: float,
                       min_rate: Optional[float], max_rate: Optional[float]) -> float:
    raw = safe_div(conv_violent_total, time_outside_months)
    return minmax_norm_scalar(raw, min_rate, max_rate)

def score_freq_total(conv_total: float, time_outside_months: float,
                     min_rate: Optional[float], max_rate: Optional[float]) -> float:
    raw = safe_div(conv_total, time_outside_months)
    return minmax_norm_scalar(raw, min_rate, max_rate)

def score_severity_trend(curr_violent_prop: float, past_violent_prop: float, years_elapsed: float) -> float:
    # Higher means a shift toward non-violence.
    raw_delta = (past_violent_prop - curr_violent_prop) / (years_elapsed + 1.0)
    return clip01((raw_delta + 1.0) / 2.0)

# Rehabilitation Scores
@dataclass
class RehabInputs:
    # Use None so callers/config decide whether to include or skip these metrics.
    edu_general_credits: Optional[float] = None
    edu_advanced_credits: Optional[float] = None
    rehab_general_credits: Optional[float] = None
    rehab_advanced_credits: Optional[float] = None

def _per_month_inside(value: float, time_inside_months: float) -> float:
    return safe_div(value, time_inside_months)

def score_edu_general(edu_general_credits: float, time_inside_months: float,
                      lo: Optional[float], hi: Optional[float]) -> float:
    return minmax_norm_scalar(_per_month_inside(edu_general_credits, time_inside_months), lo, hi)

def score_edu_advanced(edu_advanced_credits: float, time_inside_months: float,
                       lo: Optional[float], hi: Optional[float]) -> float:
    return minmax_norm_scalar(_per_month_inside(edu_advanced_credits, time_inside_months), lo, hi)

def score_rehab_general(rehab_general_credits: float, time_inside_months: float,
                        lo: Optional[float], hi: Optional[float]) -> float:
    return minmax_norm_scalar(_per_month_inside(rehab_general_credits, time_inside_months), lo, hi)

def score_rehab_advanced(rehab_advanced_credits: float, time_inside_months: float,
                         lo: Optional[float], hi: Optional[float]) -> float:
    return minmax_norm_scalar(_per_month_inside(rehab_advanced_credits, time_inside_months), lo, hi)

# Vector Inputs & Builder
@dataclass
class VectorInputs:
    time: TimeInputs
    convictions: Convictions
    age_value: float
    age_min: Optional[float]
    age_max: Optional[float]
    rehab: RehabInputs = field(default_factory=RehabInputs)
    months_elapsed_total: Optional[float] = None
    freq_min_rate: Optional[float] = None
    freq_max_rate: Optional[float] = None
    years_elapsed_for_trend: float = 0.0
    rehab_norm_bounds: Optional[Dict[str, tuple[Optional[float], Optional[float]]]] = None

def build_metrics_named(vin: VectorInputs) -> Dict[str, float]:
    """
    Build a name-keyed metric dict. Metrics are added only when inputs are valid.
    Rehab metrics are included only when corresponding credits are not None.
    """
    time_inside, _, time_outside = compute_time_vars(vin.time, vin.months_elapsed_total)

    # Descriptive
    m_desc_curr = score_desc_nonvio_curr(vin.convictions.curr_nonviolent, vin.convictions.curr_total)
    m_desc_past = score_desc_nonvio_past(vin.convictions.past_nonviolent, vin.convictions.past_total)

    # Age
    m_age = score_age_norm(vin.age_value, vin.age_min, vin.age_max)

    # Frequency (per month outside)
    m_freq_v = score_freq_violent(vin.convictions.violent_total, time_outside, vin.freq_min_rate, vin.freq_max_rate)
    m_freq_t = score_freq_total(vin.convictions.total,         time_outside, vin.freq_min_rate, vin.freq_max_rate)

    # Trend
    m_trend = score_severity_trend(vin.convictions.curr_violent_prop,
                                   vin.convictions.past_violent_prop,
                                   vin.years_elapsed_for_trend)

    out: Dict[str, float] = {
        "desc_nonvio_curr": m_desc_curr,
        "desc_nonvio_past": m_desc_past,
        "age": m_age,
        "freq_violent": m_freq_v,
        "freq_total": m_freq_t,
        "severity_trend": m_trend,
    }

    # Rehab: add only if credits are provided (None → skip)
    lohi = vin.rehab_norm_bounds or {}
    def _add_if_present(key: str, credits: Optional[float]) -> None:
        if credits is None:
            return
        lo, hi = lohi.get(key, (None, None))
        if key == "edu_general":
            out[key] = score_edu_general(credits, time_inside, lo, hi)
        elif key == "edu_advanced":
            out[key] = score_edu_advanced(credits, time_inside, lo, hi)
        elif key == "rehab_general":
            out[key] = score_rehab_general(credits, time_inside, lo, hi)
        elif key == "rehab_advanced":
            out[key] = score_rehab_advanced(credits, time_inside, lo, hi)

    _add_if_present("edu_general",    vin.rehab.edu_general_credits)
    _add_if_present("edu_advanced",   vin.rehab.edu_advanced_credits)
    _add_if_present("rehab_general",  vin.rehab.rehab_general_credits)
    _add_if_present("rehab_advanced", vin.rehab.rehab_advanced_credits)

    return out

# Suitability (name-based)
def suitability_score_named(metrics: Dict[str, float],
                            weights: Optional[Dict[str, float]] = None) -> float:
    """
    Linear suitability score with NAME-BASED weights.
    Only keys present in BOTH the metrics and the weights contribute.
    """
    if weights is None:
        if CFG is None or not hasattr(CFG, "METRIC_WEIGHTS"):
            raise RuntimeError("Weights not provided and config.METRIC_WEIGHTS not available.")
        weights = dict(CFG.METRIC_WEIGHTS)

    keys = set(metrics.keys()) & set(weights.keys())
    return float(sum(weights[k] * float(metrics[k]) for k in keys))

# Suitability out of (name-based)
def suitability_out_of_named(feats: dict, weights: dict,
                             ranges: dict | None = None) -> float:
    present = feats.keys() & weights.keys()
    # If all metrics are normalized to [0,1], this is sufficient:
    return sum(abs(weights[k]) for k in present)
    # If you later keep raw metrics, use ranges+direction to compute m_k^best
