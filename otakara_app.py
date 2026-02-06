import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import time
import re
import os

# --- 1. 設定：MASTER_LIST ---
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
    options.add_argument('--disable-gpu')
    
    # 【最強のエラー対策】
    # 自動更新ツールを使わず、システム標準のパスを直接指定します
    options.binary_location = "/usr/bin/chromium"
    
    # 多くの環境で標準的に配置されているchromedriverのパスを直接指定
    # もしこれでダメな場合は、Service() の引数を空にするか修正します
    chrome_service = Service("/usr/bin/chromedriver")
    
    try:
        return webdriver.Chrome(service=chrome_service, options=options)
    except:
        # 上記で失敗した場合、パス指定なしでシステムのパス設定(PATH)に任せる
        return webdriver.Chrome(options=options)

# --- Streamlit UI ---
st.title("🔥 逃げ馬「お宝」最速スキャナー")
st.write("ブラウザバージョン不整合を回避する特別設定版です。")

target_date = st.date_input("開催日を選択してください", value=pd.to_datetime("2026-02-07"))

if st.button("スキャン開始"):
    try:
        df_schedule = pd.read_csv("jra_schedule_2026.csv")
        day_races = df_schedule[(df_schedule['月'] == target_date.month) & (df_schedule['日'] == target_date.day)]
        
        if day_races.empty:
            st.warning("指定日の開催データがありません。")
        else:
            target_queues = []
            for _, row in day_races.iterrows():
                p_name = PLACE_MAP.get(str(row['場所コード']).zfill(2), "不明")
                if p_name in MASTER_LIST:
                    p_code = str(row['場所コード']).zfill(2)
                    kai = str(row['回']).zfill(2)
                    nichiji = str(row['日次']).zfill(2)
                    target_queues.append({'name': p_name, 'base_id': f"2026{p_code}{kai}{nichiji}"})
            
            if not target_queues:
                st.info("本日の開催に対象の競馬場はありません。")
            else:
                driver = get_driver()
                results = []
                
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
                        
                        race_header = driver.find_element("tag name", "body").text.split('\n')[0]
                        track = "芝" if "芝" in race_header else "ダート" if "ダート" in race_header else None
                        
                        if track and track in MASTER_LIST[queue['name']]:
                            target_ninkis = MASTER_LIST[queue['name']][track]
                            rows = driver.find_elements("class name", "HorseList")
                            
                            for row_el in rows:
                                text = row_el.text
                                ninki_match = re.search(r'(\d+)\n人気', text)
                                if ninki_match and float(ninki_match.group(1)) in target_ninkis:
                                    # 逃げ判定（1コーナー先頭）
                                    if re.search(r'1-\d+-\d+', text):
                                        horse_name = text.split('\n')[2]
                                        results.append({
                                            'レース': f"{queue['name']}{r}R",
                                            '馬名': horse_name,
                                            '人気': f"{int(float(ninki_match.group(1)))}人気",
                                            '区分': track,
                                            'リンク': url
                                        })

                        progress_bar.progress(current_count / total_races)
                
                driver.quit()

                if results:
                    st.success(f"発見！ {len(results)}頭の候補")
                    st.table(pd.DataFrame(results))
                else:
                    st.info("条件に合う馬はいませんでした。")

    except Exception as e:
        st.error(f"致命的なエラーが発生しました。環境設定を確認してください: {e}")