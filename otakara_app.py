import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import re
import time

# --- 設定：MASTER_LIST ---
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
    # ローカルで動かす場合は Service(ChromeDriverManager().install()) に差し替えてください
    service = Service("/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=options)

st.title("🏇 お宝馬サーチ (物理行解析モード)")

target_date = st.date_input("検証する日付を選択してください", value=pd.to_datetime("2026-02-07"))
date_str = target_date.strftime("%m,%d")

if st.button("スキャン開始"):
    try:
        df = pd.read_csv("jra_schedule_2026.csv")
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
            debug_logs = []

            for i, rid in enumerate(race_ids):
                p_code = rid[4:6]
                p_name = PLACE_MAP.get(p_code, "不明")
                r_num = int(rid[10:12])
                log_prefix = f"【{p_name}{r_num}R】"

                try:
                    driver.get(f"https://race.netkeiba.com/race/shutuba.html?race_id={rid}")
                    time.sleep(3) # 展開待ち
                    
                    race_info = driver.find_element(By.CLASS_NAME, "RaceData01").text
                    track = "芝" if "芝" in race_info else "ダート"
                    
                    if p_name not in MASTER_LIST or track not in MASTER_LIST[p_name]:
                        debug_logs.append(f"{log_prefix} ⇒ 除外（{track}条件なし）")
                        continue

                    target_ninkis = [float(n) for n in MASTER_LIST[p_name][track]]
                    
                    # ページ全体のテキストを解析
                    all_text = driver.find_element(By.TAG_NAME, "body").text
                    lines = all_text.splitlines()
                    
                    # 馬番開始行の特定
                    start_idx = -1
                    for idx, line in enumerate(lines):
                        if re.match(r'^\d+ \d+$', line.strip()):
                            start_idx = idx
                            break
                    
                    if start_idx == -1:
                        debug_logs.append(f"{log_prefix} ⇒ データ構造の不一致")
                        continue

                    ninki_found_in_race = False
                    # 1頭5行セットで解析
                    for j in range(start_idx, len(lines), 5):
                        if j + 3 >= len(lines) or "結果・成績・オッズ" in lines[j]:
                            break
                        
                        name = lines[j+2].strip()
                        detail = lines[j+3].strip()
                        parts = detail.split()
                        
                        if len(parts) >= 2:
                            n_match = re.search(r'\d+', parts[-1])
                            ninki = float(n_match.group()) if n_match else -1
                            
                            if ninki in target_ninkis:
                                ninki_found_in_race = True
                                # 脚質チェック（詳細行や前後行に「1-3-2」などのパターンがあるか）
                                # ここでは detail 行および horseList 相当のテキスト範囲を探索
                                if re.search(r'[1-3]-\d+-\d+', detail) or re.search(r'[1-3]-\d+-\d+', lines[j+4]):
                                    st.success(f"🔥 {p_name}{r_num}R: {name} ({int(ninki)}人気)")
                                    debug_logs.append(f"{log_prefix} ⇒ 🎯合致！ {name}")
                                    found_any = True
                                else:
                                    debug_logs.append(f"{log_prefix} ⇒ 条件外（{int(ninki)}人気 {name} の脚質不適合）")

                    if not ninki_found_in_race:
                        debug_logs.append(f"{log_prefix} ⇒ 不成立（対象人気 {target_ninkis} 不在）")

                except Exception as e:
                    debug_logs.append(f"{log_prefix} ⇒ ⚠️ エラー")
                
                progress_bar.progress((i + 1) / len(race_ids))
            
            driver.quit()
            st.write("---")
            with st.expander("詳細検証ログ"):
                for log in debug_logs:
                    st.write(log)

    except Exception as e:
        st.error(f"実行エラー: {e}")