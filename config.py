# config.py
import os
import math
import re
from typing import Any, Dict


# Profiles & Data Locations


PROFILE = os.getenv("CFG_PROFILE", "PROD")          # "DEV" or "PROD"
COMMIT_SHA = os.getenv("DATA_COMMIT", "main")       # pin for reproducibility

PATHS_PROD = {
    "demographics":        f"https://raw.githubusercontent.com/redoio/offenses_data/{COMMIT_SHA}/data/demographics.csv",
    "prior_commitments":   f"https://raw.githubusercontent.com/redoio/offenses_data/{COMMIT_SHA}/data/prior_commitments.csv",
    "current_commitments": f"https://raw.githubusercontent.com/redoio/offenses_data/{COMMIT_SHA}/data/current_commitments.xlsx",
    # optional:
    "offense_codes":       f"https://raw.githubusercontent.com/redoio/resentencing_data_initiative/{COMMIT_SHA}/eligibility_model/code/offense_codes.xlsx",
    # future optional (if available later):
    # "rehab":            "path-or-url-to-rehab-credits.csv",
}

PATHS_DEV = {
    "demographics":        r"D:\Judge_bias_detection\milestone_2\demographics.csv",
    "prior_commitments":   r"D:\Judge_bias_detection\milestone_2\prior_commitments.csv",
    "current_commitments": r"D:\Judge_bias_detection\milestone_2\current_commitments.xlsx",
    "offense_codes":       r"/data/local/offense_codes.xlsx",
}

PATHS = PATHS_PROD if PROFILE == "PROD" else PATHS_DEV



# Column Map

# Rule: any None => SKIP

COLS = {
    "id": "cdcno",                           # REQUIRED identifier
    "age_years": None,                       # No age available -> feature skipped
    "dob": None,                             # optional (unused if None)
    "reference_date": None,                  # optional
    # Time/term fields (optional; used if your compute code supports them)
    "current_sentence": "aggregate sentence in months",
    "completed_time":  "time served in years",
    "past_time":       None,                 # optional
    # Offense text fields (used by counting logic)
    "current_offense_text": "offense",
    "prior_offense_text":   "offense",
    # Category text (ignored by compute if not used)
    "current_category_text": "offense category",
    "prior_category_text":   "offense category",
    # Future rehab columns (if you add a credits table later)
    # "rehab_edu_general":   None,
    # "rehab_edu_advanced":  None,
    # "rehab_prog_general":  None,
    # "rehab_prog_advanced": None,
}



# Defaults / Behavior Knobs

DEFAULTS = {
    # Missing numerics stay NaN; skip-if-missing prevents fake values.
    "missing_numeric": math.nan,

    # If your compute script requires certain time fields, list them here.
    # Downstream code must respect "skip-if-missing" behavior.
    "require_time_fields": ("current_sentence", "completed_time"),

    # Age normalization (only used if age_years is present and valid)
    "age_min": 18.0,
    "age_max": 90.0,
    # IMPORTANT: keep fallback NaN so age is SKIPPED when absent.
    "age_fallback_years": math.nan,

    # Frequency normalization bounds:
    # If either is None => SKIP freq_* entirely.
    "freq_min_rate": None,
    "freq_max_rate": None,

    # Years window for severity trend (if used)
    "trend_years_elapsed": 10.0,

    # Childhood months (if used by any metric; leave at 0 if not applicable)
    "childhood_months": 0.0,

    # Rehab toggles and normalization (used only if rehab inputs are provided)
    "enable_rehab": False,  # flip to True only when rehab inputs are wired
    "rehab_defaults": {     # applied ONLY if caller explicitly opts to fill missing credits
        "edu_general_credits": 0.0,
        "edu_advanced_credits": 0.0,
        "rehab_general_credits": 0.0,
        "rehab_advanced_credits": 0.0,
    },
    "rehab_norm_bounds": {
        "edu_general":   (None, None),
        "edu_advanced":  (None, None),
        "rehab_general": (None, None),
        "rehab_advanced":(None, None),
    },
}



# Offense Policies

# Explicit lists only. Anything not listed → "other" (unless you enable 'rest' policy).
OFFENSE_LISTS = {
    # Replace with your true codes (examples below).
    "violent":    ["187", "211", "245"],       # e.g., homicide / robbery / assault
    "nonviolent": ["459", "484", "10851"],     # e.g., burglary / theft / vehicle
}

OFFENSE_POLICY = {
    "nonviolent_rest_mode": False,  # if True, any unlisted offense → "nonviolent"
    "case_insensitive": True,       # normalize text case
    "strip_punctuation": True,      # basic cleanup before matching
}

# Offense classification helpers (centralized) 

_PENAL_RE = re.compile(r"[0-9]{2,5}(?:\.[0-9]+)?")  # e.g., '187', '653.22'

def _normalize_offense_token(x: Any) -> str:
    """
    Extract a normalized token for matching: prefer a numeric penal code if present,
    else cleaned lowercase text.
    """
    if x is None:
        return ""
    s = str(x).strip()
    if OFFENSE_POLICY.get("case_insensitive", True):
        s = s.lower()
    m = _PENAL_RE.search(s)
    if m:
        return m.group(0)  # numeric code match
    if OFFENSE_POLICY.get("strip_punctuation", True):
        s = re.sub(r"[^a-z0-9\. ]+", " ", s).strip()
    return s

def classify_offense(code_or_text: Any, lists: Dict[str, Any] | None = None) -> str:
    """
    Map offense to: 'violent' | 'nonviolent' | 'other' | 'clash'.
    - Uses OFFENSE_LISTS when 'lists' is None.
    - If OFFENSE_POLICY['nonviolent_rest_mode'] is True, any unlisted offense → 'nonviolent'.
    - If a token is in both lists → 'clash'.
    """
    li = lists or OFFENSE_LISTS
    token = _normalize_offense_token(code_or_text)

    vio = set(li.get("violent") or [])
    non = set(li.get("nonviolent") or [])

    is_v = token in vio
    is_n = token in non

    if is_v and is_n:
        return "clash"
    if is_v:
        return "violent"
    if is_n:
        return "nonviolent"
    if OFFENSE_POLICY.get("nonviolent_rest_mode", False):
        return "nonviolent"
    return "other"

# Optional early warning if lists overlap
_DUP = set(OFFENSE_LISTS.get("violent", [])) & set(OFFENSE_LISTS.get("nonviolent", []))
if _DUP:
    print(f"[WARN] Offense codes appear in both categories (clash): {sorted(_DUP)[:10]} ...")



# Metric Names & Weights


# Ordered list for display/aggregation; add/remove freely (n-dimensional).
METRIC_NAMES = [
    "desc_nonvio_curr", "desc_nonvio_past", "age",
    "freq_violent", "freq_total", "severity_trend",
    "edu_general", "edu_advanced", "rehab_general", "rehab_advanced",
]

# Name-based weights. Only PRESENT features contribute at score time.
METRIC_WEIGHTS = {
    # Turn off age until data is truly available.
    "age": 0.0,

    # Descriptive proportions (computed only if denominators > 0)
    "desc_nonvio_curr": 1.0,
    "desc_nonvio_past": 1.0,

    # Frequency metrics (only used if freq_min_rate/max_rate are set AND time is valid)
    "freq_violent": 1.0,
    "freq_total": 1.0,

    # Severity trend (only if both current & past denominators > 0)
    "severity_trend": 1.0,

    # Rehab / Education (included only when rehab inputs are available)
    "edu_general": 1.0,
    "edu_advanced": 1.0,
    "rehab_general": 1.0,
    "rehab_advanced": 1.0,
}

