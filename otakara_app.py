import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import re
import time
import os

# --- 設定：あなたの MASTER_LIST ---
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
    # ページ読み込みを待たずに要素を探す設定（高速化＆タイムアウト防止）
    options.page_load_strategy = 'eager'
    
    # Streamlit Cloud環境でのバイナリ指定を自動化
    if os.path.exists("/usr/bin/chromium-browser"):
        options.binary_location = "/usr/bin/chromium-browser"
    elif os.path.exists("/usr/bin/chromium"):
        options.binary_location = "/usr/bin/chromium"

    try:
        # Serviceのパス指定をCloud環境（Linux）に最適化
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)
    except:
        # ローカル（Windows）での実行時など、パスが違う場合のバックアップ
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        except:
            # 最終手段：パス指定なし
            driver = webdriver.Chrome(options=options)
            
    driver.set_page_load_timeout(60)
    return driver

def get_target_race_ids(target_dt):
    year = target_dt.strftime('%Y')
    month = target_dt.strftime('%m').zfill(2)
    day = target_dt.strftime('%d').zfill(2)
    csv_file = f"jra_schedule_{year}.csv"
    
    # アプリがあるディレクトリからCSVを探す
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, csv_file)
    
    if not os.path.exists(file_path):
        return None # 2027年以降など、CSV未作成の場合

    try:
        df = pd.read_csv(file_path, dtype=str)
        # 0埋めを確実に行う
        df['月'] = df['月'].str.zfill(2)
        df['日'] = df['日'].str.zfill(2)
        
        today_data = df[(df['月'] == month) & (df['日'] == day)]
        if today_data.empty: return []

        race_ids = []
        for _, row in today_data.iterrows():
            p_name = row['場所']
            if p_name in MASTER_LIST: # あなたのリストにある会場のみ
                base_id = f"{year}{row['場所コード']}{row['回'].zfill(2)}{row['日次'].zfill(2)}"
                for r in range(1, 13):
                    race_ids.append(f"{base_id}{str(r).zfill(2)}")
        return race_ids
    except Exception as e:
        st.error(f"CSV読み込み失敗: {e}")
        return None

st.set_page_config(page_title="お宝馬サーチ", page_icon="🏇")
st.title("🏇 お宝馬サーチ (デバッグ隊検証済み版)")

target_dt = st.date_input("実行日", pd.to_datetime("today"))
target_str = target_dt.strftime('%Y%m%d')

if st.button("選抜スキャン開始"):
    with st.spinner("1. データベース照合中..."):
        race_ids = get_target_race_ids(target_dt)
    
    if race_ids == []:
        st.warning(f"⚠️ {target_str} は対象会場の開催がありません。")
    else:
        with st.spinner("2. ブラウザを起動中..."):
            driver = get_driver()
            
            # CSVがない場合はネットから拾う（保険）
            if race_ids is None:
                st.info("年間表がないためネットから日程を取得中...")
                try:
                    driver.get(f"https://race.netkeiba.com/top/race_list.html?kasai_date={target_str}")
                    time.sleep(2)
                    links = driver.find_elements(By.TAG_NAME, "a")
                    race_ids = sorted(list(set([re.search(r'race_id=(\d{12})', l.get_attribute("href")).group(1) 
                                                for l in links if l.get_attribute("href") and "race_id=" in l.get_attribute("href")])))
                except:
                    race_ids = []

        if not race_ids:
            st.error("スキャン対象が見つかりませんでした。")
            if 'driver' in locals(): driver.quit()
        else:
            st.info(f"🚀 {len(race_ids)}レースを精査します。")
            found_any = False
            progress_bar = st.progress(0)
            
            for i, rid in enumerate(race_ids):
                p_code = rid[4:6]
                p_name = PLACE_MAP.get(p_code)
                
                try:
                    driver.get(f"https://race.netkeiba.com/race/shutuba.html?race_id={rid}")
                    if "HorseList" in driver.page_source:
                        race_info = driver.find_element(By.CLASS_NAME, "RaceData01").text
                        track = "芝" if "芝" in race_info else "ダート"
                        
                        if track in MASTER_LIST[p_name]:
                            target_ninkis = MASTER_LIST[p_name][track]
                            rows = driver.find_elements(By.CLASS_NAME, "HorseList")
                            for row in rows:
                                try:
                                    n_txt = row.find_element(By.CLASS_NAME, "Ninki").text
                                    if n_txt.replace('.','',1).isdigit():
                                        ninki = float(n_txt)
                                        # あなたの条件（人気 + 逃げ・先行実績）
                                        if ninki in target_ninkis and re.search(r'[1-3]-\d+-\d+', row.text):
                                            name = row.find_element(By.CLASS_NAME, "HorseName").text
                                            st.success(f"🔥 {p_name}{int(rid[10:12])}R ({track}): {name} ({ninki}人)")
                                            found_any = True
                                except: continue
                except Exception as e:
                    st.write(f"⚠️ {rid} は読み込みエラーのためスキップします。")
                    continue
                progress_bar.progress((i + 1) / len(race_ids))
            
            driver.quit()
            if not found_any: st.warning("本日の条件に合う馬は見つかりませんでした。")
            st.balloons()