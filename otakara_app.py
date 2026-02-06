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
    '阪神': {'ダート': [11.0, 8.0, 9.0, 6.0], '芝': [9.0, 5.0, 6.0, 7.0] + [5, 6, 7, 8, 9, 11]},
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
    options.page_load_strategy = 'eager'
    service = Service("/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=options)

st.title("🏇 お宝馬サーチ (ロジック検証モード)")

# 日付選択
target_date = st.date_input("検証する日付を選択してください", value=pd.to_datetime("2026-02-07"))
date_str = target_date.strftime("%m,%d")

if st.button("スキャン開始"):
    try:
        df = pd.read_csv("jra_schedule_2026.csv")
        # 型合わせ
        df['月'] = df['月'].astype(str).str.zfill(2)
        df['日'] = df['日'].astype(str).str.zfill(2)
        
        day_races = df[(df['月'] == date_str.split(',')[0]) & (df['日'] == date_str.split(',')[1])]
        
        if day_races.empty:
            st.warning("指定された日の開催データが見つかりません。")
        else:
            race_ids = []
            for _, row in day_races.iterrows():
                p_code = str(row['場所コード']).zfill(2)
                kai = str(row['回']).zfill(2)
                nichiji = str(row['日次']).zfill(2)
                for r in range(1, 13):
                    race_ids.append(f"2026{p_code}{kai}{nichiji}{str(r).zfill(2)}")

            driver = get_driver()
            progress_bar = st.progress(0)
            found_any = False
            debug_logs = [] # 検証トレース用

            for i, rid in enumerate(race_ids):
                p_code = rid[4:6]
                p_name = PLACE_MAP.get(p_code, "不明")
                r_num = int(rid[10:12])
                log_prefix = f"【{p_name}{r_num}R】"

                try:
                    driver.get(f"https://race.netkeiba.com/race/shutuba.html?race_id={rid}")
                    
                    # コース情報の取得
                    race_info = driver.find_element(By.CLASS_NAME, "RaceData01").text
                    track = "芝" if "芝" in race_info else "ダート"
                    
                    # 1. 場所のチェック
                    if p_name not in MASTER_LIST:
                        debug_logs.append(f"{log_prefix} ⇒ 除外（{p_name}は設定対象外）")
                        continue
                    
                    # 2. コース種のチェック
                    if track not in MASTER_LIST[p_name]:
                        debug_logs.append(f"{log_prefix} ⇒ 除外（{p_name}の{track}条件なし）")
                        continue

                    target_ninkis = MASTER_LIST[p_name][track]
                    rows = driver.find_elements(By.CLASS_NAME, "HorseList")
                    
                    ninki_found = False
                    for row in rows:
                        try:
                            n_txt = row.find_element(By.CLASS_NAME, "Ninki").text
                            if n_txt.replace('.','',1).isdigit():
                                ninki = float(n_txt)
                                
                                if ninki in target_ninkis:
                                    ninki_found = True
                                    # 3. 脚質（逃げ・先行）チェック
                                    if re.search(r'[1-3]-\d+-\d+', row.text):
                                        name = row.find_element(By.CLASS_NAME, "HorseName").text
                                        st.success(f"🔥 発見！ {p_name}{r_num}R ({track}): {name} ({int(ninki)}番人気)")
                                        debug_logs.append(f"{log_prefix} ⇒ 🎯合致！ [{name}]")
                                        found_any = True
                                    else:
                                        debug_logs.append(f"{log_prefix} ⇒ 条件外（{int(ninki)}人気はいたが脚質実績なし）")
                        except: continue
                    
                    if not ninki_found:
                        debug_logs.append(f"{log_prefix} ⇒ 不成立（対象人気 {target_ninkis} が不在）")

                except Exception as e:
                    debug_logs.append(f"{log_prefix} ⇒ ⚠️ エラー (サイト構造変化の可能性)")
                
                progress_bar.progress((i + 1) / len(race_ids))
            
            driver.quit()
            
            if not found_any:
                st.warning("条件に合致する馬は見つかりませんでした。")

            # --- トレース詳細の表示 ---
            st.write("---")
            with st.expander("詳細検証ログを確認する（不採用理由のトレース）"):
                for log in debug_logs:
                    st.write(log)

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")