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
from datetime import datetime, timedelta, timezone

import google.generativeai as genai
import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "csvfile")

# --- 날짜 관련: GitHub Actions 러너는 UTC를 사용하므로, 반드시 KST(한국시간) 기준으로 날짜를 계산한다 ---
# 원인: cron이 UTC 22:15에 실행되도록 되어 있는데(=KST 07:15), datetime.now()는
# 타임존 정보 없이 러너의 로컬 시간(UTC)을 그대로 반환하기 때문에 날짜가 하루 전(UTC 기준)으로 찍힌다.
KST = timezone(timedelta(hours=9))


def now_kst():
    return datetime.now(KST)


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


# =========================================================================
# [신규] Bank Credit (FRED: TOTBKCR) 지표 + Liquidity Index
#   - index.html 의 computeBankCreditMetrics / renderLiquidityIndexGauge 와 동일한 공식입니다.
#   - Liquidity Index = (1 - W) × 기존 점수(시장 Total 유동 공급량 백분위) + W × Bank Credit Score
# =========================================================================
BANK_SCORE_SMOOTH_WEEKS = 13   # index.html 과 동일하게 유지 (1 = 주간값 그대로)
BANK_SCORE_WINDOW_WEEKS = 520  # 최근 10년 롤링 분포 (index.html 과 동일)
BANK_CREDIT_WEIGHT = 0.12  # index.html 의 BANK_CREDIT_WEIGHT 와 반드시 같은 값으로 유지


def bank_score_label(score):
    if score < 20:
        return "강한 신용위축"
    if score < 40:
        return "신용위축"
    if score < 60:
        return "중립"
    if score < 80:
        return "신용확대"
    return "강한 신용확대"


def _near(df, dates):
    idx = df.index.get_indexer(dates, method='nearest')
    return df['value'].to_numpy()[idx]


def compute_bank_credit(data_store):
    """TOTBKCR.csv 로 Bank Credit 지표 계산. 파일이 없거나 실패하면 None."""
    try:
        df = pd.read_csv(os.path.join(DATA_DIR, 'TOTBKCR.csv'))
        df[df.columns[0]] = pd.to_datetime(df[df.columns[0]])
        df = df.set_index(df.columns[0])
        df['value'] = pd.to_numeric(df[df.columns[0]], errors='coerce')
        df = df[['value']].dropna().sort_index()
        df = df[~df.index.duplicated()]
        if len(df) < 30:
            return None
    except Exception as e:
        print(f"Bank Credit(TOTBKCR) 로드 실패 - 건너뜁니다: {e}")
        return None

    v = df['value']
    ratios = (v.diff() / v.shift(1) * 100).dropna()          # Bank Credit Flow Ratio (%)
    sm = ratios.rolling(BANK_SCORE_SMOOTH_WEEKS).mean().dropna()
    arr = sm.to_numpy()
    out = np.full(len(arr), np.nan)
    for k in range(len(arr)):   # 각 시점 기준 '직전 10년' 분포 내 백분위
        lo = max(0, k - BANK_SCORE_WINDOW_WEEKS + 1)
        if k - lo + 1 >= 104:
            out[k] = (arr[lo:k + 1] <= arr[k]).mean() * 100
    scores = pd.Series(out, index=sm.index).dropna()
    if scores.empty:
        return None

    n = len(v)
    return {
        "date": v.index[-1],
        "latest": float(v.iloc[-1]),
        "weekly": float(v.iloc[-1] - v.iloc[-2]),
        "cum4": float(v.iloc[-1] - v.iloc[-5]) if n > 4 else None,
        "cum13": float(v.iloc[-1] - v.iloc[-14]) if n > 13 else None,
        "ratio": float(ratios.iloc[-1]),
        "ratio_smooth": float(sm.iloc[-1]),
        "score": float(scores.iloc[-1]),
        "scores": scores,
    }


def compute_net_market_flow_history(data_store):
    """index.html 의 computeNetMarketFlowHistory() 와 동일한 계산 (WTREGEN 날짜 기준)."""
    d = {k: data_store[k][~data_store[k].index.duplicated()].sort_index() for k in
         ['WTREGEN', 'WALCL', 'RRPONTSYD', 'WRESBAL', 'MMF2MARKET', 'MMF2GOVERNMENT', 'MMMFFAQ027S']}
    t = d['WTREGEN'].index
    t7, t30 = t - pd.Timedelta(days=7), t - pd.Timedelta(days=30)

    tga = (_near(d['WTREGEN'], t) - _near(d['WTREGEN'], t7)) / 1000
    walcl = (_near(d['WALCL'], t) - _near(d['WALCL'], t7)) / 1000
    rrp = _near(d['RRPONTSYD'], t) - _near(d['RRPONTSYD'], t7)
    resbal = (_near(d['WRESBAL'], t) - _near(d['WRESBAL'], t7)) / 1000
    fed = walcl - (tga + 2 * rrp + 2 * resbal)

    mmf_combined = ((_near(d['MMF2MARKET'], t) - _near(d['MMF2MARKET'], t30))
                    + (_near(d['MMF2GOVERNMENT'], t) - _near(d['MMF2GOVERNMENT'], t30))) / 1e9
    mmf_asset = (_near(d['MMMFFAQ027S'], t) - _near(d['MMMFFAQ027S'], t30)) / 1e9
    final_mmf = (mmf_combined - mmf_asset) / 4.0
    return pd.Series(fed - tga + final_mmf, index=t)


def compute_liquidity_index(data_store, bank):
    """(Bank Credit 반영 지수, Bank Credit 제외 지수) 반환."""
    net = compute_net_market_flow_history(data_store).dropna()
    vals = np.sort(net.to_numpy())
    pct = lambda x: int(np.floor(np.searchsorted(vals, x, side='right') / len(vals) * 100 + 0.5))
    latest_t, latest_v = net.index[-1], net.iloc[-1]
    ex_bank = pct(latest_v)
    total = float(ex_bank)
    if bank is not None:
        bs = bank["scores"].asof(latest_t)
        if pd.notna(bs):
            total = (1 - BANK_CREDIT_WEIGHT) * ex_bank + BANK_CREDIT_WEIGHT * float(bs)
    return int(np.floor(total + 0.5)), ex_bank


def add_bank_and_index_metrics(results, data_store):
    """results 딕셔너리에 Bank Credit / Liquidity Index 항목 추가 (실패해도 기존 파이프라인은 계속 진행)."""
    try:
        bank = compute_bank_credit(data_store)
        if bank is not None:
            results["Bank Credit 현재 잔액"] = f"{bank['latest']:.2f} B $"
            results["Bank Credit 최신 주간 변화량"] = f"{bank['weekly']:+.2f} B $/Week"
            if bank["cum4"] is not None:
                results["Bank Credit 최근 4주 누적 변화량"] = f"{bank['cum4']:+.2f} B $"
            if bank["cum13"] is not None:
                results["Bank Credit 최근 13주 누적 변화량"] = f"{bank['cum13']:+.2f} B $"
            results["Bank Credit Flow Ratio"] = f"{bank['ratio']:+.4f} %"
            results["Bank Credit Flow Ratio (13주 평균, 점수 산정 기준)"] = f"{bank['ratio_smooth']:+.4f} %"
            results["Bank Credit Score"] = f"{bank['score']:.0f} / 100 ({bank_score_label(bank['score'])})"
            results["Bank Credit 데이터 기준일"] = bank["date"].strftime('%Y-%m-%d')
        total, ex_bank = compute_liquidity_index(data_store, bank)
        results["Liquidity Index (Bank Credit 반영)"] = f"{total} / 100"
        results["Liquidity Index (Bank Credit 제외, 기존 방식)"] = f"{ex_bank} / 100"
        if bank is not None:
            results["Bank Credit 가중치"] = f"{int(round(BANK_CREDIT_WEIGHT * 100))} %"
            results["Bank Credit의 Liquidity Index 기여 (점)"] = f"{total - ex_bank:+d}"
    except Exception as e:
        print(f"Bank Credit / Liquidity Index 계산 중 오류 (건너뜀): {e}")


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

    add_bank_and_index_metrics(results, data_store)

    return results


def analyze_with_gemini(metrics_data):
    if not model:
        print("Gemini AI 모델이 설정되지 않아 분석을 건너뜁니다.")
        return

    print("\n--- Gemini AI 경제 분석 시작 ---")
    analysis_prompt_data = json.dumps(metrics_data, ensure_ascii=False, indent=2)
    rate_keys = ["역레포 금리", "연준 할인율", "EFFR 금리", "SOFR 금리", "SOFR EFFR 스프레드",
                 "3개월 미 국채금리", "2년물 미 국채금리", "10년물 미 국채금리"]
    rate_prompt_data = json.dumps({k: v for k, v in metrics_data.items() if k in rate_keys}, ensure_ascii=False, indent=2)

    prompt1 = f"""
    당신은 Ai 전문 경제 분석가입니다. 아래는 미국의 최신 통화 유동성 및 은행 신용(Bank Credit) 관련 데이터입니다.
    이 데이터를 바탕으로 현재 미국 시장의 유동성 상황이 돈이 공급되는 상황인지 흡수되는 상황인지를 설명해주고,
    왜 그렇게 생각했는지를 최소 2,3가지 지표 숫자를 근거를 설명해주고(단, 다른 지표는 상관없는데, 연준 관련 유동성 설명을 할꺼면 "연준 유동성"과 "연준 역레포 및 지급준비금 부채" 중 하나만 골라서 언급해줘 둘다 같이 쓰면 헷갈려. 그리고, 미국 정부 TGA 잔고 변화량에 대해서는 꼭 설명해줘.), 설명한 지표가 무엇을 의미하는지도 함께 설명해주세요. (단위 잘 고려해서 설명해줘! 참고로 단위 B $는 Billion Dollar야. 단위 잘 고려해서 말해줘.)

    [Bank Credit 해석 규칙 - 반드시 지켜주세요]
    - Bank Credit(FRED TOTBKCR)은 미국 상업은행 전체의 Bank Credit 잔액입니다. 대출·리스뿐 아니라 은행 보유 증권 등이 포함될 수 있습니다.
    - 아래 순서로 판단하고 그 결과를 글에 녹여주세요.
      ① 은행 신용이 증가했는가 감소했는가? ② 최신 주간 변화량(및 4주/13주 누적)은 얼마인가?
      ③ 은행 시스템 규모 대비 얼마나 큰 변화인가?(Flow Ratio) ④ 역사적으로 강한 신용확대/위축인가?(Bank Credit Score = 13주 평균 Flow Ratio를 최근 10년 분포와 비교한 점수. 한 주의 일시적 증감이 아니라 최근 추세를 반영함)
      ⑤ TGA/역레포/MMF/연준 지표와 같은 방향인가? ⑥ 반대 방향인가? ⑦ Liquidity Index에 어떤 영향을 주었는가?(Bank Credit 반영 vs 제외 점수 차이)
    - 사용할 표현 예: "은행의 Bank Credit이 전주 대비 ○○억 달러 증가/감소했습니다", "은행권 신용공급이 확대/위축되고 있습니다",
      "은행 신용창출 흐름은 현재 유동성에 우호적/비우호적인 방향으로 작용하고 있습니다".
    - 절대 쓰지 말 것: "은행이 시장에 현금을 공급했다", "Bank Credit 증가 = 신규 통화/신규 대출 100% 증가", 변화량을 곧바로 "신규 대출 ○○억 달러" 또는 "새로 만들어진 돈"이라고 표현하는 것,
      "Bank Credit 증가 = 주식시장 상승", "Bank Credit 감소 = 주식시장 하락" 같은 시장 방향 단정.
    - 항상 "방향"과 "가능성" 중심으로 표현하고, 주식시장의 상승/하락을 단정하지 마세요.
    - 참고: TGA 감소 + 역레포 감소 + Bank Credit 증가 → 정부/시장과 은행권 모두에서 유동성·신용 공급이 확대되는 방향 / TGA 증가 + 역레포 증가 + Bank Credit 감소 → 모두 위축되는 방향.
      (단, 실제 데이터가 이와 다르면 데이터대로 "엇갈리는 방향"이라고 설명)
    - 데이터에 Bank Credit 항목이 없으면 Bank Credit 설명은 생략하세요.

    전체 글자수는 400자 이내로(공백제외) 답변해주세요. 분석 결과는 인사 이후에 두칸 내려서 답변해주세요. 마지막에 결론 글도 작성해주는데, 결론글은 두칸 내려서 답변해줘. <br>을 써서 칸을 내리는 형식으로 바꿔주세요.
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
    {rate_prompt_data}
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
            "date": now_kst().strftime('%y-%m-%d'),
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
            "Bank Credit 현재 잔액": "bank_credit_balance_billion",
            "Bank Credit 최신 주간 변화량": "bank_credit_weekly_change_billion",
            "Bank Credit 최근 4주 누적 변화량": "bank_credit_4w_change_billion",
            "Bank Credit 최근 13주 누적 변화량": "bank_credit_13w_change_billion",
            "Bank Credit Flow Ratio": "bank_credit_flow_ratio_percent",
            "Bank Credit Flow Ratio (13주 평균, 점수 산정 기준)": "bank_credit_flow_ratio_13w_percent",
            "Bank Credit Score": "bank_credit_score",
            "Liquidity Index (Bank Credit 반영)": "liquidity_index",
            "Liquidity Index (Bank Credit 제외, 기존 방식)": "liquidity_index_ex_bank",
            "3개월 미 국채금리": "dgs3mo_rate_percent",
            "2년물 미 국채금리": "dgs2_rate_percent",
            "10년물 미 국채금리": "dgs10_rate_percent",
        }

        app_data = {"date": now_kst().strftime('%Y-%m-%d')}
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
