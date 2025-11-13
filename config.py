# config.py
import os
import math
from typing import Any, Dict

# Profiles & Data Locations
PROFILE = os.getenv("CFG_PROFILE", "PROD")          # "DEV" or "PROD"
COMMIT_SHA = os.getenv("DATA_COMMIT", "main")       # pin for reproducibility

PATHS_PROD = {
    "demographics":        f"https://raw.githubusercontent.com/redoio/offenses_data/{COMMIT_SHA}/data/demographics.csv",
    "prior_commitments":   f"https://raw.githubusercontent.com/redoio/offenses_data/{COMMIT_SHA}/data/prior_commitments.csv",
    "current_commitments": f"https://raw.githubusercontent.com/redoio/offenses_data/{COMMIT_SHA}/data/current_commitments.csv",
    # future optional (if available later):
    # "rehab":            "path-or-url-to-rehab-credits.csv",
}

PATHS_DEV = {
    "demographics":        r"D:\Judge_bias_detection\milestone_2\demographics.csv",
    "prior_commitments":   r"D:\Judge_bias_detection\milestone_2\prior_commitments.csv",
    "current_commitments": r"D:\Judge_bias_detection\milestone_2\current_commitments.xlsx",
}

PATHS = PATHS_PROD if PROFILE == "PROD" else PATHS_DEV

# Column Map
COLS: Dict[str, Any] = {
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
}

# Defaults / Behavior Knobs
DEFAULTS: Dict[str, Any] = {
    "missing_numeric": math.nan,
    "require_time_fields": ("current_sentence", "completed_time"),

    # Optional global exposure window (months); if None, compute per-person.
    "months_elapsed_total": None,

    # Age normalization (only used if age_years is present and valid)
    "age_min": 18.0,
    "age_max": 90.0,
    "age_fallback_years": math.nan,

    # Frequency normalization bounds (None => skip freq_* entirely)
    "freq_min_rate": None,
    "freq_max_rate": None,

    # Years window for severity trend
    "trend_years_elapsed": 10.0,

    # Childhood months (if used)
    "childhood_months": 0.0,

    # Rehab toggles and normalization
    "enable_rehab": False,
    "rehab_defaults": {
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

# Offense Policies (constants)
OFFENSE_LISTS = {
    "violent":    ["187", "211", "245"],
    "nonviolent": ["459", "484", "10851"],
}

OFFENSE_POLICY = {
    "nonviolent_rest_mode": False,  # if True, any unlisted offense → "nonviolent"
    "case_insensitive": True,
    "strip_punctuation": True,
}

# Metric Names & Weights
METRIC_NAMES = [
    "desc_nonvio_curr", "desc_nonvio_past", "age",
    "freq_violent", "freq_total", "severity_trend",
    "edu_general", "edu_advanced", "rehab_general", "rehab_advanced",
]

METRIC_WEIGHTS: Dict[str, float] = {
    "age": 0.0,
    "desc_nonvio_curr": 1.0,
    "desc_nonvio_past": 1.0,
    "freq_violent": 1.0,
    "freq_total": 1.0,
    "severity_trend": 1.0,
    "edu_general": 1.0,
    "edu_advanced": 1.0,
    "rehab_general": 1.0,
    "rehab_advanced": 1.0,
}

METRIC_DIRECTIONS: Dict[str, int] = {
    "desc_nonvio_curr": +1,
    "desc_nonvio_past": +1,
    "age": +1,
    "freq_violent": -1,
    "freq_total": -1,
    "severity_trend": +1,
    "edu_general": +1,
    "edu_advanced": +1,
    "rehab_general": +1,
    "rehab_advanced": +1,
}

METRIC_RANGES: Dict[str, Any] = {
    "desc_nonvio_curr": (0.0, 1.0),
    "desc_nonvio_past": (0.0, 1.0),
    # metric is normalized to [0,1]
    "age": (0.0, 1.0),
    "freq_violent": (DEFAULTS["freq_min_rate"], DEFAULTS["freq_max_rate"]),
    "freq_total":   (DEFAULTS["freq_min_rate"], DEFAULTS["freq_max_rate"]),
    "severity_trend": (0.0, 1.0),
    "edu_general":   (0.0, 1.0),
    "edu_advanced":  (0.0, 1.0),
    "rehab_general": (0.0, 1.0),
    "rehab_advanced":(0.0, 1.0),
}
