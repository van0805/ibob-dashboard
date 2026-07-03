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
GITHUB_INTL_CSV_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/data/international_visitors.csv"
LOCAL_INTL_CSV = Path(__file__).resolve().parent / "data" / "international_visitors.csv"
GOV_DATA_URL = "https://www.immd.gov.hk/opendata/eng/transport/immigration_clearance/statistics_on_daily_passenger_traffic.csv"
BASELINE_YEAR = 2018

INTL_MARKETS = [
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
    ("", "Middle East³", ["Middle East"]),
    ("", "the Others⁴", "others4"),
    ("", "Total", "grand_total"),
]

_ASEAN_MARKETS = {m for m, g in MARKET_GROUP_MAP.items() if g == "ASEAN"}
_G7_MARKETS = {m for m, g in MARKET_GROUP_MAP.items() if g == "G7"}
_PPT_LISTED_MARKETS = (
    {"Taiwan", "South Korea", "Macau SAR", "Australia", "Middle East"}
    | _ASEAN_MARKETS | _G7_MARKETS
)

# 2018 hardcoded (not in gov CSV which starts 2021)
INBOUND_2018 = {1:172050,2:188606,3:161133,4:176720,5:159774,6:158059,7:176168,8:190192,9:157285,10:189823,11:199834,12:212460}
OUTBOUND_2018 = {1:236056,2:236056,3:269689,4:252022,5:247218,6:257566,7:250747,8:245103,9:240199,10:249645,11:263862,12:278927}

# Holiday periods - all 2026 holidays with 3+ days
# For CNY: 'lunar_offset' = offset from 初一 (0=初一, -1=除夕, 1=初二, etc.)
# This aligns the x-axis across years by lunar date
# Note: offset -1 is always 除夕 (may be 廿九 or 三十 depending on year)
# offset -2 is "除夕前一天" (廿八 if no 三十, or 廿九 if 三十 exists)
_LUNAR_LABELS = {-3:'廿七', -2:'廿八', -1:'除夕', 0:'初一', 1:'初二', 2:'初三', 3:'初四', 4:'初五', 5:'初六', 6:'初七', 7:'初八', 8:'初九', 9:'初十'}

HOLIDAY_PERIODS = {
    'inbound': {
        'CNY (春节)': {
            2024: {'start':'2024-02-10','end':'2024-02-17', 'note':'8d  Feb 10 (Sat, 初一) – Feb 17 (Sat, 初八)', 'lunar_offset': 0},
            2025: {'start':'2025-01-28','end':'2025-02-04', 'note':'8d  Jan 28 (Tue, 除夕) – Feb 4 (Tue, 初七)', 'lunar_offset': -1},
            2026: {'start':'2026-02-15','end':'2026-02-23', 'note':'9d  Feb 15 (Sun, 廿八) – Feb 23 (Mon, 初七)', 'lunar_offset': -2},
        },
        'Qingming (清明)': {
            2024: {'start':'2024-04-04','end':'2024-04-06', 'note':'3d  Apr 4 (Thu) – Apr 6 (Sat)'},
            2025: {'start':'2025-04-04','end':'2025-04-06', 'note':'3d  Apr 4 (Fri) – Apr 6 (Sun)'},
            2026: {'start':'2026-04-04','end':'2026-04-06', 'note':'3d  Apr 4 (Sat) – Apr 6 (Mon)'},
        },
        'Labour Day (劳动节)': {
            2024: {'start':'2024-05-01','end':'2024-05-05', 'note':'5d  May 1 (Wed) – May 5 (Sun)'},
            2025: {'start':'2025-05-01','end':'2025-05-05', 'note':'5d  May 1 (Thu) – May 5 (Mon)'},
            2026: {'start':'2026-05-01','end':'2026-05-05', 'note':'5d  May 1 (Fri) – May 5 (Tue)'},
        },
        'Dragon Boat (端午)': {
            2024: {'start':'2024-06-08','end':'2024-06-10', 'note':'3d  Jun 8 (Sat) – Jun 10 (Mon)'},
            2025: {'start':'2025-05-31','end':'2025-06-02', 'note':'3d  May 31 (Sat) – Jun 2 (Mon)'},
            2026: {'start':'2026-06-19','end':'2026-06-21', 'note':'3d  Jun 19 (Fri) – Jun 21 (Sun)'},
        },
        'Mid-Autumn (中秋)': {
            2024: {'start':'2024-09-15','end':'2024-09-17', 'note':'3d  Sep 15 (Sun) – Sep 17 (Tue)'},
            2025: {'start':'2025-10-04','end':'2025-10-06', 'note':'3d  Oct 4 (Sat) – Oct 6 (Mon), merged with National Day'},
            2026: {'start':'2026-09-25','end':'2026-09-27', 'note':'3d  Sep 25 (Fri) – Sep 27 (Sun)'},
        },
        'National Day (国庆)': {
            2024: {'start':'2024-10-01','end':'2024-10-07', 'note':'7d  Oct 1 (Tue) – Oct 7 (Mon)'},
            2025: {'start':'2025-10-01','end':'2025-10-08', 'note':'8d  Oct 1 (Wed) – Oct 8 (Wed), merged with Mid-Autumn'},
            2026: {'start':'2026-10-01','end':'2026-10-07', 'note':'7d  Oct 1 (Thu) – Oct 7 (Wed)'},
        },
    },
    'outbound': {
        'CNY (春节)': {
            2024: {'start':'2024-02-10','end':'2024-02-17', 'note':'8d  Feb 10 (Sat, 初一) – Feb 17 (Sat, 初八)', 'lunar_offset': 0},
            2025: {'start':'2025-01-28','end':'2025-02-04', 'note':'8d  Jan 28 (Tue, 除夕) – Feb 4 (Tue, 初七)', 'lunar_offset': -1},
            2026: {'start':'2026-02-15','end':'2026-02-23', 'note':'9d  Feb 15 (Sun, 廿八) – Feb 23 (Mon, 初七)', 'lunar_offset': -2},
            2027: {'start':'2027-02-06','end':'2027-02-09', 'note':'4d  Feb 6 (Sat, 初一) – Feb 9 (Tue, 初四 sub for Day 2 Sun)', 'lunar_offset': 0},
        },
        'Easter (复活节)': {
            2024: {'start':'2024-03-29','end':'2024-04-01', 'note':'4d  Mar 29 (Fri) – Apr 1 (Mon)'},
            2025: {'start':'2025-04-18','end':'2025-04-21', 'note':'4d  Apr 18 (Fri) – Apr 21 (Mon)'},
            2026: {'start':'2026-04-03','end':'2026-04-07', 'note':'5d  Apr 3 (Fri) – Apr 7 (Tue), Easter+Ching Ming overlap'},
            2027: {'start':'2027-03-26','end':'2027-03-29', 'note':'4d  Mar 26 (Fri, Good Fri) – Mar 29 (Mon, Easter Mon)'},
        },
        'Labour Day (劳动节)': {
            2024: {'start':'2024-05-01','end':'2024-05-01', 'note':'1d  May 1 (Wed) only — no bridge (Wed is 2 workdays from Sat)'},
            2025: {'start':'2025-05-01','end':'2025-05-04', 'note':'4d  May 1 (Thu) – May 4 (Sun), bridge Fri + weekend'},
            2026: {'start':'2026-05-01','end':'2026-05-03', 'note':'3d  May 1 (Fri) – May 3 (Sun)'},
            2027: {'start':'2027-05-01','end':'2027-05-01', 'note':'1d  May 1 (Sat) on weekend'},
        },
        'Dragon Boat (端午)': {
            2024: {'start':'2024-06-08','end':'2024-06-10', 'note':'3d  Jun 8 (Sat) – Jun 10 (Mon)'},
            2025: {'start':'2025-05-31','end':'2025-06-01', 'note':'2d  May 31 (Sat) – Jun 1 (Sun), Tuen Ng on Sat'},
            2026: {'start':'2026-06-19','end':'2026-06-21', 'note':'3d  Jun 19 (Fri) – Jun 21 (Sun)'},
            2027: {'start':'2027-06-09','end':'2027-06-09', 'note':'1d  Jun 9 (Wed) only — no bridge (Wed is 2 workdays from Sat)'},
        },
        'National Day (国庆)': {
            2024: {'start':'2024-09-28','end':'2024-10-01', 'note':'4d  Sep 28 (Sat) – Oct 1 (Tue), bridge Mon + prior Sat-Sun'},
            2025: {'start':'2025-10-01','end':'2025-10-01', 'note':'1d  Oct 1 (Wed) only — no bridge (Wed is 2 workdays from Sat)'},
            2026: {'start':'2026-10-01','end':'2026-10-04', 'note':'4d  Oct 1 (Thu) – Oct 4 (Sun), bridge Fri + weekend'},
            2027: {'start':'2027-10-01','end':'2027-10-03', 'note':'3d  Oct 1 (Fri) – Oct 3 (Sun), Fri is start of weekend'},
        },
        'Christmas (圣诞)': {
            2024: {'start':'2024-12-25','end':'2024-12-29', 'note':'5d  Dec 25 (Wed) – Dec 29 (Sun), bridge Fri + weekend'},
            2025: {'start':'2025-12-25','end':'2025-12-28', 'note':'4d  Dec 25 (Thu) – Dec 28 (Sun)'},
            2026: {'start':'2026-12-25','end':'2026-12-27', 'note':'3d  Dec 25 (Fri) – Dec 27 (Sun)'},
            2027: {'start':'2027-12-25','end':'2027-12-27', 'note':'3d  Dec 25 (Sat) – Dec 27 (Mon, sub for Dec 26 Sun)'},
        },
    },
}

CP_COLORS = {'rail':'#3A7976','car':'#B9A779','air':'#CF9E9A','other':'#A6A6A6'}
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


def fetch_international_data():
    """Fetch international visitor CSV from GitHub cache, then local file."""
    errors = []
    for label, source, is_url in (
        ("GitHub cache", GITHUB_INTL_CSV_URL, True),
        ("local file", LOCAL_INTL_CSV, False),
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


def _intl_year_totals(df, year, months=None):
    """Sum monthly arrivals by market for a year (optionally limited to months)."""
    yd = df[df['year'] == year].copy()
    if yd.empty:
        return {}
    if months is not None:
        yd = yd[yd['month'].isin(months)]
    totals = {}
    for market in INTL_MARKETS:
        if market not in yd.columns:
            continue
        vals = pd.to_numeric(yd[market], errors='coerce')
        if vals.notna().any():
            totals[market] = int(vals.sum())
    return totals


def _intl_row_total(market_totals, markets):
    return sum(market_totals.get(m, 0) for m in markets)


def _intl_others4_total(market_totals):
    return sum(v for m, v in market_totals.items() if m not in _PPT_LISTED_MARKETS)


def _days_in_period(year, months):
    if not months:
        return 0
    return sum(calendar.monthrange(int(year), int(m))[1] for m in months)


def _period_market_totals(df, year, months):
    totals = _intl_year_totals(df, year, months=months)
    return totals, _days_in_period(year, months)


def _period_daily_avg(totals, period_days, markets):
    if not totals or period_days <= 0:
        return None
    if markets == "others4":
        total_val = _intl_others4_total(totals)
    elif isinstance(markets, list):
        total_val = _intl_row_total(totals, markets)
    else:
        return None
    return total_val / period_days


def _intl_baseline_2018(df, markets, months):
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


def build_ppt_summary(df, target_year=None, target_month=None, compare_year_1=None, compare_year_2=None):
    """Build international visitors summary with period daily averages."""
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

    period_range_label = f"Jan–{_month_abbr(target_month)}"
    period_label = f"{period_range_label} {target_year}"
    period_daily_label = f"{period_label} Daily Avg"

    compare_pool = [
        int(y) for y in available_years
        if int(y) < target_year and int(y) != BASELINE_YEAR and int(y) >= 2024
    ]
    if compare_year_1 not in compare_pool:
        compare_year_1 = compare_pool[-1] if compare_pool else None
    compare_pool_2 = [y for y in compare_pool if y != compare_year_1]
    if compare_year_2 not in compare_pool_2:
        compare_year_2 = compare_pool_2[-1] if compare_pool_2 else None

    curr_totals, curr_days = _period_market_totals(df, target_year, target_months)
    comp1_totals, comp1_days = _period_market_totals(df, compare_year_1, target_months) if compare_year_1 else ({}, 0)
    comp2_totals, comp2_days = _period_market_totals(df, compare_year_2, target_months) if compare_year_2 else ({}, 0)

    comp1_daily_label = f"{period_range_label} {compare_year_1} Daily Avg" if compare_year_1 else None
    comp2_daily_label = f"{period_range_label} {compare_year_2} Daily Avg" if compare_year_2 else None
    comp1_vs_label = f"vs {compare_year_1}" if compare_year_1 else None
    comp2_vs_label = f"vs {compare_year_2}" if compare_year_2 else None

    rows = []
    row_styles = []
    for category, label, spec in PPT_SUMMARY_ROWS:
        if spec == "asean_total":
            markets = list(_ASEAN_MARKETS)
        elif spec == "g7_total":
            markets = list(_G7_MARKETS)
        elif spec == "others4":
            curr_val = _period_daily_avg(curr_totals, curr_days, "others4")
            comp1_val = _period_daily_avg(comp1_totals, comp1_days, "others4") if compare_year_1 else None
            comp2_val = _period_daily_avg(comp2_totals, comp2_days, "others4") if compare_year_2 else None
            base_val = _intl_baseline_2018(df, "others4", months=target_months)
            row = {
                "Category": category,
                "Market": label,
                period_daily_label: _fmt_daily_avg(curr_val),
            }
            if compare_year_1:
                row[comp1_daily_label] = _fmt_daily_avg(comp1_val)
                row[comp1_vs_label] = _fmt_pct(_pct_change(curr_val, comp1_val))
            if compare_year_2:
                row[comp2_daily_label] = _fmt_daily_avg(comp2_val)
                row[comp2_vs_label] = _fmt_pct(_pct_change(curr_val, comp2_val))
            row["vs 2018"] = _fmt_pct(_pct_change(curr_val, base_val))
            rows.append(row)
            row_styles.append({"kind": "others"})
            continue
        elif spec == "grand_total":
            markets = INTL_MARKETS
        else:
            markets = spec

        curr_val = _period_daily_avg(curr_totals, curr_days, markets)
        comp1_val = _period_daily_avg(comp1_totals, comp1_days, markets) if compare_year_1 else None
        comp2_val = _period_daily_avg(comp2_totals, comp2_days, markets) if compare_year_2 else None
        base_val = _intl_baseline_2018(df, markets, months=target_months)

        row = {
            "Category": category,
            "Market": label,
            period_daily_label: _fmt_daily_avg(curr_val),
        }
        if compare_year_1:
            row[comp1_daily_label] = _fmt_daily_avg(comp1_val)
            row[comp1_vs_label] = _fmt_pct(_pct_change(curr_val, comp1_val))
        if compare_year_2:
            row[comp2_daily_label] = _fmt_daily_avg(comp2_val)
            row[comp2_vs_label] = _fmt_pct(_pct_change(curr_val, comp2_val))
        row["vs 2018"] = _fmt_pct(_pct_change(curr_val, base_val))
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

    # Merge-look grouping column: show group label once and hide inner borders per block.
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

    columns = ["Category", "Market", period_daily_label]
    if compare_year_1:
        columns += [comp1_daily_label, comp1_vs_label]
    if compare_year_2:
        columns += [comp2_daily_label, comp2_vs_label]
    columns += ["vs 2018"]
    summary_df = pd.DataFrame(rows, columns=columns)
    return summary_df, row_styles, {
        "target_year": target_year,
        "target_month": target_month,
        "compare_year_1": compare_year_1,
        "compare_year_2": compare_year_2,
        "months": target_months,
        "period_label": period_label,
    }


def _month_abbr(month):
    return ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(month)]


def style_ppt_summary(summary_df, row_styles):
    """Apply PPT-style formatting: header, subtotals, green/red percentages."""
    pct_cols = [c for c in summary_df.columns if c.startswith("vs ")]

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
    pct_cols = {c for c in columns if c.startswith("vs ")}

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
.intl-summary-table { width: 100%; border-collapse: collapse; font-size: 15px; }
.intl-summary-table th { background:#B9A779; color:#fff; font-weight:700; text-align:center; padding:6px 8px; border:1px solid #d4d4d4; }
.intl-summary-table td { border:1px solid #d4d4d4; padding:4px 8px; text-align:right; }
.intl-summary-table td.col-category, .intl-summary-table td.col-market { text-align:left; }
.intl-summary-table td.group-child { padding-left:1.25em; }
.intl-summary-table tr.asean-total td.col-market, .intl-summary-table tr.asean-total td.col-main { font-weight:700; border:2px solid #2e5c3e; }
.intl-summary-table tr.g7-total td.col-market, .intl-summary-table tr.g7-total td.col-main { font-weight:700; border:2px solid #8b2942; }
.intl-summary-table tr.grand-total td { font-weight:700; }
</style>
""")
    html.append('<table class="intl-summary-table">')
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

    # Split arrival / departure
    arrivals = df[df['Arrival / Departure'] == 'Arrival'].copy()
    departures = df[df['Arrival / Departure'] == 'Departure'].copy()

    # Daily inbound (sum all control points per day)
    arrivals['tourist_total'] = arrivals['Mainland Visitors'] + arrivals['Other Visitors']
    daily_in = arrivals.groupby('Date', as_index=False).agg(
        tourist_arrival=('tourist_total','sum'),
        mainland_arrival=('Mainland Visitors','sum'),
        intl_arrival=('Other Visitors','sum')
    ).reset_index()
    daily_in['Year'] = daily_in['Date'].dt.year
    daily_in['Month'] = daily_in['Date'].dt.month

    # Daily outbound (HK residents)
    daily_out = departures.groupby('Date').agg(
        hk_departure=('Hong Kong Residents','sum')
    ).reset_index()
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

    result = [jf]
    for m in range(3,13):
        v = yd[yd['Month']==m]['daily_avg'].values
        result.append(v[0] if len(v) else None)
    return result


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


def get_holiday_data(raw_arrivals_df, raw_departures_df, daily_in, daily_out, holiday_name, direction='inbound'):
    """Compute holiday stats dynamically from CSV data.
    direction: 'inbound' = Mainland tourist arrivals, 'outbound' = HK resident departures
    """
    if direction == 'inbound':
        if raw_arrivals_df is None or daily_in is None:
            return None
        daily_df = daily_in
        value_col = 'mainland_arrival'
        cp_df = raw_arrivals_df
        cp_value_col = 'Mainland Visitors'
    else:  # outbound
        if raw_departures_df is None or daily_out is None:
            return None
        daily_df = daily_out
        value_col = 'hk_departure'
        cp_df = raw_departures_df
        cp_value_col = 'Hong Kong Residents'

    periods = HOLIDAY_PERIODS.get(direction, {}).get(holiday_name, {})
    if not periods:
        return None
    result = {'avg':{},'days':{},'daily':{},'cp_data':{}}

    for year, p in periods.items():
        start, end = pd.to_datetime(p['start']), pd.to_datetime(p['end'])

        mask = (daily_df['Date'] >= start) & (daily_df['Date'] <= end)
        subset = daily_df[mask]
        if subset.empty:
            continue

        n_days = len(subset)
        avg = subset[value_col].mean()
        daily_vals = subset[value_col].tolist()

        result['avg'][str(year)] = int(avg)
        result['days'][str(year)] = n_days
        result['daily'][str(year)] = [int(v) for v in daily_vals]

        # Control point breakdown
        cp_mask = (cp_df['Date'] >= start) & (cp_df['Date'] <= end)
        cp_subset = cp_df[cp_mask]
        cp_daily = cp_subset.groupby('Control Point')[cp_value_col].sum() / n_days
        result['cp_data'][str(year)] = cp_daily.to_dict()

    # Compute growth rates
    years_avail = sorted(result['avg'].keys())
    growth = []
    for i in range(len(years_avail)-1):
        y1, y2 = years_avail[i], years_avail[i+1]
        pct = (result['avg'][y2] - result['avg'][y1]) / result['avg'][y1]
        growth.append(f"+{pct:.0%}" if pct >= 0 else f"{pct:.0%}")
    result['growth'] = growth

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
            # Default: Gregorian day labels from the latest year
            latest = years_avail[-1]
            n = len(result['daily'].get(latest, []))
            start_date = pd.to_datetime(periods[int(latest)]['start'])
            result['day_labels'] = [(start_date + pd.Timedelta(days=i)).strftime('%d %b') for i in range(n)]

    return result


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
st.subheader("🛬 Inbound Tourist Trend: Recovery Rate vs 2018")

inbound_2018 = [(INBOUND_2018[1]+INBOUND_2018[2])/2]+[INBOUND_2018[m] for m in range(3,13)]
inbound_s = {'2018': inbound_2018}
for yr in DISPLAY_YEARS:
    inbound_s[str(yr)] = get_series(monthly_in, yr)
st.plotly_chart(make_chart("Daily Arrival of All Tourists by Month", inbound_s, y_max=300000), use_container_width=True)

# Recovery rate table (computed dynamically)
st.markdown("**Recovery Rate vs. 2018**")
# 2018 baseline by type (from Excel - Mainland and Intl)
MAINLAND_2018 = {1:132097,2:156357,3:117796,4:134413,5:122709,6:120557,7:141419,8:154956,9:123129,10:149308,11:153770,12:164596}
INTL_2018 = {k: INBOUND_2018[k]-MAINLAND_2018[k] for k in INBOUND_2018}

# Get monthly mainland and intl series
monthly_mainland = get_monthly(daily_in, 'mainland_arrival') if daily_in is not None else None
monthly_intl = get_monthly(daily_in, 'intl_arrival') if daily_in is not None else None

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

rec_rows = []
for yr in DISPLAY_YEARS[-2:]:  # latest 2 years for recovery comparison
    rec_rows.append([f'{yr} Overall'] + calc_recovery(monthly_in, INBOUND_2018, yr))
    rec_rows.append([f'{yr} Mainland'] + calc_recovery(monthly_mainland, MAINLAND_2018, yr))
    rec_rows.append([f'{yr} Intl'] + calc_recovery(monthly_intl, INTL_2018, yr))

months_h = ['Jan&Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
rec_df = pd.DataFrame(rec_rows, columns=['Recovery Rate vs 2018']+months_h+['FY'])
st.dataframe(rec_df, use_container_width=True, hide_index=True)
st.caption("Source: Transportation Dept; Tourism Board; Immigration Dept.")

def render_international_visitors_section():
    """Render international visitors table at page bottom."""
    st.markdown("---")
    st.subheader("🌏 International Visitor Arrivals")

    intl_df, intl_fetch_time = fetch_international_data()
    if intl_df is not None:
        st.caption(f"📅 {intl_fetch_time} | Rows: {len(intl_df)}")

        intl_years = sorted(pd.to_numeric(intl_df['year'], errors='coerce').dropna().unique().astype(int))
        icol1, icol2, icol3, icol4 = st.columns(4)
        with icol1:
            curr_year = st.selectbox("Current year", intl_years, index=len(intl_years) - 1, key="curr_year")
        curr_months = sorted(pd.to_numeric(intl_df.loc[intl_df['year'] == curr_year, 'month'], errors='coerce').dropna().unique().astype(int))
        with icol2:
            curr_month = st.selectbox("Current month", curr_months, index=len(curr_months) - 1, key="curr_month")

        compare_candidates = [y for y in intl_years if y < curr_year and y != BASELINE_YEAR and y >= 2024]
        with icol3:
            compare_year_1 = st.selectbox(
                "Comparison year 1",
                compare_candidates if compare_candidates else ["—"],
                index=len(compare_candidates) - 1 if compare_candidates else 0,
                key="compare_year_1",
                disabled=not compare_candidates,
            )
        compare_candidates_2 = [y for y in compare_candidates if y != compare_year_1]
        with icol4:
            compare_year_2 = st.selectbox(
                "Comparison year 2",
                compare_candidates_2 if compare_candidates_2 else ["—"],
                index=len(compare_candidates_2) - 1 if compare_candidates_2 else 0,
                key="compare_year_2",
                disabled=not compare_candidates_2,
            )

        summary_df, row_styles, meta = build_ppt_summary(
            intl_df,
            target_year=int(curr_year),
            target_month=int(curr_month),
            compare_year_1=int(compare_year_1) if compare_candidates else None,
            compare_year_2=int(compare_year_2) if compare_candidates_2 else None,
        )

        if summary_df is not None:
            month_note = f"{len(meta['months'])} months" if len(meta['months']) < 12 else "full year"
            st.markdown(
                f"**Visitor Arrivals Summary (Daily Average)** — {meta['period_label']} ({month_note})"
            )
            render_ppt_summary_html(summary_df, row_styles)
            st.caption(
                "Source: HKTB PartnerNet (COR Arrivals). "
                "¹ ASEAN Others = Malaysia + Vietnam. "
                "² G7 Others = Canada, France, Germany. "
                "⁴ Remaining markets (e.g. India, Russia). "
                "vs 2018 uses full-year 2018 rows in international_visitors.csv (from Book export)."
            )
        else:
            st.info("Not enough data to build the summary for the selected year.")
    else:
        st.info(
            "International visitor data not yet available. "
            "Click **Refresh Data** above if the CSV was recently updated, "
            "or wait for the monthly GitHub Actions job."
        )
        st.caption(f"⚠️ {intl_fetch_time}")

# ===== OUTBOUND =====
st.markdown("---")
st.subheader("🛫 HK Resident Outbound: Daily Departures")

outbound_2018 = [(OUTBOUND_2018[1]+OUTBOUND_2018[2])/2]+[OUTBOUND_2018[m] for m in range(3,13)]
outbound_s = {'2018': outbound_2018}
for yr in DISPLAY_YEARS:
    outbound_s[str(yr)] = get_series(monthly_out, yr)
st.plotly_chart(make_chart("Daily Departures of Hong Kong Residents", outbound_s, 0, 500000), use_container_width=True)

# Growth rate table (computed dynamically)
st.markdown("**YoY Growth Rate**")
gr_rows = []
for yr in DISPLAY_YEARS[-2:]:  # latest 2 years for YoY growth
    prev_s = outbound_s[str(yr-1)]
    curr_s = outbound_s[str(yr)]
    rates = []
    for i in range(11):
        if curr_s[i] and prev_s[i] and prev_s[i] > 0:
            pct = (curr_s[i] - prev_s[i]) / prev_s[i]
            rates.append(f"{pct:+.0%}")
        else:
            rates.append("—")
    gr_rows.append([f'{yr} vs {yr-1}'] + rates)
gr_df = pd.DataFrame(gr_rows, columns=['Growth Rate']+months_h)
st.dataframe(gr_df, use_container_width=True, hide_index=True)
st.caption("Source: Immigration Department.")

# ===== HOLIDAY ANALYSIS =====
st.markdown("---")
st.subheader("✨ Holiday Period Analysis")

# Direction filter
direction = st.radio("Select Direction", ['Inbound (Mainland Tourist Arrival)', 'Outbound (HK Resident Departure)'], horizontal=True)
dir_key = 'inbound' if 'Inbound' in direction else 'outbound'

# Holiday selector (changes based on direction)
holiday_options = list(HOLIDAY_PERIODS.get(dir_key, {}).keys())
selected_holiday = st.selectbox("Select Holiday", holiday_options, index=0)

# Show holiday duration notes per year
holiday_periods_for_selected = HOLIDAY_PERIODS.get(dir_key, {}).get(selected_holiday, {})
notes_parts = []
for yr in sorted(holiday_periods_for_selected.keys()):
    note = holiday_periods_for_selected[yr].get('note', '')
    if note:
        notes_parts.append(f"**{yr}**: {note}")
if notes_parts:
    st.caption("📅 " + " · ".join(notes_parts))

hd = get_holiday_data(arrivals_df, departures_df, daily_in, daily_out, selected_holiday, dir_key)

if hd and hd['avg']:
    col_bar, col_line = st.columns([1, 1.3])

    with col_bar:
        if dir_key == 'inbound':
            st.markdown(f"**Average Daily Mainland Arrival** during {selected_holiday}")
        else:
            st.markdown(f"**Average Daily HK Resident Departure** during {selected_holiday}")
        years_avail = sorted(hd['avg'].keys())
        bar_vals = [hd['avg'][yr] for yr in years_avail]
        bar_colors = [COLORS.get(yr,'#c8c8c8') if yr==str(CURRENT_YEAR) else '#c8c8c8' for yr in years_avail]
        bar_labels = [f"{yr}<br>{hd['days'][yr]}d" for yr in years_avail]

        fig_bar = go.Figure(go.Bar(x=bar_labels, y=bar_vals, marker_color=bar_colors,
            text=[f"<b>{int(v/1000)}K</b>" for v in bar_vals], textposition='outside'))
        # Growth annotations
        for i, g in enumerate(hd['growth']):
            fig_bar.add_annotation(x=(i+i+1)/2, y=(bar_vals[i]+bar_vals[i+1])/2,
                text=f"<b>{g}</b>", showarrow=False,
                font=dict(size=12, color='#333'),
                bgcolor='#fff',
                bordercolor='#555',
                borderwidth=1.5, borderpad=4)
        fig_bar.update_layout(yaxis=dict(visible=False), showlegend=False,
            margin=dict(l=20,r=20,t=30,b=40), height=380, template='plotly_white')
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_line:
        if dir_key == 'inbound':
            st.markdown(f"**Daily Mainland Arrival** by day during {selected_holiday}")
        else:
            st.markdown(f"**Daily HK Resident Departure** by day during {selected_holiday}")
        fig_daily = go.Figure()
        for yr in years_avail:
            data = hd['daily'].get(yr, [])
            if data:
                labels = hd['day_labels'][:len(data)] if 'day_labels' in hd else [f"Day {j+1}" for j in range(len(data))]
                fig_daily.add_trace(go.Scatter(x=labels, y=data, name=yr, mode='lines+markers',
                    line=dict(color=COLORS.get(yr,'#999'), width=3 if yr==years_avail[-1] else 2,
                              dash='dash' if yr==years_avail[0] else 'solid', shape='spline'),
                    marker=dict(size=6),
                    hovertemplate=yr+': <b>%{customdata}K</b><extra></extra>',
                    customdata=[int(round(v/1000)) if v is not None else 0 for v in data],
                    connectgaps=False))
        # Vertical reference lines
        max_len = max(len(hd['daily'].get(yr,[])) for yr in years_avail)
        for i in range(max_len):
            fig_daily.add_vline(x=i, line_width=1, line_dash="dot", line_color="#e0e0e0")
        fig_daily.update_layout(yaxis=dict(tickformat=','), showlegend=True,
            legend=dict(orientation='h',yanchor='bottom',y=1.02),
            margin=dict(l=50,r=20,t=30,b=40), height=380, template='plotly_white',
            yaxis_range=[0, None])
        st.plotly_chart(fig_daily, use_container_width=True)

    # Control Point Chart
    top_cps = ['Lok Ma Chau Spur Line','Express Rail Link West Kowloon','Lo Wu',
               'Shenzhen Bay','Heung Yuen Wai','Hong Kong-Zhuhai-Macao Bridge','Lok Ma Chau','Airport']

    cp_years = sorted(hd['cp_data'].keys())  # years that have CP data
    fig_cp = go.Figure()
    cp_x_idx = list(range(len(cp_years)))  # use numeric index [0, 1, 2]
    # Collect annotation data first, then apply anti-overlap
    annotation_items = []
    for cp in top_cps:
        pts = []
        for yr in cp_years:
            val = hd['cp_data'].get(yr, {}).get(cp, 0)
            pts.append(int(val) if val > 500 else None)
        cp_type = CP_TYPE_MAP.get(cp, 'other')
        fig_cp.add_trace(go.Scatter(x=cp_x_idx, y=pts, name=cp, mode='lines+markers', showlegend=False,
            line=dict(color=CP_COLORS[cp_type], width=2.5),
            marker=dict(size=7)))
        # Collect label info
        if len(pts) >= 2 and pts[-1] and pts[-2] and pts[-2] > 0:
            g = (pts[-1]-pts[-2])/pts[-2]
            g_text = f"+{g:.0%}" if g >= 0 else f"{g:.0%}"
            annotation_items.append({'y': pts[-1], 'text': f"{CP_DISPLAY_NAME.get(cp, cp)}  {g_text}", 'color': CP_COLORS[cp_type]})
        elif len(pts) >= 1 and pts[-1]:
            annotation_items.append({'y': pts[-1], 'text': f"{CP_DISPLAY_NAME.get(cp, cp)}", 'color': CP_COLORS[cp_type]})

    # Add "Others" line: sum of all CPs not in top_cps
    others_pts = []
    for yr in cp_years:
        yr_data = hd['cp_data'].get(yr, {})
        others_val = sum(v for k, v in yr_data.items() if k not in top_cps)
        others_pts.append(int(others_val) if others_val > 0 else None)
    fig_cp.add_trace(go.Scatter(x=cp_x_idx, y=others_pts, name='Others', mode='lines+markers', showlegend=False,
        line=dict(color='#A6A6A6', width=1.5, dash='dot'),
        marker=dict(size=5)))
    if others_pts and others_pts[-1]:
        annotation_items.append({'y': others_pts[-1], 'text': 'Others', 'color': '#A6A6A6'})

    # Anti-overlap: sort by y value, ensure minimum gap between labels
    annotation_items.sort(key=lambda a: a['y'], reverse=True)
    min_gap = 2500  # minimum pixel gap between labels (in y-axis units)
    adjusted_y = []
    for i, item in enumerate(annotation_items):
        y = item['y']
        if i > 0 and adjusted_y:
            # Check if too close to previous (above) label
            prev_y = adjusted_y[-1]
            if prev_y - y < min_gap:
                y = prev_y - min_gap
        adjusted_y.append(y)

    # Add annotations with adjusted positions
    for item, adj_y in zip(annotation_items, adjusted_y):
        fig_cp.add_annotation(
            x=cp_x_idx[-1], y=adj_y,
            text=item['text'],
            showarrow=False,
            xanchor='left', xshift=10,
            font=dict(size=14, color=item['color'], family='Arial'))

    fig_cp.update_layout(
        xaxis=dict(tickmode='array', tickvals=cp_x_idx, ticktext=[str(yr) for yr in cp_years],
                   range=[-0.3, len(cp_years)-0.7]),
        yaxis=dict(tickformat=',', range=[0, None]),
        showlegend=False,
        margin=dict(l=60,r=250,t=60,b=40), height=420, template='plotly_white',
        title=dict(text=f"Avg. Daily {'Mainland Visitors' if dir_key=='inbound' else 'HK Departures'} by Control Point during {selected_holiday}*<br><sup>(Immigration Department Data)          Growth^ ({str(CURRENT_YEAR)[-2:]} vs {str(CURRENT_YEAR-1)[-2:]})</sup>",
                   font=dict(size=16)))
    st.plotly_chart(fig_cp, use_container_width=True)

else:
    st.info("No data available for the selected holiday period.")

st.caption(f"Source: Immigration Department Open Data | [Gov CSV]({GOV_DATA_URL})")

# ===== INTERNATIONAL VISITORS (BOTTOM) =====
render_international_visitors_section()
