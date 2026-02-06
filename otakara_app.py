import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import re

# --- 1. 設定：MASTER_LIST（分析データに基づく「儲かる」条件） ---
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
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

# --- Streamlit UI ---
st.title("🔥 逃げ馬「お宝」最速スキャナー")
st.write("設定された競馬場と人気条件に合致する馬だけを狙い撃ちします。")

target_date = st.date_input("開催日を選択してください", value=pd.to_datetime("2026-02-07"))

if st.button("スキャン開始"):
    try:
        # 1. スケジュールの読み込み
        df_schedule = pd.read_csv("jra_schedule_2026.csv")
        day_races = df_schedule[(df_schedule['月'] == target_date.month) & (df_schedule['日'] == target_date.day)]
        
        if day_races.empty:
            st.warning("指定日の開催データがありません。")
        else:
            # 2. ロジック対象の場所だけを抽出してURLを生成
            target_queues = []
            for _, row in day_races.iterrows():
                p_name = PLACE_MAP.get(str(row['場所コード']).zfill(2), "不明")
                if p_name in MASTER_LIST:
                    p_code = str(row['場所コード']).zfill(2)
                    kai = str(row['回']).zfill(2)
                    nichiji = str(row['日次']).zfill(2)
                    target_queues.append({'name': p_name, 'base_id': f"2026{p_code}{kai}{nichiji}"})
            
            if not target_queues:
                st.info("本日の開催にロジック対象の競馬場（阪神・中山等）はありません。")
            else:
                driver = get_driver()
                results = []
                debug_logs = []
                
                # 3. 対象競馬場の1〜12Rをスキャン
                total_races = len(target_queues) * 12
                progress_bar = st.progress(0)
                current_count = 0

                for queue in target_queues:
                    for r in range(1, 13):
                        current_count += 1
                        r_id = f"{queue['base_id']}{str(r).zfill(2)}"
                        url = f"https://race.netkeiba.com/race/shutuba.aspx?race_id={r_id}"
                        
                        driver.get(url)
                        time.sleep(1) # 最低限の待機
                        
                        # 芝・ダートの判定
                        race_header = driver.find_element("tag name", "body").text.split('\n')[0]
                        track = "芝" if "芝" in race_header else "ダート" if "ダート" in race_header else None
                        
                        # その競馬場のそのコース（芝/ダ）に条件がある場合のみ解析
                        if track and track in MASTER_LIST[queue['name']]:
                            target_ninkis = MASTER_LIST[queue['name']][track]
                            rows = driver.find_elements("class name", "HorseList")
                            
                            for row_el in rows:
                                row_text = row_el.text
                                ninki_match = re.search(r'(\d+)\n人気', row_text)
                                if ninki_match and float(ninki_match.group(1)) in target_ninkis:
                                    # 「前走1番手（逃げ）」の判定
                                    if re.search(r'1-\d+-\d+', row_text):
                                        horse_name = row_text.split('\n')[2]
                                        results.append({
                                            'レース': f"{queue['name']}{r}R",
                                            '馬名': horse_name,
                                            '人気': f"{int(float(ninki_match.group(1)))}人気",
                                            '区分': track,
                                            'リンク': url
                                        })
                                        debug_logs.append(f"✅ {queue['name']}{r}R: {horse_name} 発見")

                        progress_bar.progress(current_count / total_races)
                
                driver.quit()

                # 4. 結果表示
                if results:
                    st.success(f"スキャン完了！ {len(results)}頭の候補が見つかりました。")
                    st.table(pd.DataFrame(results))
                else:
                    st.info("条件に合致する馬は見つかりませんでした。")

                with st.expander("詳細ログ"):
                    for log in debug_logs: st.write(log)

    except Exception as e:
        st.error(f"エラー: {e}")