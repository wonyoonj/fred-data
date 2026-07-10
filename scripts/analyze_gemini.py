# -*- coding: utf-8 -*-
"""
data/csvfile/ 안의 CSV들을 읽어 지표를 계산하고, Gemini AI로 분석 문구를 생성해
data/csvfile/financial_analysis.json 과 data/csvfile/app_data.json 으로 저장합니다.

필요 환경변수:
    GEMINI_API_KEY  (GitHub Secrets에서 주입)
"""
import json
import os
import re
from datetime import datetime, timedelta

import google.generativeai as genai
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "csvfile")

# --- Gemini 설정: 반드시 환경변수에서만 읽는다 (하드코딩 금지) ---
gemini_api_key = os.environ.get("GEMINI_API_KEY")
model = None
if not gemini_api_key:
    print("경고: GEMINI_API_KEY 환경변수가 없어 AI 분석 단계는 건너뜁니다.")
else:
    try:
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
    except Exception as e:
        print(f"Gemini AI 설정 중 오류 발생: {e}")
        model = None


def get_closest_data(df, target_date):
    if df.empty:
        return None
    closest_date = min(df.index, key=lambda date: abs(date - target_date))
    return df.loc[closest_date, 'value']


def calculate_all_metrics():
    indicators = [
        'WTREGEN', 'WALCL', 'RRPONTSYD', 'WRESBAL',
        'MMF2RRP', 'MMF2MARKET', 'MMF2GOVERNMENT', 'MMMFFAQ027S',
        'RRPONTSYAWARD', 'DPCREDIT', 'FEDFUNDS', 'SOFR',
        'DGS3MO', 'DGS2', 'DGS10'
    ]

    data_store = {}
    print("--- 데이터 파일 로드 시작 ---")
    for indicator in indicators:
        try:
            filename = os.path.join(DATA_DIR, f'{indicator}.csv')
            df = pd.read_csv(filename)
            date_col, value_col = df.columns[0], df.columns[1]
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.set_index(date_col)
            df[value_col] = pd.to_numeric(df[value_col], errors='coerce')
            df = df.dropna(subset=[value_col])
            df = df.rename(columns={value_col: 'value'})
            data_store[indicator] = df
            print(f"'{indicator}.csv' 로드 성공")
        except FileNotFoundError:
            print(f"에러: '{indicator}.csv' 파일을 찾을 수 없습니다.")
            return None
        except Exception as e:
            print(f"에러: '{indicator}.csv' 처리 중 오류 - {e}")
            return None
    print("--- 데이터 파일 로드 완료 ---\n")

    results = {}

    base_indicators = ['WTREGEN', 'WALCL', 'RRPONTSYD', 'WRESBAL']
    if all(ind in data_store and not data_store[ind].empty for ind in base_indicators):
        common_latest_date = min(data_store[ind].index[-1] for ind in base_indicators)
        past_date_7d = common_latest_date - timedelta(days=7)

        latest = {ind: get_closest_data(data_store[ind], common_latest_date) for ind in base_indicators}
        past = {ind: get_closest_data(data_store[ind], past_date_7d) for ind in base_indicators}

        if all(v is not None for v in latest.values()) and all(v is not None for v in past.values()):
            tga_diff = latest['WTREGEN'] / 1000 - past['WTREGEN'] / 1000
            walcl_diff = (latest['WALCL'] / 1000) - (past['WALCL'] / 1000)
            rrp_diff = latest['RRPONTSYD'] - past['RRPONTSYD']
            resbal_diff = latest['WRESBAL'] / 1000 - past['WRESBAL'] / 1000
            fed_liquidity_diff = walcl_diff - (tga_diff + 2 * rrp_diff + 2 * resbal_diff)
            fed_dept_diff = rrp_diff + resbal_diff

            results["TGA 잔고 (주 변화량)"] = f"{tga_diff:+.2f} B $/Week"
            results["연준 유동성 (주 변화량)"] = f"{fed_liquidity_diff:+.2f} B $/Week"
            results["연준 역레포 및 지급준비금 부채 (주 변화량)"] = f"{fed_dept_diff:+.2f} B $/Week"

            final_mmf_to_market_diff = None

            if 'MMF2RRP' in data_store and not data_store['MMF2RRP'].empty:
                df_mmf2rrp = data_store['MMF2RRP']
                latest_val = df_mmf2rrp.iloc[-1]['value']
                past_val = get_closest_data(df_mmf2rrp, df_mmf2rrp.index[-1] - timedelta(days=30))
                if latest_val is not None and past_val is not None:
                    mmf_to_fed_diff = ((latest_val - past_val) / 1e9) / 4.0
                    results["MMF -> FED (주 환산 변화량)"] = f"{mmf_to_fed_diff:+.2f} B $/Week"

            if all(k in data_store for k in ('MMF2MARKET', 'MMF2GOVERNMENT', 'MMMFFAQ027S')):
                df_mkt, df_gov, df_asset = data_store['MMF2MARKET'], data_store['MMF2GOVERNMENT'], data_store['MMMFFAQ027S']
                latest_m, past_m = df_mkt.iloc[-1]['value'], get_closest_data(df_mkt, df_mkt.index[-1] - timedelta(days=30))
                latest_g, past_g = df_gov.iloc[-1]['value'], get_closest_data(df_gov, df_gov.index[-1] - timedelta(days=30))
                latest_a, past_a = df_asset.iloc[-1]['value'], get_closest_data(df_asset, df_asset.index[-1] - timedelta(days=30))

                if all(v is not None for v in [latest_m, past_m, latest_g, past_g, latest_a, past_a]):
                    mmf_to_market_combined_30d = ((latest_m - past_m) + (latest_g - past_g)) / 1e9
                    mmf_asset_change_30d = (latest_a - past_a) / 1e9
                    final_mmf_to_market_diff = (mmf_to_market_combined_30d - mmf_asset_change_30d) / 4.0
                    results["MMF -> 시장 (주 환산 변화량)"] = f"{final_mmf_to_market_diff:+.2f} B $/Week"

            if all(v is not None for v in [fed_liquidity_diff, tga_diff, final_mmf_to_market_diff]):
                net_market_flow = fed_liquidity_diff - tga_diff + final_mmf_to_market_diff
                results["시장 Total 유동 공급량 (주 변화량)"] = f"{net_market_flow:+.2f} B $/Week"

    rate_indicators = {
        "역레포 금리": "RRPONTSYAWARD", "연준 할인율": "DPCREDIT",
        "EFFR 금리": "FEDFUNDS", "SOFR 금리": "SOFR",
        "3개월 미 국채금리": "DGS3MO", "2년물 미 국채금리": "DGS2",
        "10년물 미 국채금리": "DGS10"
    }
    for label, code in rate_indicators.items():
        if code in data_store and not data_store[code].empty:
            results[label] = f"{data_store[code].iloc[-1]['value']:.2f} %"

    if '역레포 금리' in results and 'SOFR 금리' in results and 'EFFR 금리' in results:
        sofr_val = float(results['SOFR 금리'].replace(' %', ''))
        effr_val = float(results['EFFR 금리'].replace(' %', ''))
        results["SOFR EFFR 스프레드"] = f"{sofr_val - effr_val:+.2f} %"

    return results


def analyze_with_gemini(metrics_data):
    if not model:
        print("Gemini AI 모델이 설정되지 않아 분석을 건너뜁니다.")
        return

    print("\n--- Gemini AI 경제 분석 시작 ---")
    analysis_prompt_data = json.dumps(metrics_data, ensure_ascii=False, indent=2)

    prompt1 = f"""
    당신은 Ai 전문 경제 분석가입니다. 아래는 미국의 최신 통화 유동성 관련 데이터입니다.
    이 데이터를 바탕으로 현재 미국 시장의 유동성 상황이 돈이 공급되는 상황인지 흡수되는 상황인지를 설명해주고,
    왜 그렇게 생각했는지를 최소 2,3가지 지표 숫자를 근거를 설명해주고(단, 다른 지표는 상관없는데, 연준 관련 유동성 설명을 할꺼면 "연준 유동성"과 "연준 역레포 및 지급준비금 부채" 중 하나만 골라서 언급해줘 둘다 같이 쓰면 헷갈려. 그리고, 미국 정부 TGA 잔고 변화량에 대해서는 꼭 설명해줘.), 설명한 지표가 무엇을 의미하는지도 함께 설명해주세요. (단위 잘 고려해서 설명해줘! 참고로 단위 B $는 Billion Dollar야. 단위 잘 고려해서 말해줘.)
    전체 글자수는 250자 이내로(공백제외) 답변해주세요. 분석 결과는 인사 이후에 두칸 내려서 답변해주세요. 마지막에 결론 글도 작성해주는데, 결론글은 두칸 내려서 답변해줘. <br>을 써서 칸을 내리는 형식으로 바꿔주세요.
    내용중에 중요하고 강조하고 싶은 부분은 html 형식으로 빨간색 글씨로 표현할 수 있게 해줘 작성해줘. (html 방식의 부분은 글자수에 포함 안됨)

    [최신 유동성 데이터]
    {analysis_prompt_data}
    """

    prompt2 = f"""
    당신은 Ai 금융 시장 분석가입니다. 아래는 미국의 최신 주요 금리 데이터입니다.
    나눠서 현재 시장 상황을 아래 2가지 파트로 설명해줘. 각 파트별로 글자수는 200자 이내로(공백제외) 현재 미국 금리 시장의 상황이 긴축을 예상하는지 완화를 예상하는지를 직관적으로 이해하기 쉽게 설명해주고,
    왜 그렇게 생각했는지를 지표 숫자 근거를 바탕으로 직관적으로 이해하기 쉽게 설명해주세요.
    분석1: 연준 할인율, 역레포 금리,EFFR 금리, SOFR 금리 및 스프레드
    분석2 : 3개월 미 국채금리, 2년물 미 국채금리, 10년물 미 국채금리
    분석1 결과는 인사 이후에 두칸 내려서 답변해주세요.
    그리고 분석2 결과글 시작하기 전에 두칸 아래 내려서 답변해주세요. <br>을 써서 칸을 내리는 형식으로 바꿔주세요.
    내용중에 중요하고 강조하고 싶은 부분은 html 형식으로 빨간색 글씨로 표현할 수 있게 해줘 작성해줘. (html 방식의 부분은 글자수에 포함 안됨)

    [최신 금리 데이터]
    {analysis_prompt_data}
    """

    prompt_translate = """
    You are a professional translator specializing in financial and economic content.
    Please translate the following Korean analysis into natural, professional English.
    It is crucial to maintain the original meaning, nuance, and tone.
    Also, preserve all HTML tags exactly as they are, including `<br>` and `<span style='color:red;'>...</span>`.

    [Korean Text to Translate]
    {text_to_translate}
    """

    try:
        response1_ko = model.generate_content(prompt1)
        liquidity_analysis_ko = response1_ko.text

        response2_ko = model.generate_content(prompt2)
        interest_rate_analysis_ko = response2_ko.text

        response1_en = model.generate_content(prompt_translate.format(text_to_translate=liquidity_analysis_ko))
        liquidity_analysis_en = response1_en.text

        response2_en = model.generate_content(prompt_translate.format(text_to_translate=interest_rate_analysis_ko))
        interest_rate_analysis_en = response2_en.text

        final_analysis = {
            "date": datetime.now().strftime('%y-%m-%d'),
            "liquidity_analysis": liquidity_analysis_ko,
            "interest_rate_analysis": interest_rate_analysis_ko,
            "liquidity_analysis_en": liquidity_analysis_en,
            "interest_rate_analysis_en": interest_rate_analysis_en,
        }

        output_filename = os.path.join(DATA_DIR, 'financial_analysis.json')
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(final_analysis, f, ensure_ascii=False, indent=4)
        print(f"\n분석 완료! '{output_filename}' 저장됨.")

    except Exception as e:
        print(f"Gemini AI 분석 중 오류 발생: {e}")


def parse_value(value_str):
    if isinstance(value_str, str):
        numbers = re.findall(r"[-+]?\d*\.\d+|\d+", value_str)
        if numbers:
            return float(numbers[0])
    return None


if __name__ == '__main__':
    calculated_metrics = calculate_all_metrics()

    if calculated_metrics:
        print("\n--- 모든 지표 계산 결과 ---")
        for key, value in calculated_metrics.items():
            print(f"{key}: {value}")

        key_map = {
            "TGA 잔고 (주 변화량)": "tga_weekly_change_billion",
            "연준 유동성 (주 변화량)": "fed_liquidity_weekly_change_billion",
            "연준 역레포 및 지급준비금 부채 (주 변화량)": "fed_debt_weekly_change_billion",
            "MMF -> FED (주 환산 변화량)": "mmf_to_fed_weekly_equiv_change_billion",
            "MMF -> 시장 (주 환산 변화량)": "mmf_to_market_weekly_equiv_change_billion",
            "시장 Total 유동 공급량 (주 변화량)": "total_market_liquidity_weekly_change_billion",
            "역레포 금리": "reverse_repo_rate_percent",
            "연준 할인율": "discount_rate_percent",
            "EFFR 금리": "effr_rate_percent",
            "SOFR 금리": "sofr_rate_percent",
            "SOFR EFFR 스프레드": "sofr_effr_spread_percent",
            "3개월 미 국채금리": "dgs3mo_rate_percent",
            "2년물 미 국채금리": "dgs2_rate_percent",
            "10년물 미 국채금리": "dgs10_rate_percent",
        }

        app_data = {"date": datetime.now().strftime('%Y-%m-%d')}
        for kor_key, eng_key in key_map.items():
            if kor_key in calculated_metrics:
                app_data[eng_key] = parse_value(calculated_metrics[kor_key])

        try:
            app_data_filename = os.path.join(DATA_DIR, 'app_data.json')
            with open(app_data_filename, 'w', encoding='utf-8') as f:
                json.dump(app_data, f, indent=4)
            print(f"app_data.json 저장 완료: {app_data_filename}")
        except Exception as e:
            print(f"app_data.json 저장 중 오류: {e}")

        analyze_with_gemini(calculated_metrics)
    else:
        print("지표 계산에 실패해 분석을 건너뜁니다.")
