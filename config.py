# config.py
import os
import math


# Profiles & Data Locations

PROFILE = os.getenv("CFG_PROFILE", "PROD")          # "DEV" or "PROD"
COMMIT_SHA = os.getenv("DATA_COMMIT", "main")       # pin for reproducibility

PATHS_PROD = {
    "demographics":        f"https://raw.githubusercontent.com/redoio/offenses_data/{COMMIT_SHA}/data/demographics.csv",
    "prior_commitments":   f"https://raw.githubusercontent.com/redoio/offenses_data/{COMMIT_SHA}/data/prior_commitments.csv",
    "current_commitments": f"https://raw.githubusercontent.com/redoio/offenses_data/{COMMIT_SHA}/data/current_commitments.xlsx",
    # optional:
    "offense_codes":       f"https://raw.githubusercontent.com/redoio/resentencing_data_initiative/{COMMIT_SHA}/eligibility_model/code/offense_codes.xlsx",
}

PATHS_DEV = {
    "demographics":        "/data/local/demographics.csv",
    "prior_commitments":   "/data/local/prior_commitments.csv",
    "current_commitments": "/data/local/current_commitments.xlsx",
    "offense_codes":       "/data/local/offense_codes.xlsx",
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
    # Offense text fields (used by your counting logic)
    "current_offense_text": "offense",
    "prior_offense_text":   "offense",
    # Category text (ignored by compute if not used)
    "current_category_text": "offense category",
    "prior_category_text":   "offense category",
}


# Defaults / Behavior Knobs

DEFAULTS = {
    # Missing numerics stay NaN; skip-if-missing should prevent fake values.
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
    # If either is None => SKIP freq_* entirely (prevents constant 1.0s).
    "freq_min_rate": None,
    "freq_max_rate": None,

    # Years window for severity trend (if used)
    "trend_years_elapsed": 10.0,

    # Childhood months (if used by any metric; leave at 0 if not applicable)
    "childhood_months": 0.0,
}


# Offense Lists
# NO implicit 'rest' fallback now.
# Anything not in these lists should be treated as "other".

OFFENSE_LISTS = {
    # Replace with your true codes (examples below).
    "violent":    ["187", "211", "245"],                 # e.g., homicide/robbery/assault codes
    "nonviolent": ["459", "484", "10851"],               # e.g., burglary/theft/vehicle
    # NOTE: Do NOT use "rest". We intentionally avoid implied categories for now.
}


# Weights (name-based; n-D)
# Only PRESENT features are used at scoring time.

WEIGHTS_10D = {
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

    # Rehab / Education (leave as-is; features will be skipped unless computed upstream)
    "edu_general": 1.0,
    "edu_advanced": 1.0,
    "rehab_general": 1.0,
    "rehab_advanced": 1.0,
}
