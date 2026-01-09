import streamlit as st
import pandas as pd
import gspread
import datetime
import urllib.parse
import re
from google.oauth2.service_account import Credentials
from google.cloud import storage

# --- 1. 設定と定数 ---
try:
    SHEET_ID = st.secrets["google_resources"]["spreadsheet_id"]
    GCS_BUCKET_NAME = "auto-poster-images"
    POSTING_ACCOUNT_SHEETS = ["投稿Aアカウント", "投稿Bアカウント", "投稿Cアカウント", "投稿Dアカウント"]
    # 処理に使用する最初の7列
    DF_COLS = ["エリア", "店名", "媒体", "投稿時間", "女の子の名前", "タイトル", "本文"]
except KeyError:
    st.error("🚨 secrets.tomlの設定を確認してください。")
    st.stop()

# --- 2. 補助関数 ---

def normalize_text(s):
    """スペース・全角・大文字小文字の差をなくす"""
    if not s: return ""
    return re.sub(r'\s+', '', str(s)).replace('　', '').lower()

def parse_to_datetime(t_str):
    """時間文字列を計算可能な型に変換"""
    t_clean = re.sub(r'[^0-9]', '', str(t_str))
    if len(t_clean) == 3: t_clean = "0" + t_clean
    if len(t_clean) == 4:
        try:
            return datetime.datetime.strptime(t_clean, "%H%M")
        except:
            return None
    return None

def is_time_match(base_time, target_filename, window_min=20):
    """ファイル名の先頭数字が±20分以内か判定"""
    if not base_time: return False
    match = re.match(r'^(\d{3,4})', target_filename)
    if not match: return False
    
    t_target = parse_to_datetime(match.group(1))
    if not t_target: return False
    
    diff = abs((base_time - t_target).total_seconds()) / 60
    return diff <= window_min or diff >= (1440 - window_min)

def get_cached_url(blob_name):
    safe_path = urllib.parse.quote(blob_name)
    return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{safe_path}"

# --- 3. API連携 ---
@st.cache_resource(ttl=3600)
def get_clients():
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    gcs = storage.Client.from_service_account_info(st.secrets["gcp_service_account"])
    return gc, gcs

try:
    GC, GCS_CLIENT = get_clients()
    SPRS = GC.open_by_key(SHEET_ID)
except Exception as e:
    st.error(f"API接続エラー: {e}")
    st.stop()

# --- 4. UI ---
st.set_page_config(layout="wide", page_title="日記×画像 照合エディタ")
st.markdown("<style>header[data-testid='stHeader'] { display: none !important; }</style>", unsafe_allow_html=True)

def main():
    st.title("📝 日記×画像 マッチング編集部")

    # --- データの読み込み ---
    all_rows = []
    with st.spinner("シートを読み込み中..."):
        for s_name in POSTING_ACCOUNT_SHEETS:
            try:
                ws = SPRS.worksheet(s_name)
                data = ws.get_all_values()
                if len(data) > 1:
                    rows = data[1:]
                    # 列数がバラバラでも対応できるように一度DataFrame化
                    tmp_df = pd.DataFrame(rows)
                    
                    # 💡 8列目（ステータス）以降を切り捨て、最初の7列だけを確実に取得
                    tmp_df = tmp_df.iloc[:, :7]
                    
                    # 列数が7に満たない場合の保険
                    while tmp_df.shape[1] < 7:
                        tmp_df[tmp_df.shape[1]] = ""
                    
                    tmp_df.columns = DF_COLS
                    tmp_df['__sheet__'] = s_name
                    tmp_df['__row__'] = range(2, len(data) + 1)
                    all_rows.append(tmp_df)
            except: continue

    if not all_rows:
        st.warning("表示できるデータがありません。")
        return

    full_df = pd.concat(all_rows)

    # フィルタUI
    c1, c2 = st.columns(2)
    areas = sorted(full_df["エリア"].unique())
    selected_area = c1.selectbox("📍 エリアを選択", ["未選択"] + areas)
    if selected_area == "未選択": return

    stores = sorted(full_df[full_df["エリア"] == selected_area]["店名"].unique())
    selected_store = c2.selectbox("🏢 店舗を選択", ["未選択"] + stores)
    if selected_store == "未選択": return

    # 店舗データとGCS画像取得
    target_df = full_df[(full_df["エリア"] == selected_area) & (full_df["店名"] == selected_store)]
    
    bucket = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
    blobs = list(bucket.list_blobs(prefix=f"{selected_area}/"))
    
    store_norm = normalize_text(selected_store)
    media_type = target_df.iloc[0]["媒体"]

    store_images = []
    for b in blobs:
        parts = b.name.split('/')
        if len(parts) >= 3:
            folder_part_norm = normalize_text(parts[1])
            if folder_part_norm in [store_norm, normalize_text(f"デリじゃ{selected_store}")]:
                store_images.append(b.name)

    st.divider()

    # --- メイン表示 ---
    for idx, row in target_df.iterrows():
        base_time = parse_to_datetime(row["投稿時間"])
        girl_name_norm = normalize_text(row["女の子の名前"])
        
        # 画像照合ロジック
        matched_files = [
            img for img in store_images 
            if girl_name_norm in normalize_text(img.split('/')[-1]) and is_time_match(base_time, img.split('/')[-1])
        ]

        with st.container(border=True):
            col_info, col_edit, col_img = st.columns([1, 2, 1])
            
            with col_info:
                st.write(f"**⏰ {row['投稿時間']}**")
                st.write(f"**👤 {row['女の子の名前']}**")
                if matched_files:
                    st.success(f"✅ 一致 ({len(matched_files)}枚)")
                else:
                    st.error("🚨 画像なし")
                    st.caption(f"条件: {row['投稿時間']} ±20分")

            with col_edit:
                new_title = st.text_input("タイトル", value=row["タイトル"], key=f"ti_{idx}")
                new_body = st.text_area("本文", value=row["本文"], key=f"bo_{idx}", height=120)
                
                if st.button("💾 この内容で更新", key=f"btn_{idx}"):
                    ws = SPRS.worksheet(row['__sheet__'])
                    # F列(6), G列(7)を更新。ステータス(8)は触らない。
                    ws.update_cell(row['__row__'], 6, new_title)
                    ws.update_cell(row['__row__'], 7, new_body)
                    st.success("更新しました！")
                    st.cache_data.clear()

            with col_img:
                if matched_files:
                    for m in matched_files:
                        st.image(get_cached_url(m), use_container_width=True)
                        st.caption(m.split('/')[-1])
                else:
                    st.info("不一致")

if __name__ == "__main__":
    main()
