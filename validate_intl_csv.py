"""Validate monthly variation in international_visitors.csv for a given year."""

import argparse
import sys

import pandas as pd


def validate(path: str, year: int, min_months: int = 12, max_flat_markets: int = 3) -> None:
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    sub = df[df["year"] == year]
    if len(sub) < min_months:
        raise SystemExit(f"FAIL: year {year} has {len(sub)} rows, expected >={min_months}")

    markets = [c for c in sub.columns if c not in ("year", "month")]
    flat = []
    for col in markets:
        vals = pd.to_numeric(sub[col], errors="coerce").dropna()
        if len(vals) >= 2 and vals.nunique() <= 1:
            flat.append(col)

    if len(flat) > max_flat_markets:
        raise SystemExit(
            f"FAIL: year {year} has {len(flat)} flat markets "
            f"(same value every month): {flat[:8]}"
        )

    print(f"OK: year {year} passed ({len(sub)} months, {len(flat)} flat markets)")


def main():
    parser = argparse.ArgumentParser(description="Validate international visitor CSV")
    parser.add_argument("csv", help="Path to international_visitors.csv")
    parser.add_argument("--year", type=int, required=True, help="Year to validate")
    parser.add_argument("--min-months", type=int, default=12)
    parser.add_argument("--max-flat-markets", type=int, default=3)
    args = parser.parse_args()
    try:
        validate(args.csv, args.year, args.min_months, args.max_flat_markets)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
