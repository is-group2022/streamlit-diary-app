import streamlit as st
import pandas as pd
import gspread
import datetime
import urllib.parse
import re
from google.cloud import storage

# --- 1. 設定 ---
SHEET_ID = st.secrets["google_resources"]["spreadsheet_id"]
GCS_BUCKET_NAME = "auto-poster-images"

# --- 2. 補助関数 (マッチングの核) ---

def normalize_time(t_str):
    """'00:48' や '0048' を timeオブジェクトに変換"""
    t_str = re.sub(r'[^0-9]', '', str(t_str))
    if len(t_str) == 3: t_str = "0" + t_str
    if len(t_str) == 4:
        return datetime.datetime.strptime(t_str, "%H%M")
    return None

def is_time_in_range(base_time, target_str, window_min=20):
    """ファイル名の先頭数字が base_time の±20分以内か判定"""
    target_num = re.match(r'^(\d{3,4})', target_str)
    if not target_num: return False
    
    try:
        t_target = normalize_time(target_num.group(1))
        if not t_target or not base_time: return False
        
        # 日付を固定して差分を計算
        diff = abs((base_time - t_target).total_seconds()) / 60
        # 深夜の跨ぎを考慮 (23:55 と 00:05 など)
        return diff <= window_min or diff >= (1440 - window_min)
    except:
        return False

def get_cached_url(blob_name):
    safe_path = urllib.parse.quote(blob_name)
    return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{safe_path}"

# --- 3. API連携 ---
@st.cache_resource(ttl=3600)
def get_clients():
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    gcs = storage.Client.from_service_account_info(st.secrets["gcp_service_account"])
    return gc, gcs

GC, GCS_CLIENT = get_clients()
SPRS = GC.open_by_key(SHEET_ID)

# --- 4. UI ---
st.set_page_config(layout="wide", page_title="高度なマッチング編集")

def main():
    st.title("🔍 高度な日記×画像マッチング")

    # データ読み込み
    all_ws = SPRS.worksheets()
    target_sheets = ["投稿Aアカウント", "投稿Bアカウント", "投稿Cアカウント", "投稿Dアカウント"]
    all_rows = []
    for ws in all_ws:
        if ws.title in target_sheets:
            data = ws.get_all_values()
            if len(data) > 1:
                tmp_df = pd.DataFrame(data[1:], columns=data[0][:7])
                tmp_df['__sheet__'] = ws.title
                tmp_df['__row__'] = range(2, len(data) + 1)
                all_rows.append(tmp_df)
    
    if not all_rows: return
    full_df = pd.concat(all_rows)

    # 選択UI
    areas = sorted(full_df["エリア"].unique())
    c1, c2 = st.columns(2)
    sel_area = c1.selectbox("📍 エリア", ["未選択"] + areas)
    
    if sel_area != "未選択":
        stores = sorted(full_df[full_df["エリア"] == sel_area]["店名"].unique())
        sel_store = c2.selectbox("🏢 店舗", ["未選択"] + stores)

        if sel_store != "未選択":
            target_df = full_df[(full_df["エリア"] == sel_area) & (full_df["店名"] == sel_store)]
            media = target_df.iloc[0]["媒体"]
            
            # GCSスキャン (デリじゃのスペース曖昧回避)
            bucket = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
            # 全件取得してPython側で正規化マッチング
            prefix = f"{sel_area}/"
            blobs = list(bucket.list_blobs(prefix=prefix))
            
            # フォルダ名の判定用(スペース・全角半角を無視)
            def normalize_name(s): return re.sub(r'\s+', '', s).replace('　','')

            target_store_norm = normalize_name(sel_store)
            if media == "デリじゃ":
                target_store_norm = normalize_name(f"デリじゃ{sel_store}")

            # 該当店舗の画像だけ抽出
            store_images = []
            for b in blobs:
                parts = b.name.split('/')
                if len(parts) >= 3:
                    folder_part = normalize_name(parts[1])
                    if folder_part == target_store_norm:
                        store_images.append(b.name)

            # 表示
            for idx, row in target_df.iterrows():
                base_time = normalize_time(row["投稿時間"])
                girl_name = normalize_name(row["女の子の名前"])
                
                # 画像検索ロジック
                # 1. 名前が含まれているか (全角半角無視)
                # 2. 時間が±20分以内か
                matches = []
                for img_path in store_images:
                    img_file = normalize_name(img_path.split('/')[-1])
                    if girl_name in img_file and is_time_in_range(base_time, img_file):
                        matches.append(img_path)

                with st.container(border=True):
                    col_info, col_edit, col_img = st.columns([1, 2, 1])
                    with col_info:
                        st.write(f"⏰ {row['投稿時間']} / 👤 {row['女の子の名前']}")
                        if matches: st.success("✅ マッチ")
                        else: st.error("🚨 画像不在")
                    
                    with col_edit:
                        t = st.text_input("タイトル", row["タイトル"], key=f"t_{idx}")
                        b = st.text_area("本文", row["本文"], key=f"b_{idx}")
                        if st.button("更新", key=f"s_{idx}"):
                            ws = SPRS.worksheet(row['__sheet__'])
                            ws.update_cell(row['__row__'], 6, t)
                            ws.update_cell(row['__row__'], 7, b)
                            st.rerun()

                    with col_img:
                        for m in matches:
                            st.image(get_cached_url(m))
                            st.caption(m.split('/')[-1])

if __name__ == "__main__":
    main()
