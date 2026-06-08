import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import requests
from io import StringIO
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

# Holiday periods (CN mainland holidays)
HOLIDAY_PERIODS = {
    'Labour Day (劳动节)': {
        2024: {'start':'2024-05-01','end':'2024-05-05'},
        2025: {'start':'2025-05-01','end':'2025-05-05'},
        2026: {'start':'2026-05-01','end':'2026-05-05'},
    },
    'CNY (春节)': {
        2024: {'start':'2024-02-10','end':'2024-02-17'},
        2025: {'start':'2025-01-28','end':'2025-02-04'},
        2026: {'start':'2026-02-15','end':'2026-02-23'},
    },
    'National Day (国庆)': {
        2024: {'start':'2024-10-01','end':'2024-10-07'},
        2025: {'start':'2025-10-01','end':'2025-10-08'},
        2026: {'start':'2026-10-01','end':'2026-10-07'},
    },
}

CP_COLORS = {'rail':'#3A7976','car':'#B9A779','air':'#CF9E9A','other':'#A6A6A6'}
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
                    return df, f"{datetime.now().strftime('%Y-%m-%d %H:%M')} ({source})"
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
        mainland_arrival=('Mainland Visitors','sum')
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
    return daily_in, daily_out, arrivals


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
    fig.update_layout(title=dict(text=title,font=dict(size=14)),
        yaxis=dict(tickformat=',', range=[y_min, y_max]),
        legend=dict(orientation='h',yanchor='bottom',y=1.02,xanchor='right',x=1),
        margin=dict(l=60,r=20,t=60,b=40), height=380, template='plotly_white', hovermode='x unified')
    return fig


def get_holiday_data(arrivals_df, daily_in, holiday_name):
    """Compute holiday stats dynamically from CSV data."""
    if arrivals_df is None or daily_in is None:
        return None
    periods = HOLIDAY_PERIODS.get(holiday_name, {})
    result = {'avg':{},'days':{},'daily':{},'cp_data':{}}

    for year, p in periods.items():
        start, end = pd.to_datetime(p['start']), pd.to_datetime(p['end'])

        # Daily mainland arrivals
        mask = (daily_in['Date'] >= start) & (daily_in['Date'] <= end)
        subset = daily_in[mask]
        if subset.empty:
            continue

        n_days = len(subset)
        avg = subset['mainland_arrival'].mean()
        daily_vals = subset['mainland_arrival'].tolist()

        result['avg'][str(year)] = int(avg)
        result['days'][str(year)] = n_days
        result['daily'][str(year)] = [int(v) for v in daily_vals]

        # Control point breakdown
        cp_mask = (arrivals_df['Date'] >= start) & (arrivals_df['Date'] <= end)
        cp_subset = arrivals_df[cp_mask]
        cp_daily = cp_subset.groupby('Control Point')['Mainland Visitors'].sum() / n_days
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
st.title("✈️ Golden Week Traffic Trends")
st.caption("Inbound | Outbound | Holiday Analysis")

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

daily_in, daily_out, arrivals_df = process_raw(raw_df.copy() if raw_df is not None else None)
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
rec_rows = []
for yr in [2025,2026]:
    series = inbound_s[str(yr)]
    rates = []
    for i, val in enumerate(series):
        base = inbound_2018[i] if i == 0 else INBOUND_2018.get(i+2, None)
        # map index: 0=Jan&Feb, 1=Mar(3), 2=Apr(4)...
        month_key = [0,3,4,5,6,7,8,9,10,11,12][i] if i < 11 else None
        if i == 0:
            base_val = (INBOUND_2018[1]+INBOUND_2018[2])/2
        else:
            base_val = INBOUND_2018.get(i+2, None)
        if val and base_val:
            rates.append(f"{val/base_val:.0%}")
        else:
            rates.append("—")
    rec_rows.append([f'{yr} Overall'] + rates)

months_h = ['Jan&Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
rec_df = pd.DataFrame(rec_rows, columns=['Recovery Rate vs 2018']+months_h)
st.dataframe(rec_df, use_container_width=True, hide_index=True)
st.caption("Source: Immigration Department. Recovery rate = daily avg vs 2018 comparable month.")

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
st.subheader("🎌 Holiday Period Analysis")
selected_holiday = st.selectbox("Select Holiday", list(HOLIDAY_PERIODS.keys()), index=0)

hd = get_holiday_data(arrivals_df, daily_in, selected_holiday)

if hd and hd['avg']:
    col_bar, col_line = st.columns([1, 1.3])

    with col_bar:
        st.markdown(f"**Average Daily Mainland Arrival** during {selected_holiday}")
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
                font=dict(size=12, color='#fff' if i==len(hd['growth'])-1 else '#555'),
                bgcolor='#3A7976' if i==len(hd['growth'])-1 else '#fff',
                bordercolor='#3A7976' if i==len(hd['growth'])-1 else '#555',
                borderwidth=1.5, borderpad=4)
        fig_bar.update_layout(yaxis=dict(visible=False), showlegend=False,
            margin=dict(l=20,r=20,t=30,b=40), height=380, template='plotly_white')
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_line:
        st.markdown(f"**Daily Mainland Arrival** by day during {selected_holiday}")
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
            margin=dict(l=50,r=20,t=30,b=40), height=380, template='plotly_white')
        st.plotly_chart(fig_daily, use_container_width=True)

    # Control Point Chart
    st.markdown(f"**Avg. Daily Mainland Visitors by Control Point** during {selected_holiday}")
    # Get top CPs
    top_cps = ['Lok Ma Chau Spur Line','Express Rail Link West Kowloon','Lo Wu',
               'Shenzhen Bay','Heung Yuen Wai','Hong Kong-Zhuhai-Macao Bridge','Lok Ma Chau','Airport']

    fig_cp = go.Figure()
    for cp in top_cps:
        pts = []
        for yr in years_avail:
            val = hd['cp_data'].get(yr, {}).get(cp, 0)
            pts.append(int(val) if val > 500 else None)
        cp_type = CP_TYPE_MAP.get(cp, 'other')
        # Growth label
        if len(pts) >= 2 and pts[-1] and pts[-2] and pts[-2] > 0:
            g = (pts[-1]-pts[-2])/pts[-2]
            label = f"{cp} ({g:+.0%})"
        else:
            label = cp
        fig_cp.add_trace(go.Scatter(x=years_avail, y=pts, name=label, mode='lines+markers',
            line=dict(color=CP_COLORS[cp_type], width=2.5),
            marker=dict(size=7)))
    fig_cp.update_layout(yaxis=dict(tickformat=','),
        legend=dict(x=1.02, y=1, font=dict(size=10)),
        margin=dict(l=60,r=220,t=40,b=40), height=420, template='plotly_white',
        title=dict(text=f"(Immigration Department Data)", font=dict(size=11, color='#888')))
    st.plotly_chart(fig_cp, use_container_width=True)

else:
    st.info("No data available for the selected holiday period.")

st.caption(f"Source: Immigration Department Open Data | [Gov CSV]({GOV_DATA_URL})")
