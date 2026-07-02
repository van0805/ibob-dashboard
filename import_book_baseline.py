"""
Import 2018 international visitor baselines from Book(Auto-update).csv
into data/international_visitors.csv (wide format, same schema as scraper).

Usage:
    python import_book_baseline.py
    python import_book_baseline.py --book path/to/Book(Auto-update).csv --output data/international_visitors.csv
"""

import argparse
import csv
from pathlib import Path

import pandas as pd

BOOK_MARKET_MAP = {
    "Mainland China": "Mainland",
}

INTL_COLUMNS = [
    "Australia", "Canada", "France", "Germany", "India", "Indonesia",
    "Japan", "Macau SAR", "Mainland", "Malaysia", "Netherlands",
    "Philippines", "Russia", "Singapore", "South Korea", "Taiwan",
    "Thailand", "United Kingdom", "USA", "Vietnam", "Middle East",
]


def _normalize_book(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.str.strip()
    market_col = "market regions/markets"
    df["market"] = df[market_col].astype(str).str.strip()
    df["market"] = df["market"].replace(BOOK_MARKET_MAP)
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["month"] = pd.to_numeric(df["month"], errors="coerce")
    arrivals = df["total arrivals"].astype(str).str.replace(",", "", regex=False).str.strip()
    df["arrivals"] = pd.to_numeric(arrivals, errors="coerce")
    return df.dropna(subset=["year", "month", "arrivals"])


def extract_2018_wide(book_path: Path) -> pd.DataFrame:
    """Return year/month wide rows for 2018 from the Book export."""
    raw = pd.read_csv(book_path, encoding="utf-8-sig")
    book = _normalize_book(raw)
    b18 = book[book["year"] == 2018].copy()
    if b18.empty:
        raise ValueError(f"No 2018 rows found in {book_path}")

    wide = (
        b18.pivot_table(index=["year", "month"], columns="market", values="arrivals", aggfunc="sum")
        .reset_index()
    )
    wide.columns.name = None

    for col in INTL_COLUMNS:
        if col not in wide.columns:
            wide[col] = ""

    wide = wide[["year", "month"] + INTL_COLUMNS]
    wide["year"] = wide["year"].astype(int)
    wide["month"] = wide["month"].astype(int)
    return wide.sort_values(["year", "month"]).reset_index(drop=True)


def merge_baseline(output_path: Path, baseline_2018: pd.DataFrame) -> pd.DataFrame:
    """Write 2018 baseline rows to a dedicated CSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_2018.to_csv(output_path, index=False, encoding="utf-8")
    return baseline_2018


def merge_into_visitors(visitors_path: Path, baseline_2018: pd.DataFrame) -> pd.DataFrame:
    """Optionally merge 2018 into international_visitors.csv for a single-file export."""
    if visitors_path.exists():
        existing = pd.read_csv(visitors_path, encoding="utf-8-sig")
        existing.columns = existing.columns.str.strip()
        existing["year"] = pd.to_numeric(existing["year"], errors="coerce")
        existing = existing[existing["year"] != 2018]
    else:
        existing = pd.DataFrame(columns=["year", "month"] + INTL_COLUMNS)

    for col in INTL_COLUMNS:
        if col not in existing.columns:
            existing[col] = ""

    merged = pd.concat([baseline_2018, existing], ignore_index=True)
    merged = merged.sort_values(["year", "month"]).reset_index(drop=True)
    visitors_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(visitors_path, index=False, encoding="utf-8")
    return merged


def main():
    parser = argparse.ArgumentParser(description="Import 2018 visitor baselines from Book CSV")
    parser.add_argument(
        "--book",
        default="Book(Auto-update).csv",
        help="Path to Book(Auto-update).csv export",
    )
    parser.add_argument(
        "--output",
        default="data/international_visitors_baseline_2018.csv",
        help="Path for 2018 baseline CSV (committed to git)",
    )
    parser.add_argument(
        "--merge-into",
        default="data/international_visitors.csv",
        help="Also merge 2018 into this visitors CSV (optional convenience)",
    )
    args = parser.parse_args()

    book_path = Path(args.book)
    output_path = Path(args.output)
    visitors_path = Path(args.merge_into)
    if not book_path.exists():
        raise SystemExit(f"Book file not found: {book_path}")

    baseline = extract_2018_wide(book_path)
    merge_baseline(output_path, baseline)
    merged = merge_into_visitors(visitors_path, baseline)
    print(f"Imported {len(baseline)} months of 2018 baseline from {book_path}")
    print(f"Saved baseline to {output_path}")
    print(f"Merged into {visitors_path} ({len(merged)} total rows)")
    annual = baseline[INTL_COLUMNS].apply(pd.to_numeric, errors="coerce").sum()
    print("  2018 annual totals (thousands):")
    for market in ["Taiwan", "Australia", "USA", "India", "Middle East"]:
        if market in annual.index:
            print(f"    {market}: {int(annual[market] / 1000):,}k")


if __name__ == "__main__":
    main()
