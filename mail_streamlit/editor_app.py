import streamlit as st
import pandas as pd
import gspread
import datetime
import urllib.parse
import re
from google.cloud import storage

# --- 1. 定数・設定 ---
try:
    SHEET_ID = st.secrets["google_resources"]["spreadsheet_id"]
    GCS_BUCKET_NAME = "auto-poster-images"
    ACCOUNT_OPTIONS = ["A", "B", "C", "D"]
    SHEET_MAP = {opt: f"投稿{opt}アカウント" for opt in ACCOUNT_OPTIONS}
    DF_COLS = ["エリア", "店名", "媒体", "投稿時間", "女の子の名前", "タイトル", "本文"]
except KeyError:
    st.error("🚨 secrets.tomlの設定を確認してください。")
    st.stop()

# --- 2. 補助関数 ---
def normalize_text(s):
    if not s: return ""
    return re.sub(r'\s+', '', str(s)).replace('　', '').lower()

def parse_to_datetime(t_str):
    t_clean = re.sub(r'[^0-9]', '', str(t_str))
    if len(t_clean) == 3: t_clean = "0" + t_clean
    if len(t_clean) == 4:
        try: return datetime.datetime.strptime(t_clean, "%H%M")
        except: return None
    return None

def is_time_match(base_time, target_filename, window_min=20):
    if not base_time: return False
    match = re.match(r'^(\d{3,4})', target_filename)
    if not match: return False
    t_target = parse_to_datetime(match.group(1))
    if not t_target: return False
    diff = abs((base_time - t_target).total_seconds()) / 60
    return diff <= window_min or diff >= (1440 - window_min)

def get_cached_url(blob_name):
    return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{urllib.parse.quote(blob_name)}"

# --- 3. API接続 ---
@st.cache_resource(ttl=3600)
def get_clients():
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    gcs = storage.Client.from_service_account_info(st.secrets["gcp_service_account"])
    return gc, gcs

GC, GCS_CLIENT = get_clients()
SPRS = GC.open_by_key(SHEET_ID)

# --- 4. UI構築 ---
st.set_page_config(layout="wide", page_title="写メ日記エディタ")

# カスタムCSS
st.markdown("""
    <style>
    [data-testid="stHeader"] { display: none; }
    /* 選択パネルのスタイル */
    .filter-panel {
        background-color: #f1f3f6;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 25px;
        border: 1px solid #d1d5db;
    }
    .stTextArea textarea { font-size: 15px; line-height: 1.6; }
    /* 区切り線 */
    .diary-divider {
        border-bottom: 2px solid #eee;
        padding-bottom: 30px;
        margin-bottom: 30px;
    }
    </style>
""", unsafe_allow_html=True)

def main():
    st.title("📸 写メ日記投稿管理")

    # --- メイン画面上部の選択パネル (常に表示) ---
    st.markdown('<div class="filter-panel">', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    
    with c1:
        sel_acc = st.selectbox("👤 アカウント", ACCOUNT_OPTIONS, index=0)
    
    # 選択されたアカウントのデータを取得
    ws = SPRS.worksheet(SHEET_MAP[sel_acc])
    data = ws.get_all_values()
    
    if len(data) <= 1:
        st.warning("このシートには有効なデータがありません。")
        st.markdown('</div>', unsafe_allow_html=True)
        return
        
    full_df = pd.DataFrame(data[1:])
    full_df = full_df.iloc[:, :7]
    while full_df.shape[1] < 7: full_df[full_df.shape[1]] = ""
    full_df.columns = DF_COLS
    full_df['__row__'] = range(2, len(data) + 1)

    with c2:
        areas = sorted(full_df["エリア"].unique())
        sel_area = st.selectbox("📍 エリア", ["未選択"] + areas)
    
    sel_store = "未選択"
    with c3:
        if sel_area != "未選択":
            stores = sorted(full_df[full_df["エリア"] == sel_area]["店名"].unique())
            sel_store = st.selectbox("🏢 店舗", ["未選択"] + stores)
        else:
            st.selectbox("🏢 店舗", ["エリアを選択してください"], disabled=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

    # 未選択時のガイド
    if sel_store == "未選択":
        st.info("💡 上記のパネルから「エリア」と「店舗」を選択してください。")
        return

    # --- 選択後のメインコンテンツ ---
    target_df = full_df[(full_df["エリア"] == sel_area) & (full_df["店名"] == sel_store)]
    
    st.subheader(f"📊 {sel_store} (合計: {len(target_df)} 件)")

    # GCS画像取得
    bucket = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
    blobs = list(bucket.list_blobs(prefix=f"{sel_area}/"))
    store_norm = normalize_text(sel_store)
    store_images = [b.name for b in blobs if normalize_text(b.name.split('/')[1]) in [store_norm, normalize_text(f"デリじゃ{sel_store}")]]

    st.write("---")

    for idx, row in target_df.iterrows():
        base_time = parse_to_datetime(row["投稿時間"])
        name_norm = normalize_text(row["女の子の名前"])
        matched_files = [img for img in store_images if name_norm in normalize_text(img.split('/')[-1]) and is_time_match(base_time, img.split('/')[-1])]

        with st.container():
            st.markdown(f"#### 👤 {row['女の子の名前']} / ⏰ {row['投稿時間']}")
            col_txt, col_img, col_ops = st.columns([2.5, 1, 1])

            with col_txt:
                new_title = st.text_input("タイトル", row["タイトル"], key=f"ti_{idx}")
                # 本文をさらに大きく表示 (height=400)
                new_body = st.text_area("本文", row["本文"], key=f"bo_{idx}", height=400)
                
                if st.button("💾 内容を保存", key=f"sv_{idx}", type="primary"):
                    ws.update_cell(row['__row__'], 6, new_title)
                    ws.update_cell(row['__row__'], 7, new_body)
                    st.toast("保存しました！")

            with col_img:
                if matched_files:
                    for m_path in matched_files:
                        st.image(get_cached_url(m_path), use_container_width=True)
                        with st.popover("🗑️ 削除"):
                            st.write("本当に削除しますか？")
                            if st.button("実行する", key=f"del_{idx}_{m_path}"):
                                bucket.blob(m_path).delete()
                                st.cache_data.clear()
                                st.rerun()
                else:
                    st.error("🚨 画像なし")

            with col_ops:
                up_file = st.file_uploader("📥 画像追加", type=["jpg","png","jpeg"], key=f"up_{idx}")
                if up_file:
                    if st.button("🚀 アップ", key=f"u_btn_{idx}"):
                        ext = up_file.name.split('.')[-1]
                        folder_name = f"デリじゃ {sel_store}" if row["媒体"] == "デリじゃ" else sel_store
                        new_blob_name = f"{sel_area}/{folder_name}/{row['投稿時間']}_{row['女の子の名前']}.{ext}"
                        blob = bucket.blob(new_blob_name)
                        blob.upload_from_string(up_file.getvalue(), content_type=up_file.type)
                        st.cache_data.clear()
                        st.rerun()
            
            # 区切り用HTML (SyntaxErrorを修正)
            st.markdown("<div class='diary-divider'></div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()

