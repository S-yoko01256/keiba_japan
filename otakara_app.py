import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import re

# 会場名と場所コードの変換マップ（CSVの「場所名」と一致させる）
VENUE_MAP = {
    '札幌': '01', '函館': '02', '福島': '03', '新潟': '04', '東京': '05',
    '中山': '06', '中京': '07', '京都': '08', '阪神': '09', '小倉': '10'
}

ADAPTIVE_PARAMS = {
    '東京': {'weight': 480, 'pos': 1}, '新潟': {'weight': 480, 'pos': 1},
    '中京': {'weight': 480, 'pos': 1}, '中山': {'weight': 490, 'pos': 2},
    '阪神': {'weight': 490, 'pos': 2}, '小倉': {'weight': 470, 'pos': 3},
    '福島': {'weight': 470, 'pos': 3}, '函館': {'weight': 470, 'pos': 3},
    '札幌': {'weight': 470, 'pos': 3}, '京都': {'weight': 470, 'pos': 3},
}

def get_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    return webdriver.Chrome(options=options)

def scan_race(driver, race_id, venue_name):
    """判定ロジック（汚れ馬・馬体重）はそのまま維持"""
    url = f"https://race.netkeiba.com/race/shutuba_past.html?race_id={race_id}"
    driver.get(url)
    time.sleep(1) 
    
    try:
        all_text = driver.find_element(By.TAG_NAME, "body").text
        lines = all_text.splitlines()
    except:
        return []
    
    params = ADAPTIVE_PARAMS.get(venue_name, {'weight': 470, 'pos': 3})
    found_horses = []

    for i in range(len(lines)):
        line = lines[i].strip()
        if re.match(r'^\d+\s+\d+$', line):
            try:
                horse_name = lines[i+2].strip()
                current_weight = 0
                for j in range(i+1, i+15):
                    w_match = re.search(r'(\d{3})kg', lines[j])
                    if w_match:
                        current_weight = int(w_match.group(1))
                        break
                
                ranks = []
                for k in range(i+1, i+100):
                    if k >= len(lines): break
                    if re.match(r'^\d+\s+\d+$', lines[k].strip()) and k > i: break
                    if re.match(r'^\d{4}\.\d{2}\.\d{2}', lines[k]):
                        rank_val = lines[k+1].strip()
                        if rank_val.isdigit():
                            ranks.append(int(rank_val))
                
                dirt_flag = any(r >= 10 for r in ranks[:2])
                weight_flag = current_weight >= params['weight']
                
                if dirt_flag and weight_flag:
                    found_horses.append({
                        'R': f"{race_id[-2:]}R",
                        '会場': venue_name,
                        '馬名': horse_name,
                        '体重': f"{current_weight}kg",
                        '前走': ranks[0] if ranks else "-",
                        '前々': ranks[1] if len(ranks) > 1 else "-"
                    })
            except Exception:
                continue
    return found_horses

# --- UI部 ---
st.set_page_config(page_title="お宝馬一括スキャナー", layout="wide")
st.title("🏇 2026年度版 全レース一括スキャナー")

try:
    # CSV読み込み
    df_schedule = pd.read_csv('jra_schedule_2026.csv')
    
    # CSVの「月」と「日」を組み合わせて選択肢を作る
    df_schedule['表示用日付'] = df_schedule['月'].astype(str) + "月" + df_schedule['日'].astype(str) + "日"
    available_dates = df_schedule['表示用日付'].unique()
    
    selected_date_str = st.selectbox("スキャンする日を選択", available_dates)

    if st.button("全レーススキャン開始"):
        # 選択された日のデータを抽出
        today_venues = df_schedule[df_schedule['表示用日付'] == selected_date_str]
        
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        driver = get_driver()
        try:
            total_venues = len(today_venues)
            for idx, row in today_venues.reset_index().iterrows():
                v_name = row['場所名'] # CSVの列名「場所名」を使用
                v_code = str(row['場所コード']).zfill(2) # CSVの「場所コード」を使用
                
                # レースIDの組み立て
                # 年(2026) + 場所コード(2桁) + 回(2桁) + 日(2桁)
                kai = str(row['回']).zfill(2)
                nichiji = str(row['日']).zfill(2) # CSVの最後の「日」列（日次）を使用
                base_id = f"2026{v_code}{kai}{nichiji}"
                
                for r in range(1, 13):
                    r_str = str(r).zfill(2)
                    race_id = f"{base_id}{r_str}"
                    status_text.text(f"スキャン中: {v_name} {r}R (ID: {race_id})")
                    
                    hits = scan_race(driver, race_id, v_name)
                    results.extend(hits)
                
                progress_bar.progress((idx + 1) / total_venues)

            status_text.text("スキャン完了！")
            if results:
                st.success(f"🎯 合計 {len(results)} 頭のお宝候補が見つかりました")
                st.table(pd.DataFrame(results))
            else:
                st.info("条件に合う馬は見つかりませんでした。")
        finally:
            driver.quit()

except Exception as e:
    st.error(f"エラーが発生しました: {e}")
    st.write("CSVの列名を確認してください:", df_schedule.columns.tolist() if 'df_schedule' in locals() else "読み込み失敗")