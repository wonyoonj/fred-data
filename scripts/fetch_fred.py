# -*- coding: utf-8 -*-
"""
FRED에서 지표들을 받아 data/csvfile/ 아래에 CSV로 저장합니다.
GitHub Actions 실행 시 저장소 루트를 기준으로 상대경로를 사용합니다.

필요 환경변수:
    FRED_API_KEY  (GitHub Secrets에서 주입)
"""
import io
import os
from datetime import datetime

import pandas as pd
from fredapi import Fred

# --- API 키: 반드시 환경변수에서만 읽는다 (하드코딩 금지) ---
api_key = os.environ.get("FRED_API_KEY")
if not api_key:
    raise ValueError("FRED_API_KEY 환경변수가 설정되지 않았습니다. (GitHub Secrets 확인)")

fred = Fred(api_key=api_key)

# --- 저장소 루트 기준 상대경로 ---
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(REPO_ROOT, "csvfile")
os.makedirs(OUTPUT_DIR, exist_ok=True)
print(f"Data will be saved to: {OUTPUT_DIR}")

series_ids = [
    'WTREGEN', 'WRESBAL', 'M2SL', 'M1SL', 'SOFR', 'FEDFUNDS', 'DGS3MO', 'DGS2',
    'RRPONTSYD', 'SP500', 'WILL5000IND', 'DPCREDIT', 'DRBLACBS',
    'NASDAQ100', 'WALCL', 'RRPONTSYAWARD', 'ALTSALES', 'HOUST', 'DGS10', 'DCOILBRENTEU', 'IORB'
]

end_date = datetime.now()
start_date = datetime(1940, 1, 1)

print("\n--- Processing FRED Data ---")
for series_id in series_ids:
    try:
        data = fred.get_series(series_id, start_date, end_date)
        if data.empty:
            print(f"No data for {series_id}")
            continue
        data = data.dropna()
        if data.empty:
            print(f"No valid data points for {series_id} after dropping NaN.")
            continue

        df_individual = data.to_frame(name=series_id)
        df_individual.reset_index(inplace=True)
        df_individual.rename(columns={'index': 'Date'}, inplace=True)

        output_file = os.path.join(OUTPUT_DIR, f"{series_id}.csv")
        df_individual.to_csv(output_file, index=False, encoding='utf-8')
        print(f"Data for {series_id} saved ({len(data)} records)")

    except Exception as e:
        print(f"Error processing {series_id}: {e}")

# --- S&P 500 시가총액 (수동 데이터, 민감정보 아님) ---
print("\n--- Processing S&P 500 Market Cap Data ---")
sp500_mcap_raw_data = """
Date,Value
March 31 2025,47.55T
December 31 2024,49.81T
September 30 2024,48.70T
June 30 2024,45.84T
March 31 2024,44.08T
December 31 2023,40.04T
September 30 2023,35.94T
June 30 2023,37.16T
March 31 2023,34.34T
December 31 2022,32.13T
September 30 2022,30.12T
June 30 2022,31.90T
March 31 2022,38.29T
December 31 2021,40.36T
September 30 2021,36.54T
June 30 2021,36.32T
March 31 2021,33.62T
December 31 2020,31.66T
September 30 2020,27.87T
June 30 2020,25.64T
March 31 2020,21.42T
December 31 2019,26.76T
September 30 2019,24.71T
June 30 2019,24.42T
March 31 2019,23.62T
December 31 2018,21.03T
September 30 2018,24.58T
June 30 2018,23.04T
March 31 2018,22.50T
December 31 2017,22.82T
September 30 2017,21.58T
June 30 2017,20.76T
March 31 2017,20.28T
December 31 2016,19.27T
September 30 2016,18.74T
June 30 2016,18.19T
March 31 2016,17.96T
December 31 2015,17.90T
September 30 2015,16.92T
June 30 2015,18.22T
March 31 2015,18.30T
December 31 2014,18.25T
September 30 2014,17.52T
June 30 2014,17.40T
March 31 2014,16.70T
December 31 2013,16.49T
September 30 2013,14.96T
June 30 2013,14.31T
March 31 2013,13.98T
December 31 2012,12.74T
"""

try:
    df_mcap = pd.read_csv(io.StringIO(sp500_mcap_raw_data), sep=',', engine='python')
    df_mcap['Date'] = pd.to_datetime(df_mcap['Date'])
    df_mcap['Value'] = df_mcap['Value'].str.replace('T', '').astype(float) * 1_000_000_000_000
    df_mcap.rename(columns={'Value': 'SP500_MCAP'}, inplace=True)

    output_file_mcap = os.path.join(OUTPUT_DIR, 'SP500_MCAP.csv')
    df_mcap.to_csv(output_file_mcap, index=False, encoding='utf-8')
    print(f"S&P 500 Market Cap data saved ({len(df_mcap)} records)")

except Exception as e:
    print(f"Error processing S&P 500 Market Cap data: {e}")

print("\nAll FRED files created successfully.")
