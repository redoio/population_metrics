#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import math
import traceback
from typing import Dict, Any, List, Optional

import pandas as pd
from tqdm import tqdm

import config as CFG
import sentencing_math as sm
import compute_metrics as cm


def _flatten_counts(prefix: str, d: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k1, v1 in (d or {}).items():
        if isinstance(v1, dict):
            for k2, v2 in v1.items():
                out[f"{prefix}{k1}_{k2}"] = v2
        else:
            out[f"{prefix}{k1}"] = v1
    return out


def _load_ids(ids_csv: Optional[str], demo: pd.DataFrame) -> List[str]:
    id_col = CFG.COLS["id"]
    if demo is None or id_col not in demo.columns:
        raise ValueError(
            f"Demographics table is missing required id column '{id_col}'. "
            f"Available columns: {list(demo.columns) if demo is not None else 'None'}"
        )

    if ids_csv:
        df_ids = pd.read_csv(ids_csv)
        if id_col not in df_ids.columns:
            raise ValueError(f"--ids-csv must contain a column named '{id_col}' (from config.COLS['id']).")
        return df_ids[id_col].astype(str).dropna().unique().tolist()

    return demo[id_col].astype(str).dropna().unique().tolist()


def _ensure_dense_metrics(feats: Dict[str, Any]) -> Dict[str, Any]:
    """
    If CFG.METRIC_NAMES exists, ensure all metric columns appear (NaN if missing).
    This makes population outputs schema-stable.
    """
    names = getattr(CFG, "METRIC_NAMES", None)
    if not names:
        return feats
    out = dict(feats)
    for k in names:
        out.setdefault(k, math.nan)
    return out


def main():
    ap = argparse.ArgumentParser(description="Compute population-level sentencing metrics.")
    ap.add_argument("--out", default="population_metrics.csv")
    ap.add_argument("--format", choices=["csv", "parquet", "auto"], default="auto")
    ap.add_argument("--ids-csv", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--include-aux", action="store_true")
    ap.add_argument("--dense", action="store_true", help="Include all CFG.METRIC_NAMES columns (NaN if missing).")
    ap.add_argument("--print-every", type=int, default=0)
    ap.add_argument("--fail-fast", action="store_true")
    ap.add_argument("--tracebacks", action="store_true", help="Include stack traces in the .errors.jsonl file.")
    args = ap.parse_args()

    # Load source tables
    demo = cm.read_table(CFG.PATHS["demographics"])
    cur = cm.read_table(CFG.PATHS["current_commitments"])
    pri = cm.read_table(CFG.PATHS["prior_commitments"])

    # Policy knobs
    lists = getattr(CFG, "OFFENSE_LISTS", {"violent": [], "nonviolent": []})
    weights = getattr(CFG, "METRIC_WEIGHTS", getattr(CFG, "WEIGHTS", {}))
    directions = getattr(CFG, "METRIC_DIRECTIONS", {})

    # Who to run
    ids = _load_ids(args.ids_csv, demo)
    if args.limit:
        ids = ids[: args.limit]
    print(f"Total IDs to process: {len(ids)}")

    rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    pbar = tqdm(total=len(ids), ncols=90, desc="Computing")
    for i, uid in enumerate(ids, start=1):
        try:
            feats, aux = cm.compute_features(str(uid), demo, cur, pri, lists)

            # Optional: stable schema (include NaNs for missing metrics)
            feats_out = _ensure_dense_metrics(feats) if args.dense else feats

            # Final suitability as ratio + parts:
            #   numerator = w · m       (dot with actual metrics)
            #   denom     = w · x*      (dot with best-case vector)
            score_ratio, numerator, denom = sm.suitability_score_named(
                feats,
                weights=weights,
                directions=directions,
                return_parts=True,
            )

            # NaN/None/0 safe handling
            no_denom = (
                denom is None
                or denom == 0
                or (isinstance(denom, float) and math.isnan(denom))
            )

            if no_denom:
                score_ratio_safe = math.nan
                numerator_safe = math.nan
                denom_safe = math.nan
                evaluated_flag = 0  # not evaluated / insufficient data
                score_pct_of_out = math.nan
            else:
                score_ratio_safe = float(score_ratio)
                numerator_safe = float(numerator)
                denom_safe = float(denom)
                evaluated_flag = 1  # evaluated
                score_pct_of_out = (numerator_safe / denom_safe) * 100.0

            record: Dict[str, Any] = {
                CFG.COLS["id"]: str(uid),
                **feats_out,
                "score": numerator_safe,
                "score_out_of": denom_safe,
                "score_ratio": score_ratio_safe,
                "score_pct_of_out": score_pct_of_out,
                "evaluated": evaluated_flag,
            }

            if args.include_aux:
                record["age_value"] = aux.get("age_value")
                record["pct_completed"] = aux.get("pct_completed")
                record["time_outside_months"] = aux.get("time_outside")
                record.update(_flatten_counts("counts_", aux.get("counts_by_category")))

            rows.append(record)

            if args.print_every and (i % args.print_every == 0):
                print(f"[{i}/{len(ids)}] processed …")

        except Exception as e:
            if args.fail_fast:
                raise
            err_rec: Dict[str, Any] = {
                CFG.COLS["id"]: str(uid),
                "error": f"{type(e).__name__}: {e}",
            }
            if args.tracebacks:
                err_rec["traceback"] = traceback.format_exc()
            errors.append(err_rec)
        finally:
            pbar.update(1)
    pbar.close()

    out_df = pd.DataFrame(rows)

    # Column ordering: id, metrics (if configured), score fields, then the rest
    id_col = CFG.COLS["id"]
    metric_order = getattr(CFG, "METRIC_NAMES", [])
    score_order = ["score_ratio", "score", "score_out_of", "score_pct_of_out", "evaluated"]

    ordered: List[str] = []
    for c in [id_col] + list(metric_order) + score_order:
        if c in out_df.columns and c not in ordered:
            ordered.append(c)
    # append any remaining columns
    for c in out_df.columns:
        if c not in ordered:
            ordered.append(c)
    out_df = out_df[ordered] if not out_df.empty else out_df

    # Write
    out_fmt = (
        args.format
        if args.format != "auto"
        else ("parquet" if args.out.lower().endswith(".parquet") else "csv")
    )
    if out_fmt == "parquet":
        out_df.to_parquet(args.out, index=False)
    else:
        out_df.to_csv(args.out, index=False)

    print(f"\nWrote {len(out_df):,} rows to {args.out}")

    # Error log
    if errors:
        err_path = args.out.rsplit(".", 1)[0] + ".errors.jsonl"
        with open(err_path, "w", encoding="utf-8") as f:
            for rec in errors:
                f.write(json.dumps(rec) + "\n")
        print(f"Encountered {len(errors)} errors. Details → {err_path}")

    # Preview
    if not out_df.empty:
        preferred = [id_col, "score_ratio", "score", "score_out_of", "score_pct_of_out", "evaluated"]
        extra = [c for c in out_df.columns if c not in preferred][:5]
        preview_cols = [c for c in preferred if c in out_df.columns] + extra
        print("\nPreview:")
        print(out_df[preview_cols].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
