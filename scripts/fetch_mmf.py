# -*- coding: utf-8 -*-
"""
OFR 사이트에서 MMF 관련 원본 CSV 2개를 다운로드합니다.
GitHub Actions(헤드리스 리눅스)에서 동작하도록 수정:
  - 절대경로(C:\\...) 제거 -> 저장소 상대경로
  - 헤드리스 옵션 + CDP 다운로드 허용 추가 (헤드리스에서는 기본 다운로드가 막혀 있음)

주의: 이 스크립트는 OFR 웹사이트의 현재 UI 구조(버튼 텍스트/클래스명)에 의존합니다.
사이트 구조가 바뀌면 셀렉터를 다시 확인해야 할 수 있습니다.
"""
import glob
import os
import time

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOAD_DIR = os.path.join(REPO_ROOT, "data", "mmf_flow")


def _build_driver(download_dir: str):
    chrome_options = Options()
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_settings.popups": 0,
        "profile.default_content_setting_values.automatic_downloads": 1,
    }
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    # 헤드리스 모드에서는 다운로드가 기본적으로 막혀 있어 CDP로 명시적 허용해야 함
    driver.execute_cdp_cmd(
        "Page.setDownloadBehavior",
        {"behavior": "allow", "downloadPath": download_dir},
    )
    return driver


def wait_for_download(download_dir, start_time, max_wait_time=120):
    print(f"다운로드 대기 중... (최대 {max_wait_time}초)")
    while time.time() - start_time < max_wait_time:
        downloaded_files = [
            f for f in os.listdir(download_dir) if not f.endswith(('.crdownload', '.tmp', '.part'))
        ]
        if downloaded_files:
            new_files = [
                f for f in downloaded_files
                if os.path.getctime(os.path.join(download_dir, f)) > start_time
            ]
            if new_files:
                latest_file = max(new_files, key=lambda x: os.path.getctime(os.path.join(download_dir, x)))
                file_path = os.path.join(download_dir, latest_file)
                file_size = os.path.getsize(file_path)
                if file_size > 1024:
                    time.sleep(1)
                    if os.path.getsize(file_path) == file_size:
                        print(f"다운로드 완료: {latest_file} ({file_size} bytes)")
                        return latest_file
        time.sleep(2)
    print("다운로드 시간 초과")
    return None


def download_mmf_dataset():
    target_url = "https://www.financialresearch.gov/short-term-funding-monitor/datasets/mmf-single/?mnemonic=MMF-MMF_BRA_TOT-M"
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    driver = None
    try:
        driver = _build_driver(DOWNLOAD_DIR)
        driver.get(target_url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(5)

        download_button = None
        selectors = [
            (By.ID, "downloadDatasetData"),
            (By.XPATH, "//button[contains(text(), 'Download')]"),
            (By.XPATH, "//a[contains(text(), 'Download')]"),
            (By.XPATH, "//*[contains(@class, 'download') and contains(@class, 'button')]"),
            (By.CSS_SELECTOR, ".download-button"),
            (By.CSS_SELECTOR, "[data-download]"),
        ]
        for selector_type, selector_value in selectors:
            try:
                download_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((selector_type, selector_value))
                )
                break
            except Exception:
                continue

        if not download_button:
            with open(os.path.join(DOWNLOAD_DIR, "page_source.html"), "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            raise Exception("다운로드 버튼을 찾을 수 없습니다. page_source.html을 아티팩트로 확인하세요.")

        driver.execute_script("arguments[0].scrollIntoView(true);", download_button)
        time.sleep(1)
        try:
            download_button.click()
        except Exception:
            driver.execute_script("arguments[0].click();", download_button)
        time.sleep(3)

        csv_selectors = [
            (By.XPATH, "//div[@id='downloadDatasetContent']//a[contains(text(), 'CSV')]"),
            (By.XPATH, "//a[contains(text(), 'CSV')]"),
            (By.XPATH, "//*[contains(@href, '.csv') or contains(text(), 'CSV')]"),
            (By.CSS_SELECTOR, "a[href*='.csv']"),
        ]
        csv_button = None
        for selector_type, selector_value in csv_selectors:
            try:
                csv_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((selector_type, selector_value))
                )
                break
            except Exception:
                continue

        if csv_button:
            try:
                csv_button.click()
            except Exception:
                driver.execute_script("arguments[0].click();", csv_button)

        start_time = time.time()
        latest_file = wait_for_download(DOWNLOAD_DIR, start_time)
        if not latest_file:
            raise Exception("다운로드가 완료되지 않았습니다.")

        original_path = os.path.join(DOWNLOAD_DIR, latest_file)
        new_path = os.path.join(DOWNLOAD_DIR, "mmf_bra_tot_m_data.csv")
        if os.path.exists(new_path):
            os.remove(new_path)
        os.rename(original_path, new_path)
        print(f"파일 저장 완료: {new_path}")
        validate_csv_file(new_path)

    except Exception as e:
        print(f"오류 발생: {e}")
        if driver:
            driver.save_screenshot(os.path.join(DOWNLOAD_DIR, "error_screenshot_mmf.png"))
        raise
    finally:
        if driver:
            driver.quit()


def download_mmf_total_dataset():
    target_url = "https://www.financialresearch.gov/money-market-funds/us-mmfs-investments-by-fund-category/"
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    driver = None
    try:
        driver = _build_driver(DOWNLOAD_DIR)
        driver.get(target_url)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(5)

        try:
            data_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "data-button"))
            )
        except Exception:
            data_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Data')]"))
            )

        driver.execute_script("arguments[0].scrollIntoView(true);", data_button)
        time.sleep(1)
        try:
            data_button.click()
        except Exception:
            driver.execute_script("arguments[0].click();", data_button)
        time.sleep(5)

        ofrdata_path = os.path.join(DOWNLOAD_DIR, "ofrdata.csv")
        new_path = os.path.join(DOWNLOAD_DIR, "mmf_total_data.csv")
        if os.path.exists(new_path):
            os.remove(new_path)

        if os.path.exists(ofrdata_path):
            os.rename(ofrdata_path, new_path)
            print("파일명 변경 완료: ofrdata.csv -> mmf_total_data.csv")
            validate_csv_file(new_path)
        else:
            raise Exception(f"ofrdata.csv 파일을 찾을 수 없습니다: {ofrdata_path}")

    except Exception as e:
        print(f"오류 발생: {e}")
        if driver:
            driver.save_screenshot(os.path.join(DOWNLOAD_DIR, "error_screenshot_total.png"))
        raise
    finally:
        if driver:
            driver.quit()


def validate_csv_file(file_path):
    try:
        for encoding in ['utf-8', 'cp1252', 'iso-8859-1']:
            try:
                df = pd.read_csv(file_path, encoding=encoding)
                print(f"파일 읽기 성공 (인코딩: {encoding}), 행 수: {len(df)}")
                return True
            except UnicodeDecodeError:
                continue
        print("모든 인코딩으로 파일 읽기 실패")
        return False
    except Exception as e:
        print(f"파일 검증 오류: {e}")
        return False


def clean_download_directory(download_dir):
    for pattern in ("*.crdownload", "*.tmp"):
        for temp_file in glob.glob(os.path.join(download_dir, pattern)):
            try:
                os.remove(temp_file)
            except Exception:
                pass


if __name__ == '__main__':
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    try:
        print("=== MMF 데이터 다운로드 시작 ===")
        clean_download_directory(DOWNLOAD_DIR)

        print("\n1. MMF BRA TOT 데이터셋 다운로드...")
        download_mmf_dataset()
        print("완료")

        time.sleep(5)

        print("\n2. MMF Total 데이터셋 다운로드...")
        download_mmf_total_dataset()
        print("완료")

        print("\n=== 모든 다운로드 완료 ===")
    finally:
        clean_download_directory(DOWNLOAD_DIR)
