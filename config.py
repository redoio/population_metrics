# config.py

# Single place to define paths, columns, defaults, weights,
# and final violent / nonviolent lists.


import os
import math

# Paths (profiles) 
PROFILE = os.getenv("CFG_PROFILE", "PROD")  # "DEV" or "PROD"
COMMIT_SHA = os.getenv("DATA_COMMIT", "main")  # pin for reproducibility

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

#  Columns 
COLS = {
    "id": "cdcno",
    "age_years": None,               # set if present; else fallback/NaN
    "dob": None,
    "reference_date": None,
    "current_sentence": "aggregate sentence in months",  # years/days ok; code converts to months
    "completed_time":  "time served in years",           # unit-aware conversion
    "past_time":       None,                             # optional
    "current_offense_text": "offense",
    "prior_offense_text":   "offense",
    "current_category_text": "offense category",         # ignored by compute script
    "prior_category_text":   "offense category",
}

#  Defaults / behavior 
DEFAULTS = {
    "missing_numeric": math.nan,                      # keep missing as NaN
    "require_time_fields": ("current_sentence", "completed_time"),
    "childhood_months": 0.0,
    "age_min": 18.0, "age_max": 90.0,
    "age_fallback_years": math.nan,                   # or a number if you prefer
    "freq_min_rate": None, "freq_max_rate": None,     # set numeric bounds if you want non-1.0 outputs
    "trend_years_elapsed": 10.0,
}

# Offense lists 
OFFENSE_LISTS = {
    "violent": ["187", "211", "245"],  # examples; use your codes
    "nonviolent": "rest",              # or explicit list like ["459", "10851"]
}

# Weights 
WEIGHTS_10D = {
    "desc_nonvio_curr": 1.0,
    "desc_nonvio_past": 1.0,
    "age": 1.0,
    "freq_violent": 0.0,
    "freq_total": 0.0,
    "severity_trend": 0.0,
    "edu_general": 1.0, "edu_advanced": 1.0,
    "rehab_general": 1.0, "rehab_advanced": 1.0,
}
