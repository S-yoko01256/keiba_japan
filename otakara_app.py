import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import time
import re

# 1. 会場別アダプティブ条件（馬体重基準）
ADAPTIVE_PARAMS = {
    '東京': {'weight': 480}, '新潟': {'weight': 480},
    '中京': {'weight': 480}, '中山': {'weight': 490},
    '阪神': {'weight': 490}, '小倉': {'weight': 470},
    '福島': {'weight': 470}, '函館': {'weight': 470},
    '札幌': {'weight': 470}, '京都': {'weight': 470},
}

def get_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    return webdriver.Chrome(options=options)

def scan_race(driver, race_id, venue_name):
    """
    ダンプデータを解析し、『前走先行してバテた大型馬』を抽出。
    競馬場、レース番号、馬番を正確に取得する。
    """
    url = f"https://race.netkeiba.com/race/shutuba_past.html?race_id={race_id}"
    driver.get(url)
    time.sleep(1) 
    
    try:
        all_text = driver.find_element(By.TAG_NAME, "body").text
        lines = all_text.splitlines()
    except:
        return []
    
    params = ADAPTIVE_PARAMS.get(venue_name, {'weight': 470})
    found_horses = []

    for i in range(len(lines)):
        line = lines[i].strip()
        
        # 1. 枠番と馬番の行を見つける (例: "1 1", "8 16")
        num_match = re.match(r'^(\d+)\s+(\d+)$', line)
        if num_match:
            try:
                waku_num = num_match.group(1) # 枠番
                uma_num = num_match.group(2)  # 馬番
                
                horse_name = lines[i+2].strip() # 2行下：馬名
                
                # 馬体重の取得
                current_weight = 0
                for w_idx in range(i+1, i+15):
                    w_match = re.search(r'(\d{3})kg', lines[w_idx])
                    if w_match:
                        current_weight = int(w_match.group(1))
                        break

                # 過去成績（前走）の解析
                past_results = []
                for j in range(i+10, i+60): 
                    if j >= len(lines): break
                    
                    if re.match(r'^\d{4}\.\d{2}\.\d{2}', lines[j]):
                        res_rank = int(lines[j+1].strip()) # 次の行：着順
                        
                        pass_order = "不明"
                        agari_time = 0.0
                        
                        # 通過順と上がりタイム (例: 7-7 (38.9)) を探す
                        for k in range(j+1, j+10):
                            info_match = re.search(r'(\d{1,2}-\d{1,2}(?:-\d{1,2})?)\s+\((\d{2}\.\d)\)', lines[k])
                            if info_match:
                                pass_order = info_match.group(1)
                                agari_time = float(info_match.group(2))
                                break
                        
                        past_results.append({
                            'rank': res_rank,
                            'pass': pass_order,
                            'agari': agari_time
                        })
                        if len(past_results) >= 1: break # 前走のみ

                if not past_results: continue

                # 判定ロジック
                p1 = past_results[0]
                is_dirty = p1['rank'] >= 10
                is_heavy = current_weight >= params['weight']
                
                try:
                    first_pos = int(p1['pass'].split('-')[0])
                    is_front_runner = (first_pos <= 3)
                except:
                    is_front_runner = False
                
                # 条件合致
                if is_dirty and is_heavy and is_front_runner:
                    found_horses.append({
                        '競馬場': venue_name,
                        'R': f"{int(race_id[-2:])}R",
                        '馬番': uma_num,
                        '馬名': horse_name,
                        '体重': f"{current_weight}kg",
                        '前走': f"{p1['rank']}着",
                        '通過': p1['pass'],
                        '上がり': f"{p1['agari']}s",
                        '狙い': "逃げ残り" if p1['agari'] >= 37.0 else "先行粘り"
                    })

            except Exception:
                continue
                
    return found_horses

# --- Streamlit UI ---
st.set_page_config(page_title="お宝馬スキャナー3.2", layout="wide")
st.title("🏇 お宝馬スキャナー Ver 3.2")
st.write("条件：前走10着以下 ＋ 大型馬 ＋ 前走3番手以内（先行力重視）")

try:
    df_schedule = pd.read_csv('jra_schedule_2026.csv')
    df_schedule['表示用日付'] = df_schedule['月'].astype(str) + "月" + df_schedule['日'].astype(str) + "日"
    available_dates = df_schedule['表示用日付'].unique()
    selected_date_str = st.selectbox("開催日を選択", available_dates)

    if st.button("全レース一括スキャン開始"):
        today_venues = df_schedule[df_schedule['表示用日付'] == selected_date_str]
        
        all_results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        driver = get_driver()
        try:
            total_venues = len(today_venues)
            for idx, row in today_venues.reset_index().iterrows():
                v_name = row['場所']  
                v_code = str(row['場所コード']).zfill(2) 
                kai = str(row['回']).zfill(2)
                nichiji = str(row['日次']).zfill(2) 
                base_id = f"2026{v_code}{kai}{nichiji}"
                
                for r in range(1, 13):
                    r_str = str(r).zfill(2)
                    race_id = f"{base_id}{r_str}"
                    status_text.text(f"【{v_name}】{r}R 解析中...")
                    
                    hits = scan_race(driver, race_id, v_name)
                    all_results.extend(hits)
                
                progress_bar.progress((idx + 1) / total_venues)

            status_text.text("スキャン完了！")
            
            if all_results:
                st.success(f"🎯 期待値の高い先行馬が {len(all_results)} 頭見つかりました")
                # 表の表示
                output_df = pd.DataFrame(all_results)
                st.table(output_df[['競馬場', 'R', '馬番', '馬名', '体重', '前走', '通過', '上がり', '狙い']])
            else:
                st.info("条件に合う馬は見つかりませんでした。")
        finally:
            driver.quit()

except Exception as e:
    st.error(f"エラー: {e}")