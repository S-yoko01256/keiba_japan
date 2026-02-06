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

# --- 設定：あなたの精鋭リスト ---
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
    # タイムアウト対策：ページ読み込み戦略を 'eager' (インタラクティブになればOK) に変更
    options.page_load_strategy = 'eager'
    
    if os.path.exists("/usr/bin/chromium-browser"):
        options.binary_location = "/usr/bin/chromium-browser"
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # 読み込み待ち時間を30秒に設定
    driver.set_page_load_timeout(30)
    return driver

def get_target_race_ids(target_dt):
    year = target_dt.strftime('%Y')
    month = target_dt.strftime('%m')
    day = target_dt.strftime('%d')
    csv_file = f"jra_schedule_{year}.csv"
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, csv_file)
    
    if not os.path.exists(file_path):
        return None

    df = pd.read_csv(file_path, dtype=str)
    today_data = df[(df['月'] == month) & (df['日'] == day)]
    
    if today_data.empty: return []

    race_ids = []
    for _, row in today_data.iterrows():
        p_name = row['場所']
        # 【重要】リスト外の会場はURLすら作らない
        if p_name in MASTER_LIST:
            base_id = f"{year}{row['場所コード']}{row['回']}{row['日次']}"
            for r in range(1, 13):
                race_ids.append(f"{base_id}{str(r).zfill(2)}")
    return race_ids

st.title("🏇 お宝馬サーチ (タイムアウト対策版)")

target_dt = st.date_input("実行日", pd.to_datetime("today"))
target_str = target_dt.strftime('%Y%m%d')

if st.button("選抜スキャン開始"):
    with st.spinner("1. スケジュールをCSVから確認中..."):
        race_ids = get_target_race_ids(target_dt)
    
    if race_ids is None:
        st.info("年間表がないためネットから取得します...")
        driver = get_driver()
        try:
            driver.get(f"https://race.netkeiba.com/top/race_list.html?kasai_date={target_str}")
            time.sleep(2)
            links = driver.find_elements(By.TAG_NAME, "a")
            race_ids = sorted(list(set([re.search(r'race_id=(\d{12})', l.get_attribute("href")).group(1) 
                                        for l in links if l.get_attribute("href") and "race_id=" in l.get_attribute("href")])))
        except:
            st.error("日程ページの取得でタイムアウトしました。")
            race_ids = []
    else:
        driver = get_driver()

    if not race_ids:
        st.warning("対象となる開催はありません。")
        if 'driver' in locals(): driver.quit()
    else:
        st.info(f"🔍 リスト対象の {len(race_ids)}レースをスキャンします。")
        found_any = False
        progress_bar = st.progress(0)
        
        for i, rid in enumerate(race_ids):
            p_code = rid[4:6]
            p_name = PLACE_MAP.get(p_code)
            
            try:
                # タイムアウトエラーが起きても止まらないようにtry-exceptで囲む
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
                                    if ninki in target_ninkis and re.search(r'[1-3]-\d+-\d+', row.text):
                                        name = row.find_element(By.CLASS_NAME, "HorseName").text
                                        st.success(f"🔥 {p_name}{int(rid[10:12])}R ({track}): {name} ({ninki}人)")
                                        found_any = True
                            except: continue
            except Exception as e:
                # タイムアウトしても警告を出して次へ進む
                st.write(f"⚠️ {p_name}{int(rid[10:12])}R は読み込み遅延のためスキップしました。")
                continue
            
            progress_bar.progress((i + 1) / len(race_ids))
        
        driver.quit()
        if not found_any: st.warning("条件に合う馬は見つかりませんでした。")
        st.balloons()