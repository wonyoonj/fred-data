# -*- coding: utf-8 -*-
"""
CNN 공포·탐욕 지수(Fear & Greed Index)를 받아 csvfile/FEARGREED.csv 로 저장합니다.

- 저장 형식은 FRED CSV 와 같습니다:  Date,FEARGREED   (웹 그래프 페이지가 그대로 읽을 수 있음)
- 실행할 때마다 기존 이력에 새 값을 합쳐서(같은 날짜는 최신값으로) 이력이 계속 쌓입니다.
- 이상한 응답(비어 있거나 너무 짧음)이면 기존 파일을 덮어쓰지 않고 오류로 종료합니다.
  워크플로에서 continue-on-error 로 실행하므로, 이 단계가 실패해도 나머지 데이터 갱신은 계속됩니다.

주의: CNN 의 공개 JSON 주소(production.dataviz.cnn.io)는 공식 API 가 아니라서
      주소/응답 형식이 바뀌거나 GitHub 서버 IP 가 차단될 수 있습니다.
"""
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(REPO_ROOT, "csvfile")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "FEARGREED.csv")

CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
CNN_START_DATE = "2020-07-14"  # 이 날짜부터의 이력 요청 (실패하면 기본 범위로 재시도)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.cnn.com/",
    "Origin": "https://www.cnn.com",
}


def http_get(url, retries=3, timeout=30):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"  시도 {attempt}/{retries} 실패 ({url}): {e}")
            time.sleep(2 * attempt)
    raise RuntimeError(f"요청 실패: {url}: {last_err}")


def _utc_date_from_ms(ms):
    return dt.datetime.fromtimestamp(ms / 1000.0, tz=dt.timezone.utc).strftime("%Y-%m-%d")


def parse_cnn(json_text):
    """CNN graphdata JSON -> {날짜: 점수}"""
    data = json.loads(json_text)
    rows = {}
    for p in (data.get("fear_and_greed_historical") or {}).get("data") or []:
        try:
            rows[_utc_date_from_ms(float(p["x"]))] = round(float(p["y"]), 2)
        except (KeyError, TypeError, ValueError):
            continue

    # 가장 최신 값(오늘 값)도 이력에 반영
    cur = data.get("fear_and_greed") or {}
    if cur.get("score") is not None:
        ts = str(cur.get("timestamp") or "")
        date = ts[:10] if len(ts) >= 10 else dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        rows[date] = round(float(cur["score"]), 2)
    return rows


def read_existing(path):
    rows = {}
    if not os.path.exists(path):
        return rows
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader, None)
        for r in reader:
            if len(r) >= 2:
                try:
                    rows[r[0]] = float(r[1])
                except ValueError:
                    pass
    return rows


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print("CNN 공포·탐욕 지수 수집 중...")
    try:
        new_rows = parse_cnn(http_get(f"{CNN_URL}/{CNN_START_DATE}"))
    except Exception as e:  # noqa: BLE001
        print(f"날짜 지정 요청 실패({e}) -> 기본 범위로 재시도")
        new_rows = parse_cnn(http_get(CNN_URL))

    if len(new_rows) < 30:
        print(f"[오류] 받은 데이터가 너무 적습니다({len(new_rows)}행). 기존 파일을 유지합니다.")
        return 1

    merged = read_existing(OUTPUT_FILE)
    merged.update(new_rows)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")  # 기존 FRED CSV 와 같은 줄바꿈(\n)
        w.writerow(["Date", "FEARGREED"])
        for d in sorted(merged):
            w.writerow([d, merged[d]])

    last = max(merged)
    print(f"[성공] {OUTPUT_FILE} 저장 완료 ({len(merged)}행, 최신 {last} = {merged[last]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
