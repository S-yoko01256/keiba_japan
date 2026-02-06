import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import time
import re

# --- 設定：MASTER_LIST ---
MASTER_LIST = {
    '阪神': {'ダート': [11.0, 8.0, 9.0, 6.0], '芝': [9.0, 5.0, 6.0, 7.0]},
    '中山': {'ダート': [8.0], '芝': [5.0, 8.0]},
    '京都': {'ダート': [6.0, 8.0, 10.0], '芝': [3.0, 9.0]},
    '東京': {'ダート': [7.0]},
    '福島': {'ダート': [3.0]},
    '小倉': {'芝': [8.0]},
    '新潟': {'芝': [5.0]},
}

PLACE_MAP = {'01':'札幌','02':'函館','03':'福島','04':'新潟','05':'東京','06':'中山','07':'中京','08':'京都','09':'阪神','10':'小倉'}

def get_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.binary_location = "/usr/bin/chromium"
    service = Service("/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=options)

st.title("🏇 逃げ馬スキャナー（shutuba_past 解析版）")

target_date = st.date_input("開催日を選択", value=pd.to_datetime("2026-02-07"))

if st.button("スキャン開始"):
    try:
        df_schedule = pd.read_csv("jra_schedule_2026.csv")
        day_races = df_schedule[(df_schedule['月'] == target_date.month) & (df_schedule['日'] == target_date.day)]
        
        if day_races.empty:
            st.warning("開催データなし")
        else:
            driver = get_driver()
            results = []
            detailed_logs = []

            for _, row in day_races.iterrows():
                p_code = str(row['場所コード']).zfill(2)
                p_name = PLACE_MAP.get(p_code, "不明")
                if p_name not in MASTER_LIST: continue
                
                base_id = f"2026{p_code}{str(row['回']).zfill(2)}{str(row['日次']).zfill(2)}"
                
                for r in range(1, 13):
                    r_id = f"{base_id}{str(r).zfill(2)}"
                    # 事実1: 解析可能なデータが含まれるURLを指定
                    url = f"https://race.netkeiba.com/race/shutuba_past.html?race_id={r_id}"
                    
                    st.write(f"🔍 調査中: {p_name}{r}R ({url})")
                    driver.get(url)
                    time.sleep(2)
                    
                    # コース情報の取得
                    page_source = driver.page_source
                    track = "芝" if "芝" in page_source[:2000] else "ダート" if "ダ" in page_source[:2000] else "不明"
                    
                    if track not in MASTER_LIST[p_name]:
                        detailed_logs.append(f"🚫 【コースNG】{p_name}{r}R: {track}")
                        continue

                    target_ninkis = MASTER_LIST[p_name][track]
                    rows = driver.find_elements("class name", "HorseList")
                    
                    for row_el in rows:
                        text = row_el.text
                        parts = text.split('\n')
                        # ダンプデータに基づき、馬名は通常3番目の要素
                        h_name = parts[2] if len(parts) > 2 else "不明"
                        
                        # 人気の抽出（例：「9人気」）
                        n_match = re.search(r'(\d+)\n人気', text)
                        if n_match:
                            cur_ninki = float(n_match.group(1))
                            
                            if cur_ninki in target_ninkis:
                                # 事実2: ダンプデータ104行目の「7-7」形式を検索
                                # 前走欄から「数字-数字」を抽出し、それが「1-」で始まるか確認
                                pass_matches = re.findall(r'(\d{1,2}-\d{1,2})', text)
                                
                                # pass_matches[0] が前走の通過順
                                if pass_matches and pass_matches[0].startswith("1-"):
                                    results.append({
                                        'レース': f"{p_name}{r}R",
                                        '馬名': h_name,
                                        '人気': f"{int(cur_ninki)}人気",
                                        '前走通過順': pass_matches[0]
                                    })
                                    detailed_logs.append(f"🎯 【合致】{h_name}: 前走{pass_matches[0]}")
                                else:
                                    prev_pos = pass_matches[0] if pass_matches else "不明"
                                    detailed_logs.append(f"❌ 【脚質NG】{h_name}: 前走{prev_pos}")

            driver.quit()
            if results:
                st.table(pd.DataFrame(results))
            else:
                st.info("条件合致なし")
            
            with st.expander("詳細ログ"):
                for log in detailed_logs: st.write(log)

    except Exception as e:
        st.error(f"エラー: {e}")