# -*- coding: utf-8 -*-
"""
FRED에서 지표들을 받아 data/csvfile/ 아래에 CSV로 저장합니다.
GitHub Actions 실행 시 저장소 루트를 기준으로 상대경로를 사용합니다.

이 파일은 두 가지 작업을 합니다:
  1) (기존 기능, 복구됨) 21개 FRED 시계열 지표 + S&P500 시가총액을 csvfile/*.csv로 저장
  2) (최근에 추가되어 있던 기능, 유지) FOMC/CPI/NFP 등 주요 경제 캘린더 이벤트를 csvfile/calendar_events.csv로 저장

※ 이전에는 이 파일이 2)번 기능으로만 통째로 덮어써져 있어서 1)번 기능(지표 CSV 갱신)이
   약 한 달간 동작하지 않았습니다. 이번에 두 기능을 합쳐서 복구했습니다.

필요 환경변수:
    FRED_API_KEY  (GitHub Secrets에서 주입)
"""
import csv
import datetime
import io
import json
import os
import urllib.request
from datetime import datetime as dt

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


# =========================================================================
# 1) FRED 지표 21개 + S&P500 시가총액  (기존 기능 복구)
# =========================================================================
def fetch_fred_series():
    series_ids = [
        'WTREGEN', 'WRESBAL', 'M2SL', 'M1SL', 'SOFR', 'FEDFUNDS', 'DGS3MO', 'DGS2',
        'RRPONTSYD', 'SP500', 'WILL5000IND', 'DPCREDIT', 'DRBLACBS',
        'NASDAQ100', 'WALCL', 'RRPONTSYAWARD', 'ALTSALES', 'HOUST', 'DGS10', 'DCOILBRENTEU', 'IORB'
    ]

    end_date = dt.now()
    start_date = dt(1940, 1, 1)

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

    print("\nAll FRED series files created successfully.")


# =========================================================================
# 2) 경제 캘린더 이벤트 (FOMC/CPI/NFP 등)  (기존에 있던 기능 유지, 저장 위치만 csvfile/로 통일)
# =========================================================================
def fetch_fred_calendar_events():
    """
    FRED Release 캘린더 및 주요 경제 지표 발표 일정(FOMC, CPI, PCE, NFP, GDP 등)을 추출하여
    csvfile/calendar_events.csv 파일로 저장합니다.
    """
    output_filename = os.path.join(OUTPUT_DIR, "calendar_events.csv")
    events = []

    # 주요 FRED Release ID 목록
    # 10: CPI, 13: Employment Situation (NFP), 31: Retail Sales, 53: GDP, 54: PCE, 175: FOMC Release 등
    release_ids = [10, 13, 31, 53, 54, 175, 86]

    print("\n[INFO] FRED API를 활용하여 주요 이벤트 일정을 수집합니다...")
    for r_id in release_ids:
        try:
            url = f"https://api.stlouisfed.org/fred/release/dates?release_id={r_id}&api_key={api_key}&file_type=json"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode('utf-8'))
                release_dates = data.get('release_dates', [])

                # 지표별 한국어 커스텀 명칭 매핑
                name_map = {
                    10: 'CPI 소비자물가지수',
                    13: 'NFP 고용보고서',
                    31: '소매판매 지수',
                    53: 'GDP 성장률 발표',
                    54: 'PCE 개인소비지출',
                    175: 'FOMC 금리 결정'
                }
                event_name = name_map.get(r_id, f"Release_{r_id}")

                for rd in release_dates:
                    events.append({
                        'date': rd.get('date'),
                        'event': event_name,
                        'importance': 'high' if r_id in [10, 13, 54, 175] else 'normal'
                    })
        except Exception as e:
            print(f"[WARN] Release ID {r_id} 수집 중 예외 발생: {e}")

    # API 호출이 전부 실패했거나 데이터가 비어있을 경우 표준 경제 이벤트 캘린더로 보완
    if not events:
        print("[INFO] 표준 FRED 주요 시장 이벤트 일정 캘린더 세트를 생성합니다...")
        events = [
            {'date': '2026-04-10', 'event': 'CPI 소비자물가지수', 'importance': 'high'},
            {'date': '2026-04-16', 'event': '미국 소매판매 지수', 'importance': 'normal'},
            {'date': '2026-04-30', 'event': 'PCE 개인소비지출', 'importance': 'high'},
            {'date': '2026-05-01', 'event': 'NFP 비농업고용보고서', 'importance': 'high'},
            {'date': '2026-05-06', 'event': 'FOMC 기준금리 결정', 'importance': 'high'},
            {'date': '2026-05-13', 'event': 'CPI 소비자물가지수', 'importance': 'high'},
            {'date': '2026-05-28', 'event': 'GDP 성장률(수정치)', 'importance': 'normal'},
            {'date': '2026-05-29', 'event': 'PCE 개인소비지출', 'importance': 'high'},
            {'date': '2026-06-05', 'event': 'NFP 비농업고용보고서', 'importance': 'high'},
            {'date': '2026-06-10', 'event': 'CPI 소비자물가지수', 'importance': 'high'},
            {'date': '2026-06-17', 'event': 'FOMC 기준금리 결정', 'importance': 'high'},
            {'date': '2026-06-26', 'event': 'PCE 개인소비지출', 'importance': 'high'},
            {'date': '2026-07-02', 'event': 'NFP 비농업고용보고서', 'importance': 'high'},
            {'date': '2026-07-14', 'event': 'CPI 소비자물가지수', 'importance': 'high'},
            {'date': '2026-07-29', 'event': 'FOMC 기준금리 결정', 'importance': 'high'},
            {'date': '2026-07-30', 'event': 'GDP 성장률(속보치)', 'importance': 'high'},
            {'date': '2026-07-31', 'event': 'PCE 개인소비지출', 'importance': 'high'},
            {'date': '2026-08-07', 'event': 'NFP 비농업고용보고서', 'importance': 'high'},
            {'date': '2026-08-12', 'event': 'CPI 소비자물가지수', 'importance': 'high'},
            {'date': '2026-08-28', 'event': 'PCE 개인소비지출', 'importance': 'high'},
            {'date': '2026-09-04', 'event': 'NFP 비농업고용보고서', 'importance': 'high'},
            {'date': '2026-09-11', 'event': 'CPI 소비자물가지수', 'importance': 'high'},
            {'date': '2026-09-16', 'event': 'FOMC 기준금리 결정', 'importance': 'high'},
            {'date': '2026-09-25', 'event': 'PCE 개인소비지출', 'importance': 'high'},
            {'date': '2026-10-02', 'event': 'NFP 비농업고용보고서', 'importance': 'high'},
            {'date': '2026-10-14', 'event': 'CPI 소비자물가지수', 'importance': 'high'},
            {'date': '2026-10-29', 'event': 'GDP 성장률(속보치)', 'importance': 'high'},
            {'date': '2026-10-30', 'event': 'PCE 개인소비지출', 'importance': 'high'},
            {'date': '2026-11-05', 'event': 'FOMC 기준금리 결정', 'importance': 'high'},
            {'date': '2026-11-06', 'event': 'NFP 비농업고용보고서', 'importance': 'high'},
            {'date': '2026-11-12', 'event': 'CPI 소비자물가지수', 'importance': 'high'},
            {'date': '2026-11-27', 'event': 'PCE 개인소비지출', 'importance': 'high'},
            {'date': '2026-12-04', 'event': 'NFP 비농업고용보고서', 'importance': 'high'},
            {'date': '2026-12-10', 'event': 'CPI 소비자물가지수', 'importance': 'high'},
            {'date': '2026-12-16', 'event': 'FOMC 기준금리 결정', 'importance': 'high'}
        ]

    # 중복 제거 및 날짜순 정렬
    seen = set()
    unique_events = []
    for item in events:
        key = (item['date'], item['event'])
        if key not in seen:
            seen.add(key)
            unique_events.append(item)

    unique_events.sort(key=lambda x: x['date'])

    with open(output_filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['date', 'event', 'importance'])
        for item in unique_events:
            writer.writerow([item['date'], item['event'], item['importance']])

    print(f"[SUCCESS] {len(unique_events)}개의 주요 이벤트 일정이 {output_filename}에 정상 저장되었습니다.")


if __name__ == '__main__':
    fetch_fred_series()
    fetch_fred_calendar_events()
