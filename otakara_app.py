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
import os

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

# --- データベースから本日のレースID候補を生成する関数 ---
def get_race_ids_from_db(target_dt):
    year = target_dt.strftime('%Y')
    month = target_dt.strftime('%m')
    day = target_dt.strftime('%d')
    csv_file = f"jra_schedule_{year}.csv"
    
    if not os.path.exists(csv_file):
        return None # CSVがない場合は従来モードへ
    
    df = pd.read_csv(csv_file, dtype=str)
    # 当日の開催を抽出
    today_race = df[(df['月'] == month) & (df['日'] == day)]
    
    if today_race.empty:
        return [] # 開催なし
    
    race_ids = []
    for _, row in today_race.iterrows():
        # netkeiba形式のレースID (2026 + 場所05 + 回01 + 日03 + レース01〜12)
        base_id = f"{year}{row['場所コード']}{row['回']}{row['日次']}"
        for r in range(1, 13):
            race_ids.append(f"{base_id}{str(r).zfill(2)}")
    return race_ids

st.set_page_config(page_title="お宝馬アラート", page_icon="🏇")
st.title("🏇 心理の歪み・お宝馬サーチ")
st.caption("データベース活用版：高速スキャン対応")

target_date_dt = st.date_input("実行日を選択", pd.to_datetime("today"))
target_date_str = target_date_dt.strftime('%Y%m%d')

if st.button("全会場スキャン開始"):
    # 1. まずはデータベース（CSV）を確認
    with st.spinner("開催スケジュールを確認中..."):
        race_ids = get_race_ids_from_db(target_date_dt)
        
        # CSVがない場合はブラウザを立ち上げて従来通り取りに行く
        if race_ids is None:
            st.info("年間表がないため、ネットから開催情報を取得します...")
            driver = get_driver()
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
            if not race_ids:
                driver.quit()
        else:
            driver = get_driver() # CSVからIDが作れた場合もブラウザは必要

    # 2. スキャン実行
    if not race_ids:
        st.warning(f"{target_date_str} は開催日ではないか、データが見つかりませんでした。")
    else:
        st.info(f"🔍 {len(race_ids)}件のレースを検知。データベース照合で開始します。")
        found_any = False
        wait = WebDriverWait(driver, 15)
        
        progress_bar = st.progress(0)
        for i, rid in enumerate(race_ids):
            p_code = rid[4:6]
            p_name = PLACE_MAP.get(p_code)
            if not p_name: continue
            
            r_num = int(rid[10:12])
            driver.get(f"https://race.netkeiba.com/race/shutuba.html?race_id={rid}")
            
            try:
                # ページの存在確認（CSVにあるが中止などの場合を考慮）
                if "一致する情報は見つかりませんでした" in driver.page_source:
                    continue
                
                wait.until(EC.presence_of_element_located((By.CLASS_NAME, "HorseList")))
                race_data = driver.find_element(By.CLASS_NAME, "RaceData01").text
                track = "芝" if "芝" in race_data else "ダート"
                
                if p_name in MASTER_LIST and track in MASTER_LIST[p_name]:
                    target_ninkis = MASTER_LIST[p_name][track]
                    rows = driver.find_elements(By.CLASS_NAME, "HorseList")
                    for row in rows:
                        try:
                            ninki_text = row.find_element(By.CLASS_NAME, "Ninki").text
                            if not ninki_text or ninki_text == " ": continue
                            ninki = float(ninki_text)
                            if ninki in target_ninkis:
                                name = row.find_element(By.CLASS_NAME, "HorseName").text
                                if re.search(r'[1-3]-\d+-\d+', row.text):
                                    st.success(f"🔥 【お宝】{p_name}{r_num}R ({track}) {name} {ninki}人気")
                                    found_any = True
                        except: continue
            except: continue
            progress_bar.progress((i + 1) / len(race_ids))

        if not found_any:
            st.warning("本日の条件に合致する馬は見つかりませんでした。")
        driver.quit()
        st.write("スキャン完了。")