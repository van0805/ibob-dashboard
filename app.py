import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import requests
from io import StringIO
import time
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="IBOB Dashboard", page_icon="✈️", layout="wide")

# ===== CONFIG =====
CACHE_TTL = 604800  # 7 days auto-refresh
COLORS = {'2018':'#A6A6A6','2024':'#CF9E9A','2025':'#B9A779','2026':'#3A7976'}
GOV_DATA_URL = "https://www.immd.gov.hk/opendata/eng/transport/immigration_clearance/statistics_on_daily_passenger_traffic.csv"
# GitHub raw URL for the cached CSV (updated weekly by GitHub Actions)
GITHUB_USER = "van0805"  # ← Change to your GitHub username
GITHUB_REPO = "ibob-dashboard"  # ← Change to your repo name
GITHUB_CSV_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/data/daily_passenger_traffic.csv"

# ===== 2018 HARDCODED =====
INBOUND_2018 = {1:172050,2:188606,3:161133,4:176720,5:159774,6:158059,7:176168,8:190192,9:157285,10:189823,11:199834,12:212460}
OUTBOUND_2018 = {1:236056,2:236056,3:269689,4:252022,5:247218,6:257566,7:250747,8:245103,9:240199,10:249645,11:263862,12:278927}

# ===== HOLIDAY DATA =====
HOLIDAY_DATA = {
    'Labour Day (劳动节)': {
        'avg': {'2024':153000,'2025':184000,'2026':202000},
        'days': {'2024':5,'2025':5,'2026':5},
        'growth': ['+20%','+10%'],
        'day_labels': ['1st May','2nd May','3rd May','4th May','5th May'],
        'daily': {'2024':[175000,170000,155000,135000,130000],'2025':[223000,253000,211000,149000,83000],'2026':[252000,248000,219000,189000,101000]},
        'yoy': ['+13%','-2%','+4%','+27%','+22%'],
        'cp_names': ['Lok Ma Chau Spur Line','Express Rail Link (XRL)','Lo Wu','Shenzhen Bay','Heung Yuen Wai','HK-Zhuhai-Macao Bridge','Lok Ma Chau (皇岗)','Airport','Others'],
        'cp_type': ['rail','rail','rail','car','car','car','car','air','other'],
        'cp_2024': [33000,32000,25000,20000,10000,10000,5000,19000,5000],
        'cp_2025': [37000,40000,30000,28000,12000,12000,9000,15000,5000],
        'cp_2026': [45000,40500,29500,32000,13500,12500,11000,18000,5000],
        'cp_growth': ['+22%','+2%','-2%','+15%','+12%','+3%','+19%','+18%','—'],
    },
    'CNY (春节)': {
        'avg': {'2024':127000,'2025':155000,'2026':180000},
        'days': {'2024':8,'2025':8,'2026':9},
        'growth': ['+22%','+16%'],
        'day_labels': ['Day 1','Day 2','Day 3','Day 4','Day 5','Day 6','Day 7','Day 8','Day 9'],
        'daily': {'2024':[95000,120000,145000,160000,155000,140000,120000,85000],'2025':[110000,145000,175000,195000,190000,170000,145000,100000],'2026':[130000,170000,200000,220000,215000,195000,175000,145000,110000]},
        'yoy': ['+18%','+17%','+14%','+13%','+13%','+15%','+21%','+45%','N/A'],
        'cp_names': ['Lok Ma Chau Spur Line','Express Rail Link (XRL)','Lo Wu','Shenzhen Bay','Heung Yuen Wai','HK-Zhuhai-Macao Bridge','Lok Ma Chau (皇岗)','Airport','Others'],
        'cp_type': ['rail','rail','rail','car','car','car','car','air','other'],
        'cp_2024': [28000,25000,22000,18000,8000,9000,4000,17000,4000],
        'cp_2025': [35000,32000,24000,22000,10000,10000,7000,18000,5000],
        'cp_2026': [42000,38000,25000,27000,13000,12000,9000,20000,5000],
        'cp_growth': ['+20%','+19%','+4%','+23%','+30%','+20%','+29%','+11%','—'],
    },
    'National Day (国庆)': {
        'avg': {'2024':140000,'2025':168000,'2026':None},
        'days': {'2024':7,'2025':8,'2026':7},
        'growth': ['+20%','—'],
        'day_labels': ['Day 1','Day 2','Day 3','Day 4','Day 5','Day 6','Day 7','Day 8'],
        'daily': {'2024':[160000,175000,170000,155000,140000,120000,100000],'2025':[180000,200000,195000,185000,175000,155000,130000,110000],'2026':[]},
        'yoy': [],
        'cp_names': ['Lok Ma Chau Spur Line','Express Rail Link (XRL)','Lo Wu','Shenzhen Bay','Heung Yuen Wai','HK-Zhuhai-Macao Bridge','Lok Ma Chau (皇岗)','Airport','Others'],
        'cp_type': ['rail','rail','rail','car','car','car','car','air','other'],
        'cp_2024': [30000,28000,23000,18000,9000,9000,5000,18000,5000],
        'cp_2025': [38000,35000,26000,24000,11000,11000,8000,16000,5000],
        'cp_2026': [None]*9,
        'cp_growth': ['—']*9,
    },
}

CP_COLORS = {'rail':'#3A7976','car':'#B9A779','air':'#CF9E9A','other':'#A6A6A6'}


@st.cache_data(ttl=CACHE_TTL)
def fetch_gov_data():
    """
    Try to read data in this order:
    1. GitHub repo CSV (updated weekly by Actions)
    2. Direct from gov website (fallback)
    """
    # Method 1: Read from GitHub repo (most reliable)
    try:
        r = requests.get(GITHUB_CSV_URL, timeout=30)
        if r.status_code == 200 and len(r.text) > 5000:
            df = pd.read_csv(StringIO(r.text))
            if len(df) > 100:
                return df, f"{datetime.now().strftime('%Y-%m-%d %H:%M')} (from GitHub cache)"
    except:
        pass

    # Method 2: Direct from gov website (fallback)
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        r = requests.get(GOV_DATA_URL, headers=headers, timeout=60, verify=False)
        if r.status_code == 200 and len(r.text) > 5000:
            df = pd.read_csv(StringIO(r.text))
            if len(df) > 100:
                return df, f"{datetime.now().strftime('%Y-%m-%d %H:%M')} (direct from gov)"
    except Exception as e:
        pass

    return None, "Error: Could not fetch data from GitHub cache or gov website"


def process_monthly(df):
    if df is None: return None
    df.columns = df.columns.str.strip()
    df['Date'] = pd.to_datetime(df.iloc[:,0], format='%d-%m-%Y', errors='coerce')
    df = df.dropna(subset=['Date'])
    df['Year'], df['Month'] = df['Date'].dt.year, df['Date'].dt.month
    arr_cols = [c for c in df.columns if 'Arrival' in c and 'Hong Kong' not in c]
    dep_cols = [c for c in df.columns if 'Departure' in c and 'Hong Kong' in c]
    for c in arr_cols+dep_cols: df[c] = pd.to_numeric(df[c], errors='coerce')
    if arr_cols: df['tourist_arrival'] = df[arr_cols].sum(axis=1)
    if dep_cols: df['hk_departure'] = df[dep_cols].sum(axis=1)
    agg = {'Date':'count'}
    for c in ['tourist_arrival','hk_departure']:
        if c in df.columns: agg[c]='sum'
    m = df.groupby(['Year','Month']).agg(agg).reset_index().rename(columns={'Date':'days'})
    if 'tourist_arrival' in m.columns: m['inbound_daily'] = m['tourist_arrival']/m['days']
    if 'hk_departure' in m.columns: m['outbound_daily'] = m['hk_departure']/m['days']
    return m


def get_series(monthly, year, col):
    if monthly is None or col not in monthly.columns: return [None]*11
    yd = monthly[monthly['Year']==year]
    j = yd[yd['Month']==1][col].values
    f = yd[yd['Month']==2][col].values
    jv, fv = (j[0] if len(j) else None), (f[0] if len(f) else None)
    jf = (jv+fv)/2 if jv and fv else (jv or fv)
    res = [jf]
    for m in range(3,13):
        v = yd[yd['Month']==m][col].values
        res.append(v[0] if len(v) and v[0]>1000 else None)
    return res


def make_monthly_chart(title, series_dict, y_min=0):
    months = ['Jan&Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    fig = go.Figure()
    for yr, data in series_dict.items():
        valid = [d if d and d>1000 else None for d in data]
        fig.add_trace(go.Scatter(x=months, y=valid, name=yr, mode='lines',
            line=dict(color=COLORS[yr], width=3 if yr=='2026' else 2.5,
                      dash='dash' if yr=='2018' else 'solid', shape='spline', smoothing=1.0),
            hovertemplate='%{x}: '+yr+' <b>%{customdata}K</b><extra></extra>',
            customdata=[int(round(v/1000)) if v else 0 for v in valid],
            connectgaps=False))
    fig.update_layout(title=dict(text=title,font=dict(size=14)), yaxis=dict(tickformat=',',range=[y_min,None]),
        legend=dict(orientation='h',yanchor='bottom',y=1.02,xanchor='right',x=1),
        margin=dict(l=60,r=20,t=60,b=40), height=380, template='plotly_white', hovermode='x unified')
    return fig


# ==================== MAIN APP ====================
st.title("✈️ Golden Week Traffic Trends")
st.caption("Inbound | Outbound | Holiday Analysis")

col1, col2 = st.columns([1,5])
with col1:
    if st.button("🔄 Refresh Data", type="primary"):
        st.cache_data.clear()
        st.rerun()

raw_df, fetch_time = fetch_gov_data()
if fetch_time and not fetch_time.startswith("Error"):
    st.caption(f"📅 Last fetched: {fetch_time} | Auto-refresh: weekly | Rows: {len(raw_df) if raw_df is not None else 0}")
elif fetch_time:
    st.warning(f"⚠️ Data fetch issue: {fetch_time}")
    st.info("The government data source may be temporarily unavailable. Dashboard will auto-retry on next refresh.")

monthly = process_monthly(raw_df.copy() if raw_df is not None else None)

# ===== INBOUND =====
st.markdown("---")
st.subheader("🛬 Inbound Tourist Trend: Recovery Rate vs 2018")
inbound_2018 = [(INBOUND_2018[1]+INBOUND_2018[2])/2]+[INBOUND_2018[m] for m in range(3,13)]
inbound_s = {'2018': inbound_2018}
for yr in [2024,2025,2026]: inbound_s[str(yr)] = get_series(monthly,yr,'inbound_daily')
st.plotly_chart(make_monthly_chart("Daily Arrival of All Tourists by Month", inbound_s), use_container_width=True)

st.markdown("**Recovery Rate vs. 2018**")
rec = {'Rate':['2025 Overall','2025 Mainland','2025 Intl','2026 Overall','2026 Mainland','2026 Intl'],
    'Jan&Feb':['79%','76%','90%','94%','93%','96%'],'Mar':['76%','75%','80%','87%','87%','87%'],
    'Apr':['73%','70%','82%','80%','77%','88%'],'May':['82%','82%','83%','90%','92%','86%'],
    'Jun':['73%','72%','77%','—','—','—'],'Jul':['80%','80%','82%','—','—','—'],
    'Aug':['87%','88%','85%','—','—','—'],'Sep':['70%','67%','82%','—','—','—'],
    'Oct':['78%','75%','91%','—','—','—'],'Nov':['70%','66%','83%','—','—','—'],
    'Dec':['71%','66%','87%','—','—','—'],'FY':['77%','74%','84%','—','—','—']}
st.dataframe(pd.DataFrame(rec), use_container_width=True, hide_index=True)

# ===== OUTBOUND =====
st.markdown("---")
st.subheader("🛫 HK Resident Outbound: Daily Departures")
outbound_2018 = [OUTBOUND_2018[1]]+[OUTBOUND_2018[m] for m in range(3,13)]
outbound_s = {'2018': outbound_2018}
for yr in [2024,2025,2026]: outbound_s[str(yr)] = get_series(monthly,yr,'outbound_daily')
st.plotly_chart(make_monthly_chart("Daily Departures of Hong Kong Residents", outbound_s, 200000), use_container_width=True)

gr = {'Rate':['2025 vs 2024','2026 vs 2025'],'Jan&Feb':['+19%','+12%'],'Mar':['+4%','+9%'],
    'Apr':['+33%','+6%'],'May':['+18%','+8%'],'Jun':['+5%','—'],'Jul':['+10%','—'],
    'Aug':['+10%','—'],'Sep':['+5%','—'],'Oct':['+11%','—'],'Nov':['+12%','—'],'Dec':['+11%','—']}
st.dataframe(pd.DataFrame(gr), use_container_width=True, hide_index=True)

# ===== HOLIDAY ANALYSIS =====
st.markdown("---")
st.subheader("🎌 Holiday Period Analysis")
selected = st.selectbox("Select Holiday", list(HOLIDAY_DATA.keys()), index=0)
hd = HOLIDAY_DATA[selected]

# --- Bar + Daily side by side ---
col_bar, col_line = st.columns([1, 1.3])

with col_bar:
    st.markdown(f"**Average Daily Arrival** of Mainland Visitors during {selected}")
    years_avail = [yr for yr in ['2024','2025','2026'] if hd['avg'].get(yr)]
    bar_vals = [hd['avg'][yr] for yr in years_avail]
    bar_colors = [COLORS[yr] if yr=='2026' else '#c8c8c8' for yr in years_avail]
    bar_labels = [f"{yr}<br>{hd['days'][yr]} days" for yr in years_avail]

    fig_bar = go.Figure(go.Bar(
        x=bar_labels, y=bar_vals, marker_color=bar_colors,
        text=[f"<b>{int(v/1000)}K</b>" for v in bar_vals], textposition='outside',
        hovertemplate='%{x}: %{y:,.0f}<extra></extra>'
    ))
    # Add growth annotations
    for i, g in enumerate(hd['growth']):
        if g != '—' and i+1 < len(bar_vals):
            fig_bar.add_annotation(x=(i+i+1)/2, y=(bar_vals[i]+bar_vals[i+1])/2,
                text=f"<b>{g}</b>", showarrow=False,
                font=dict(size=13, color='#3A7976' if i==1 else '#555'),
                bgcolor='#3A7976' if i==1 else '#fff',
                bordercolor='#3A7976' if i==1 else '#555',
                borderwidth=1.5, borderpad=4,
                font_color='#fff' if i==1 else '#333')
    fig_bar.update_layout(yaxis=dict(visible=False), showlegend=False,
        margin=dict(l=20,r=20,t=30,b=40), height=380, template='plotly_white')
    st.plotly_chart(fig_bar, use_container_width=True)

with col_line:
    st.markdown(f"**Daily Arrival #** by day during {selected}")
    fig_daily = go.Figure()
    for yr in ['2024','2025','2026']:
        data = hd['daily'].get(yr, [])
        if data:
            fig_daily.add_trace(go.Scatter(
                x=hd['day_labels'][:len(data)], y=data, name=yr, mode='lines+markers',
                line=dict(color=COLORS[yr], width=3 if yr=='2026' else 2,
                          dash='dash' if yr=='2024' else 'solid', shape='spline'),
                marker=dict(size=6),
                hovertemplate=yr+': <b>%{customdata}K</b><extra></extra>',
                customdata=[int(round(v/1000)) for v in data]))
    # Add vertical reference lines
    for i, lbl in enumerate(hd['day_labels'][:max(len(hd['daily'].get(yr,[])) for yr in ['2024','2025','2026'])]):
        fig_daily.add_vline(x=i, line_width=1, line_dash="dot", line_color="#e0e0e0")
    fig_daily.update_layout(yaxis=dict(tickformat=','), showlegend=True,
        legend=dict(orientation='h',yanchor='bottom',y=1.02),
        margin=dict(l=50,r=20,t=30,b=40), height=380, template='plotly_white')
    st.plotly_chart(fig_daily, use_container_width=True)

# --- Control Point Chart ---
st.markdown(f"**Avg. Daily Mainland Visitors by Control Point** during {selected}")
fig_cp = go.Figure()
cp_cats = ['2024','2025'] + (['2026'] if hd['cp_2026'][0] is not None else [])
for i, name in enumerate(hd['cp_names']):
    pts = [hd['cp_2024'][i], hd['cp_2025'][i]]
    if hd['cp_2026'][i] is not None: pts.append(hd['cp_2026'][i])
    cp_type = hd['cp_type'][i]
    fig_cp.add_trace(go.Scatter(
        x=cp_cats, y=pts, name=f"{name} ({hd['cp_growth'][i]})", mode='lines+markers',
        line=dict(color=CP_COLORS[cp_type], width=2.5 if i<2 else 2),
        marker=dict(size=7)))
fig_cp.update_layout(yaxis=dict(tickformat=','),
    legend=dict(x=1.02, y=1, font=dict(size=10)),
    margin=dict(l=60,r=200,t=40,b=40), height=420, template='plotly_white')
st.plotly_chart(fig_cp, use_container_width=True)

st.caption("Source: Tourism Board; Immigration Department. *Based on mainland China public holidays.")
st.markdown("---")
st.caption(f"Built for SHKP Data Analytics | [Gov Data Source]({GOV_DATA_URL})")
