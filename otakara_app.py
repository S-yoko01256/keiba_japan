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
    ダンプデータを解析し、単なるデブ馬ではなく
    『前走先行してバテた大型馬』を抽出する
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
        
        # 1. 馬番行を見つける (例: "1 1")
        if re.match(r'^\d+\s+\d+$', line):
            try:
                # 基本情報の取得
                horse_name = lines[i+2].strip() # 2行下：馬名
                
                # 馬体重の取得（9行下付近から抽出）
                current_weight = 0
                for w_idx in range(i+1, i+15):
                    w_match = re.search(r'(\d{3})kg', lines[w_idx])
                    if w_match:
                        current_weight = int(w_match.group(1))
                        break

                # 過去成績の解析（先行力と上がりのチェック）
                # ダンプから「日付」「着順」「通過順(上がり)」「馬体重」の4点セットを正確に抜く
                past_results = []
                for j in range(i+10, i+60): # 過去5走分をカバーする範囲
                    if j >= len(lines): break
                    
                    # 日付行を見つけたら、そこから成績をセットで取得
                    if re.match(r'^\d{4}\.\d{2}\.\d{2}', lines[j]):
                        res_rank = int(lines[j+1].strip()) # 次の行：着順
                        
                        # 通過順と上がりタイムを抽出 (例: "7-7 (38.9)")
                        pass_order = "不明"
                        agari_time = 0.0
                        
                        # 日付から数行先まで通過順・上がりを探す
                        for k in range(j+1, j+10):
                            # 通過順と上がりタイムのパターン (例: 7-7 (38.9))
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
                        if len(past_results) >= 2: break # 前走と前々走だけでOK

                if not past_results: continue

                # --- 3-2型：最強の絞り込み条件 ---
                
                # 1. 前走の結果を取得
                p1 = past_results[0]
                
                # 汚れ条件：前走が10着以下
                is_dirty = p1['rank'] >= 10
                
                # 馬体重条件：会場別基準をクリア
                is_heavy = current_weight >= params['weight']
                
                # 先行意欲条件：前走の最初の通過順が「3番手以内」
                # 例: "1-1", "2-3-4" の最初の数字を見る
                try:
                    first_pos = int(p1['pass'].split('-')[0])
                    is_front_runner = (first_pos <= 3)
                except:
                    is_front_runner = False
                
                # 上がり条件：逃げ切りを狙うなら、上がりが37.0秒以上（＝バテた）が理想
                # (速すぎると次走人気になるため)
                is_slow_finish = p1['agari'] >= 37.0

                # すべての条件が合致した馬だけを「本当のお宝馬」とする
                if is_dirty and is_heavy and is_front_runner:
                    found_horses.append({
                        'R': f"{race_id[-2:]}R",
                        '馬名': horse_name,
                        '体重': f"{current_weight}kg",
                        '前走着順': f"{p1['rank']}着",
                        '前走通過': p1['pass'],
                        '上がり': f"{p1['agari']}s",
                        '判定': "🔥先行残り期待" if is_slow_finish else "⚡️先行力あり"
                    })

            except Exception:
                continue
                
    return found_horses

# --- Streamlit UI ---
st.set_page_config(page_title="お宝馬スキャナー3.2", layout="wide")
st.title("🏇 お宝馬スキャナー Ver 3.2 (先行・上がり精査版)")
st.write("『前走10着以下＋大型馬＋前走3番手以内』の馬を抽出します。")

try:
    # 1. CSV読み込み
    df_schedule = pd.read_csv('jra_schedule_2026.csv')
    df_schedule['表示用日付'] = df_schedule['月'].astype(str) + "月" + df_schedule['日'].astype(str) + "日"
    available_dates = df_schedule['表示用日付'].unique()
    selected_date_str = st.selectbox("開催日を選択", available_dates)

    if st.button("全レース一括スキャン開始"):
        today_venues = df_schedule[df_schedule['表示用日付'] == selected_date_str]
        
        results = []
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
                    status_text.text(f"【{v_name}】{r}R を解析中... (ID: {race_id})")
                    
                    hits = scan_race(driver, race_id, v_name)
                    results.extend(hits)
                
                progress_bar.progress((idx + 1) / total_venues)

            status_text.text("すべてのスキャンが完了しました。")
            
            if results:
                st.success(f"🎯 厳選されたお宝候補が {len(results)} 頭見つかりました！")
                st.table(pd.DataFrame(results))
            else:
                st.info("条件に合致する「先行・大型・汚れ馬」は見つかりませんでした。")
        finally:
            driver.quit()

except Exception as e:
    st.error(f"エラーが発生しました: {e}")