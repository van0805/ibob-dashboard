# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import requests
from io import StringIO
from datetime import timezone, timedelta
from pathlib import Path
import calendar
from html import escape
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="IBOB Dashboard", page_icon="✈️", layout="wide")

# ===== CONFIG =====
CACHE_TTL = 604800  # 7 days
# Dynamic color palette — auto-assigns colors by position (latest year gets teal)
_YEAR_PALETTE = ['#CF9E9A','#B9A779','#3A7976']  # [oldest, middle, latest]
BASELINE_COLOR = '#A6A6A6'  # for 2018 baseline (dashed line)
def get_year_colors(years):
    """Assign colors to a list of years (excluding baseline). Latest year gets the bold color."""
    return {str(yr): _YEAR_PALETTE[i] if i < len(_YEAR_PALETTE) else '#333' for i, yr in enumerate(years)}
GITHUB_USER = "van0805"
GITHUB_REPO = "ibob-dashboard"
GITHUB_CSV_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/data/daily_passenger_traffic.csv"
GITHUB_INTERNATIONAL_CSV_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/data/international_visitors.csv"
LOCAL_INTERNATIONAL_CSV = Path(__file__).resolve().parent / "data" / "international_visitors.csv"
GOV_DATA_URL = "https://www.immd.gov.hk/opendata/eng/transport/immigration_clearance/statistics_on_daily_passenger_traffic.csv"
BASELINE_YEAR = 2018

INTERNATIONAL_MARKETS = [
    "Australia", "Canada", "France", "Germany", "India", "Indonesia",
    "Japan", "Macau SAR", "Malaysia", "Netherlands", "Philippines", "Russia",
    "Singapore", "South Korea", "Taiwan", "Thailand", "United Kingdom",
    "USA", "Vietnam", "Middle East",
]

# Market grouping reference from workbook mapping
MARKET_GROUP_MAP = {
    "Australia": "Australia",
    "Canada": "G7",
    "France": "G7",
    "Germany": "G7",
    "India": "India",
    "Indonesia": "ASEAN",
    "Japan": "G7",
    "Macau SAR": "Macau SAR",
    "Mainland": "Mainland China",
    "Malaysia": "ASEAN",
    "Netherlands": "Others",
    "Philippines": "ASEAN",
    "Russia": "Russia",
    "Singapore": "ASEAN",
    "South Korea": "South Korea",
    "Taiwan": "Taiwan",
    "Thailand": "ASEAN",
    "United Kingdom": "G7",
    "USA": "G7",
    "Vietnam": "ASEAN",
    "Middle East": "Middle East",
}

# PPT summary row layout (matches Macro Update_IBOB Master TABLE 2)
PPT_SUMMARY_ROWS = [
    ("", "Taiwan", ["Taiwan"]),
    ("", "South Korea", ["South Korea"]),
    ("", "Macau SAR", ["Macau SAR"]),
    ("ASEAN", "Philippines", ["Philippines"]),
    ("ASEAN", "Thailand", ["Thailand"]),
    ("ASEAN", "Indonesia", ["Indonesia"]),
    ("ASEAN", "Singapore", ["Singapore"]),
    ("ASEAN", "the Others¹", ["Malaysia", "Vietnam"]),
    ("ASEAN", "ASEAN Total", "asean_total"),
    ("G7", "USA", ["USA"]),
    ("G7", "Japan", ["Japan"]),
    ("G7", "United Kingdom", ["United Kingdom"]),
    ("G7", "the Others²", ["Canada", "France", "Germany"]),
    ("G7", "G7 Total", "g7_total"),
    ("", "Australia", ["Australia"]),
    ("", "Middle East", ["Middle East"]),
    ("", "India", ["India"]),
    ("", "Russia", ["Russia"]),
    ("", "Netherlands", ["Netherlands"]),
    ("", "Total", "grand_total"),
]

_ASEAN_MARKETS = {m for m, g in MARKET_GROUP_MAP.items() if g == "ASEAN"}
_G7_MARKETS = {m for m, g in MARKET_GROUP_MAP.items() if g == "G7"}
_PPT_LISTED_MARKETS = (
    {"Taiwan", "South Korea", "Macau SAR", "Australia", "Middle East", "India", "Russia", "Netherlands"}
    | _ASEAN_MARKETS | _G7_MARKETS
)

# 2018 hardcoded (not in gov CSV which starts 2021)
INBOUND_2018 = {1:172050,2:188606,3:161133,4:176720,5:159774,6:158059,7:176168,8:190192,9:157285,10:189823,11:199834,12:212460}
OUTBOUND_2018 = {1:236056,2:236056,3:269689,4:252022,5:247218,6:257566,7:250747,8:245103,9:240199,10:249645,11:263862,12:278927}

# Holiday periods — region (CN/HK) × year × holiday × variant (official / extended_al)
# For CNY charts: lunar_offset = days from 初一 (0=初一, -1=除夕, etc.)
_LUNAR_LABELS = {-3:'廿七', -2:'廿八', -1:'除夕', 0:'初一', 1:'初二', 2:'初三', 3:'初四', 4:'初五', 5:'初六', 6:'初七', 7:'初八', 8:'初九', 9:'初十'}
CONTEXT_TO_REGION = {'Mainland': 'CN', 'CN': 'CN', 'HK': 'HK'}
CONTEXT_DIRECTION = {'CN': 'inbound', 'Mainland': 'inbound', 'HK': 'outbound'}
HOLIDAY_VARIANTS = ('Official Days', 'Extended Leave Days')
VARIANT_TO_KEY = {'Official Days': 'official', 'Extended Leave Days': 'extended_al'}
HOLIDAY_DISPLAY = {
    'CNY': 'CNY (春节)',
    'Qingming': 'Qingming (清明)',
    'Labour_Day': 'Labour Day (劳动节)',
    'Dragon_Boat': 'Dragon Boat (端午)',
    'Mid_Autumn': 'Mid-Autumn (中秋)',
    'National_Day': 'National Day (国庆)',
    'Easter': 'Easter (复活节)',
    'Christmas': 'Christmas (圣诞)',
}
HOLIDAYS_BY_REGION = {
    'CN': ['CNY', 'Qingming', 'Labour_Day', 'Dragon_Boat', 'Mid_Autumn', 'National_Day'],
    'HK': ['CNY', 'Easter', 'Labour_Day', 'Dragon_Boat', 'National_Day', 'Christmas'],
}
_CNY_FIRST_DAY = {2024: '2024-02-10', 2025: '2025-01-29', 2026: '2026-02-17'}
CP_TYPE_LABELS = {'rail': 'Rail', 'car': 'Car / Land', 'air': 'Air', 'other': 'Other'}

HOLIDAY_PERIODS = {
    "CN": {
        2024: {
            "CNY": {"official": {"start": "2024-02-10", "end": "2024-02-17"}}, #
            "Qingming": {"official": {"start": "2024-04-04", "end": "2024-04-06"}}, #
            "Labour_Day": {"official": {"start": "2024-05-01", "end": "2024-05-05"}}, #
            "Dragon_Boat": {"official": {"start": "2024-06-08", "end": "2024-06-10"}}, 
            "Mid_Autumn": {"official": {"start": "2024-09-15", "end": "2024-09-17"}}, #
            "National_Day": {"official": {"start": "2024-10-01", "end": "2024-10-07"}} #
        },
        2025: {
            "CNY": {"official": {"start": "2025-01-28", "end": "2025-02-04"}}, #
            "Qingming": {"official": {"start": "2025-04-04", "end": "2025-04-06"}}, 
            "Labour_Day": {"official": {"start": "2025-05-01", "end": "2025-05-05"}}, 
            "Dragon_Boat": {"official": {"start": "2025-05-31", "end": "2025-06-02"}}, 
            "Mid_Autumn": {"official": {"start": "2025-10-06", "end": "2025-10-08"}}, # Merged with National Block
            "National_Day": {"official": {"start": "2025-10-01", "end": "2025-10-08"}}
        },
        2026: {
            "CNY": {"official": {"start": "2026-02-15", "end": "2026-02-23"}}, 
            "Qingming": {"official": {"start": "2026-04-04", "end": "2026-04-06"}}, 
            "Labour_Day": {"official": {"start": "2026-05-01", "end": "2026-05-05"}}, 
            "Dragon_Boat": {"official": {"start": "2026-06-19", "end": "2026-06-21"}}, 
            "Mid_Autumn": {"official": {"start": "2026-09-25", "end": "2026-09-27"}}, 
            "National_Day": {"official": {"start": "2026-10-01", "end": "2026-10-07"}}
        }
    },
    "HK": {
        2024: {
            "CNY": {
                "official": {"start": "2024-02-10", "end": "2024-02-13"}, # Sat-Tue
                "extended_al": {"start": "2024-02-10", "end": "2024-02-13"}
            },
            "Easter": {
                "official": {"start": "2024-03-29", "end": "2024-04-01"}, # Fri-Mon
                "extended_al": {"start": "2024-03-29", "end": "2024-04-01"}
            },
            "Labour_Day": {
                "official": {"start": "2024-05-01", "end": "2024-05-01"}, # Wed
                "extended_al": {"start": "2024-05-01", "end": "2024-05-01"} # Isolated
            },
            "Dragon_Boat": {
                "official": {"start": "2024-06-10", "end": "2024-06-10"}, # Mon
                "extended_al": {"start": "2024-06-08", "end": "2024-06-10"} # Weekend link
            },
            "National_Day": {
                "official": {"start": "2024-10-01", "end": "2024-10-01"}, # Tue
                "extended_al": {"start": "2024-09-28", "end": "2024-10-01"} # Bridge Mon Sep 30
            },
            "Christmas": {
                "official": {"start": "2024-12-25", "end": "2024-12-26"}, # Wed-Thu
                "extended_al": {"start": "2024-12-25", "end": "2024-12-29"} # Bridge Fri Dec 27
            }
        },
        2025: {
            "CNY": {
                "official": {"start": "2025-01-29", "end": "2025-01-31"}, # Wed-Fri
                "extended_al": {"start": "2025-01-29", "end": "2025-02-02"} # Weekend link
            },
            "Easter": {
                "official": {"start": "2025-04-18", "end": "2025-04-21"}, # Fri-Mon
                "extended_al": {"start": "2025-04-18", "end": "2025-04-21"}
            },
            "Labour_Day": {
                "official": {"start": "2025-05-01", "end": "2025-05-01"}, # Thu
                "extended_al": {"start": "2025-05-01", "end": "2025-05-04"} # Bridge Fri May 2
            },
            "Dragon_Boat": {
                "official": {"start": "2025-05-31", "end": "2025-05-31"}, # Sat
                "extended_al": {"start": "2025-05-31", "end": "2025-06-01"}
            },
            "National_Day": {
                "official": {"start": "2025-10-01", "end": "2025-10-01"}, # Wed
                "extended_al": {"start": "2025-10-01", "end": "2025-10-01"} # Isolated
            },
            "Christmas": {
                "official": {"start": "2025-12-25", "end": "2025-12-26"}, # Thu-Fri
                "extended_al": {"start": "2025-12-25", "end": "2025-12-28"}
            }
        },
        2026: {
            "CNY": {
                "official": {"start": "2026-02-17", "end": "2026-02-19"}, # Tue-Thu
                "extended_al": {"start": "2026-02-14", "end": "2026-02-22"} # Bridge Mon Feb 16 & Fri Feb 20
            },
            "Easter": {
                "official": {"start": "2026-04-03", "end": "2026-04-06"}, # Good Fri to Easter Mon
                "extended_al": {"start": "2026-04-03", "end": "2026-04-06"}
            },
            "Labour_Day": {
                "official": {"start": "2026-05-01", "end": "2026-05-01"}, # Fri
                "extended_al": {"start": "2026-05-01", "end": "2026-05-03"}
            },
            "Dragon_Boat": {
                "official": {"start": "2026-06-19", "end": "2026-06-19"}, # Fri
                "extended_al": {"start": "2026-06-19", "end": "2026-06-21"}
            },
            "National_Day": {
                "official": {"start": "2026-10-01", "end": "2026-10-01"}, # Thu
                "extended_al": {"start": "2026-10-01", "end": "2026-10-04"} # Bridge Fri Oct 2
            },
            "Christmas": {
                "official": {"start": "2026-12-25", "end": "2026-12-26"}, # Fri-Sat
                "extended_al": {"start": "2026-12-25", "end": "2026-12-27"} # Natural Sun link
            }
        }
    }
}

CP_COLORS = {
    # Each control point gets distinct color; shades grouped by type
    'Lok Ma Chau Spur Line': '#1B6B5A',          # rail — deep teal
    'Express Rail Link West Kowloon': '#3A9790',  # rail — medium teal
    'Lo Wu': '#6EC4B8',                            # rail — light teal
    'Shenzhen Bay': '#B8860B',                     # car — dark goldenrod
    'Heung Yuen Wai': '#DAA520',                   # car — goldenrod
    'Hong Kong-Zhuhai-Macao Bridge': '#CD853F',    # car — peru
    'Lok Ma Chau': '#E8C547',                      # car — golden yellow
    'Airport': '#CF9E9A',                          # air — rose
    'Others': '#A6A6A6',                           # other — gray
}
CP_DISPLAY_NAME = {
    'Lok Ma Chau': 'Lok Ma Chau (皇岗口岸)',
}

CP_TYPE_MAP = {
    'Lok Ma Chau Spur Line':'rail','Express Rail Link West Kowloon':'rail','Lo Wu':'rail',
    'Shenzhen Bay':'car','Heung Yuen Wai':'car','Hong Kong-Zhuhai-Macao Bridge':'car','Lok Ma Chau':'car',
    'Airport':'air',
}


@st.cache_data(ttl=CACHE_TTL)
def fetch_data():
    """Fetch CSV from GitHub cache first, then gov website as fallback."""
    for url in [GITHUB_CSV_URL, GOV_DATA_URL]:
        try:
            headers = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            r = requests.get(url, headers=headers, timeout=60, verify=False)
            if r.status_code == 200 and len(r.text) > 5000:
                df = pd.read_csv(StringIO(r.text), encoding='utf-8-sig')
                if len(df) > 100:
                    source = "GitHub cache" if "github" in url else "gov website"
                    hkt = datetime.now(timezone(timedelta(hours=8)))
                    return df, f"{hkt.strftime('%Y-%m-%d %H:%M')} HKT ({source})"
        except:
            continue
    return None, "Error: Could not fetch data"


@st.cache_data(ttl=CACHE_TTL)
def _parse_international_csv(csv_text, source_label):
    """Parse and validate international visitor CSV (cached only on success)."""
    df = pd.read_csv(StringIO(csv_text), encoding='utf-8-sig')
    df.columns = df.columns.str.strip()
    if df.empty or 'year' not in df.columns:
        return None, None
    hkt = datetime.now(timezone(timedelta(hours=8)))
    return df, f"{hkt.strftime('%Y-%m-%d %H:%M')} HKT ({source_label})"


@st.cache_data(ttl=CACHE_TTL)
def fetch_international_data():
    """Fetch international visitor CSV from GitHub cache, then local file."""
    errors = []
    for label, source, is_url in (
        ("GitHub cache", GITHUB_INTERNATIONAL_CSV_URL, True),
        ("local file", LOCAL_INTERNATIONAL_CSV, False),
    ):
        try:
            if is_url:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                r = requests.get(source, headers=headers, timeout=60, verify=False)
                if r.status_code != 200:
                    errors.append(f"{label}: HTTP {r.status_code}")
                    continue
                if len(r.text) <= 100:
                    errors.append(f"{label}: empty response")
                    continue
                csv_text = r.text
            else:
                if not source.exists():
                    errors.append(f"{label}: file not found")
                    continue
                csv_text = source.read_text(encoding='utf-8-sig')
            df, fetch_time = _parse_international_csv(csv_text, label)
            if df is not None:
                return df, fetch_time
            errors.append(f"{label}: invalid CSV")
        except Exception as exc:
            errors.append(f"{label}: {exc}")

    detail = "; ".join(errors) if errors else "no sources tried"
    return None, f"No international visitor data available ({detail})"


def _international_year_totals(df, year, months=None):
    """Sum monthly arrivals by market for a year (optionally limited to months)."""
    yd = df[df['year'] == year].copy()
    if yd.empty:
        return {}
    if months is not None:
        yd = yd[yd['month'].isin(months)]
    totals = {}
    for market in INTERNATIONAL_MARKETS:
        if market not in yd.columns:
            continue
        vals = pd.to_numeric(yd[market], errors='coerce')
        if vals.notna().any():
            totals[market] = int(vals.sum())
    return totals


def _international_row_total(market_totals, markets):
    return sum(market_totals.get(m, 0) for m in markets)


def _international_others4_total(market_totals):
    return sum(v for m, v in market_totals.items() if m not in _PPT_LISTED_MARKETS)


def _days_in_period(year, months):
    if not months:
        return 0
    return sum(calendar.monthrange(int(year), int(m))[1] for m in months)


def _period_market_totals(df, year, months):
    totals = _international_year_totals(df, year, months=months)
    return totals, _days_in_period(year, months)


def _period_daily_avg(totals, period_days, markets):
    if not totals or period_days <= 0:
        return None
    if markets == "others4":
        total_val = _international_others4_total(totals)
    elif isinstance(markets, list):
        total_val = _international_row_total(totals, markets)
    else:
        return None
    return total_val / period_days


def _international_baseline_2018(df, markets, months):
    """Period-matched 2018 baseline daily average from international_visitors.csv."""
    totals, period_days = _period_market_totals(df, BASELINE_YEAR, months=months)
    return _period_daily_avg(totals, period_days, markets)


def _pct_change(current_k, baseline_k):
    if current_k is None or baseline_k in (None, 0):
        return None
    return (current_k - baseline_k) / baseline_k


def _fmt_pct(pct):
    if pct is None:
        return "—"
    if abs(pct) < 0.005:
        return "0%"
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct:.0%}"


def _fmt_daily_avg(value):
    if value is None:
        return "—"
    return f"{int(round(value)):,}"


def build_ppt_summary(df, target_year=None, target_month=None, year_columns=None):
    """Build international visitors summary with daily averages and inline YoY growth."""
    if df is None or df.empty:
        return None, None, None

    df = df.copy()
    df['year'] = pd.to_numeric(df['year'], errors='coerce').astype('Int64')
    df['month'] = pd.to_numeric(df['month'], errors='coerce').astype('Int64')
    available_years = sorted(df['year'].dropna().unique())
    if not len(available_years):
        return None, None, None

    if target_year is None:
        target_year = int(available_years[-1])
    year_months = sorted(df.loc[df['year'] == target_year, 'month'].dropna().unique())
    if not year_months:
        return None, None, None

    if target_month is None:
        target_month = int(year_months[-1])
    target_month = int(target_month)
    target_months = [m for m in year_months if int(m) <= target_month]
    if not target_months:
        return None, None, None

    period_label = f"YTD {target_year}"

    if year_columns is None:
        year_columns = [target_year]

    # Compute totals for each year column (same month range)
    year_totals = {}
    year_days = {}
    for yr in year_columns:
        totals, days = _period_market_totals(df, int(yr), target_months)
        year_totals[int(yr)] = totals
        year_days[int(yr)] = days

    # Build table rows with inline growth columns
    rows = []
    row_styles = []
    yr_list = [int(y) for y in year_columns]
    yr0 = yr_list[0]
    yr1 = yr_list[1] if len(yr_list) > 1 else None
    yr2 = yr_list[2] if len(yr_list) > 2 else None
    yr_base = yr_list[-1]

    # Column keys for growth detection
    growth_cols = set()
    if yr1:
        growth_cols.add(f"{yr0 % 100} v {yr1 % 100}")
    if yr2:
        growth_cols.add(f"{yr1 % 100} v {yr2 % 100}")
    growth_cols.add(f"{yr0 % 100} v {yr_base % 100}")

    for category, label, spec in PPT_SUMMARY_ROWS:
        if spec == "asean_total":
            markets = list(_ASEAN_MARKETS)
        elif spec == "g7_total":
            markets = list(_G7_MARKETS)
        elif spec == "others4":
            markets = "others4"
        elif spec == "grand_total":
            markets = INTERNATIONAL_MARKETS
        else:
            markets = spec

        # Daily averages for each year
        daily_vals = {}
        for yr in yr_list:
            val = _period_daily_avg(year_totals[yr], year_days[yr], markets)
            daily_vals[yr] = val

        row = {"Category": category, "Market": label}

        # Build columns in order: yr0 Daily, yr0 vs yr1, yr1 Daily, yr1 vs yr2, yr2 Daily, yr0 vs base, base Daily
        # yr0 data
        row[f"{yr0} YTD Daily Avg"] = _fmt_daily_avg(daily_vals[yr0])
        # yr0 vs yr1
        if yr1:
            if daily_vals.get(yr0) and daily_vals.get(yr1):
                row[f"{yr0 % 100} v {yr1 % 100}"] = _fmt_pct(_pct_change(daily_vals[yr0], daily_vals[yr1]))
            else:
                row[f"{yr0 % 100} v {yr1 % 100}"] = "—"
        # yr1 data
        if yr1:
            row[f"{yr1} YTD Daily Avg"] = _fmt_daily_avg(daily_vals[yr1])
        # yr1 vs yr2
        if yr2:
            if daily_vals.get(yr1) and daily_vals.get(yr2):
                row[f"{yr1 % 100} v {yr2 % 100}"] = _fmt_pct(_pct_change(daily_vals[yr1], daily_vals[yr2]))
            else:
                row[f"{yr1 % 100} v {yr2 % 100}"] = "—"
        # yr2 data
        if yr2:
            row[f"{yr2} YTD Daily Avg"] = _fmt_daily_avg(daily_vals[yr2])
        # yr0 vs baseline
        if daily_vals.get(yr0) and daily_vals.get(yr_base):
            row[f"{yr0 % 100} v {yr_base % 100}"] = _fmt_pct(_pct_change(daily_vals[yr0], daily_vals[yr_base]))
        else:
            row[f"{yr0 % 100} v {yr_base % 100}"] = "—"
        # baseline data
        row[f"{yr_base} YTD Daily Avg"] = _fmt_daily_avg(daily_vals[yr_base])

        rows.append(row)

        if spec == "asean_total":
            row_styles.append({"kind": "asean_total"})
        elif spec == "g7_total":
            row_styles.append({"kind": "g7_total"})
        elif spec == "grand_total":
            row_styles.append({"kind": "grand_total"})
        elif category:
            row_styles.append({"kind": "group_child"})
        else:
            row_styles.append({"kind": "default"})

    # Merge-look grouping column
    categories = [row.get("Category", "") for row in rows]
    n = len(categories)
    for i, cat in enumerate(categories):
        if not cat:
            row_styles[i]["category_cell"] = "none"
            continue
        prev_same = i > 0 and categories[i - 1] == cat
        next_same = i < n - 1 and categories[i + 1] == cat
        if not prev_same and next_same:
            row_styles[i]["category_cell"] = "start"
        elif prev_same and next_same:
            row_styles[i]["category_cell"] = "middle"
        elif prev_same and not next_same:
            row_styles[i]["category_cell"] = "end"
        else:
            row_styles[i]["category_cell"] = "single"

    prev_category = None
    for row in rows:
        cat = row.get("Category", "")
        if cat and cat == prev_category:
            row["Category"] = ""
        elif cat:
            prev_category = cat
        else:
            prev_category = None

    columns = ["Category", "Market"] + list(rows[0].keys())[2:]  # skip Category, Market
    summary_df = pd.DataFrame(rows, columns=columns)

    return summary_df, row_styles, {
        "target_year": target_year,
        "target_month": target_month,
        "year_columns": yr_list,
        "months": target_months,
        "period_label": period_label,
        "growth_cols": growth_cols,
    }


def _month_abbr(month):
    return ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(month)]


def style_ppt_summary(summary_df, row_styles):
    """Apply PPT-style formatting: header, subtotals, green/red percentages."""
    pct_cols = [c for c in summary_df.columns if c.startswith("vs ") or " v " in c]

    def _pct_color(val):
        if not isinstance(val, str) or val == "—":
            return ""
        try:
            num = float(val.replace("%", "").replace("+", ""))
            if num > 0:
                return "color: #2e7d32"
            if num < 0:
                return "color: #8b2942"
        except ValueError:
            pass
        return "color: #111"

    def _row_style(row_idx):
        if row_idx >= len(row_styles):
            return [""] * len(summary_df.columns)
        kind = row_styles[row_idx]["kind"]
        styles = [""] * len(summary_df.columns)
        if kind == "asean_total":
            styles[1] = "font-weight: 700; border: 2px solid #2e5c3e"
            styles[2] = "font-weight: 700; border: 2px solid #2e5c3e"
        elif kind == "g7_total":
            styles[1] = "font-weight: 700; border: 2px solid #8b2942"
            styles[2] = "font-weight: 700; border: 2px solid #8b2942"
        elif kind == "grand_total":
            styles = ["font-weight: 700"] * len(summary_df.columns)
        elif kind == "group_child":
            styles[1] = "padding-left: 1.25em"
        category_cell = row_styles[row_idx].get("category_cell", "none")
        if category_cell == "start":
            styles[0] = "font-weight: 700; border-bottom: none;"
        elif category_cell == "middle":
            styles[0] = "border-top: none; border-bottom: none;"
        elif category_cell == "end":
            styles[0] = "border-top: none;"
        elif category_cell == "single":
            styles[0] = "font-weight: 700;"
        return styles

    styler = summary_df.style
    for col in pct_cols:
        styler = styler.map(_pct_color, subset=[col])
    styler = styler.apply(lambda row: _row_style(row.name), axis=1)
    styler = styler.set_table_styles([
        {"selector": "th", "props": [
            ("background-color", "#B9A779"),
            ("color", "white"),
            ("font-weight", "700"),
            ("text-align", "center"),
        ]},
        {"selector": "td", "props": [("text-align", "right")]},
        {"selector": "td.col0", "props": [("text-align", "left")]},
        {"selector": "td.col1", "props": [("text-align", "left")]},
    ], overwrite=False)
    styler = styler.hide(axis="index")
    return styler


def render_ppt_summary_html(summary_df, row_styles):
    """Render summary table as HTML with real rowspans for category blocks."""
    columns = list(summary_df.columns)
    pct_cols = {c for c in columns if c.startswith("vs ") or " v " in c}

    def _pct_color(val):
        if not isinstance(val, str) or val == "—":
            return "#111"
        try:
            num = float(val.replace("%", "").replace("+", ""))
            if num > 0:
                return "#2e7d32"
            if num < 0:
                return "#8b2942"
        except ValueError:
            pass
        return "#111"

    # Pre-compute rowspan for each category start row.
    rowspans = {}
    i = 0
    while i < len(row_styles):
        cstate = row_styles[i].get("category_cell", "none")
        if cstate == "start":
            span = 1
            j = i + 1
            while j < len(row_styles):
                nxt = row_styles[j].get("category_cell", "none")
                if nxt in ("middle", "end"):
                    span += 1
                    if nxt == "end":
                        break
                    j += 1
                    continue
                break
            rowspans[i] = span
        elif cstate == "single":
            rowspans[i] = 1
        i += 1

    html = []
    html.append("""
<style>
.international-summary-table { width: 100%; border-collapse: collapse; font-size: 15px; }
.international-summary-table th { background:#B9A779; color:#fff; font-weight:700; text-align:center; padding:6px 8px; border:1px solid #d4d4d4; }
.international-summary-table td { border:1px solid #d4d4d4; padding:4px 8px; text-align:right; }
.international-summary-table td.col-category, .international-summary-table td.col-market { text-align:left; }
.international-summary-table td.group-child { padding-left:1.25em; }
.international-summary-table tr.asean-total td.col-market, .international-summary-table tr.asean-total td.col-main { font-weight:700; border:2px solid #2e5c3e; }
.international-summary-table tr.g7-total td.col-market, .international-summary-table tr.g7-total td.col-main { font-weight:700; border:2px solid #8b2942; }
.international-summary-table tr.grand-total td { font-weight:700; }
</style>
""")
    html.append('<table class="international-summary-table">')
    html.append("<thead><tr>")
    for col in columns:
        html.append(f"<th>{escape(str(col))}</th>")
    html.append("</tr></thead><tbody>")

    for idx in range(len(summary_df)):
        row = summary_df.iloc[idx]
        kind = row_styles[idx].get("kind", "default")
        tr_class = {
            "asean_total": "asean-total",
            "g7_total": "g7-total",
            "grand_total": "grand-total",
        }.get(kind, "")
        html.append(f'<tr class="{tr_class}">')

        # Category cell with real rowspan.
        cstate = row_styles[idx].get("category_cell", "none")
        if cstate in ("start", "single"):
            span = rowspans.get(idx, 1)
            cat_val = escape(str(row.get("Category", "")))
            html.append(f'<td class="col-category" rowspan="{span}">{cat_val}</td>')
        elif cstate == "none":
            # Keep table columns aligned for rows that do not belong to any category block.
            html.append('<td class="col-category"></td>')

        # Market cell
        market_cls = "col-market group-child" if kind == "group_child" else "col-market"
        html.append(f'<td class="{market_cls}">{escape(str(row.get("Market", "")))}</td>')

        # Remaining value columns
        for col in columns[2:]:
            val = row.get(col, "")
            val_str = "—" if pd.isna(val) else str(val)
            color = _pct_color(val_str) if col in pct_cols else "#111"
            extra_cls = " col-main" if col == columns[2] else ""
            html.append(f'<td class="{extra_cls.strip()}" style="color:{color};">{escape(val_str)}</td>')

        html.append("</tr>")

    html.append("</tbody></table>")
    st.markdown("".join(html), unsafe_allow_html=True)


def process_raw(df):
    """Process raw CSV into daily inbound/outbound/cp data."""
    if df is None:
        return None, None, None, None

    df.columns = df.columns.str.strip()
    df.rename(columns={df.columns[0]: 'Date'}, inplace=True)
    df['Date'] = pd.to_datetime(df['Date'], format='%d-%m-%Y', errors='coerce')
    if df['Date'].isna().all():
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True, errors='coerce')
    df = df.dropna(subset=['Date'])

    for col in ['Hong Kong Residents','Mainland Visitors','Other Visitors','Total']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    for col in ['Hong Kong Residents', 'Mainland Visitors', 'Other Visitors']:
        if col not in df.columns:
            df[col] = 0

    if 'Total' not in df.columns:
        residency_cols = [c for c in ('Hong Kong Residents', 'Mainland Visitors', 'Other Visitors') if c in df.columns]
        df['Total'] = df[residency_cols].sum(axis=1) if residency_cols else 0

    # Split arrival / departure
    arrivals = df[df['Arrival / Departure'] == 'Arrival'].copy()
    departures = df[df['Arrival / Departure'] == 'Departure'].copy()

    # Daily inbound — absolute total arrivals plus residency breakdown for trend charts
    arrivals['tourist_total'] = arrivals['Mainland Visitors'] + arrivals['Other Visitors']
    daily_in = arrivals.groupby('Date', as_index=False).agg(
        total_arrival=('Total', 'sum'),
        tourist_arrival=('tourist_total', 'sum'),
        mainland_arrival=('Mainland Visitors', 'sum'),
        international_arrival=('Other Visitors', 'sum'),
    )
    daily_in['Year'] = daily_in['Date'].dt.year
    daily_in['Month'] = daily_in['Date'].dt.month

    # Daily outbound — absolute total departures plus HK-resident series for trend charts
    daily_out = departures.groupby('Date', as_index=False).agg(
        total_departure=('Total', 'sum'),
        hk_departure=('Hong Kong Residents', 'sum'),
    )
    daily_out['Year'] = daily_out['Date'].dt.year
    daily_out['Month'] = daily_out['Date'].dt.month

    # Keep arrivals with CP detail for holiday analysis
    return daily_in, daily_out, arrivals, departures


def get_monthly(daily_df, value_col):
    """Aggregate daily to monthly."""
    if daily_df is None:
        return None
    monthly = daily_df.groupby(['Year','Month']).agg(
        days=('Date','count'),
        total=(value_col,'sum')
    ).reset_index()
    monthly['daily_avg'] = monthly['total'] / monthly['days']
    return monthly


def is_month_complete(year, month):
    """Check if a month has ended (today >= first day of next month in HKT)."""
    today = datetime.now(timezone(timedelta(hours=8)))
    if month == 12:
        next_month = datetime(year + 1, 1, 1, tzinfo=timezone(timedelta(hours=8)))
    else:
        next_month = datetime(year, month + 1, 1, tzinfo=timezone(timedelta(hours=8)))
    return today >= next_month


def get_series(monthly, year, include_jf=True):
    """Get [Jan&Feb avg, Mar, Apr, ..., Dec] for a given year."""
    if monthly is None:
        return [None]*11
    yd = monthly[monthly['Year']==year]
    if yd.empty:
        return [None]*11

    jan = yd[yd['Month']==1]['daily_avg'].values
    feb = yd[yd['Month']==2]['daily_avg'].values
    jv = jan[0] if len(jan) else None
    fv = feb[0] if len(feb) else None
    jf = (jv+fv)/2 if jv and fv else (jv or fv)

    # Exclude incomplete months for the current year
    if year == datetime.now(timezone(timedelta(hours=8))).year:
        if not is_month_complete(year, 1) or not is_month_complete(year, 2):
            jf = None

    result = [jf]
    for m in range(3,13):
        v = yd[yd['Month']==m]['daily_avg'].values
        val = v[0] if len(v) else None
        if year == datetime.now(timezone(timedelta(hours=8))).year and not is_month_complete(year, m):
            val = None
        result.append(val)
    return result


def get_ytd_avg(monthly, year, through_month):
    """Get YTD daily average: total from Jan through through_month / days in those months."""
    if monthly is None:
        return None
    mask = (monthly["Year"] == year) & (monthly["Month"] >= 1) & (monthly["Month"] <= through_month)
    yd = monthly[mask]
    if yd.empty:
        return None
    total = yd["total"].sum()
    days = yd["days"].sum()
    return total / days if days > 0 else None


def make_ytd_table_figure(table_rows, table_header, title="YTD Daily Average", is_yoy=False):
    """Create a standalone Plotly figure with a YTD summary table (no chart)."""
    fig = go.Figure()

    columns = list(zip(*table_rows))
    n_cols = len(columns)
    n_rows = len(table_rows)

    # Row fills: gray for Overall, white for sub-rows
    row_fills = []
    for i in range(n_rows):
        label = str(table_rows[i][0]).lower()
        if "overall" in label:
            row_fills.append("#f0f0f0")
        else:
            row_fills.append("#ffffff")
    fill_colors = [[row_fills[i] for i in range(n_rows)] for _ in range(n_cols)]

    # Font colors for YoY values
    font_colors = []
    for col_idx, col in enumerate(columns):
        if col_idx == 0:
            font_colors.append(['#111'] * len(col))
        else:
            col_colors = []
            for val in col:
                if is_yoy and isinstance(val, str) and val != '—':
                    try:
                        num = float(val.replace('%', '').replace('+', ''))
                        if num > 0:
                            col_colors.append('#2e7d32')
                        elif num < 0:
                            col_colors.append('#8b2942')
                        else:
                            col_colors.append('#111')
                    except ValueError:
                        col_colors.append('#111')
                else:
                    col_colors.append('#111')
            font_colors.append(col_colors)

    columnwidth = [16] + [13] * (n_cols - 1)

    fig.add_trace(go.Table(
        header=dict(
            values=table_header,
            fill=dict(color="#B9A779"),
            font=dict(color="white", size=12, family="Arial"),
            align="center",
            line=dict(color="#d4d4d4", width=1)
        ),
        cells=dict(
            values=columns,
            font=dict(color=font_colors, size=11, family="Arial"),
            fill=dict(color=fill_colors),
            align=["left"] + ["center"] * (n_cols - 1),
            line=dict(color="#d4d4d4", width=1),
            height=25
        ),
        columnwidth=columnwidth
    ))

    fig.update_layout(
        title=dict(text=title, font=dict(size=13)),
        margin=dict(l=2, r=2, t=40, b=20),
        height=180 + 25 * n_rows,
        template="plotly_white"
    )

    return fig


def make_chart(title, series_dict, y_min=0, y_max=None):
    months = ['Jan&Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    fig = go.Figure()
    for yr, data in series_dict.items():
        valid = [d if d else None for d in data]
        fig.add_trace(go.Scatter(x=months, y=valid, name=yr, mode='lines',
            line=dict(color=COLORS.get(yr,'#333'), width=3 if yr==str(CURRENT_YEAR) else 2.5,
                      dash='dash' if yr=='2018' else 'solid', shape='spline', smoothing=1.0),
            hovertemplate='%{x}<br>'+yr+': <b>%{customdata}K</b><extra></extra>',
            customdata=[int(round(v/1000)) if v else 0 for v in valid],
            connectgaps=False))
    fig.update_layout(title=dict(text=title,font=dict(size=17)),
        yaxis=dict(tickformat=',', range=[y_min, y_max]),
        legend=dict(orientation='h',yanchor='bottom',y=1.02,xanchor='right',x=1),
        margin=dict(l=60,r=20,t=60,b=40), height=380, template='plotly_white', hovermode='x unified')
    return fig


def make_combined_figure(title, series_dict=None, table1_rows=None, table1_header=None,
                         table2_rows=None, table2_header=None, table3_rows=None, table3_header=None,
                         table3_is_yoy=False, y_min=0, y_max=None, extra_height=0):
    months = ['Jan&Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    # Use numeric x positions so we can offset chart points to align with table column centers
    x_positions = list(range(11))  # 0..10
    fig = go.Figure()
    has_chart = series_dict is not None and len(series_dict) > 0

    # Chart traces
    if has_chart:
        for yr, data in series_dict.items():
            valid = [d if d else None for d in data]
            fig.add_trace(go.Scatter(x=x_positions, y=valid, name=yr, mode='lines',
                line=dict(color=COLORS.get(yr,'#333'), width=3 if yr==str(CURRENT_YEAR) else 2.5,
                          dash='dash' if yr=='2018' else 'solid', shape='spline', smoothing=1.0),
                hovertemplate='%{customdata}<br>'+yr+': <b>%{y:,.0f}</b><extra></extra>',
                customdata=months,
                connectgaps=False))

    # Determine number of tables and layout
    num_tables = (1 if table1_rows else 0) + (1 if table2_rows else 0) + (1 if table3_rows else 0)

    if num_tables == 0:
        title_font = 17 if has_chart else 14
        fig.update_layout(title=dict(text=title, font=dict(size=title_font)),
            xaxis=dict(
                domain=[0, 1],
                range=[-0.5, 10.5],
                tickmode='array',
                tickvals=x_positions,
                ticktext=months
            ),
            yaxis=dict(tickformat=',', range=[y_min, y_max]),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
            margin=dict(l=10, r=10, t=50, b=35), height=380, template='plotly_white', hovermode='x unified')
        return fig

    # Dynamic height and domain allocation
    HEADER_PX = 35
    ROW_PX = 30
    GAP_PX = 8
    CHART_PX = 380 if has_chart else 0
    CHART_TABLE_GAP_PX = 32 if has_chart else 0  # visual separation between chart x-axis labels and top table header

    # Gather tables bottom-to-top: table3 (bottom), table2, table1 (just below chart)
    tables = []
    if table3_rows:
        tables.append((table3_rows, table3_header, table3_is_yoy))
    if table2_rows:
        tables.append((table2_rows, table2_header, False))
    if table1_rows:
        tables.append((table1_rows, table1_header, True))

    table_px = sum(HEADER_PX + len(t[0]) * ROW_PX for t in tables)
    inter_table_gap_px = GAP_PX * max(len(tables) - 1, 0)
    chart_table_gap_px = CHART_TABLE_GAP_PX if has_chart and tables else 0
    total_px = CHART_PX + table_px + inter_table_gap_px + chart_table_gap_px
    fig_height = total_px + 80 + extra_height  # 80 for title + margins, extra_height for long titles

    # Allocate table domains from bottom up (in px, convert to fractions)
    table_domains = []
    cursor_px = 0.0
    for t_rows, t_header, t_is_yoy in tables:
        t_px = HEADER_PX + len(t_rows) * ROW_PX
        table_domains.append((t_rows, t_header, t_is_yoy,
            [round(cursor_px / total_px, 4), round((cursor_px + t_px) / total_px, 4)]))
        cursor_px += t_px + GAP_PX

    # Chart domain: starts above the top table with explicit gap (only when chart present)
    if has_chart:
        top_table_top_px = cursor_px - GAP_PX  # undo the trailing GAP_PX added in last iteration
        chart_start_px = top_table_top_px + chart_table_gap_px
        chart_domain = [round(chart_start_px / total_px, 4), 1.0]

    def _build_table(table_rows, table_header, domain_y, is_yoy=False):
        if not table_rows:
            return

        # Transpose rows to columns
        columns = list(zip(*table_rows))
        n_rows = len(table_rows)
        n_cols = len(columns)

        # Compute font colors for values
        font_colors = []
        for col_idx, col in enumerate(columns):
            if col_idx == 0:
                font_colors.append(['#111'] * len(col))
            else:
                col_colors = []
                for val in col:
                    if is_yoy and isinstance(val, str) and val != '—':
                        try:
                            num = float(val.replace('%', '').replace('+', ''))
                            if num > 0:
                                col_colors.append('#2e7d32')
                            elif num < 0:
                                col_colors.append('#8b2942')
                            else:
                                col_colors.append('#111')
                        except ValueError:
                            col_colors.append('#111')
                    else:
                        col_colors.append('#111')
                font_colors.append(col_colors)

        # Compute fill colors for rows (Overall = light gray, subset = white)
        row_fills = []
        for i in range(n_rows):
            label = str(table_rows[i][0]).lower()
            if 'overall' in label or ' vs ' in label:
                row_fills.append('#f0f0f0')
            else:
                row_fills.append('#ffffff')
        fill_colors = [[row_fills[i] for i in range(n_rows)] for _ in range(n_cols)]

        # Column widths: match the table's column count
        # Use generous widths so tables fill the domain and align with chart edges
        if n_cols == 12:  # 1 label + 11 months
            columnwidth = [16] + [11] * 11
        elif n_cols == 13:  # 1 label + 11 months + FY
            columnwidth = [14] + [10] * 11 + [10]
        elif n_cols == 4:  # 1 label + 3 year columns (YTD)
            columnwidth = [16] + [13] * 3
        else:
            columnwidth = None

        fig.add_trace(go.Table(
            header=dict(
                values=table_header,
                fill=dict(color='#B9A779'),
                font=dict(color='white', size=12, family='Arial'),
                align='center',
                line=dict(color='#d4d4d4', width=1)
            ),
            cells=dict(
                values=columns,
                font=dict(color=font_colors, size=11, family='Arial'),
                fill=dict(color=fill_colors),
                align=['left'] + ['center'] * (n_cols - 1),
                line=dict(color='#d4d4d4', width=1),
                height=25
            ),
            domain=dict(x=[0, 1], y=domain_y),
            columnwidth=columnwidth
        ))

    # Add all tables bottom-to-top via precomputed domains
    for t_rows, t_header, t_is_yoy, t_domain in table_domains:
        _build_table(t_rows, t_header, t_domain, is_yoy=t_is_yoy)

    if has_chart:
        fig.update_layout(
            title=dict(text=title, font=dict(size=13)),
            xaxis=dict(
                domain=[0, 1],
                range=[-0.5, 10.5],
                tickmode='array',
                tickvals=x_positions,
                ticktext=months
            ),
            yaxis=dict(domain=chart_domain, tickformat=',', range=[y_min, y_max]),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
            margin=dict(l=10, r=10, t=60, b=35),
            height=fig_height,
            template='plotly_white',
            hovermode='x unified'
        )
    else:
        fig.update_layout(
            title=dict(text=title, font=dict(size=14)),
            margin=dict(l=10, r=10, t=45, b=20),
            height=fig_height,
            template='plotly_white',
        )

    return fig


def _resolve_region(context):
    return CONTEXT_TO_REGION.get(context, context)


def format_period_note(start_str, end_str):
    """Build a readable duration note from start/end dates."""
    start = pd.to_datetime(start_str)
    end = pd.to_datetime(end_str)
    n_days = (end - start).days + 1
    return f"{n_days}d  {start.strftime('%b %d (%a)')} – {end.strftime('%b %d (%a)')}"


def _cny_lunar_offset(start_str, year):
    """Days from 初一 for aligning CNY charts across years."""
    first_day = _CNY_FIRST_DAY.get(int(year))
    if not first_day:
        return 0
    return (pd.to_datetime(start_str) - pd.to_datetime(first_day)).days


def list_holidays_for_context(context):
    region = _resolve_region(context)
    return HOLIDAYS_BY_REGION.get(region, [])


def _enrich_period(period, holiday_key, year):
    """Add derived note and lunar offset to a period dict."""
    period = dict(period)
    period['note'] = format_period_note(period['start'], period['end'])
    if holiday_key == 'CNY':
        period['lunar_offset'] = _cny_lunar_offset(period['start'], year)
    return period


def _bridge_leave_weekdays(official, extended):
    """Weekdays in extended window outside official days (annual leave bridge days)."""
    off_start, off_end = pd.to_datetime(official['start']), pd.to_datetime(official['end'])
    ext_start, ext_end = pd.to_datetime(extended['start']), pd.to_datetime(extended['end'])
    off_dates = set(pd.date_range(off_start, off_end, freq='D'))
    bridge = []
    for d in pd.date_range(ext_start, ext_end, freq='D'):
        if d not in off_dates and d.weekday() < 5:
            bridge.append(d)
    return bridge


def _normalize_hk_holiday(cfg, holiday_key, year):
    """Classify official vs annual-leave windows; merge weekend-only links into official."""
    official = _enrich_period(cfg['official'], holiday_key, year)
    if 'extended_al' not in cfg:
        return {
            'official': official,
            'extended_al': None,
            'al_applicable': False,
            'al_reason': 'No annual leave bridge defined for this holiday.',
        }

    extended_raw = cfg['extended_al']
    if (
        official['start'] == extended_raw['start']
        and official['end'] == extended_raw['end']
    ):
        return {
            'official': official,
            'extended_al': None,
            'al_applicable': False,
            'al_reason': 'No annual leave bridge — official holiday only.',
        }

    bridge_days = _bridge_leave_weekdays(official, extended_raw)
    if not bridge_days:
        merged = {
            'start': min(official['start'], extended_raw['start']),
            'end': max(official['end'], extended_raw['end']),
        }
        merged = _enrich_period(merged, holiday_key, year)
        return {
            'official': merged,
            'extended_al': None,
            'al_applicable': False,
            'al_reason': 'Weekend link only — counted under Official View (no annual leave required).',
        }

    extended = _enrich_period(extended_raw, holiday_key, year)
    bridge_label = ', '.join(d.strftime('%d %b (%a)') for d in bridge_days)
    extended['bridge_note'] = bridge_label
    return {
        'official': official,
        'extended_al': extended,
        'al_applicable': True,
        'al_reason': None,
    }


def get_hk_holiday_meta(region, holiday_key):
    """Per-year official / AL metadata for a HK holiday."""
    meta = {}
    for year, holidays in sorted(HOLIDAY_PERIODS.get(region, {}).items()):
        cfg = holidays.get(holiday_key)
        if not cfg:
            continue
        meta[year] = _normalize_hk_holiday(cfg, holiday_key, year)
    return meta


def build_hk_al_view_periods(holiday_key):
    """AL view windows: extended where defined, otherwise official (for cross-year comparison)."""
    official = get_holiday_periods('HK', holiday_key, 'Official Days')
    extended = get_holiday_periods('HK', holiday_key, 'Extended Leave Days')
    periods = {}
    for year, off in official.items():
        if year in extended:
            periods[year] = extended[year]
        else:
            periods[year] = dict(off)
            periods[year]['official_fallback'] = True
    return periods


def get_holiday_periods(context, holiday_key, variant, al_fallback=False):
    """Return year→period dict for a region/holiday/variant selection."""
    region = _resolve_region(context)
    variant_key = VARIANT_TO_KEY.get(variant, variant)
    periods = {}

    for year, holidays in sorted(HOLIDAY_PERIODS.get(region, {}).items()):
        cfg = holidays.get(holiday_key)
        if not cfg:
            continue

        if region == 'CN':
            if variant_key != 'official':
                continue
            periods[year] = _enrich_period(cfg['official'], holiday_key, year)
            continue

        norm = _normalize_hk_holiday(cfg, holiday_key, year)
        if variant_key == 'official' and norm['official']:
            periods[year] = norm['official']
        elif variant_key == 'extended_al':
            if al_fallback:
                continue  # handled by build_hk_al_view_periods in get_holiday_data
            if norm['extended_al']:
                periods[year] = norm['extended_al']

    return periods


def format_volume_label(value):
    """Format total volume for bar labels with enough precision to distinguish values."""
    if value >= 1_000_000:
        return f"<b>{value / 1_000_000:.2f}M</b>"
    if value >= 1_000:
        return f"<b>{value / 1_000:.1f}K</b>"
    return f"<b>{value:,}</b>"


def make_multiyear_holiday_chart(daily_df, value_col, periods, title, colors):
    """Multi-year daily line chart — all years normalized to same x-axis (MM-DD) for comparison.
    Each year's holiday window highlighted with matching-color vrect.
    Period date-range labels: one block if all years share same MM-DD window,
    otherwise per-year labels."""
    if daily_df is None or daily_df.empty:
        return None

    fig = go.Figure()
    ref_year = 2024  # leap year for date normalization

    years_sorted = sorted(periods.keys(), key=lambda y: int(y))

    # --- First pass: collect normalized period info for dedup ---
    period_info = []  # (year_str, norm_start, norm_end, color, start_label, end_label)
    for year in years_sorted:
        yr_int = int(year)
        p = periods.get(year) or periods.get(yr_int) or periods.get(str(year), {})
        if not p:
            continue
        h_start = pd.to_datetime(p['start'])
        h_end = pd.to_datetime(p['end'])
        norm_start = pd.Timestamp(year=ref_year, month=h_start.month, day=h_start.day)
        norm_end = pd.Timestamp(year=ref_year, month=h_end.month, day=h_end.day)
        color = colors.get(str(year), '#3A7976')
        period_info.append((
            str(year), norm_start, norm_end, color,
            h_start.strftime('%d %b'), h_end.strftime('%d %b'),
        ))

    # Determine if all periods share the same normalized window
    unique_windows = set((ns, ne) for _, ns, ne, _, _, _ in period_info)
    single_window = len(unique_windows) == 1

    # --- Second pass: plot traces + vrects ---
    plotted = False
    for year in years_sorted:
        yr_int = int(year)
        yr_data = daily_df[daily_df['Date'].dt.year == yr_int].sort_values('Date')
        if yr_data.empty:
            continue

        # Normalize dates to reference year for overlay comparison
        norm_dates = yr_data['Date'].apply(
            lambda d: pd.Timestamp(year=ref_year, month=d.month, day=d.day)
        )

        color = colors.get(str(year), '#3A7976')
        fig.add_trace(go.Scatter(
            x=norm_dates,
            y=yr_data[value_col],
            mode='lines',
            name=str(year),
            line=dict(color=color, width=1.8),
            hovertemplate=f'{year} · %{{x|%d %b}}<br><b>%{{y:,}}</b><extra></extra>',
        ))
        plotted = True

    # --- Add vrects (no built-in annotations — we add staggered annotations below) ---
    for yr, ns, ne, color, start_lbl, end_lbl in period_info:
        fig.add_vrect(
            x0=ns,
            x1=ne + pd.Timedelta(days=1),
            fillcolor=color,
            opacity=0.12,
            line_width=0,
            layer='below',
        )

    # --- Staggered annotations to avoid overlap ---
    if single_window and period_info:
        _, ns, ne, color, start_lbl, end_lbl = period_info[0]
        mid = ns + (ne - ns) / 2
        fig.add_annotation(
            x=mid, yref='paper', y=1.02,
            text=f"<b>{start_lbl} – {end_lbl}</b>",
            showarrow=False,
            font=dict(color=color, size=11),
            bgcolor='rgba(255,255,255,0.85)',
            bordercolor=color, borderwidth=1, borderpad=4,
            xanchor='center',
        )
    elif not single_window:
        n = len(period_info)
        y_positions = [1.02 - i * 0.06 for i in range(n)]
        for i, (yr, ns, ne, color, start_lbl, end_lbl) in enumerate(period_info):
            mid = ns + (ne - ns) / 2
            fig.add_annotation(
                x=mid, yref='paper', y=y_positions[i],
                text=f"<b>{yr}</b>  {start_lbl} – {end_lbl}",
                showarrow=False,
                font=dict(color=color, size=10),
                bgcolor='rgba(255,255,255,0.85)',
                bordercolor=color, borderwidth=1, borderpad=3,
                xanchor='center',
            )

    if not plotted:
        return None

    fig.update_layout(
        title=dict(text=title, font=dict(size=15)),
        yaxis=dict(tickformat=','),
        xaxis=dict(dtick='M1', tickformat='%b', title=''),
        margin=dict(l=50, r=20, t=65, b=40),
        height=520,
        template='plotly_white',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
    )
    return fig


def get_holiday_data(raw_arrivals_df, raw_departures_df, daily_in, daily_out, holiday_key, context='Mainland', variant='Extended Leave Days', al_fallback=False, direction=None):
    """Compute holiday stats from absolute arrival/departure totals."""
    region = _resolve_region(context)
    if direction is None:
        direction = CONTEXT_DIRECTION.get(region, 'inbound')
    if direction == 'inbound':
        if raw_arrivals_df is None or daily_in is None:
            return None
        daily_df = daily_in
        value_col = 'total_arrival'
        cp_df = raw_arrivals_df
        cp_value_col = 'Total'
    else:
        if raw_departures_df is None or daily_out is None:
            return None
        daily_df = daily_out
        value_col = 'total_departure'
        cp_df = raw_departures_df
        cp_value_col = 'Total'

    if region == 'HK' and VARIANT_TO_KEY.get(variant, variant) == 'extended_al' and al_fallback:
        periods = build_hk_al_view_periods(holiday_key)
    else:
        periods = get_holiday_periods(region, holiday_key, variant, al_fallback=al_fallback)
    if not periods:
        return None
    result = {'avg': {}, 'total': {}, 'days': {}, 'daily': {}, 'cp_data': {}, 'cp_total': {}, 'periods': periods}

    if not pd.api.types.is_datetime64_any_dtype(cp_df['Date']):
        cp_df = cp_df.copy()
        cp_df['Date'] = pd.to_datetime(cp_df['Date'], errors='coerce')

    for year, p in periods.items():
        start, end = pd.to_datetime(p['start']), pd.to_datetime(p['end'])

        mask = (daily_df['Date'] >= start) & (daily_df['Date'] <= end)
        subset = daily_df[mask]
        if subset.empty:
            continue

        n_days = len(subset)
        total_vol = int(subset[value_col].sum())
        avg = subset[value_col].mean()
        daily_vals = subset[value_col].tolist()

        result['avg'][str(year)] = int(avg)
        result['total'][str(year)] = total_vol
        result['days'][str(year)] = n_days
        result['daily'][str(year)] = [int(v) for v in daily_vals]

        # Control point breakdown
        cp_mask = (cp_df['Date'] >= start) & (cp_df['Date'] <= end)
        cp_subset = cp_df[cp_mask]
        cp_daily = cp_subset.groupby('Control Point')[cp_value_col].sum() / n_days
        result['cp_data'][str(year)] = cp_daily.to_dict()
        cp_total = cp_subset.groupby('Control Point')[cp_value_col].sum()
        result['cp_total'][str(year)] = {k: int(v) for k, v in cp_total.to_dict().items()}

    # Compute growth rates
    years_avail = sorted(result['avg'].keys())
    growth = []
    total_growth = []
    for i in range(len(years_avail) - 1):
        y1, y2 = years_avail[i], years_avail[i + 1]
        if result['avg'][y1] > 0:
            pct = (result['avg'][y2] - result['avg'][y1]) / result['avg'][y1]
            growth.append(f"+{pct:.0%}" if pct >= 0 else f"{pct:.0%}")
        else:
            growth.append("—")
        if result['total'][y1] > 0:
            pct_t = (result['total'][y2] - result['total'][y1]) / result['total'][y1]
            total_growth.append(f"+{pct_t:.0%}" if pct_t >= 0 else f"{pct_t:.0%}")
        else:
            total_growth.append("—")
    result['growth'] = growth
    result['total_growth'] = total_growth

    # CP-level YoY growth (avg daily)
    cp_growth = {}  # {cp_name: [growth_rates across year pairs]}
    for cp_name in CP_TYPE_MAP:
        cp_rates = []
        for i in range(len(years_avail) - 1):
            y1, y2 = years_avail[i], years_avail[i + 1]
            v1 = result['cp_data'].get(y1, {}).get(cp_name, 0)
            v2 = result['cp_data'].get(y2, {}).get(cp_name, 0)
            if v1 and v1 > 0:
                pct = (v2 - v1) / v1
                cp_rates.append(f"+{pct:.0%}" if pct >= 0 else f"{pct:.0%}")
            else:
                cp_rates.append("—")
        cp_growth[cp_name] = cp_rates
    result['cp_growth'] = cp_growth

    # Day labels — use lunar dates for CNY, Gregorian for others
    if years_avail:
        # Check if this holiday has lunar_offset (i.e., CNY)
        has_lunar = any('lunar_offset' in periods.get(int(yr), {}) for yr in years_avail)

        if has_lunar:
            # Align all years by lunar day index
            # lunar_offset: -1=除夕, 0=初一, 1=初二, etc.
            # Find the range that covers all years
            min_lunar = min(periods[int(yr)].get('lunar_offset', 0) for yr in years_avail)
            max_lunar_end = max(
                periods[int(yr)].get('lunar_offset', 0) + len(result['daily'].get(yr, [])) - 1
                for yr in years_avail if result['daily'].get(yr)
            )
            # Build aligned daily data (pad with None where a year doesn't have data for that lunar day)
            n_total = max_lunar_end - min_lunar + 1
            for yr in years_avail:
                offset = periods[int(yr)].get('lunar_offset', 0) - min_lunar
                raw = result['daily'].get(yr, [])
                padded = [None] * n_total
                for j, v in enumerate(raw):
                    padded[offset + j] = v
                result['daily'][yr] = padded
            # Lunar day labels
            result['day_labels'] = [_LUNAR_LABELS.get(min_lunar + i, f"Day{i+1}") for i in range(n_total)]
        else:
            # Generic day labels — holiday dates differ across years,
            # so "Day N" aligns by relative position within the period
            max_len = max((len(result['daily'].get(yr, [])) for yr in years_avail), default=0)
            result['day_labels'] = [f"Day {i + 1}" for i in range(max_len)]

    return result


def render_holiday_variant_charts(hd, context, variant, selected_holiday, daily_in, daily_out, colors, current_year, holiday_key=None, fy_year=None, direction=None):
    """Render full-year, dual histogram, daily trend, and checkpoint charts for one holiday variant."""
    if direction is None:
        direction = CONTEXT_DIRECTION.get(_resolve_region(context), 'inbound')
    flow_label = 'Total Arrivals' if direction == 'inbound' else 'Total Departures'
    daily_df = daily_in if direction == 'inbound' else daily_out
    value_col = 'total_arrival' if direction == 'inbound' else 'total_departure'
    variant_slug = 'official' if variant == 'Official Days' else 'extended'
    chart_key = f"{holiday_key or 'holiday'}_{variant_slug}"

    if not hd or not hd.get('avg'):
        st.info("No data available for the selected holiday period.")
        return

    fy_years = sorted(hd['periods'].keys(), key=lambda y: int(y))

    def _period_for_year(periods, year):
        if year is None:
            return {}
        return periods.get(year) or periods.get(int(year)) or periods.get(str(year), {})

    # --- Multi-year comparison chart (all years overlaid) ---
    fig_fy = make_multiyear_holiday_chart(
        daily_df, value_col, hd['periods'],
        f"Daily {flow_label} — {variant}",
        colors,
    )
    if fig_fy:
        st.plotly_chart(fig_fy, use_container_width=True, key=f"hol_fy_{chart_key}")

    # --- Daily trend (zoom-in of holiday period, all years overlaid) ---
    years_avail = sorted(hd['avg'].keys())
    st.markdown(f"**Daily {flow_label}** by day — {variant}")
    fig_daily = go.Figure()
    day_labels = hd.get('day_labels', [])
    max_len = max((len(hd['daily'].get(yr, [])) for yr in years_avail), default=0)
    if not day_labels and max_len:
        day_labels = [f"Day {j + 1}" for j in range(max_len)]
    x_idx = list(range(len(day_labels)))

    for yr in years_avail:
        data = hd['daily'].get(yr, [])
        if data:
            fig_daily.add_trace(go.Scatter(
                x=x_idx[:len(data)], y=data, name=yr, mode='lines+markers',
                line=dict(
                    color=colors.get(yr, '#999'),
                    width=3 if yr == years_avail[-1] else 2,
                    dash='dash' if yr == years_avail[0] else 'solid',
                    shape='spline',
                ),
                marker=dict(size=6),
                hovertemplate=yr + ': <b>%{customdata}K</b><extra></extra>',
                customdata=[int(round(v / 1000)) if v is not None else 0 for v in data],
                connectgaps=False,
            ))
    for i in range(max_len):
        fig_daily.add_vline(x=i, line_width=1, line_dash="dot", line_color="#e0e0e0")
    fig_daily.update_layout(
        xaxis=dict(tickmode='array', tickvals=x_idx, ticktext=day_labels),
        yaxis=dict(tickformat=','), showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        margin=dict(l=50, r=20, t=30, b=40), height=380, template='plotly_white',
        yaxis_range=[0, None],
    )
    st.plotly_chart(fig_daily, use_container_width=True, key=f"hol_daily_{chart_key}")

    # --- Bar charts: Total Volume (left) + Avg. Daily (right) ---
    years_avail = sorted(hd['avg'].keys())
    bar_colors = [colors.get(yr, '#B9A779') if yr == str(current_year) else '#c8c8c8' for yr in years_avail]
    bar_labels = [
        f"{yr}<br>{hd['days'][yr]}d" + ("*" if _period_for_year(hd['periods'], yr).get('official_fallback') else "")
        for yr in years_avail
    ]

    col_total, col_avg = st.columns(2)
    with col_total:
        st.markdown(f"**Total Volume** — {variant}")
        total_vals = [hd['total'][yr] for yr in years_avail]
        fig_tot = go.Figure(go.Bar(
            x=bar_labels, y=total_vals, marker_color=bar_colors,
            text=[format_volume_label(v) for v in total_vals],
            textposition='outside',
        ))
        for i, g in enumerate(hd.get('total_growth', [])):
            fig_tot.add_annotation(
                x=(i + i + 1) / 2, y=(total_vals[i] + total_vals[i + 1]) / 2,
                text=f"<b>{g}</b>", showarrow=False,
                font=dict(size=12, color='#333'),
                bgcolor='#fff', bordercolor='#555', borderwidth=1.5, borderpad=4,
            )
        fig_tot.update_layout(
            yaxis=dict(visible=False), showlegend=False,
            margin=dict(l=20, r=20, t=30, b=40), height=360, template='plotly_white',
        )
        st.plotly_chart(fig_tot, use_container_width=True, key=f"hol_tot_{chart_key}")

    with col_avg:
        st.markdown(f"**Avg. Daily {flow_label}** — {variant}")
        bar_vals = [hd['avg'][yr] for yr in years_avail]
        fig_avg = go.Figure(go.Bar(
            x=bar_labels, y=bar_vals, marker_color=bar_colors,
            text=[f"<b>{int(v/1000)}K</b>" for v in bar_vals], textposition='outside',
        ))
        for i, g in enumerate(hd.get('growth', [])):
            fig_avg.add_annotation(
                x=(i + i + 1) / 2, y=(bar_vals[i] + bar_vals[i + 1]) / 2,
                text=f"<b>{g}</b>", showarrow=False,
                font=dict(size=12, color='#333'),
                bgcolor='#fff', bordercolor='#555', borderwidth=1.5, borderpad=4,
            )
        fig_avg.update_layout(
            yaxis=dict(visible=False), showlegend=False,
            margin=dict(l=20, r=20, t=30, b=40), height=360, template='plotly_white',
        )
        st.plotly_chart(fig_avg, use_container_width=True, key=f"hol_avg_{chart_key}")

    top_cps = [
        'Lok Ma Chau Spur Line', 'Express Rail Link West Kowloon', 'Lo Wu',
        'Shenzhen Bay', 'Heung Yuen Wai', 'Hong Kong-Zhuhai-Macao Bridge', 'Lok Ma Chau', 'Airport',
    ]
    cp_years = sorted(hd['cp_data'].keys())
    if not cp_years:
        st.caption("No control-point breakdown available for this period.")
        return

    fig_cp = go.Figure()
    cp_x_idx = list(range(len(cp_years)))

    # Build CP line traces with per-CP distinct colors
    cp_growth_data = hd.get('cp_growth', {})
    for cp in top_cps:
        pts = []
        for yr in cp_years:
            val = hd['cp_data'].get(yr, {}).get(cp, 0)
            pts.append(int(val) if val > 500 else None)
        cp_type = CP_TYPE_MAP.get(cp, 'other')
        cp_label = CP_DISPLAY_NAME.get(cp, cp)
        cp_color = CP_COLORS.get(cp, CP_COLORS.get(cp_type, '#A6A6A6'))
        fig_cp.add_trace(go.Scatter(
            x=cp_x_idx, y=pts,
            name=cp_label,
            legendgroup=cp_type,
            showlegend=True,
            mode='lines+markers',
            line=dict(color=cp_color, width=2.5),
            marker=dict(size=7, color=cp_color),
            hovertemplate=f"{cp_label}<br>Avg Daily: <b>%{{y:,}}</b><extra></extra>",
        ))
        # YoY growth annotations between consecutive years
        cp_rates = cp_growth_data.get(cp, [])
        for j in range(1, len(cp_years)):
            y1, y2 = cp_years[j - 1], cp_years[j]
            v1 = hd['cp_data'].get(y1, {}).get(cp, 0)
            v2 = hd['cp_data'].get(y2, {}).get(cp, 0)
            if v1 and v1 > 0 and j - 1 < len(cp_rates):
                mid_x = (cp_x_idx[j - 1] + cp_x_idx[j]) / 2
                mid_y = (v1 + v2) / 2
                rate_str = cp_rates[j - 1]
                is_pos = rate_str.startswith('+')
                fig_cp.add_annotation(
                    x=mid_x, y=mid_y,
                    text=f"<b>{rate_str}</b>",
                    showarrow=False,
                    font=dict(size=9, color='#2e7d32' if is_pos else '#8b2942' if rate_str != '—' else '#888'),
                    bgcolor='rgba(255,255,255,0.75)',
                    borderpad=2,
                )

    others_pts = []
    for yr in cp_years:
        yr_data = hd['cp_data'].get(yr, {})
        others_val = sum(v for k, v in yr_data.items() if k not in top_cps)
        others_pts.append(int(others_val) if others_val > 0 else None)
    fig_cp.add_trace(go.Scatter(
        x=cp_x_idx, y=others_pts, name='Others',
        legendgroup='other', showlegend=True,
        mode='lines+markers',
        line=dict(color=CP_COLORS.get('Others', '#A6A6A6'), width=1.5, dash='dot'),
        marker=dict(size=5, color=CP_COLORS.get('Others', '#A6A6A6')),
    ))

    fig_cp.update_layout(
        xaxis=dict(
            tickmode='array', tickvals=cp_x_idx,
            ticktext=[str(yr) for yr in cp_years],
            range=[-0.3, len(cp_years) - 0.7],
        ),
        yaxis=dict(tickformat=',', range=[0, None]),
        legend=dict(
            orientation='v', yanchor='top', y=1,
            xanchor='left', x=1.02, font=dict(size=10),
            tracegroupgap=4,
        ),
        showlegend=True,
        margin=dict(l=60, r=200, t=80, b=40), height=460, template='plotly_white',
        title=dict(
            text=(
                f"Avg. Daily {flow_label} by Control Point — {selected_holiday} ({variant})"
                f"<br><sup>Distinct colour per checkpoint · YoY growth labeled between years</sup>"
            ),
            font=dict(size=14),
        ),
    )
    st.plotly_chart(fig_cp, use_container_width=True, key=f"hol_cp_{chart_key}")

    # Standalone total-volume table (full width)
    all_cp_names = top_cps + ['Others']
    cp_table_header = ['Year'] + all_cp_names
    cp_total_rows = []
    for yr in cp_years:
        row = [str(yr)]
        for cp in all_cp_names:
            if cp == 'Others':
                yr_data = hd['cp_total'].get(yr, {})
                tv = sum(v for k, v in yr_data.items() if k not in top_cps)
                row.append(f"{int(tv):,}" if tv else "—")
            else:
                tv = hd['cp_total'].get(yr, {}).get(cp, 0)
                row.append(f"{int(tv):,}" if tv else "—")
        cp_total_rows.append(row)

    cp_table_cols = list(zip(*cp_total_rows))
    n_cp_cols = len(cp_table_header)
    n_cp_rows = len(cp_total_rows)
    cp_header_fills = ['#B9A779'] + [CP_COLORS.get(cp, '#A6A6A6') for cp in all_cp_names]
    cp_cell_fills = [['#ffffff'] * n_cp_rows for _ in range(n_cp_cols)]
    cp_cell_font_color = [['#111111'] * n_cp_rows for _ in range(n_cp_cols)]

    fig_cp_table = go.Figure()
    fig_cp_table.add_trace(go.Table(
        header=dict(
            values=[f"<b>{h}</b>" for h in cp_table_header],
            fill=dict(color=cp_header_fills),
            font=dict(color='white', size=11, family='Arial'),
            align='center',
            line=dict(color='#d4d4d4', width=1),
        ),
        cells=dict(
            values=cp_table_cols,
            font=dict(color=cp_cell_font_color, size=10, family='Arial'),
            fill=dict(color=cp_cell_fills),
            align=['left'] + ['center'] * (n_cp_cols - 1),
            line=dict(color='#d4d4d4', width=1),
            height=24,
        ),
    ))
    table_height = 35 + len(cp_total_rows) * 30 + 100
    fig_cp_table.update_layout(
        title=dict(
            text=f"Total {flow_label} by Control Point — {selected_holiday} ({variant})",
            font=dict(size=14),
        ),
        margin=dict(l=20, r=20, t=50, b=10),
        height=table_height,
        template='plotly_white',
    )
    st.plotly_chart(fig_cp_table, use_container_width=True, key=f"hol_cp_table_{chart_key}")

def render_mini_calendar_row(start_date_str, end_date_str, official_start_str, official_end_str):
    """Generates a compact horizontal calendar row showing weekends, official holidays, and bridge leave options."""
    start_dt = pd.to_datetime(start_date_str)
    end_dt = pd.to_datetime(end_date_str)
    
    # Pad to capture surrounding weekends if needed
    display_start = start_dt - pd.Timedelta(days=start_dt.weekday()) # Snap to Monday of that week
    display_end = end_dt + pd.Timedelta(days=(6 - end_dt.weekday())) # Snap to Sunday of that week
    
    days_range = pd.date_range(display_start, display_end)
    
    off_start = pd.to_datetime(official_start_str)
    off_end = pd.to_datetime(official_end_str)
    
    html = """
    <style>
        .cal-container { display: flex; flex-wrap: wrap; gap: 4px; font-family: sans-serif; margin-bottom: 15px; }
        .cal-day { width: 45px; text-align: center; border-radius: 4px; padding: 4px 0; border: 1px solid #E0E0E0; font-size: 12px; color: #222; background: #fff; }
        .cal-day .day-header { font-weight: bold; font-size: 11px; margin-bottom: 2px; text-transform: uppercase; background: #F5F5F5; color: #444; border-radius: 3px 3px 0 0; }
        .cal-day .day-num { font-size: 14px; font-weight: 600; }
        .cal-day .day-month { font-size: 9px; opacity: 0.85; }
        .cal-day.is-official { background-color: #3A7976; color: #fff; border-color: #2F615E; }
        .cal-day.is-official .day-header { background-color: #2F615E; color: #fff; }
        .cal-day.is-official .day-num, .cal-day.is-official .day-month { color: #fff; }
        .cal-day.is-weekend { background-color: #F0F2F6; color: #555; border-color: #DCDFE6; }
        .cal-day.is-weekend .day-header { background-color: #E4E7EC; color: #555; font-style: italic; }
        .cal-day.is-leave { background-color: #FFF0F0; color: #C93B2B; border-color: #F5C2C2; border-style: dashed; }
        .cal-day.is-leave .day-header { background-color: #F5D0D0; color: #C93B2B; }
    </style>
    <div class='cal-container'>
    """
    
    for d in days_range:
        is_wknd = d.weekday() in [5, 6]
        is_off = off_start <= d <= off_end
        is_leave = (start_dt <= d <= end_dt) and not is_off and not is_wknd
        
        # Class determination
        cls = ""
        status_lbl = "📅"
        if is_off:
            cls = "is-official"
            status_lbl = "Holiday"
        elif is_wknd:
            cls = "is-weekend"
            status_lbl = "Wknd"
        elif is_leave:
            cls = "is-leave"
            status_lbl = "Leave"
            
        weekday_name = d.strftime('%a')[:2]
        html += f"""
        <div class='cal-day {cls}'>
            <div class='day-header'>{weekday_name}</div>
            <div class='day-num'>{d.day}</div>
            <div class='day-month'>{d.strftime('%b')}</div>
        </div>
        """
    html += "</div>"
    return html

# ==================== MAIN APP ====================
st.title("IBOB Traffic Trends")
st.caption("Inbound | Outbound | International Visitors | Holiday Analysis | Data Analytics")

col1, _ = st.columns([1,5])
with col1:
    if st.button("🔄 Refresh Data", type="primary"):
        st.cache_data.clear()
        st.rerun()

raw_df, fetch_time = fetch_data()
if fetch_time and not fetch_time.startswith("Error"):
    st.caption(f"📅 {fetch_time} | Rows: {len(raw_df) if raw_df is not None else 0}")
else:
    st.error(f"⚠️ {fetch_time}")

daily_in, daily_out, arrivals_df, departures_df = process_raw(raw_df.copy() if raw_df is not None else None)
monthly_in = get_monthly(daily_in, 'tourist_arrival')
monthly_out = get_monthly(daily_out, 'hk_departure')

# Dynamic year detection — auto-determine which years to display
if daily_in is not None:
    _all_years = sorted(daily_in['Year'].unique())
    DISPLAY_YEARS = [yr for yr in _all_years if yr >= 2024][-3:]  # latest 3 years from 2024+
else:
    DISPLAY_YEARS = [2024, 2025, 2026]
CURRENT_YEAR = DISPLAY_YEARS[-1] if DISPLAY_YEARS else 2026
COLORS = {**get_year_colors(DISPLAY_YEARS), '2018': BASELINE_COLOR}

# ===== INBOUND =====
st.markdown("---")
st.subheader("🛬 Inbound Tourist Arrivals")

inbound_2018 = [(INBOUND_2018[1]+INBOUND_2018[2])/2]+[INBOUND_2018[m] for m in range(3,13)]
inbound_s = {'2018': inbound_2018}
for yr in DISPLAY_YEARS:
    inbound_s[str(yr)] = get_series(monthly_in, yr)

# 2018 baseline by type (from Excel - Mainland and International)
MAINLAND_2018 = {1:132097,2:156357,3:117796,4:134413,5:122709,6:120557,7:141419,8:154956,9:123129,10:149308,11:153770,12:164596}
INTERNATIONAL_2018 = {k: INBOUND_2018[k]-MAINLAND_2018[k] for k in INBOUND_2018}

# Get monthly mainland and international series
monthly_mainland = get_monthly(daily_in, 'mainland_arrival') if daily_in is not None else None
monthly_international = get_monthly(daily_in, 'international_arrival') if daily_in is not None else None

def calc_recovery(monthly_data, baseline_dict, year):
    """Calculate recovery rate for each month vs 2018."""
    if monthly_data is None:
        return ['—']*11
    series = get_series(monthly_data, year)
    rates = []
    for i, val in enumerate(series):
        if i == 0:
            base_val = (baseline_dict[1]+baseline_dict[2])/2
        else:
            base_val = baseline_dict.get(i+2, None)
        if val and base_val and base_val > 0:
            rates.append(f"{val/base_val:.0%}")
        else:
            rates.append("—")
    # FY average
    valid = [v for v in series if v]
    base_valid = [(baseline_dict[1]+baseline_dict[2])/2] + [baseline_dict.get(m,0) for m in range(3,13)]
    base_valid = [b for b, v in zip(base_valid, series) if v]
    if valid and base_valid:
        rates.append(f"{sum(valid)/sum(base_valid):.0%}")
    else:
        rates.append("—")
    return rates

def calc_yoy(monthly_data, curr_year, prev_year):
    """Calculate YoY growth rate for each month + FY average."""
    if monthly_data is None:
        return ['—']*12
    curr_s = get_series(monthly_data, curr_year)
    prev_s = get_series(monthly_data, prev_year)
    rates = []
    for i in range(11):
        if curr_s[i] and prev_s[i] and prev_s[i] > 0:
            pct = (curr_s[i] - prev_s[i]) / prev_s[i]
            rates.append(f"{pct:+.0%}")
        else:
            rates.append("—")
    # FY average
    valid_curr = [v for v in curr_s if v]
    valid_prev = [prev_s[i] for i, v in enumerate(curr_s) if v and prev_s[i]]
    if valid_curr and valid_prev and sum(valid_prev) > 0:
        rates.append(f"{(sum(valid_curr) - sum(valid_prev)) / sum(valid_prev):+.0%}")
    else:
        rates.append("—")
    return rates

months_h = ['Jan&Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

# YoY table rows
yoy_rows = []
for yr in DISPLAY_YEARS[-2:]:
    yoy_rows.append([f'<b>{yr} Overall</b>'] + calc_yoy(monthly_in, yr, yr-1))
    yoy_rows.append(['  Mainland'] + calc_yoy(monthly_mainland, yr, yr-1))
    yoy_rows.append(['  International'] + calc_yoy(monthly_international, yr, yr-1))

# Recovery table rows
rec_rows = []
for yr in DISPLAY_YEARS[-2:]:
    rec_rows.append([f'<b>{yr} Overall</b>'] + calc_recovery(monthly_in, INBOUND_2018, yr))
    rec_rows.append(['  Mainland'] + calc_recovery(monthly_mainland, MAINLAND_2018, yr))
    rec_rows.append(['  International'] + calc_recovery(monthly_international, INTERNATIONAL_2018, yr))

# -- YTD config and helper (shared by inbound + outbound) --
today_hkt = datetime.now(timezone(timedelta(hours=8)))
ytd_through_month = None
for m in range(today_hkt.month, 0, -1):
    if is_month_complete(today_hkt.year, m):
        ytd_through_month = m
        break
if ytd_through_month is None:
    ytd_through_month = max(today_hkt.month - 1, 1)
month_abbrs = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
ytd_label = f"YTD (Jan–{month_abbrs[ytd_through_month - 1]})"

def _ytd_growth(monthly, yr, prev_yr, through):
    cur = get_ytd_avg(monthly, yr, through)
    prv = get_ytd_avg(monthly, prev_yr, through)
    if cur and prv and prv > 0:
        return f"{(cur - prv) / prv:+.0%}"
    return "—"

# YTD rows for inbound
ytd_in_rows = []
ytd_in_rows.append(["<b>Overall</b>"] + [
    _ytd_growth(monthly_in, yr, yr-1, ytd_through_month)
    for yr in DISPLAY_YEARS
])
ytd_in_rows.append(["  Mainland"] + [
    _ytd_growth(monthly_mainland, yr, yr-1, ytd_through_month)
    for yr in DISPLAY_YEARS
])
ytd_in_rows.append(["  International"] + [
    _ytd_growth(monthly_international, yr, yr-1, ytd_through_month)
    for yr in DISPLAY_YEARS
])

ytd_in_header = [ytd_label] + [str(yr) for yr in DISPLAY_YEARS]

st.plotly_chart(
    make_combined_figure(
        "Daily Tourist Arrivals by Month",
        inbound_s,
        y_max=300000
    ),
    use_container_width=True
)

# Tables summary — standalone full-width figure with all three tables stacked
st.plotly_chart(
    make_combined_figure(
        "Inbound YoY, Recovery & YTD Summary",
        table1_rows=yoy_rows,
        table1_header=['YoY Growth Rate'] + months_h + ['FY'],
        table2_rows=rec_rows,
        table2_header=['Recovery Rate vs 2018'] + months_h + ['FY'],
        table3_rows=ytd_in_rows,
        table3_header=ytd_in_header,
        table3_is_yoy=True,
    ),
    use_container_width=True
)
st.caption("Source: Transportation Dept; Tourism Board; Immigration Dept.")


def _build_intl_monthly_chart(df):
    """Monthly trend chart: international visitors by market group, 2024–present."""
    df = df.copy()
    df['year'] = pd.to_numeric(df['year'], errors='coerce').astype('Int64')
    df['month'] = pd.to_numeric(df['month'], errors='coerce').astype('Int64')

    asean_mkts = [m for m in INTERNATIONAL_MARKETS if MARKET_GROUP_MAP.get(m) == 'ASEAN']
    g7_mkts = [m for m in INTERNATIONAL_MARKETS if MARKET_GROUP_MAP.get(m) == 'G7']
    other_mkts = [m for m in INTERNATIONAL_MARKETS if MARKET_GROUP_MAP.get(m) not in ('ASEAN', 'G7')]

    for m in INTERNATIONAL_MARKETS:
        if m in df.columns:
            df[m] = pd.to_numeric(df[m], errors='coerce').fillna(0)

    df['ASEAN'] = df[[m for m in asean_mkts if m in df.columns]].sum(axis=1)
    df['G7'] = df[[m for m in g7_mkts if m in df.columns]].sum(axis=1)
    df['Other Markets'] = df[[m for m in other_mkts if m in df.columns]].sum(axis=1)
    df['Total'] = df[['ASEAN', 'G7', 'Other Markets']].sum(axis=1)

    df = df[df['year'] >= 2024].sort_values(['year', 'month'])
    if df.empty:
        return None

    df['date'] = pd.to_datetime(df[['year', 'month']].assign(day=1))

    fig = go.Figure()
    groups = [
        ('Total', '#111111', 2.8, 'solid'),
        ('ASEAN', '#2E7D5E', 2.0, 'solid'),
        ('G7', '#8B2942', 2.0, 'solid'),
        ('Other Markets', '#B9A779', 1.8, 'dash'),
    ]
    for name, color, width, dash in groups:
        if name not in df.columns:
            continue
        mask = df[name].notna() & (df[name] > 0)
        fig.add_trace(go.Scatter(
            x=df.loc[mask, 'date'], y=df.loc[mask, name],
            name=name, mode='lines',
            line=dict(color=color, width=width, dash=dash),
            hovertemplate=f'{name}: <b>%{{y:,.0f}}</b><br>%{{x|%b %Y}}<extra></extra>',
        ))

    fig.update_layout(
        title=dict(text="Monthly International Visitor Arrivals by Market Group", font=dict(size=15)),
        xaxis=dict(dtick='M1', tickformat='%b<br>%Y', ticklabelstep=2),
        yaxis=dict(tickformat=',', title='Monthly Arrivals'),
        margin=dict(l=60, r=20, t=50, b=50), height=420, template='plotly_white',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        hovermode='x unified',
    )
    return fig


def render_international_visitors_section():
    """Render international visitors: monthly chart, daily-average table with inline growth."""
    st.markdown("---")
    st.subheader("🌏 International Visitor Arrivals")

    international_df, international_fetch_time = fetch_international_data()
    if international_df is not None:
        st.caption(f"📅 {international_fetch_time} | Rows: {len(international_df)}")

        international_df_c = international_df.copy()
        international_df_c['year'] = pd.to_numeric(international_df_c['year'], errors='coerce').astype('Int64')
        international_df_c['month'] = pd.to_numeric(international_df_c['month'], errors='coerce').astype('Int64')
        available_years = sorted(international_df_c['year'].dropna().unique().astype(int))

        # Auto-detect: latest year + latest month
        curr_year = int(available_years[-1])
        curr_months = sorted(international_df_c.loc[international_df_c['year'] == curr_year, 'month'].dropna().unique().astype(int))
        curr_month = int(curr_months[-1])

        # Year columns for YTD daily-average comparison
        year_columns = [curr_year]
        for y in [curr_year - 1, curr_year - 2]:
            if y in available_years:
                year_columns.append(y)
        if BASELINE_YEAR in available_years and BASELINE_YEAR not in year_columns:
            year_columns.append(BASELINE_YEAR)

        # Monthly trend chart
        monthly_chart = _build_intl_monthly_chart(international_df)
        if monthly_chart is not None:
            st.plotly_chart(monthly_chart, use_container_width=True, key="intl_monthly_chart")

        summary_df, row_styles, meta = build_ppt_summary(
            international_df_c,
            target_year=curr_year,
            target_month=curr_month,
            year_columns=year_columns,
        )

        if summary_df is not None:
            st.markdown(
                f"**Visitor Arrivals Summary (Daily Average)** — {meta['period_label']}"
            )
            render_ppt_summary_html(summary_df, row_styles)

            st.caption(
                "Source: HKTB PartnerNet (COR Arrivals). "
                "¹ ASEAN Others = Malaysia + Vietnam. "
                "² G7 Others = Canada, France, Germany."
            )
        else:
            st.info("Not enough data to build the summary for the current year.")
    else:
        st.info(
            "International visitor data not yet available. "
            "Click **Refresh Data** above if the CSV was recently updated, "
            "or wait for the monthly GitHub Actions job."
        )
        st.caption(f"⚠️ {international_fetch_time}")

# ===== OUTBOUND =====
st.markdown("---")
st.subheader("🛫 Outbound HK Resident Departures")

outbound_2018 = [(OUTBOUND_2018[1]+OUTBOUND_2018[2])/2]+[OUTBOUND_2018[m] for m in range(3,13)]
outbound_s = {'2018': outbound_2018}
for yr in DISPLAY_YEARS:
    outbound_s[str(yr)] = get_series(monthly_out, yr)

# Outbound YoY table rows (use calc_yoy for consistency with inbound)
gr_rows = []
for yr in DISPLAY_YEARS[-2:]:
    gr_rows.append([f'<b>{yr} vs {yr-1}</b>'] + calc_yoy(monthly_out, yr, yr-1))

# Outbound recovery vs 2018
out_rec_rows = []
for yr in DISPLAY_YEARS[-2:]:
    out_rec_rows.append([f'<b>{yr} vs 2018</b>'] + calc_recovery(monthly_out, OUTBOUND_2018, yr))

# Outbound YTD rows
ytd_out_rows = []
ytd_out_rows.append(["<b>HK Residents</b>"] + [
    _ytd_growth(monthly_out, yr, yr-1, ytd_through_month)
    for yr in DISPLAY_YEARS
])

st.plotly_chart(
    make_combined_figure(
        "Daily HK Resident Departures by Month",
        outbound_s,
        y_min=0, y_max=500000
    ),
    use_container_width=True
)

# Tables summary — standalone full-width figure with all three tables stacked
st.plotly_chart(
    make_combined_figure(
        "Outbound YoY, Recovery & YTD Summary",
        table1_rows=gr_rows,
        table1_header=['YoY Growth Rate'] + months_h + ['FY'],
        table2_rows=out_rec_rows,
        table2_header=['Recovery Rate vs 2018'] + months_h + ['FY'],
        table3_rows=ytd_out_rows,
        table3_header=ytd_in_header,
        table3_is_yoy=True,
        extra_height=30,
    ),
    use_container_width=True
)
st.caption("Source: Immigration Department.")

# ===== HOLIDAY ANALYSIS =====
st.markdown("---")
st.subheader("✨ Holiday Period Analysis")

col_cal, col_dir = st.columns(2)
with col_cal:
    holiday_context = st.radio(
        "Holiday Calendar",
        ['Mainland', 'HK'],
        horizontal=True,
        help="Mainland = CN public holiday schedule; HK = HK public holiday schedule. Select which region's holiday calendar to use for period windows.",
    )
with col_dir:
    # --- Flow direction (IB/OB) with context-aware defaults ---
    default_dir = 'Inbound' if holiday_context == 'Mainland' else 'Outbound'
    if 'holiday_direction' not in st.session_state:
        st.session_state.holiday_direction = default_dir
    # Reset direction to default when context changes
    prev_ctx = st.session_state.get('_prev_holiday_ctx', '')
    if prev_ctx and prev_ctx != holiday_context:
        st.session_state.holiday_direction = default_dir
    st.session_state._prev_holiday_ctx = holiday_context

    flow_direction = st.radio(
        "Flow Direction (IB / OB)",
        ['Inbound', 'Outbound'],
        index=0 if st.session_state.holiday_direction == 'Inbound' else 1,
        horizontal=True,
        help="Inbound = arrivals into HK; Outbound = departures from HK. Defaults to Inbound for Mainland calendar, Outbound for HK calendar.",
        key='holiday_dir_radio',
    )
    st.session_state.holiday_direction = flow_direction
    direction = flow_direction.lower()  # 'inbound' / 'outbound'

holiday_region = _resolve_region(holiday_context)
holiday_keys = list_holidays_for_context(holiday_context)
selected_holiday_key = st.selectbox(
    "Select Holiday",
    holiday_keys,
    format_func=lambda k: HOLIDAY_DISPLAY.get(k, k),
)
selected_holiday_label = HOLIDAY_DISPLAY.get(selected_holiday_key, selected_holiday_key)

hk_meta = get_hk_holiday_meta(holiday_region, selected_holiday_key) if holiday_region == 'HK' else {}
official_periods = get_holiday_periods(holiday_region, selected_holiday_key, 'Official Days')
extended_periods = get_holiday_periods(holiday_region, selected_holiday_key, 'Extended Leave Days')

st.write("### 🗓️ Holiday Proximity Tracker")
tracker_years = sorted(official_periods.keys())
for yr in tracker_years:
    cfg_off = official_periods.get(yr)
    if not cfg_off:
        continue

    if holiday_region == 'HK':
        meta = hk_meta.get(yr, {})
        st.markdown(f"**Year {yr}**")
        if not meta.get('al_applicable'):
            cal_html = render_mini_calendar_row(
                start_date_str=cfg_off['start'],
                end_date_str=cfg_off['end'],
                official_start_str=cfg_off['start'],
                official_end_str=cfg_off['end'],
            )
        else:
            cfg_ext = extended_periods.get(yr)
            cal_html = render_mini_calendar_row(
                start_date_str=cfg_ext['start'],
                end_date_str=cfg_ext['end'],
                official_start_str=cfg_off['start'],
                official_end_str=cfg_off['end'],
            )
    else:
        st.markdown(f"**Year {yr}**")
        cal_html = render_mini_calendar_row(
            start_date_str=cfg_off['start'],
            end_date_str=cfg_off['end'],
            official_start_str=cfg_off['start'],
            official_end_str=cfg_off['end'],
        )
    st.components.v1.html(cal_html, height=75)

# Add a simple minimalist status legend below the grid rows
st.markdown(
    "<small><span style='color:#3A7976'>■</span> Gazetted Holiday | "
    "<span style='color:#777; background:#F0F2F6; padding:0 3px;'>■</span> Weekend | "
    "<span style='color:#C93B2B; background:#FFF0F0; padding:0 3px; border:1px dashed #F5C2C2'>■</span> Strategic Annual Leave Bridge Day</small>", 
    unsafe_allow_html=True
)

tab_official, tab_extended = st.tabs(["Official View", "Annual Leave View"])

hd_official = get_holiday_data(
    arrivals_df, departures_df, daily_in, daily_out,
    selected_holiday_key, context=holiday_context, variant='Official Days',
    direction=direction,
)
hd_al = None
if holiday_region == 'HK':
    hd_al = get_holiday_data(
        arrivals_df, departures_df, daily_in, daily_out,
        selected_holiday_key, context=holiday_context, variant='Extended Leave Days',
        al_fallback=True, direction=direction,
    )
    if not hd_al or not hd_al.get('avg'):
        hd_al = hd_official

with tab_official:
    render_holiday_variant_charts(
        hd_official, holiday_context, 'Official Days', selected_holiday_label,
        daily_in, daily_out, COLORS, CURRENT_YEAR,
        holiday_key=selected_holiday_key, direction=direction,
    )

with tab_extended:
    if holiday_region == 'CN':
        st.info("Annual Leave view is not applicable for Mainland holidays (state-mandated holiday blocks only).")
    else:
        partial_na = [f"**{yr}**: {m['al_reason']}" for yr, m in sorted(hk_meta.items()) if not m['al_applicable']]
        if partial_na:
            st.warning(
                "**Years using Official window in this view** (no separate AL bridge): "
                + " · ".join(partial_na)
            )
        if hd_al and hd_al.get('avg'):
            render_holiday_variant_charts(
                hd_al, holiday_context, 'Extended Leave Days', selected_holiday_label,
                daily_in, daily_out, COLORS, CURRENT_YEAR,
                holiday_key=selected_holiday_key, direction=direction,
            )
        else:
            st.info("No traffic data available for the selected holiday periods.")

st.caption(f"Source: Immigration Department Open Data | [Gov CSV]({GOV_DATA_URL})")

# ===== INTERNATIONAL VISITORS (BOTTOM) =====
render_international_visitors_section()
