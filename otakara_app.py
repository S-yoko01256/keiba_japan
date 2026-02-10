import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import re

# 1. シミュレーション結果に基づく会場別アダプティブ条件 
ADAPTIVE_PARAMS = {
    '東京': {'weight': 480, 'pos': 1},
    '新潟': {'weight': 480, 'pos': 1},
    '中京': {'weight': 480, 'pos': 1},
    '中山': {'weight': 490, 'pos': 2},
    '阪神': {'weight': 490, 'pos': 2},
    '小倉': {'weight': 470, 'pos': 3},
    '福島': {'weight': 470, 'pos': 3},
    '函館': {'weight': 470, 'pos': 3},
    '札幌': {'weight': 470, 'pos': 3},
    '京都': {'weight': 470, 'pos': 3},
}

def get_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=options)
    return driver

def scan_race(driver, race_id, venue_name):
    url = f"https://race.netkeiba.com/race/shutuba_past.html?race_id={race_id}"
    driver.get(url)
    time.sleep(3) # 読み込み待ち
    
    all_text = driver.find_element(By.TAG_NAME, "body").text
    lines = all_text.splitlines()
    
    params = ADAPTIVE_PARAMS.get(venue_name, {'weight': 470, 'pos': 3})
    found_horses = []

    # ダンプ解析に基づいたスキャン 
    for i in range(len(lines)):
        line = lines[i].strip()
        
        # 1. 「枠 馬番」のパターンを発見 (例: "1 1")
        if re.match(r'^\d+\s+\d+$', line):
            try:
                # 2. 馬名の特定 (馬番の2〜3行下)
                horse_name = lines[i+2].strip()
                
                # 3. 馬体重の特定 (馬名の後に出現する "466kg(-4)" 形式)
                current_weight = 0
                for j in range(i+1, i+15):
                    w_match = re.search(r'(\d{3})kg', lines[j])
                    if w_match:
                        current_weight = int(w_match.group(1))
                        break
                
                # 4. 前走・前々走の汚れチェック (日付行 "2025.11.29" を起点に探索) 
                ranks = []
                for k in range(i+1, i+100): # 次の馬番が出るまで探索
                    if re.match(r'^\d+\s+\d+$', lines[k].strip()) and k > i: break
                    
                    if re.match(r'^\d{4}\.\d{2}\.\d{2}', lines[k]): # 日付発見
                        rank_val = lines[k+1].strip()
                        if rank_val.isdigit():
                            ranks.append(int(rank_val))
                
                # --- 判定セクション（シミュレーション条件に完全準拠） ---
                # 条件A: 汚れ（前走or前々走が10着以下）
                dirt_flag = any(r >= 10 for r in ranks[:2])
                
                # 条件B: 馬体重（会場別しきい値）
                weight_flag = current_weight >= params['weight']
                
                if dirt_flag and weight_flag:
                    found_horses.append({
                        'レース': f"{venue_name}{race_id[-2:]}R",
                        '馬名': horse_name,
                        '馬体重': f"{current_weight}kg",
                        '前走着順': ranks[0] if ranks else "不明",
                        '前々走': ranks[1] if len(ranks) > 1 else "-"
                    })
            except Exception:
                continue
                
    return found_horses

# --- Streamlit UI ---
st.title("🏇 シミュレーション準拠・お宝馬スキャナー")

# 開催場所とレース番号を指定（実際はスケジュール読み込みと連動可能）
venue = st.selectbox("会場", list(ADAPTIVE_PARAMS.keys()))
race_num = st.selectbox("レース番号", [str(i).zfill(2) for i in range(1, 13)])
target_id = st.text_input("レースID (例: 202605010302)", value=f"2026050103{race_num}")

if st.button("スキャン実行"):
    with st.spinner('データを解析中...'):
        driver = get_driver()
        try:
            hits = scan_race(driver, target_id, venue)
            if hits:
                st.success(f"🎯 条件合致馬が {len(hits)} 頭見つかりました！")
                st.table(pd.DataFrame(hits))
            else:
                st.info("条件に合う馬は見つかりませんでした。")
        finally:
            driver.quit()