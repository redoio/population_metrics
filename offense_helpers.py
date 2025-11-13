# offense_helpers.py
from __future__ import annotations
from typing import Any, Dict
import re
import config as CFG

_PENAL_RE = re.compile(r"[0-9]{2,5}(?:\.[0-9]+)?")  # e.g., '187', '653.22'


def _normalize_offense_token(x: Any) -> str:
    """
    Extract a normalized token for matching: prefer a numeric penal code if present,
    else cleaned lowercase text.
    """
    if x is None:
        return ""
    s = str(x).strip()
    if CFG.OFFENSE_POLICY.get("case_insensitive", True):
        s = s.lower()
    m = _PENAL_RE.search(s)
    if m:
        return m.group(0)
    if CFG.OFFENSE_POLICY.get("strip_punctuation", True):
        s = re.sub(r"[^a-z0-9\. ]+", " ", s).strip()
    return s


def classify_offense(code_or_text: Any, lists: Dict[str, Any] | None = None) -> str:
    """
    Map offense to: 'violent' | 'nonviolent' | 'other' | 'clash'.
    Uses OFFENSE_LISTS / OFFENSE_POLICY from config by default.
    """
    li = lists or CFG.OFFENSE_LISTS
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
    if CFG.OFFENSE_POLICY.get("nonviolent_rest_mode", False):
        return "nonviolent"
    return "other"


# Optional early warning if lists overlap
_DUP = set(CFG.OFFENSE_LISTS.get("violent", [])) & set(CFG.OFFENSE_LISTS.get("nonviolent", []))
if _DUP:
    print(f"[WARN] Offense codes appear in both categories (clash): {sorted(_DUP)[:10]} ...")
