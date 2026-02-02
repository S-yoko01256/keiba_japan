import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import re
import time

# --- あなたの「お宝リスト」完全網羅 ---
MASTER_LIST = {
    '阪神': {'ダート': [11.0, 8.0, 9.0, 6.0], '芝': [9.0, 5.0, 6.0, 7.0]},
    '中山': {'ダート': [8.0], '芝': [5.0, 8.0]},
    '京都': {'ダート': [6.0, 8.0, 10.0], '芝': [3.0, 9.0]},
    '東京': {'ダート': [7.0]},
    '福島': {'ダート': [3.0]},
    '小倉': {'芝': [8.0]},
    '新潟': {'芝': [5.0]}
}

PLACE_MAP = {'05': '東京', '06': '中山', '08': '京都', '09': '阪神', '03': '福島', '04': '新潟', '10': '小倉'}

def get_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

st.set_page_config(page_title="お宝馬アラート", page_icon="🏇")
st.title("🏇 心理の歪み・お宝馬サーチ")
st.caption("35年統計：特定の不人気×逃げ馬をリアルタイム検知")

# 日付選択（デフォルトは今日）
target_date = st.date_input("実行日を選択", pd.to_datetime("2026-02-02")).strftime('%Y%m%d')

if st.button("全会場スキャン開始"):
    driver = get_driver()
    found_any = False
    
    with st.spinner("出馬表とオッズを照合中..."):
        for p_id, p_name in PLACE_MAP.items():
            # 開催回(1-5)と日目(1-12)を簡易ループ（実戦では当日の開催情報を自動取得するのが理想）
            # ここでは確実性を期して第1回〜第3回、1〜8日目程度をスキャン
            for kai in range(1, 4):
                day_found = False
                for day in range(1, 9):
                    race_id_base = f"{target_date}{p_id}{kai:02}{day:02}"
                    # 1Rをチェックして開催があるか確認
                    driver.get(f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id_base}01")
                    
                    if "出馬表" not in driver.title or "一致するレース" in driver.page_source:
                        continue
                    
                    day_found = True
                    st.write(f"🔍 {p_name}競馬場をスキャン中...")
                    
                    for r in range(1, 13):
                        rid = f"{race_id_base}{r:02}"
                        driver.get(f"https://race.netkeiba.com/race/shutuba.html?race_id={rid}")
                        
                        try:
                            race_data = driver.find_element(By.CLASS_NAME, "RaceData01").text
                            track = "芝" if "芝" in race_data else "ダート"
                            
                            if p_name in MASTER_LIST and track in MASTER_LIST[p_name]:
                                target_ninkis = MASTER_LIST[p_name][track]
                                
                                rows = driver.find_elements(By.CLASS_NAME, "HorseList")
                                for row in rows:
                                    ninki_text = row.find_element(By.CLASS_NAME, "Ninki").text
                                    if not ninki_text: continue
                                    
                                    ninki = float(ninki_text)
                                    if ninki in target_ninkis:
                                        name = row.find_element(By.CLASS_NAME, "HorseName").text
                                        # 通過順に1-3があるか
                                        past = row.text
                                        if re.search(r'[1-3]-\d+-\d+', past):
                                            st.success(f"🔥 【激アツ】{p_name}{r}R {track} {name} ({ninki}人気)")
                                            found_any = True
                        except:
                            continue
                if day_found: break # 開催が見つかれば次の場所へ

    if not found_any:
        st.warning("対象の日付に合致する『お宝馬』は見つかりませんでした。")
    
    driver.quit()