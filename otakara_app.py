import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import re
import time
import os

# --- 設定 ---
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

# --- ブラウザ起動関数（Cloud/Local両対応版） ---
def get_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    
    # Streamlit Cloud環境用の特殊設定
    if os.path.exists("/usr/bin/chromium-browser"):
        options.binary_location = "/usr/bin/chromium-browser"

    try:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except:
        # 失敗した時の予備（パス指定なし）
        return webdriver.Chrome(options=options)

# --- データベース照合 ---
def get_race_ids_from_db(target_dt):
    year = target_dt.strftime('%Y')
    month = target_dt.strftime('%m')
    day = target_dt.strftime('%d')
    csv_file = f"jra_schedule_{year}.csv"
    
    # 実行ファイルの階層からCSVを探す
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, csv_file)
    
    if not os.path.exists(file_path):
        return None # 2027年以降などCSVがない場合
    
    df = pd.read_csv(file_path, dtype=str)
    # 0埋めを考慮して比較
    today_race = df[(df['月'] == month) & (df['日'] == day)]
    
    if today_race.empty:
        return [] # 開催なし
    
    race_ids = []
    for _, row in today_race.iterrows():
        base_id = f"{year}{row['場所コード']}{row['回']}{row['日次']}"
        for r in range(1, 13):
            race_ids.append(f"{base_id}{str(r).zfill(2)}")
    return race_ids

st.set_page_config(page_title="お宝馬サーチ", page_icon="🏇")
st.title("🏇 お宝馬サーチ (DB対応版)")

target_date_dt = st.date_input("実行日を選択", pd.to_datetime("today"))
target_date_str = target_date_dt.strftime('%Y%m%d')

if st.button("全会場スキャン開始"):
    # 【作戦】まずCSVで判定して、無駄な起動を避ける
    with st.spinner("スケジュール確認中..."):
        race_ids = get_race_ids_from_db(target_date_dt)
    
    if race_ids == []:
        st.warning(f"⚠️ {target_date_str} はJRAの開催日ではありません（データベース照合）")
    else:
        # 開催がある、もしくはCSVがない場合のみブラウザを起動
        with st.spinner("ブラウザを起動中..."):
            driver = get_driver()
            
            # CSVがない(None)場合はネットからIDを拾う
            if race_ids is None:
                st.info("年間表がないためネットから日程を取得中...")
                driver.get(f"https://race.netkeiba.com/top/race_list.html?kasai_date={target_date_str}")
                time.sleep(2)
                links = driver.find_elements(By.TAG_NAME, "a")
                race_ids = sorted(list(set([re.search(r'race_id=(\d{12})', l.get_attribute("href")).group(1) 
                                            for l in links if l.get_attribute("href") and "race_id=" in l.get_attribute("href")])))

        if not race_ids:
            st.error("開催データが見つかりませんでした。")
            driver.quit()
        else:
            st.info(f"🔍 {len(race_ids)}レースのスキャンを開始します。")
            found_any = False
            progress_bar = st.progress(0)
            
            for i, rid in enumerate(race_ids):
                p_code = rid[4:6]
                p_name = PLACE_MAP.get(p_code)
                if not p_name: continue
                
                driver.get(f"https://race.netkeiba.com/race/shutuba.html?race_id={rid}")
                time.sleep(1) # サーバー負荷軽減
                
                if "HorseList" in driver.page_source:
                    try:
                        race_info = driver.find_element(By.CLASS_NAME, "RaceData01").text
                        track = "芝" if "芝" in race_info else "ダート"
                        
                        if p_name in MASTER_LIST and track in MASTER_LIST[p_name]:
                            target_ninkis = MASTER_LIST[p_name][track]
                            rows = driver.find_elements(By.CLASS_NAME, "HorseList")
                            for row in rows:
                                try:
                                    n_txt = row.find_element(By.CLASS_NAME, "Ninki").text
                                    if n_txt.replace('.','',1).isdigit():
                                        ninki = float(n_txt)
                                        if ninki in target_ninkis and re.search(r'[1-3]-\d+-\d+', row.text):
                                            name = row.find_element(By.CLASS_NAME, "HorseName").text
                                            st.success(f"🔥 {p_name}{int(rid[10:12])}R: {name} ({ninki}人)")
                                            found_any = True
                                except: continue
                    except: continue
                progress_bar.progress((i + 1) / len(race_ids))
            
            driver.quit()
            if not found_any: st.warning("条件に合う馬はいませんでした。")
            st.balloons()