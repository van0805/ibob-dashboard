import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import requests
from io import StringIO
from datetime import timezone, timedelta
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="IBOB Dashboard", page_icon="✈️", layout="wide")

# ===== CONFIG =====
CACHE_TTL = 604800  # 7 days
COLORS = {'2018':'#A6A6A6','2024':'#CF9E9A','2025':'#B9A779','2026':'#3A7976'}
GITHUB_USER = "van0805"
GITHUB_REPO = "ibob-dashboard"
GITHUB_CSV_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/data/daily_passenger_traffic.csv"
GOV_DATA_URL = "https://www.immd.gov.hk/opendata/eng/transport/immigration_clearance/statistics_on_daily_passenger_traffic.csv"

# 2018 hardcoded (not in gov CSV which starts 2021)
INBOUND_2018 = {1:172050,2:188606,3:161133,4:176720,5:159774,6:158059,7:176168,8:190192,9:157285,10:189823,11:199834,12:212460}
OUTBOUND_2018 = {1:236056,2:236056,3:269689,4:252022,5:247218,6:257566,7:250747,8:245103,9:240199,10:249645,11:263862,12:278927}

# Holiday periods - all 2026 holidays with 3+ days
HOLIDAY_PERIODS = {
    'inbound': {
        'CNY (春节)': {
            2024: {'start':'2024-02-10','end':'2024-02-17'},
            2025: {'start':'2025-01-28','end':'2025-02-04'},
            2026: {'start':'2026-02-15','end':'2026-02-23'},
        },
        'Qingming (清明)': {
            2024: {'start':'2024-04-04','end':'2024-04-06'},
            2025: {'start':'2025-04-04','end':'2025-04-06'},
            2026: {'start':'2026-04-04','end':'2026-04-06'},
        },
        'Labour Day (劳动节)': {
            2024: {'start':'2024-05-01','end':'2024-05-05'},
            2025: {'start':'2025-05-01','end':'2025-05-05'},
            2026: {'start':'2026-05-01','end':'2026-05-05'},
        },
        'Dragon Boat (端午)': {
            2024: {'start':'2024-06-08','end':'2024-06-10'},
            2025: {'start':'2025-05-31','end':'2025-06-02'},
            2026: {'start':'2026-06-19','end':'2026-06-21'},
        },
        'Mid-Autumn (中秋)': {
            2024: {'start':'2024-09-15','end':'2024-09-17'},
            2025: {'start':'2025-10-04','end':'2025-10-06'},
            2026: {'start':'2026-09-25','end':'2026-09-27'},
        },
        'National Day (国庆)': {
            2024: {'start':'2024-10-01','end':'2024-10-07'},
            2025: {'start':'2025-10-01','end':'2025-10-08'},
            2026: {'start':'2026-10-01','end':'2026-10-07'},
        },
    },
    'outbound': {
        'CNY (春节)': {
            2024: {'start':'2024-02-10','end':'2024-02-14'},
            2025: {'start':'2025-01-29','end':'2025-01-31'},
            2026: {'start':'2026-02-17','end':'2026-02-19'},
        },
        'Easter (复活节)': {
            2024: {'start':'2024-03-29','end':'2024-04-01'},
            2025: {'start':'2025-04-18','end':'2025-04-21'},
            2026: {'start':'2026-04-03','end':'2026-04-06'},
        },
        'Labour Day (劳动节)': {
            2024: {'start':'2024-05-01','end':'2024-05-05'},
            2025: {'start':'2025-05-01','end':'2025-05-05'},
            2026: {'start':'2026-05-01','end':'2026-05-05'},
        },
        'Dragon Boat (端午)': {
            2024: {'start':'2024-06-08','end':'2024-06-10'},
            2025: {'start':'2025-05-31','end':'2025-06-02'},
            2026: {'start':'2026-06-19','end':'2026-06-21'},
        },
        'National Day (国庆)': {
            2024: {'start':'2024-10-01','end':'2024-10-07'},
            2025: {'start':'2025-10-01','end':'2025-10-08'},
            2026: {'start':'2026-10-01','end':'2026-10-07'},
        },
        'Christmas (圣诞)': {
            2024: {'start':'2024-12-24','end':'2024-12-26'},
            2025: {'start':'2025-12-24','end':'2025-12-26'},
            2026: {'start':'2026-12-25','end':'2026-12-27'},
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


def process_raw(df):
    """Process raw CSV into daily inbound/outbound/cp data."""
    if df is None:
        return None, None, None

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

    # Daily inbound (sum all control points)
    daily_in = arrivals.groupby('Date').agg(
        tourist_arrival=('Mainland Visitors', lambda x: x.sum() + arrivals.loc[x.index, 'Other Visitors'].sum()),
        mainland_arrival=('Mainland Visitors', 'sum')
    ).reset_index()
    # Simpler: recalculate
    arrivals['tourist_total'] = arrivals['Mainland Visitors'] + arrivals['Other Visitors']
    daily_in = arrivals.groupby('Date').agg(
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
            line=dict(color=COLORS.get(yr,'#333'), width=3 if yr=='2026' else 2.5,
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

    # Day labels
    if years_avail:
        latest = years_avail[-1]
        n = len(result['daily'].get(latest, []))
        start_date = pd.to_datetime(periods[int(latest)]['start'])
        result['day_labels'] = [(start_date + pd.Timedelta(days=i)).strftime('%d %b') for i in range(n)]

    return result


# ==================== MAIN APP ====================
st.title("IBOB Traffic Trends")
st.caption("Inbound | Outbound | Holiday Analysis | Data Analytics")

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

# ===== INBOUND =====
st.markdown("---")
st.subheader("🛬 Inbound Tourist Trend: Recovery Rate vs 2018")

inbound_2018 = [(INBOUND_2018[1]+INBOUND_2018[2])/2]+[INBOUND_2018[m] for m in range(3,13)]
inbound_s = {'2018': inbound_2018}
for yr in [2024,2025,2026]:
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
for yr in [2025, 2026]:
    rec_rows.append([f'{yr} Overall'] + calc_recovery(monthly_in, INBOUND_2018, yr))
    rec_rows.append([f'{yr} Mainland'] + calc_recovery(monthly_mainland, MAINLAND_2018, yr))
    rec_rows.append([f'{yr} Intl'] + calc_recovery(monthly_intl, INTL_2018, yr))

months_h = ['Jan&Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
rec_df = pd.DataFrame(rec_rows, columns=['Recovery Rate vs 2018']+months_h+['FY'])
st.dataframe(rec_df, use_container_width=True, hide_index=True)
st.caption("Source: Transportation Dept; Tourism Board; Immigration Dept.")

# ===== OUTBOUND =====
st.markdown("---")
st.subheader("🛫 HK Resident Outbound: Daily Departures")

outbound_2018 = [OUTBOUND_2018[1]]+[OUTBOUND_2018[m] for m in range(3,13)]
outbound_s = {'2018': outbound_2018}
for yr in [2024,2025,2026]:
    outbound_s[str(yr)] = get_series(monthly_out, yr)
st.plotly_chart(make_chart("Daily Departures of Hong Kong Residents", outbound_s, 0, 500000), use_container_width=True)

# Growth rate table (computed dynamically)
st.markdown("**YoY Growth Rate**")
gr_rows = []
for yr in [2025,2026]:
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
        bar_colors = [COLORS.get(yr,'#c8c8c8') if yr=='2026' else '#c8c8c8' for yr in years_avail]
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
                labels = hd['day_labels'][:len(data)] if 'day_labels' in hd else [f"Day {i+1}" for i in range(len(data))]
                fig_daily.add_trace(go.Scatter(x=labels, y=data, name=yr, mode='lines+markers',
                    line=dict(color=COLORS.get(yr,'#999'), width=3 if yr==years_avail[-1] else 2,
                              dash='dash' if yr==years_avail[0] else 'solid', shape='spline'),
                    marker=dict(size=6),
                    hovertemplate=yr+': <b>%{customdata}K</b><extra></extra>',
                    customdata=[int(round(v/1000)) for v in data]))
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
        title=dict(text=f"Avg. Daily {'Mainland Visitors' if dir_key=='inbound' else 'HK Departures'} by Control Point during {selected_holiday}*<br><sup>(Immigration Department Data)          Growth^ (26 vs 25)</sup>",
                   font=dict(size=16)))
    st.plotly_chart(fig_cp, use_container_width=True)

else:
    st.info("No data available for the selected holiday period.")

st.caption(f"Source: Immigration Department Open Data | [Gov CSV]({GOV_DATA_URL})")
