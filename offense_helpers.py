# offense_helpers.py — STRICT, config-driven (Aparna-approved)
from __future__ import annotations
from typing import Any, Dict
import re
import config as CFG

# Extract numeric penal code patterns like "187", "653.2", "245.5"
_PENAL_RE = re.compile(r"[0-9]{2,5}(?:\.[0-9]+)?")


def _normalize_offense_token(x: Any) -> str:
    """
    Prefer a numeric penal code if present (e.g., 'PC 187(a)' -> '187'),
    else return the original string trimmed.

    IMPORTANT:
      - Does NOT use OFFENSE_POLICY
      - No lowercase conversion
      - No punctuation stripping beyond numeric extraction
    """
    if x is None:
        return ""
    s = str(x).strip()
    if not s:
        return ""
    m = _PENAL_RE.search(s)
    return m.group(0) if m else s


def classify_offense(code_or_text: Any, lists: Dict[str, Any] | None = None) -> str:
    """
    Strict classification using config.OFFENSE_LISTS.
    Does NOT use OFFENSE_POLICY (even though it exists in config.py).

    Returns:
        "violent", "nonviolent", "other", or "clash"

    Logic:
      1. violent list is always explicit
      2. nonviolent list may be:
           - explicit list
           - "rest" meaning: everything not violent is nonviolent
      3. clash if token appears in both lists (rare, but safe)
    """
    li = lists or CFG.OFFENSE_LISTS

    token = _normalize_offense_token(code_or_text)
    if token == "":
        return "other"

    violent_list = li.get("violent", []) or []
    non_list     = li.get("nonviolent", [])

    is_v = token in violent_list
    is_n = isinstance(non_list, list) and token in non_list

    # Case 1: token appears in both lists → clash
    if is_v and is_n:
        return "clash"

    # Case 2: explicit violent
    if is_v:
        return "violent"

    # Case 3: explicit nonviolent list
    if isinstance(non_list, list):
        return "nonviolent" if is_n else "other"

    # Case 4: nonviolent == "rest" mode
    if non_list == "rest":
        return "nonviolent"

    # Case 5: fallback
    return "other"
