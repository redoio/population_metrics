# config.py
from __future__ import annotations

import os
import math
from typing import Any, Dict

# Data locations (single source of truth)
#
# Default behavior:
#   - Reads from the offenses_data GitHub repo (raw URLs)
# Optional local override:
#   - Set SIMILARITY_DATA_DIR to a folder containing:
#       demographics.csv, prior_commitments.csv, current_commitments.csv

COMMIT_SHA = os.getenv("DATA_COMMIT", "main")  # pin for reproducibility
DATA_DIR = os.getenv("SIMILARITY_DATA_DIR", "").strip()

if DATA_DIR:
    PATHS: Dict[str, str] = {
        "demographics": os.path.join(DATA_DIR, "demographics.csv"),
        "prior_commitments": os.path.join(DATA_DIR, "prior_commitments.csv"),
        "current_commitments": os.path.join(DATA_DIR, "current_commitments.csv"),
        # future optional:
        # "rehab": os.path.join(DATA_DIR, "rehab_credits.csv"),
    }
else:
    PATHS = {
        "demographics": f"https://raw.githubusercontent.com/redoio/offenses_data/{COMMIT_SHA}/data/demographics.csv",
        "prior_commitments": f"https://raw.githubusercontent.com/redoio/offenses_data/{COMMIT_SHA}/data/prior_commitments.csv",
        "current_commitments": f"https://raw.githubusercontent.com/redoio/offenses_data/{COMMIT_SHA}/data/current_commitments.csv",
        # future optional:
        # "rehab": f"https://raw.githubusercontent.com/redoio/offenses_data/{COMMIT_SHA}/data/rehab_credits.csv",
    }


# Similarity / severity configuration


# Minimum number of overlapping (valid) features required for similarity.
# If the intersection size is < MIN_OVERLAP_FOR_SIMILARITY, similarity measures return NaN.
MIN_OVERLAP_FOR_SIMILARITY: int = 3

# Decay rate λ used in the severity_trend formula:
#   severity_trend = Δv * exp(-λ * years_elapsed_for_trend)
SEVERITY_DECAY_RATE: float = 0.15  # can be tuned as needed


# Column Map

COLS: Dict[str, Any] = {
    "id": "cdcno",  # REQUIRED identifier

    # Optional / unavailable in current data -> feature skipped
    "age_years": None,
    "dob": None,
    "reference_date": None,

    # Time/term fields (optional; used if compute code supports them)
    "current_sentence": "aggregate sentence in months",
    "completed_time": "time served in years",
    "past_time": None,  # optional

    # Offense text fields (used by counting logic)
    "current_offense_text": "offense",
    "prior_offense_text": "offense",

    # Category text (ignored unless compute uses it)
    "current_category_text": "offense category",
    "prior_category_text": "offense category",

    # Optional commitment date columns (only needed if present in tables)
    # "prior_commit_date": "commitment_date",
    # "current_commit_date": "commitment_date",
}


# Defaults / Behavior Knobs

# Aparna note: keep ALL tunable defaults in one place (this dict),
# so we don't have confusing "DEFAULT_*" globals vs DEFAULTS dict.
DEFAULTS: Dict[str, Any] = {
    "missing_numeric": math.nan,
    "require_time_fields": ("current_sentence", "completed_time"),

    # Frequency exposure window (MONTHS) used ONLY for freq_* metrics.
    # If None, code computes a per-person exposure window (implementation-defined).
    "months_elapsed_for_frequency": None,

    # Trend horizon override (YEARS) used ONLY for severity_trend.
    # If None, compute from: (first prior commitment date → last current commitment date).
    # If set (e.g., 10.0), it overrides the computed years when compute uses defaults.
    "years_elapsed_for_trend": 10.0,

    # Age normalization (only used if age_years is present and valid)
    "age_min": 18.0,
    "age_max": 90.0,
    "age_fallback_years": math.nan,

    # Frequency normalization bounds (None => skip freq_* entirely)
    "freq_min_rate": None,
    "freq_max_rate": None,

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
        "edu_general": (None, None),
        "edu_advanced": (None, None),
        "rehab_general": (None, None),
        "rehab_advanced": (None, None),
    },
}


# Offense Policies

OFFENSE_LISTS = {
    "violent": ["187", "211", "245"],
    "nonviolent": ["459", "484", "10851"],
}

OFFENSE_POLICY = {
    "nonviolent_rest_mode": False,  # if True, any unlisted offense → "nonviolent"
    "case_insensitive": True,
    "strip_punctuation": True,
}


# Metric Names & Weights

METRIC_NAMES = [
    "desc_nonvio_curr",
    "desc_nonvio_past",
    "age",
    "freq_violent",
    "freq_total",
    "severity_trend",
    "edu_general",
    "edu_advanced",
    "rehab_general",
    "rehab_advanced",
]

METRIC_WEIGHTS: Dict[str, float] = {
    "age": 1.0,
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
    "severity_trend": -1,
    "edu_general": +1,
    "edu_advanced": +1,
    "rehab_general": +1,
    "rehab_advanced": +1,
}

METRIC_RANGES: Dict[str, Any] = {
    "desc_nonvio_curr": (0.0, 1.0),
    "desc_nonvio_past": (0.0, 1.0),
    "age": (0.0, 1.0),
    "freq_violent": (DEFAULTS["freq_min_rate"], DEFAULTS["freq_max_rate"]),
    "freq_total": (DEFAULTS["freq_min_rate"], DEFAULTS["freq_max_rate"]),
    "severity_trend": (0.0, 1.0),
    "edu_general": (0.0, 1.0),
    "edu_advanced": (0.0, 1.0),
    "rehab_general": (0.0, 1.0),
    "rehab_advanced": (0.0, 1.0),
}
