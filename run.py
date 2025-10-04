#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run.py — batch runner for population-level sentencing metrics

Reads raw tables from config.PATHS, computes metrics + scores for each person,
and writes a flat file (CSV/Parquet).

Depends on updated modules:
- config.py
- compute_metrics.py  (exposes: read_table, compute_features)
- sentencing_math.py  (exposes: suitability_score_named)

Usage:
  python run.py --out population_metrics.csv
  python run.py --out population_metrics.parquet --format parquet
  python run.py --ids-csv ids_subset.csv  # optional subset of IDs
  python run.py --limit 5000              # for a quick smoke test
"""

from __future__ import annotations
import argparse
import json
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
    if ids_csv:
        df_ids = pd.read_csv(ids_csv)
        if id_col not in df_ids.columns:
            raise ValueError(
                f"--ids-csv must contain a column named '{id_col}' (from config.COLS['id'])."
            )
        ids = df_ids[id_col].astype(str).dropna().unique().tolist()
        return ids
    return demo[id_col].astype(str).dropna().unique().tolist()


def main():
    ap = argparse.ArgumentParser(description="Compute population-level sentencing metrics.")
    ap.add_argument("--out", default="population_metrics.csv",
                    help="Output file path (e.g., population_metrics.csv or .parquet)")
    ap.add_argument("--format", choices=["csv", "parquet", "auto"], default="auto",
                    help="Output format; 'auto' infers from file extension")
    ap.add_argument("--ids-csv", default=None,
                    help="Optional CSV file with a single ID column named as config.COLS['id']")
    ap.add_argument("--limit", type=int, default=None,
                    help="Optional limit on number of IDs to process (for smoke tests)")
    ap.add_argument("--include-aux", action="store_true",
                    help="Include auxiliary diagnostics (age_value, pct/time, raw counts)")
    ap.add_argument("--print-every", type=int, default=0,
                    help="Print progress every N rows (0 = only tqdm)")
    ap.add_argument("--fail-fast", action="store_true",
                    help="Abort on first error (default: continue and record error message)")
    args = ap.parse_args()

    demo = cm.read_table(CFG.PATHS["demographics"])
    cur  = cm.read_table(CFG.PATHS["current_commitments"])
    pri  = cm.read_table(CFG.PATHS["prior_commitments"])

    # IMPORTANT: no implicit 'rest' fallback; leave policy to config.OFFENSE_POLICY
    lists   = getattr(CFG, "OFFENSE_LISTS", {"violent": [], "nonviolent": []})
    weights = getattr(CFG, "METRIC_WEIGHTS", getattr(CFG, "WEIGHTS_10D", {}))

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
            score = sm.suitability_score_named(feats, weights)

            record: Dict[str, Any] = {CFG.COLS["id"]: uid, **feats, "score": score}

            if args.include_aux:
                record["age_value"] = aux.get("age_value")
                record["pct_completed"] = aux.get("pct_completed")
                record["time_outside_months"] = aux.get("time_outside")
                record.update(_flatten_counts("counts_", aux.get("counts_by_category")))

            rows.append(record)

            if args.print_every and (i % args.print_every == 0):
                print(f"[{i}/{len(ids)}] processed …")

        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            if args.fail_fast:
                raise
            errors.append({CFG.COLS["id"]: uid, "error": msg})

        finally:
            pbar.update(1)
    pbar.close()

    out_df = pd.DataFrame(rows)

    cols = out_df.columns.tolist()
    id_col = CFG.COLS["id"]
    if id_col in cols:
        cols = [id_col] + [c for c in cols if c != id_col]
        out_df = out_df[cols]

    out_fmt = args.format
    if out_fmt == "auto":
        out_fmt = "parquet" if args.out.lower().endswith(".parquet") else "csv"

    if out_fmt == "parquet":
        out_df.to_parquet(args.out, index=False)
    else:
        out_df.to_csv(args.out, index=False)

    print(f"\nWrote {len(out_df):,} rows to {args.out}")

    if errors:
        err_path = args.out.rsplit(".", 1)[0] + ".errors.jsonl"
        with open(err_path, "w", encoding="utf-8") as f:
            for rec in errors:
                f.write(json.dumps(rec) + "\n")
        print(f"Encountered {len(errors)} errors. Details → {err_path}")

    if not out_df.empty:
        preview_cols = [c for c in out_df.columns if c not in {id_col}][:6]
        print("\nPreview:")
        print(out_df[[id_col] + preview_cols].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
