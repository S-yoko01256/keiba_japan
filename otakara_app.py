import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
import time
import re

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
    
    # 事実：タイムアウトを防ぐための高速化設定
    options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
    options.page_load_strategy = 'eager'
    
    # 修正の事実：DriverManagerに「今動いているChrome」のバージョンを自動判定させる
    from selenium.webdriver.chrome.service import Service as ChromeService
    from webdriver_manager.chrome import ChromeDriverManager
    
    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    driver.set_page_load_timeout(60)
    return driver  


st.title("🏇 逃げ馬スキャナー（最速・事実判定版）")

target_date = st.date_input("開催日を選択", value=pd.to_datetime("2026-02-07"))

if st.button("スキャン開始"):
    try:
        # CSVからスケジュール読み込み
        df_schedule = pd.read_csv("jra_schedule_2026.csv")
        day_races = df_schedule[(df_schedule['月'] == target_date.month) & (df_schedule['日'] == target_date.day)]
        
        if day_races.empty:
            st.warning("指定日の開催データがありません。")
        else:
            driver = get_driver()
            results = []
            detailed_logs = []

            # 会場の絞り込み（MASTER_LISTにある会場のみ）
            target_queues = []
            for _, row in day_races.iterrows():
                p_code = str(row['場所コード']).zfill(2)
                p_name = PLACE_MAP.get(p_code, "不明")
                if p_name in MASTER_LIST:
                    target_queues.append({
                        'name': p_name,
                        'base_id': f"2026{p_code}{str(row['回']).zfill(2)}{str(row['日次']).zfill(2)}"
                    })

            total_races = len(target_queues) * 12
            current_count = 0
            progress_bar = st.progress(0)

            for queue in target_queues:
                for r in range(1, 13):
                    current_count += 1
                    r_id = f"{queue['base_id']}{str(r).zfill(2)}"
                    # あなたがダンプした、前走情報が含まれるURL
                    url = f"https://race.netkeiba.com/race/shutuba_past.html?race_id={r_id}"
                    
                    st.write(f"⌛ スキャン中 ({current_count}/{total_races}): {queue['name']}{r}R")
                    
                    try:
                        driver.get(url)
                        # 文字が読み込まれるまで最小限の待機
                        time.sleep(1)

                        # コース判定
                        page_text_top = driver.find_element(By.TAG_NAME, "body").text[:2000]
                        track = "芝" if "芝" in page_text_top else "ダート" if "ダ" in page_text_top else "不明"
                        
                        if track not in MASTER_LIST[queue['name']]:
                            detailed_logs.append(f"🚫 {queue['name']}{r}R: {track}は対象外")
                            continue

                        target_ninkis = MASTER_LIST[queue['name']][track]
                        rows = driver.find_elements(By.CLASS_NAME, "HorseList")
                        
                        for row in rows:
                            text = row.text
                            # 1. 人気の抽出（ダンプ 094行目形式に対応）
                            n_match = re.search(r'\((\d+)人気\)', text)
                            if n_match:
                                cur_ninki = float(n_match.group(1))
                                if cur_ninki in target_ninkis:
                                    # 2. 前走通過順の抽出（ダンプ 104行目形式に対応）
                                    # 1-1 や 1-1-1 のどちらでも「1-」で始まれば逃げとみなす
                                    pass_matches = re.findall(r'(\d{1,2}-\d{1,2})', text)
                                    
                                    if pass_matches and pass_matches[0].startswith("1-"):
                                        h_name = text.split('\n')[2]
                                        results.append({
                                            'レース': f"{queue['name']}{r}R",
                                            '馬名': h_name,
                                            '人気': f"{int(cur_ninki)}人気",
                                            '通過順': pass_matches[0]
                                        })
                                        detailed_logs.append(f"🎯 合致: {h_name} ({pass_matches[0]})")
                                    else:
                                        detailed_logs.append(f"❌ 脚質NG: {int(cur_ninki)}人気馬")

                    except Exception as e:
                        st.error(f"⚠️ {queue['name']}{r}R でタイムアウトまたはエラー発生: {e}")
                        # タイムアウト時はドライバを再起動して詰まりを解消
                        driver.quit()
                        driver = get_driver()
                    
                    progress_bar.progress(current_count / total_races)

            driver.quit()

            if results:
                st.success(f"{len(results)}頭の候補が見つかりました。")
                st.table(pd.DataFrame(results))
            else:
                st.info("条件に合う馬はいませんでした。")

            with st.expander("詳細ログを確認"):
                for log in detailed_logs: st.write(log)

    except Exception as e:
        st.error(f"致命的なエラー: {e}")