#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sentencing_math.py

Pure math/metrics layer aligned to:
Aparna Komarla (2025), "Exploring Computational Approaches to Sentencing Reform".

Design goals

• No I/O and no pandas dependency.
• All policy-sensitive defaults (e.g., bounds, thresholds, childhood months, weights)
  are NOT hard-coded here. Callers pass them explicitly OR use the provided
  config-backed helpers that read from `config.py`.
• Conviction information is consolidated in one class (`Convictions`) with
  clear properties for totals and proportions.
• Weights are NAME-BASED (dict), not positional. No forced metric ordering.

Author: Taufia Hussain
License: MIT
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Sequence
import math

# Optional config hook 
# These helpers let callers pull defaults from config.py without hard-coding.
try:  # safe optional import; the module remains usable without config
    import config as CFG  # type: ignore
except Exception:  # config is optional; callers may pass values directly
    CFG = None  # type: ignore


# Utilities

def safe_div(n: float, d: float) -> float:
    """
    Division that returns 0.0 when denominator is 0 or None.

    Args:
        n: Numerator.
        d: Denominator (may be 0 or None).

    Returns:
        n / d if d is positive; otherwise 0.0.
    """
    if d is None or d == 0:
        return 0.0
    return float(n) / float(d)


def clip01(x: float) -> float:
    """
    Clamp a scalar to the closed interval [0, 1].

    Args:
        x: Input value.

    Returns:
        Value clipped to [0, 1].
    """
    return max(0.0, min(1.0, float(x)))


def minmax_norm_scalar(x: float,
                       lo: Optional[float],
                       hi: Optional[float]) -> float:
    """
    Min–max normalization of a single value to [0, 1].

    Args:
        x: Value to normalize.
        lo: Lower bound (from config or caller). If None or degenerate with `hi`,
            the function returns 1.0 (constant-series behavior).
        hi: Upper bound (from config or caller).

    Returns:
        Normalized value in [0, 1] if lo/hi are valid; otherwise 1.0.
    """
    if lo is None or hi is None or hi == lo:
        return 1.0
    return clip01((float(x) - float(lo)) / (float(hi) - float(lo)))


# Time variables 

@dataclass
class TimeInputs:
    """
    Inputs for time-based metrics (units: MONTHS).

    Args:
        current_sentence_months: Total current sentence length.
        completed_months: Time already served for current sentence.
        past_time_months: Time served in past incarcerations.
        childhood_months: Months before adulthood to exclude from exposure.
            Do NOT hard-code defaults here; callers should provide this, or use
            `get_childhood_months_from_cfg()` to read from config.DEFAULTS.
    """
    current_sentence_months: float
    completed_months: float
    past_time_months: float
    childhood_months: Optional[float] = None  # pull from config via helper if None


def get_childhood_months_from_cfg() -> float:
    """
    Convenience: read childhood_months from config.DEFAULTS.

    Returns:
        Float months from config.DEFAULTS['childhood_months'].

    Raises:
        RuntimeError if config/default missing.
    """
    if CFG is None:
        raise RuntimeError("config.py not available; pass childhood_months explicitly.")
    try:
        return float(CFG.DEFAULTS["childhood_months"])
    except Exception as e:
        raise RuntimeError("DEFAULTS['childhood_months'] missing in config.py") from e


def compute_time_vars(t: TimeInputs,
                      months_elapsed_total: Optional[float]) -> tuple[float, float, float]:
    """
    Compute time-based variables.

    Args:
        t: TimeInputs (months). If `t.childhood_months` is None, this function will
           try to pull it from config.DEFAULTS via `get_childhood_months_from_cfg()`.
        months_elapsed_total: Total months elapsed over which to measure exposure
           (e.g., months since adulthood or since first record). If None, exposure
           (time_outside) is treated as 0.0 by definition here.

    Returns:
        (time_inside_months, pct_current_completed, time_outside_months)
    """
    cm = t.childhood_months if t.childhood_months is not None else get_childhood_months_from_cfg()
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
    """
    Conviction counts by period and type.

    Args:
        curr_nonviolent: Current-period non-violent convictions.
        curr_violent:    Current-period violent convictions.
        past_nonviolent: Past-period non-violent convictions.
        past_violent:    Past-period violent convictions.

    Exposes:
        • Totals (curr_total, past_total, total).
        • Totals by type (violent_total, nonviolent_total).
        • Proportions (curr_nonviolent_prop, past_nonviolent_prop,
                       curr_violent_prop, past_violent_prop).
    """
    curr_nonviolent: float
    curr_violent: float
    past_nonviolent: float
    past_violent: float

    # Totals
    @property
    def curr_total(self) -> float:
        return float(self.curr_nonviolent) + float(self.curr_violent)

    @property
    def past_total(self) -> float:
        return float(self.past_nonviolent) + float(self.past_violent)

    @property
    def total(self) -> float:
        return self.curr_total + self.past_total

    @property
    def violent_total(self) -> float:
        return float(self.curr_violent) + float(self.past_violent)

    @property
    def nonviolent_total(self) -> float:
        return float(self.curr_nonviolent) + float(self.past_nonviolent)

    # Proportions (clipped to [0,1])
    @property
    def curr_nonviolent_prop(self) -> float:
        return clip01(safe_div(self.curr_nonviolent, self.curr_total))

    @property
    def past_nonviolent_prop(self) -> float:
        return clip01(safe_div(self.past_nonviolent, self.past_total))

    @property
    def curr_violent_prop(self) -> float:
        return clip01(safe_div(self.curr_violent, self.curr_total))

    @property
    def past_violent_prop(self) -> float:
        return clip01(safe_div(self.past_violent, self.past_total))


#  Descriptive scores 

def score_desc_nonvio_curr(curr_nonviolent: float, conv_curr_total: float) -> float:
    """
    Proportion of non-violent CURRENT convictions.

    Args:
        curr_nonviolent: Count of current-period non-violent convictions.
        conv_curr_total: Total current-period convictions.

    Returns:
        Value in [0, 1].
    """
    return clip01(safe_div(curr_nonviolent, conv_curr_total))


def score_desc_nonvio_past(past_nonviolent: float, conv_past_total: float) -> float:
    """
    Proportion of non-violent PAST convictions.

    Args:
        past_nonviolent: Count of past-period non-violent convictions.
        conv_past_total: Total past-period convictions.

    Returns:
        Value in [0, 1].
    """
    return clip01(safe_div(past_nonviolent, conv_past_total))


def score_age_norm(age_value: float,
                   age_min: Optional[float],
                   age_max: Optional[float]) -> float:
    """
    Age normalized to [0, 1] via min-max.

    Args:
        age_value: Age in years.
        age_min: Lower bound (from config).
        age_max: Upper bound (from config).

    Returns:
        Value in [0, 1].
    """
    return minmax_norm_scalar(age_value, age_min, age_max)


#  Trend & frequency scores 

def score_freq_violent(conv_violent_total: float,
                       time_outside_months: float,
                       min_rate: Optional[float],
                       max_rate: Optional[float]) -> float:
    """
    Normalized frequency of violent convictions per month outside.

    Args:
        conv_violent_total: Violent conviction count (current + past).
        time_outside_months: Exposure in months outside.
        min_rate: Lower bound for normalization (from config).
        max_rate: Upper bound for normalization (from config).

    Returns:
        Value in [0, 1]; if bounds are None/degenerate, returns 1.0.
    """
    raw = safe_div(conv_violent_total, time_outside_months)
    return minmax_norm_scalar(raw, min_rate, max_rate)


def score_freq_total(conv_total: float,
                     time_outside_months: float,
                     min_rate: Optional[float],
                     max_rate: Optional[float]) -> float:
    """
    Normalized frequency of ALL convictions per month outside.

    Args:
        conv_total: Total convictions (current + past).
        time_outside_months: Exposure in months outside.
        min_rate: Lower bound for normalization (from config).
        max_rate: Upper bound for normalization (from config).

    Returns:
        Value in [0, 1]; if bounds are None/degenerate, returns 1.0.
    """
    raw = safe_div(conv_total, time_outside_months)
    return minmax_norm_scalar(raw, min_rate, max_rate)


def score_severity_trend(curr_violent_prop: float,
                         past_violent_prop: float,
                         years_elapsed: float) -> float:
    """
    Severity trend mapped to [0, 1]; higher is a shift toward non-violence.

    Args:
        curr_violent_prop: Current violent share in [0, 1].
        past_violent_prop: Past violent share in [0, 1].
        years_elapsed: Years between past and current periods (from config).

    Returns:
        Value in [0, 1]; computed as:
            raw_delta = (past_violent_prop - curr_violent_prop) / (years_elapsed + 1)
            trend = clip01((raw_delta + 1) / 2)
    """
    raw_delta = (past_violent_prop - curr_violent_prop) / (years_elapsed + 1.0)
    return clip01((raw_delta + 1.0) / 2.0)


#  Rehabilitation scores 

@dataclass
class RehabInputs:
    """
    Raw credit/milestone tallies achieved during incarceration.

    Args:
        edu_general_credits: General education credits.
        edu_advanced_credits: Advanced education credits.
        rehab_general_credits: General rehabilitation credits.
        rehab_advanced_credits: Advanced rehabilitation credits.
    """
    edu_general_credits: float = 0.0
    edu_advanced_credits: float = 0.0
    rehab_general_credits: float = 0.0
    rehab_advanced_credits: float = 0.0


def _per_month_inside(value: float, time_inside_months: float) -> float:
    """
    Opportunity-adjusted rate per month inside.

    Args:
        value: Credit count.
        time_inside_months: Months inside.

    Returns:
        value / time_inside_months, 0.0-safe.
    """
    return safe_div(value, time_inside_months)


def score_edu_general(edu_general_credits: float, time_inside_months: float,
                      lo: Optional[float], hi: Optional[float]) -> float:
    """Min-max normalize per-month general education rate using config bounds."""
    return minmax_norm_scalar(_per_month_inside(edu_general_credits, time_inside_months), lo, hi)


def score_edu_advanced(edu_advanced_credits: float, time_inside_months: float,
                       lo: Optional[float], hi: Optional[float]) -> float:
    """Min-max normalize per-month advanced education rate using config bounds."""
    return minmax_norm_scalar(_per_month_inside(edu_advanced_credits, time_inside_months), lo, hi)


def score_rehab_general(rehab_general_credits: float, time_inside_months: float,
                        lo: Optional[float], hi: Optional[float]) -> float:
    """Min-max normalize per-month general rehab rate using config bounds."""
    return minmax_norm_scalar(_per_month_inside(rehab_general_credits, time_inside_months), lo, hi)


def score_rehab_advanced(rehab_advanced_credits: float, time_inside_months: float,
                         lo: Optional[float], hi: Optional[float]) -> float:
    """Min-max normalize per-month advanced rehab rate using config bounds."""
    return minmax_norm_scalar(_per_month_inside(rehab_advanced_credits, time_inside_months), lo, hi)


#  Named 10-metric computation 

# This list is informational only; ordering is not required anywhere.
DEFAULT_METRIC_NAMES = [
    "desc_nonvio_curr", "desc_nonvio_past", "age",
    "freq_violent", "freq_total", "severity_trend",
    "edu_general", "edu_advanced", "rehab_general", "rehab_advanced",
]


@dataclass
class VectorInputs:
    """
    Inputs required to compute the 10 metrics (named).

    Args:
        time: TimeInputs (months). childhood_months should come from config (see helper).
        convictions: Convictions (current/past × violent/non-violent).
        age_value: Raw age in years.
        age_min: Min age for normalization (from config).
        age_max: Max age for normalization (from config).
        rehab: RehabInputs credits.
        months_elapsed_total: Exposure window in months (from config/caller).
        freq_min_rate: Lower bound for frequency normalization (from config).
        freq_max_rate: Upper bound for frequency normalization (from config).
        years_elapsed_for_trend: Elapsed years between past and current (from config).
        rehab_norm_bounds: Optional dict with keys
            {"edu_general": (lo,hi), "edu_advanced": (lo,hi),
             "rehab_general": (lo,hi), "rehab_advanced": (lo,hi)}
            taken from config.
    """
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
    Compute the 10 metrics and return a name→value dictionary.

    Returns:
        Dict with keys matching DEFAULT_METRIC_NAMES (order not guaranteed).
    """
    # Time
    time_inside, _, time_outside = compute_time_vars(vin.time, vin.months_elapsed_total)

    # Descriptive (non-violent proportions)
    m_desc_curr = score_desc_nonvio_curr(vin.convictions.curr_nonviolent, vin.convictions.curr_total)
    m_desc_past = score_desc_nonvio_past(vin.convictions.past_nonviolent, vin.convictions.past_total)

    # Age
    m_age = score_age_norm(vin.age_value, vin.age_min, vin.age_max)

    # Frequency (per month outside)
    m_freq_v = score_freq_violent(vin.convictions.violent_total, time_outside, vin.freq_min_rate, vin.freq_max_rate)
    m_freq_t = score_freq_total(vin.convictions.total,         time_outside, vin.freq_min_rate, vin.freq_max_rate)

    # Trend (violent share ↓ is good)
    m_trend = score_severity_trend(vin.convictions.curr_violent_prop,
                                   vin.convictions.past_violent_prop,
                                   vin.years_elapsed_for_trend)

    # Rehab (per-month-inside, min–max normalized by type)
    lohi = vin.rehab_norm_bounds or {}
    eg_lo, eg_hi = lohi.get("edu_general", (None, None))
    ea_lo, ea_hi = lohi.get("edu_advanced", (None, None))
    rg_lo, rg_hi = lohi.get("rehab_general", (None, None))
    ra_lo, ra_hi = lohi.get("rehab_advanced", (None, None))

    m_edu_g = score_edu_general(vin.rehab.edu_general_credits, time_inside, eg_lo, eg_hi)
    m_edu_a = score_edu_advanced(vin.rehab.edu_advanced_credits, time_inside, ea_lo, ea_hi)
    m_reh_g = score_rehab_general(vin.rehab.rehab_general_credits, time_inside, rg_lo, rg_hi)
    m_reh_a = score_rehab_advanced(vin.rehab.rehab_advanced_credits, time_inside, ra_lo, ra_hi)

    return {
        "desc_nonvio_curr": m_desc_curr,
        "desc_nonvio_past": m_desc_past,
        "age": m_age,
        "freq_violent": m_freq_v,
        "freq_total": m_freq_t,
        "severity_trend": m_trend,
        "edu_general": m_edu_g,
        "edu_advanced": m_edu_a,
        "rehab_general": m_reh_g,
        "rehab_advanced": m_reh_a,
    }


#  Cosine similarity 

def cosine_similarity(u: Sequence[float], v: Sequence[float]) -> float:
    """
    Cosine similarity between two equal-length numeric sequences.

    Args:
        u: Sequence of floats.
        v: Sequence of floats.

    Returns:
        Cosine similarity in [-1, 1]. For nonnegative vectors, in [0, 1].
        Returns 0.0 if either vector has zero norm.
    """
    num = sum(ux * vx for ux, vx in zip(u, v))
    nu = math.sqrt(sum(ux * ux for ux in u))
    nv = math.sqrt(sum(vx * vx for vx in v))
    if nu == 0.0 or nv == 0.0:
        return 0.0
    return num / (nu * nv)


def cosine_from_named(u: Dict[str, float], v: Dict[str, float]) -> float:
    """
    Cosine similarity for two metric dicts by intersecting keys.

    Args:
        u: name→value dict.
        v: name→value dict.

    Returns:
        Cosine similarity over the intersection of keys; 0.0 if empty or zero-norm.
    """
    keys = sorted(set(u).intersection(v))
    if not keys:
        return 0.0
    u_vec = [float(u[k]) for k in keys]
    v_vec = [float(v[k]) for k in keys]
    return cosine_similarity(u_vec, v_vec)


# Suitability (named weights) 

def suitability_score_named(metrics: Dict[str, float],
                            weights: Optional[Dict[str, float]] = None) -> float:
    """
    Linear suitability score with NAME-BASED weights.

    Args:
        metrics: name→value dict (e.g., from `build_metrics_named`).
        weights: name→weight dict (usually from config.METRIC_WEIGHTS).
                 If None, attempts to read from config.METRIC_WEIGHTS.

    Returns:
        Sum over shared keys of (weight * metric value).
    """
    if weights is None:
        if CFG is None or not hasattr(CFG, "METRIC_WEIGHTS"):
            raise RuntimeError("Weights not provided and config.METRIC_WEIGHTS not available.")
        weights = dict(CFG.METRIC_WEIGHTS)
    return float(sum(weights.get(k, 0.0) * float(metrics.get(k, 0.0)) for k in weights))


# Rules-based eligibility 

def rules_based_eligibility(current_sentence_months: float,
                            completed_months: float,
                            min_sentence_months: float,
                            min_completed_months: float,
                            has_disqualifying_offense: bool) -> bool:
    """
    Basic eligibility predicate.

    Args:
        current_sentence_months: Total current sentence length (months).
        completed_months: Months served on the current sentence.
        min_sentence_months: Threshold from config (no hard-coding here).
        min_completed_months: Threshold from config (no hard-coding here).
        has_disqualifying_offense: True if any disqualifier applies.

    Returns:
        True if all conditions are met; False otherwise.
    """
    cond_len = float(current_sentence_months) >= float(min_sentence_months)
    cond_srv = float(completed_months) >= float(min_completed_months)
    return bool(cond_len and cond_srv and (not has_disqualifying_offense))


def rules_based_eligibility_from_cfg(current_sentence_months: float,
                                     completed_months: float,
                                     has_disqualifying_offense: bool) -> bool:
    """
    Convenience wrapper that reads thresholds from config.ELIGIBILITY.

    Requires:
        config.ELIGIBILITY = {
            "min_sentence_months": ...,
            "min_completed_months": ...
        }
    """
    if CFG is None or not hasattr(CFG, "ELIGIBILITY"):
        raise RuntimeError("config.ELIGIBILITY not available.")
    try:
        ms = float(CFG.ELIGIBILITY["min_sentence_months"])
        mc = float(CFG.ELIGIBILITY["min_completed_months"])
    except Exception as e:
        raise RuntimeError("ELIGIBILITY thresholds missing in config.py") from e
    return rules_based_eligibility(current_sentence_months, completed_months, ms, mc, has_disqualifying_offense)


# Demo (optional) 

if __name__ == "__main__":
    # Tiny smoke test (kept minimal; not a policy default).
    # For real use, construct values from your pipeline/config.
    t = TimeInputs(current_sentence_months=360.0, completed_months=180.0, past_time_months=60.0,
                   childhood_months=None)  # will pull from config if available
    c = Convictions(curr_nonviolent=4, curr_violent=0, past_nonviolent=3, past_violent=0)
    vin = VectorInputs(
        time=t,
        convictions=c,
        age_value=40.0,
        age_min=18.0,
        age_max=90.0,
        months_elapsed_total=600.0,
        freq_min_rate=None,
        freq_max_rate=None,
        years_elapsed_for_trend=10.0,
        rehab=RehabInputs(edu_general_credits=5, edu_advanced_credits=1, rehab_general_credits=2, rehab_advanced_credits=0),
        rehab_norm_bounds=None,
    )
    feats = build_metrics_named(vin)
    print("Metrics dict:", {k: round(v, 3) for k, v in feats.items()})
    try:
        print("Suitability (config weights):", round(suitability_score_named(feats), 3))
    except Exception:
        print("Suitability: provide weights dict or config.METRIC_WEIGHTS.")
