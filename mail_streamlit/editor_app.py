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
    ACCOUNT_STATUS_SHEET_ID = "1_GmWjpypap4rrPGNFYWkwcQE1SoK3QOMJlozEhkBwVM"
    
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

# --- 3. API接続 & キャッシュ設定 ---
@st.cache_resource(ttl=3600)
def get_clients():
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    gcs = storage.Client.from_service_account_info(st.secrets["gcp_service_account"])
    return gc, gcs

GC, GCS_CLIENT = get_clients()

# 【API制限対策】手動更新ボタンが押されるまで1週間キャッシュを保持
@st.cache_data(ttl=604800)
def get_full_sheet_data(sheet_key, worksheet_name):
    try:
        sh = GC.open_by_key(sheet_key)
        ws = sh.worksheet(worksheet_name)
        return ws.get_all_values()
    except Exception as e:
        st.error(f"シート読み込みエラー: {e}")
        return None

# --- 4. UI構築 ---
st.set_page_config(layout="wide", page_title="写メ日記投稿データ管理")

st.markdown("""
    <style>
    [data-testid="stHeader"] { display: none; }
    .block-container { padding-top: 1.5rem !important; padding-bottom: 0rem !important; }
    .stApp h1 { padding-top: 0px !important; margin-top: -15px !important; padding-bottom: 10px !important; margin-bottom: 0px !important; font-size: 1.8rem !important; }
    .filter-panel { background-color: #f1f3f6; padding: 12px 20px; border-radius: 10px; margin-top: 5px !important; margin-bottom: 15px; border: 1px solid #d1d5db; }
    .stTextArea textarea { font-size: 15px; line-height: 1.6; }
    .diary-divider { border-bottom: 2px solid #eee; padding-bottom: 30px; margin-bottom: 30px; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    </style>
""", unsafe_allow_html=True)

def main():
    st.title("📸 写メ日記投稿データ管理")

    tab1, tab2 = st.tabs(["📝 日記編集・画像管理", "📊 店舗アカウント状況"])

    with tab1:
        with st.expander("📖 使い方（クリックで開閉）", expanded=False):
            st.markdown("### データの更新について\nこのアプリはAPI制限を避けるため、一度読み込んだデータを保存しています。スプレッドシートを直接編集した場合は、右上の **「🔄 最新データに更新」** ボタンを押してください。")
            
        # --- メイン画面上部の選択パネル ---
        st.markdown('<div class="filter-panel">', unsafe_allow_html=True)
        # ボタンを2つ並べるためにカラムを6つに調整
        c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 1, 1.5, 1, 0.8]) 
        
        with c1:
            sel_acc = st.selectbox("👤 アカウント", ACCOUNT_OPTIONS, index=0)
        
        # 🔄 最新データに更新ボタン (右端に配置)
        with c6:
            st.write("") 
            if st.button("🔄 更新", use_container_width=True):
                st.cache_data.clear()
                st.rerun()
        
        # キャッシュからデータを取得
        data = get_full_sheet_data(SHEET_ID, SHEET_MAP[sel_acc])
        
        if not data or len(data) <= 1:
            st.warning("有効なデータがありません。")
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            full_df = pd.DataFrame(data[1:])
            full_df = full_df.iloc[:, :7]
            while full_df.shape[1] < 7: full_df[full_df.shape[1]] = ""
            full_df.columns = DF_COLS
            full_df['__row__'] = range(2, len(data) + 1)
            full_df = full_df[full_df["店名"].str.strip() != ""]
            full_df = full_df[full_df["女の子の名前"].str.strip() != ""]

            with c2:
                areas = sorted(full_df["エリア"].unique())
                sel_area = st.selectbox("📍 エリア", ["未選択"] + areas)
            
            sel_store = "未選択"
            with c3:
                if sel_area != "未選択":
                    stores = sorted(full_df[full_df["エリア"] == sel_area]["店名"].unique())
                    sel_store = st.selectbox("🏢 店舗", ["未選択"] + stores)
                else:
                    st.selectbox("🏢 店舗", ["エリアを選択"], disabled=True)
                    
            with c4:
                search_query = st.text_input("🔍 検索", placeholder="キーワード入力...")

            # --- 📥 画像一括ダウンロード (c5) ---
            with c5:
                st.write("") 
                if sel_store != "未選択":
                    bucket = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
                    blobs = list(bucket.list_blobs(prefix=f"{sel_area}/"))
                    store_norm = normalize_text(sel_store)
                    store_images = [b.name for b in blobs if normalize_text(b.name.split('/')[1]) in [store_norm, normalize_text(f"デリじゃ{sel_store}")]]
                    
                    if store_images:
                        from io import BytesIO
                        import zipfile
                        buf = BytesIO()
                        with zipfile.ZipFile(buf, "w") as zf:
                            for img_path in store_images:
                                file_content = bucket.blob(img_path).download_as_bytes()
                                zf.writestr(img_path.split("/")[-1], file_content)
                        
                        st.download_button(
                            label="📥 画像保存",
                            data=buf.getvalue(),
                            file_name=f"{sel_store}_images.zip",
                            mime="application/zip",
                            use_container_width=True
                        )
                    else:
                        st.button("📥 なし", disabled=True, use_container_width=True)
                else:
                    st.button("📥 未選択", disabled=True, use_container_width=True)

            st.markdown('</div>', unsafe_allow_html=True)

    
    with tab2:
        st.markdown("## 📊 店舗アカウント状況")
        
        combined_data = []
        acc_summary = {}; acc_counts = {}
        try:
            for opt in ACCOUNT_OPTIONS:
                rows = get_full_sheet_data(SHEET_ID, SHEET_MAP[opt])
                if rows and len(rows) > 1:
                    for i, r in enumerate(rows[1:]):
                        if any(str(c).strip() for c in r[:7]):
                            combined_data.append([opt, i+2] + [r[j] if j<len(r) else "" for j in range(7)])
                            a, s, m = str(r[0]).strip(), str(r[1]).strip(), str(r[2]).strip()
                            acc_counts[opt] = acc_counts.get(opt, 0) + 1
                            if opt not in acc_summary: acc_summary[opt] = {}
                            if a not in acc_summary[opt]: acc_summary[opt][a] = set()
                            acc_summary[opt][a].add(f"{m} : {s}")
        except: pass

        if combined_data:
            for acc_code in ACCOUNT_OPTIONS:
                count = acc_counts.get(acc_code, 0)
                st.markdown(f"### 👤 投稿{acc_code}アカウント `{count} 件`")
                if acc_code in acc_summary:
                    areas = acc_summary[acc_code]
                    area_cols = st.columns(len(areas) if len(areas) > 0 else 1)
                    for idx, (area_name, shops) in enumerate(areas.items()):
                        with area_cols[idx]:
                            st.info(f"📍 **{area_name}**")
                            for shop in sorted(shops):
                                st.checkbox(f"{shop}", key=f"move_{acc_code}_{area_name}_{shop}")
            
            selected_shops = [
                {"acc": k.split('_')[1], "area": k.split('_')[2], "shop": k.split('_')[3].split(" : ")[-1]}
                for k, v in st.session_state.items() if k.startswith("move_") and v
            ]

            if selected_shops:
                if st.button("🚀 選択した店舗を【落ち店】へ移動する", type="primary", use_container_width=True):
                    st.session_state.confirm_move = True

                if st.session_state.get("confirm_move"):
                    st.error("❗ 本当に実行しますか？")
                    col_yes, col_no = st.columns(2)
                    if col_no.button("❌ キャンセル", use_container_width=True):
                        st.session_state.confirm_move = False
                        st.rerun()

                    if col_yes.button("⭕ はい、実行します", type="primary", use_container_width=True):
                        import time
                        try:
                            sh_stock = GC.open_by_key("1e-iLey43A1t0bIBoijaXP55t5fjONdb0ODiTS53beqM")
                            ws_stock = sh_stock.sheet1
                            for item in selected_shops:
                                ws_main = GC.open_by_key(SHEET_ID).worksheet(SHEET_MAP[item['acc']])
                                main_data = ws_main.get_all_values()
                                for row_idx in range(len(main_data), 0, -1):
                                    row = main_data[row_idx-1]
                                    if len(row) >= 2 and row[1] == item['shop']:
                                        ws_stock.append_row([None, None, row[5], row[6]], value_input_option='USER_ENTERED')
                                        time.sleep(2.0)
                                        ws_main.delete_rows(row_idx)
                                status_sprs = GC.open_by_key(ACCOUNT_STATUS_SHEET_ID)
                                ws_link = status_sprs.worksheet(SHEET_MAP[item['acc']])
                                link_data = ws_link.get_all_values()
                                for row_idx in range(len(link_data), 0, -1):
                                    if len(link_data[row_idx-1]) >= 2 and link_data[row_idx-1][1] == item['shop']:
                                        ws_link.delete_rows(row_idx)
                                        break
                                bucket = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
                                found_blobs = []
                                for pfx in [f"{item['area']}/{item['shop']}/", f"{item['area']}/デリじゃ {item['shop']}/"]:
                                    blobs = list(bucket.list_blobs(prefix=pfx))
                                    if blobs: found_blobs = blobs; break
                                for b in found_blobs:
                                    file_name = b.name.split('/')[-1]
                                    new_name = f"【落ち店】/{item['shop']}/{file_name}"
                                    bucket.copy_blob(b, bucket, new_name)
                                    b.delete()
                            
                            st.success("🎉 移動完了！ 最新データにするには更新ボタンを押してください。")
                            st.session_state.confirm_move = False
                        except Exception as e:
                            st.error(f"エラー: {e}")

if __name__ == "__main__":
    main()


