import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import time

# --- 判定ロジック・条件は一切変更していません ---
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
    options.add_argument('--disable-gpu')
    options.add_argument('--remote-debugging-port=9222') 
    return webdriver.Chrome(options=options)

st.set_page_config(page_title="お宝馬アラート", page_icon="🏇")
st.title("🏇 心理の歪み・お宝馬サーチ")
st.caption("35年統計：特定の不人気×逃げ馬をリアルタイム検知")

# 日付選択
target_date_dt = st.date_input("実行日を選択", pd.to_datetime("2026-02-02"))
target_date = target_date_dt.strftime('%Y%m%d')

if st.button("全会場スキャン開始"):
    driver = get_driver()
    wait = WebDriverWait(driver, 10)
    found_any = False
    
    with st.spinner("開催情報を確認中..."):
        for p_id, p_name in PLACE_MAP.items():
            # その競馬場で開催があるか、第1〜5回までを高速チェック
            venue_active = False
            for kai in range(1, 6):
                # 各開催の「1日目」があるかだけを確認
                check_id = f"{target_date}{p_id}{kai:02}0101"
                driver.get(f"https://race.netkeiba.com/race/shutuba.html?race_id={check_id}")
                
                # ページソース内に「出馬表」があり、かつエラーメッセージがないことを確認
                if "出馬表" in driver.title and "一致するレース" not in driver.page_source:
                    venue_active = True
                    current_kai = kai
                    break
            
            if not venue_active:
                # 開催がなければこの競馬場はスキップ
                continue

            # 開催がある場合のみ、日目（1〜12日目）を特定してスキャン
            st.write(f"🔍 {p_name}競馬場の開催を検知。詳細スキャン中...")
            for day in range(1, 13):
                race_id_base = f"{target_date}{p_id}{current_kai:02}{day:02}"
                # その日の1Rが存在するかチェック
                driver.get(f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id_base}01")
                if "出馬表" not in driver.title or "一致するレース" in driver.page_source:
                    continue

                for r in range(1, 13):
                    rid = f"{race_id_base}{r:02}"
                    driver.get(f"https://race.netkeiba.com/race/shutuba.html?race_id={rid}")
                    
                    try:
                        # 画面表示を待機
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
                                            st.success(f"🔥 【激アツ】{p_name}{r}R {track} {name} ({ninki}人気)")
                                            found_any = True
                                except:
                                    continue
                    except:
                        continue
            # その競馬場の処理が終わったら次の競馬場へ

    if not found_any:
        st.warning("対象の日付に合致する『お宝馬』は見つかりませんでした。")
    
    driver.quit()