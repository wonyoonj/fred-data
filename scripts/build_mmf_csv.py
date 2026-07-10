# -*- coding: utf-8 -*-
"""
data/mmf_flow/ 안의 원본 CSV(mmf_total_data.csv, mmf_bra_tot_m_data.csv)를 읽어
data/csvfile/ 에 정리된 CSV(MMF2MARKET, MMF2GOVERNMENT, MMF2RRP, MMMFFAQ027S)로 저장합니다.
"""
import os

import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(REPO_ROOT, "data", "mmf_flow")
OUTPUT_DIR = os.path.join(REPO_ROOT, "csvfile")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- 1. mmf_total_data.csv -> MMF2MARKET.csv, MMF2GOVERNMENT.csv ---
try:
    mmf_total_df = pd.read_csv(os.path.join(INPUT_DIR, 'mmf_total_data.csv'), skiprows=2)

    expected_columns = [
        'Date', 'Prime', 'Prime Institutional', 'Prime Retail',
        'Government (No Fees & Gates)', 'Government', 'Government (Fees & Gates)',
        'Tax Exempt', 'Tax Exempt Retail', 'Tax Exempt Institutional'
    ]
    mmf_total_df.columns = expected_columns[:len(mmf_total_df.columns)]
    print("mmf_total_data.csv 컬럼:", mmf_total_df.columns.tolist())

    mmf_total_df['Date'] = pd.to_datetime(mmf_total_df['Date'])

    numeric_cols = [
        'Prime', 'Prime Institutional', 'Prime Retail',
        'Government (No Fees & Gates)', 'Government', 'Government (Fees & Gates)'
    ]
    for col in numeric_cols:
        if col in mmf_total_df.columns:
            mmf_total_df[col] = pd.to_numeric(mmf_total_df[col], errors='coerce').fillna(0)
        else:
            print(f"경고: '{col}' 컬럼이 없어 0으로 초기화합니다.")
            mmf_total_df[col] = 0.0

    mmf_total_df['Prime Total'] = (
        mmf_total_df['Prime'] + mmf_total_df['Prime Institutional'] + mmf_total_df['Prime Retail']
    )
    mmf_total_df['Government Total'] = (
        mmf_total_df['Government (No Fees & Gates)'] + mmf_total_df['Government']
        + mmf_total_df['Government (Fees & Gates)']
    )

    mmf2market_df = mmf_total_df[['Date', 'Prime Total']].copy()
    mmf2market_df.to_csv(os.path.join(OUTPUT_DIR, 'MMF2MARKET.csv'), index=False)
    print("MMF2MARKET.csv 생성 완료")

    mmf2government_df = mmf_total_df[['Date', 'Government Total']].copy()
    mmf2government_df.to_csv(os.path.join(OUTPUT_DIR, 'MMF2GOVERNMENT.csv'), index=False)
    print("MMF2GOVERNMENT.csv 생성 완료")

except FileNotFoundError:
    print(f"오류: '{os.path.join(INPUT_DIR, 'mmf_total_data.csv')}' 파일을 찾을 수 없습니다.")
except Exception as e:
    print(f"mmf_total_data.csv 처리 중 오류: {e}")

# --- 2. mmf_bra_tot_m_data.csv -> MMF2RRP.csv, MMMFFAQ027S.csv ---
try:
    mmf_bra_df = pd.read_csv(os.path.join(INPUT_DIR, 'mmf_bra_tot_m_data.csv'), header=3)
    mmf_bra_df.columns = mmf_bra_df.columns.str.strip()
    print("mmf_bra_tot_m_data.csv 컬럼:", mmf_bra_df.columns.tolist())

    mmf_bra_df['date'] = pd.to_datetime(mmf_bra_df['date'])
    mmf_bra_df = mmf_bra_df[mmf_bra_df['date'] >= pd.to_datetime('2013-09-30')]

    target_col = 'MMF-MMF_RP_wFR-M'
    if target_col not in mmf_bra_df.columns:
        raise KeyError(target_col)
    mmf_bra_df[target_col] = pd.to_numeric(mmf_bra_df[target_col], errors='coerce')

    mmf2rrp_df = mmf_bra_df[['date', target_col]].copy()
    mmf2rrp_df.to_csv(os.path.join(OUTPUT_DIR, 'MMF2RRP.csv'), index=False)
    print("MMF2RRP.csv 생성 완료")

    tot_col = 'MMF-MMF_TOT-M'
    if tot_col not in mmf_bra_df.columns:
        raise KeyError(tot_col)
    mmf_bra_df[tot_col] = pd.to_numeric(mmf_bra_df[tot_col], errors='coerce')

    mmf_tot_df = mmf_bra_df[['date', tot_col]].copy()
    mmf_tot_df.to_csv(os.path.join(OUTPUT_DIR, 'MMMFFAQ027S.csv'), index=False)
    print("MMMFFAQ027S.csv 생성 완료")

except FileNotFoundError:
    print(f"오류: '{os.path.join(INPUT_DIR, 'mmf_bra_tot_m_data.csv')}' 파일을 찾을 수 없습니다.")
except KeyError as e:
    print(f"오류: 컬럼 {e}을(를) 찾을 수 없습니다.")
except Exception as e:
    print(f"mmf_bra_tot_m_data.csv 처리 중 오류: {e}")
