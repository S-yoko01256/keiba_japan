import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import re
import time
import os  # ファイル存在確認に必要

# --- 判定ロジック：回収率85%以上の条件リスト ---
MASTER_LIST = {
    '阪神': {'ダート': [11.0, 8.0, 9.0, 6.0], '芝': [9.0, 5.0, 6.0, 7.0]},
    '中山': {'ダート': [8.0], '芝': [5.0, 8.0]},
    '京都': {'ダート': [6.0, 8.0, 10.0], '芝': [3.0, 9.0]},
    '東京': {'ダート': [7.0]},
    '福島': {'ダート': [3.0]},
    '小倉': {'芝': [8.0]},
    '新潟': {'芝': [5.0]},
}

PLACE_MAP = {'05': '東京', '06': '中山', '08': '京都', '09': '阪神', '03': '福島', '04': '新潟', '10': '小倉'}

def get_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

def get_race_ids_from_db(target_dt):
    year = target_dt.strftime('%Y')
    month = target_dt.strftime('%m')
    day = target_dt.strftime('%d')
    csv_file = f"jra_schedule_{year}.csv"
    
    # 修正：ファイルパスを絶対パスで確認するように強化
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, csv_file)
    
    if not os.path.exists(file_path):
        return None # 2027年などでCSVがない場合はネット取得モードへ
    
    try:
        df = pd.read_csv(file_path, dtype=str)
        # 月と日の比較（zfillで0埋めして確実に一致させる）
        today_race = df[(df['月'] == month) & (df['日'] == day)]
        
        if today_race.empty:
            return [] # 開催がない日
        
        race_ids = []
        for _, row in today_race.iterrows():
            base_id = f"{year}{row['場所コード']}{row['回']}{row['日次']}"
            for r in range(1, 13):
                race_ids.append(f"{base_id}{str(r).zfill(2)}")
        return race_ids
    except Exception as e:
        st.error(f"CSV読み込みエラー: {e}")
        return None

st.set_page_config(page_title="お宝馬アラート", page_icon="🏇")
st.title("🏇 お宝馬サーチ (DB対応版)")

target_date_dt = st.date_input("実行日を選択", pd.to_datetime("today"))
target_date_str = target_date_dt.strftime('%Y%m%d')

if st.button("全会場スキャン開始"):
    race_ids = []
    
    # --- STEP 1: 開催日程の特定 ---
    with st.spinner("スケジュールを確認中..."):
        race_ids = get_race_ids_from_db(target_date_dt)
        
        # データベースにない年の場合、ネットから取得
        if race_ids is None:
            st.info("年間表がないためネットから取得します...")
            driver = get_driver()
            try:
                driver.get(f"https://race.netkeiba.com/top/race_list.html?kasai_date={target_date_str}")
                time.sleep(2)
                links = driver.find_elements(By.TAG_NAME, "a")
                race_ids = []
                for link in links:
                    href = link.get_attribute("href")
                    if href and "race_id=" in href:
                        match = re.search(r'race_id=(\d{12})', href)
                        if match: race_ids.append(match.group(1))
                race_ids = sorted(list(set(race_ids)))
            finally:
                if not race_ids: driver.quit()
        else:
            # データベースでIDが作れた場合でも、中身を見るためにブラウザが必要
            driver = get_driver()

    # --- STEP 2: レース内容の解析 ---
    if not race_ids:
        st.warning(f"{target_date_str} の開催予定が見つかりませんでした。")
    else:
        st.info(f"🔍 {len(race_ids)}レースをスキャン中...")
        found_any = False
        progress_bar = st.progress(0)
        
        try:
            for i, rid in enumerate(race_ids):
                p_code = rid[4:6]
                p_name = PLACE_MAP.get(p_code)
                if not p_name: continue
                
                driver.get(f"https://race.netkeiba.com/race/shutuba.html?race_id={rid}")
                # 簡易読み込み待ち
                time.sleep(1) 
                
                # ... (以下、お宝馬判定ロジック) ...
                # 出馬表があるか確認
                if "HorseList" in driver.page_source:
                    race_data_el = driver.find_elements(By.CLASS_NAME, "RaceData01")
                    if race_data_el:
                        race_data = race_data_el[0].text
                        track = "芝" if "芝" in race_data else "ダート"
                        
                        if p_name in MASTER_LIST and track in MASTER_LIST[p_name]:
                            target_ninkis = MASTER_LIST[p_name][track]
                            rows = driver.find_elements(By.CLASS_NAME, "HorseList")
                            for row in rows:
                                try:
                                    ninki_text = row.find_element(By.CLASS_NAME, "Ninki").text
                                    if ninki_text.replace('.','',1).isdigit():
                                        ninki = float(ninki_text)
                                        if ninki in target_ninkis:
                                            if re.search(r'[1-3]-\d+-\d+', row.text):
                                                name = row.find_element(By.CLASS_NAME, "HorseName").text
                                                st.success(f"🔥 {p_name}{int(rid[10:12])}R: {name} ({ninki}人)")
                                                found_any = True
                                except: continue
                progress_bar.progress((i + 1) / len(race_ids))
        finally:
            driver.quit()

        if not found_any:
            st.warning("条件に合う馬は見つかりませんでした。")
        st.balloons()