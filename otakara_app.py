import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import re

# --- 1. 設定：MASTER_LIST（出現頻度が高く、かつ儲かるリスト） ---
MASTER_LIST = {
    '阪神': {'ダート': [11.0, 8.0, 9.0, 6.0], '芝': [9.0, 5.0, 6.0, 7.0]},
    '中山': {'ダート': [8.0], '芝': [5.0, 8.0]},
    '京都': {'ダート': [6.0, 8.0, 10.0], '芝': [3.0, 9.0]},
    '東京': {'ダート': [7.0]},
    '福島': {'ダート': [3.0]},
    '小倉': {'芝': [8.0]},
    '新潟': {'芝': [5.0]},
}

PLACE_MAP = {
    '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
    '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉'
}

def get_driver():
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    # バージョンエラー対策：バイナリパス固定
    options.binary_location = "/usr/bin/chromium"
    
    # サービスの設定（システムのchromedriverを優先使用）
    try:
        service = Service("/usr/bin/chromedriver")
        return webdriver.Chrome(service=service, options=options)
    except:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)

# --- Streamlit UI ---
st.title("🔥 逃げ馬「NG理由可視化」スキャナー")
st.write("指定条件から外れた理由（コース・人気・脚質）をすべてログに残します。")

target_date = st.date_input("開催日を選択してください", value=pd.to_datetime("2026-02-07"))

if st.button("スキャン開始"):
    try:
        # 1. スケジュール読み込み
        df_schedule = pd.read_csv("jra_schedule_2026.csv")
        day_races = df_schedule[(df_schedule['月'] == target_date.month) & (df_schedule['日'] == target_date.day)]
        
        if day_races.empty:
            st.warning("開催データなし")
        else:
            # 2. 競馬場による事前フィルタリング
            target_queues = []
            for _, row in day_races.iterrows():
                p_name = PLACE_MAP.get(str(row['場所コード']).zfill(2), "不明")
                if p_name in MASTER_LIST:
                    p_code = str(row['場所コード']).zfill(2)
                    kai = str(row['回']).zfill(2)
                    nichiji = str(row['日次']).zfill(2)
                    target_queues.append({'name': p_name, 'base_id': f"2026{p_code}{kai}{nichiji}"})
            
            if not target_queues:
                st.info("本日の開催にMASTER_LIST対象の競馬場はありません。")
            else:
                driver = get_driver()
                results = []
                detailed_logs = []
                
                total_races = len(target_queues) * 12
                progress_bar = st.progress(0)
                current_count = 0

                for queue in target_queues:
                    for r in range(1, 13):
                        current_count += 1
                        r_id = f"{queue['base_id']}{str(r).zfill(2)}"
                        url = f"https://race.netkeiba.com/race/shutuba.aspx?race_id={r_id}"
                        
                        driver.get(url)
                        time.sleep(1)
                        
                        # レース情報の取得
                        header = driver.find_element("tag name", "body").text.split('\n')[0]
                        track = "芝" if "芝" in header else "ダート" if "ダート" in header else "不明"
                        
                        # --- 【NG理由1：コース不一致】 ---
                        if track not in MASTER_LIST[queue['name']]:
                            detailed_logs.append(f"🚫 【コースNG】{queue['name']}{r}R: {track} の条件が設定されていません")
                            progress_bar.progress(current_count / total_races)
                            continue

                        target_ninkis = MASTER_LIST[queue['name']][track]
                        rows = driver.find_elements("class name", "HorseList")
                        ninki_found_in_race = False
                        
                        for row_el in rows:
                            text = row_el.text
                            # 馬名の抽出（3行目と想定）
                            parts = text.split('\n')
                            h_name = parts[2] if len(parts) > 2 else "不明"
                            
                            # 人気の抽出
                            n_match = re.search(r'(\d+)\n人気', text)
                            if n_match:
                                cur_ninki = float(n_match.group(1))
                                
                                # --- 【NG理由2：人気不一致はログが膨大になるため、合致した時のみ次へ】 ---
                                if cur_ninki in target_ninkis:
                                    ninki_found_in_race = True
                                    # --- 【NG理由3：脚質不一致（1番手ではない）】 ---
                                    if re.search(r'1-\d+-\d+', text):
                                        results.append({
                                            'レース': f"{queue['name']}{r}R",
                                            '馬名': h_name,
                                            '人気': f"{int(cur_ninki)}人気",
                                            '区分': track
                                        })
                                        detailed_logs.append(f"🎯 【合致】{queue['name']}{r}R: {h_name} ({int(cur_ninki)}人気 / 前走逃げ)")
                                    else:
                                        detailed_logs.append(f"❌ 【脚質NG】{queue['name']}{r}R: {h_name} ({int(cur_ninki)}人気ですが、前走1番手ではありません)")
                        
                        if not ninki_found_in_race:
                            detailed_logs.append(f"☁️ 【人気NG】{queue['name']}{r}R: 対象人気 {target_ninkis} の馬がいませんでした")

                        progress_bar.progress(current_count / total_races)
                
                driver.quit()

                # 結果表示
                if results:
                    st.success(f"発見！ {len(results)}頭の候補")
                    st.table(pd.DataFrame(results))
                else:
                    st.info("条件合致なし。詳細は下のログを確認してください。")

                with st.expander("🔍 なぜ外れたか（判定ログ）"):
                    for log in detailed_logs:
                        st.write(log)

    except Exception as e:
        st.error(f"エラー: {e}")