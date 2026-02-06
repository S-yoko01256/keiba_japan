import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import re
import time

# --- 判定ロジック：回収率85%以上の条件リスト ---
MASTER_LIST = {
    '阪神': {'ダート': [11.0, 8.0, 9.0, 6.0], '芝': [9.0, 5.0, 6.0, 7.0]},
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
    options.add_argument('--disable-gpu')
    # Streamlit Cloud環境での動作を安定させる設定
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)

st.set_page_config(page_title="お宝馬アラート", page_icon="🏇")
st.title("🏇 心理の歪み・お宝馬サーチ")
st.caption("35年統計：特定の不人気×逃げ実績馬をリアルタイム検知")

# 日付選択（デフォルトは実行日の日付）
target_date_dt = st.date_input("実行日を選択", pd.to_datetime("today"))
target_date = target_date_dt.strftime('%Y%m%d')

if st.button("全会場スキャン開始"):
    driver = get_driver()
    wait = WebDriverWait(driver, 15)
    found_any = False
    
    with st.spinner("今日の開催レースを確認中..."):
        # 1. 開催一覧ページを開いてレースIDを自動取得（高速化修正）
        top_url = f"https://race.netkeiba.com/top/race_list.html?kasai_date={target_date}"
        driver.get(top_url)
        time.sleep(2) # 読み込み待ち

        links = driver.find_elements(By.TAG_NAME, "a")
        race_ids = []
        for link in links:
            href = link.get_attribute("href")
            if href and "race_id=" in href:
                match = re.search(r'race_id=(\d{12})', href)
                if match:
                    race_ids.append(match.group(1))
        
        # 重複を排除して昇順に並べ替え
        race_ids = sorted(list(set(race_ids)))

        if not race_ids:
            st.warning(f"{target_date} の開催レースが見つかりませんでした。日付を確認してください。")
        else:
            st.info(f"🔍 {len(race_ids)}件のレースを検知しました。順番にスキャンします。")
            
            # 2. 抽出したレースIDを巡回
            for rid in race_ids:
                p_code = rid[4:6]  # 競馬場コード
                p_name = PLACE_MAP.get(p_code)
                
                if not p_name: continue # リスト外の競馬場（地方など）はスキップ
                
                r_num = int(rid[10:12]) # レース番号

                driver.get(f"https://race.netkeiba.com/race/shutuba.html?race_id={rid}")
                
                try:
                    # 出馬表の読み込みを待機
                    wait.until(EC.presence_of_element_located((By.CLASS_NAME, "HorseList")))
                    
                    # 芝・ダートの判定
                    race_data = driver.find_element(By.CLASS_NAME, "RaceData01").text
                    track = "芝" if "芝" in race_data else "ダート"
                    
                    # 条件に合致する競馬場・トラックか確認
                    if p_name in MASTER_LIST and track in MASTER_LIST[p_name]:
                        target_ninkis = MASTER_LIST[p_name][track]
                        rows = driver.find_elements(By.CLASS_NAME, "HorseList")
                        
                        for row in rows:
                            try:
                                # 人気順を取得
                                ninki_text = row.find_element(By.CLASS_NAME, "Ninki").text
                                if not ninki_text or ninki_text == " ": continue
                                
                                ninki = float(ninki_text)
                                
                                # 統計上の人気条件に合致するか
                                if ninki in target_ninkis:
                                    name = row.find_element(By.CLASS_NAME, "HorseName").text
                                    
                                    # 逃げ・先行実績の判定（近走のどこかで3番手以内）
                                    if re.search(r'[1-3]-\d+-\d+', row.text):
                                        st.success(f"🔥 【お宝発見】{p_name}{r_num}R ({track}) {name} - {ninki}人気")
                                        found_any = True
                            except:
                                continue
                except Exception as e:
                    # レース詳細の読み込み失敗時は次へ
                    continue

    if not found_any:
        st.warning("本日の条件に合致する馬は見つかりませんでした。")
    
    st.write("スキャン完了しました。")
    driver.quit()