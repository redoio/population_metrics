#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
offense_helpers.py — strict, config-driven offense classification

Design:
- Prefer numeric penal code extraction when present (e.g., "PC 187(a)" -> "187")
- Classify using config.OFFENSE_LISTS:
    violent:   explicit list
    nonviolent: explicit list (or special "rest" mode)
- Optional "rest" mode:
    * Either set OFFENSE_LISTS["nonviolent"] = "rest"
    * OR set OFFENSE_POLICY["nonviolent_rest_mode"] = True
  In either case: anything not in violent_list is treated as nonviolent.

Notes:
- We intentionally do NOT implement case-insensitivity or punctuation stripping beyond numeric extraction,
  because penal-code extraction is the primary normalization for these datasets.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
import re
import config as CFG

# Extract numeric penal code patterns like "187", "653.2", "245.5"
_PENAL_RE = re.compile(r"[0-9]{2,5}(?:\.[0-9]+)?")


def _normalize_offense_token(x: Any) -> str:
    """
    Prefer numeric penal code if present (e.g., 'PC 187(a)' -> '187'),
    else return the original string trimmed.

    IMPORTANT:
      - Strict mode: does NOT apply OFFENSE_POLICY case folding / punctuation stripping.
      - Numeric extraction already removes most formatting variance.
    """
    if x is None:
        return ""
    s = str(x).strip()
    if not s:
        return ""
    m = _PENAL_RE.search(s)
    return m.group(0) if m else s


def classify_offense(code_or_text: Any, lists: Optional[Dict[str, Any]] = None) -> str:
    """
    Strict classification using offense lists.

    Returns:
        "violent", "nonviolent", "other", or "clash"

    Logic:
      1) If token in both violent and nonviolent lists -> "clash"
      2) If token in violent list -> "violent"
      3) If nonviolent is explicit list:
            token in list -> "nonviolent" else "other"
      4) If "rest" mode enabled:
            anything not violent -> "nonviolent"
      5) fallback -> "other"
    """
    li = lists if lists is not None else getattr(CFG, "OFFENSE_LISTS", {})

    token = _normalize_offense_token(code_or_text)
    if token == "":
        return "other"

    violent_list = li.get("violent", []) or []
    non_list = li.get("nonviolent", [])

    # Determine whether "rest mode" is enabled
    policy = getattr(CFG, "OFFENSE_POLICY", {}) or {}
    rest_mode = bool(policy.get("nonviolent_rest_mode", False)) or (non_list == "rest")

    is_v = token in violent_list
    is_n = isinstance(non_list, list) and (token in non_list)

    if is_v and is_n:
        return "clash"
    if is_v:
        return "violent"

    if isinstance(non_list, list):
        return "nonviolent" if is_n else ("nonviolent" if rest_mode else "other")

    # non_list is not a list (e.g., "rest")
    if rest_mode:
        return "nonviolent"

    return "other"
