# config.py

# Single place to define paths, columns, defaults, weights,
# and final violent / nonviolent lists.


# File paths 
PATHS = {
    "demographics": "demographics.csv",         # or .xlsx
    "current_commitments": "current_commitments.xlsx", # or .csv
    "prior_commitments": "prior_commitments.xlsx",    # or .csv
    "selection_criteria": "selection_criteria.xlsx",  # optional reference
}

# Column names 
COLS = {
    "id": "cdcno",  # unique person ID

    # Demographics (optional; if missing, feature skipped)
    "age_years": None,               # e.g., "Age"
    "dob": None,                     # optional
    "reference_date": None,          # if computing from DOB

    # Time variables (on demographics file)
    "current_sentence": "aggregate sentence in months",  # months
    "completed_time":  "time served in years",           # years; will be converted to months
    "past_time":       None,                             # months; optional

    # Commitments (offense text + optional pre-labeled category)
    "current_offense_text": "offense",
    "prior_offense_text":   "offense",
    "current_category_text": "offense category",
    "prior_category_text":   "offense category",
}

# Defaults 
DEFAULTS = {
    "age_fallback_years": 40.0,
    "childhood_months": 0.0,
    "trend_years_elapsed": 10.0,
    "freq_min_rate": None,
    "freq_max_rate": None,
    "age_min": 18.0,
    "age_max": 90.0,
}

# Offense lists 
# Rules:
# - If nonviolent = "rest", then any code not in violent → nonviolent
# - If both lists explicit, then leftover → "other"
# - If code appears in multiple categories → "clash"

OFFENSE_LISTS = {
    "violent": [
        # examples only — fill with real codes/texts
        "PC187", "PC211", "PC245",
    ],
    "nonviolent": "rest",  # OR replace with explicit list: ["PC459", "VC10851"]
}

# Suitability weights 
# Only applied to features that are computed
WEIGHTS_10D = {
    "desc_nonvio_curr": 1.0,
    "desc_nonvio_past": 1.0,
    "age": 1.0,
    "freq_violent": 0.0,
    "freq_total": 0.0,
    "severity_trend": 0.0,
    "edu_general": 1.0,
    "edu_advanced": 1.0,
    "rehab_general": 1.0,
    "rehab_advanced": 1.0,
}
