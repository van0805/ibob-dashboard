"""
Scraper for IMMD daily passenger traffic data.
Runs via GitHub Actions weekly, saves CSV to data/ folder.
"""
import requests
import pandas as pd
from datetime import datetime
import os
import time

GOV_DATA_URL = "https://www.immd.gov.hk/opendata/eng/transport/immigration_clearance/statistics_on_daily_passenger_traffic.csv"
OUTPUT_PATH = "data/daily_passenger_traffic.csv"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/csv,text/plain,*/*',
    'Accept-Language': 'en-US,en;q=0.9,zh-HK;q=0.8',
    'Referer': 'https://www.immd.gov.hk/eng/facts/passenger-statistics.html',
}


def fetch_and_save():
    print(f"[{datetime.now()}] Fetching IMMD data...")
    
    for attempt in range(5):
        try:
            r = requests.get(GOV_DATA_URL, headers=HEADERS, timeout=120, verify=False)
            print(f"  Attempt {attempt+1}: status={r.status_code}, length={len(r.text)}")
            
            if r.status_code == 200 and len(r.text) > 5000:
                # Validate it's actual CSV
                lines = r.text.strip().split('\n')
                if len(lines) > 100 and ',' in lines[0]:
                    os.makedirs('data', exist_ok=True)
                    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
                        f.write(r.text)
                    
                    # Also save metadata
                    with open('data/last_updated.txt', 'w') as f:
                        f.write(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
                        f.write(f"Rows: {len(lines)-1}\n")
                        f.write(f"Source: {GOV_DATA_URL}\n")
                    
                    print(f"  ✅ Success! Saved {len(lines)-1} rows to {OUTPUT_PATH}")
                    return True
                else:
                    print(f"  ❌ Response doesn't look like valid CSV")
            
        except Exception as e:
            print(f"  ❌ Attempt {attempt+1} failed: {e}")
        
        time.sleep(5)
    
    print("  ⚠️ All attempts failed. Data not updated.")
    return False


if __name__ == '__main__':
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    fetch_and_save()
