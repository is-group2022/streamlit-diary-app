import streamlit as st
import pandas as pd
import gspread
import zipfile
import datetime
import re
from io import BytesIO
from datetime import timedelta
from google.oauth2.service_account import Credentials
from google.cloud import storage 
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- 1. 定数と初期設定 ---
try:
    SHEET_ID = st.secrets["google_resources"]["spreadsheet_id"] 
    ACCOUNT_STATUS_SHEET_ID = "1_GmWjpypap4rrPGNFYWkwcQE1SoK3QOMJlozEhkBwVM"
    USABLE_DIARY_SHEET_ID = "1e-iLey43A1t0bIBoijaXP55t5fjONdb0ODiTS53beqM"
    
    GCS_BUCKET_NAME = "auto-poster-images"

    SHEET_NAMES = st.secrets["sheet_names"]
    POSTING_ACCOUNT_SHEETS = {
        "A": "投稿Aアカウント",
        "B": "投稿Bアカウント",
        "C": "投稿Cアカウント",
        "D": "投稿Dアカウント"
    }
    
    USABLE_DIARY_SHEET = "【使用可能日記文】"
    MEDIA_OPTIONS = ["駅ちか", "デリじゃ"]
    POSTING_ACCOUNT_OPTIONS = ["A", "B", "C", "D"] 
    
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/cloud-platform']
except KeyError:
    st.error("🚨 secrets.tomlの設定を確認してください。")
    st.stop()

REGISTRATION_HEADERS = ["エリア", "店名", "媒体", "投稿時間", "女の子の名前", "タイトル", "本文"]
INPUT_HEADERS = ["投稿時間", "女の子の名前", "タイトル", "本文"]

# --- 2. 各種API連携 ---
@st.cache_resource(ttl=3600)
def get_gspread_client():
    """スプレッドシートAPIのクライアントを作成"""
    return gspread.service_account_from_dict(st.secrets["gcp_service_account"])

@st.cache_resource(ttl=3600)
def get_gcs_client():
    """Google Cloud Storageのクライアントを作成"""
    from google.cloud import storage
    return storage.Client.from_service_account_info(st.secrets["gcp_service_account"])

try:
    # 1. まずクライアントを作成
    GC = get_gspread_client()
    GCS_CLIENT = get_gcs_client()
    
    # 2. スプレッドシートを開く
    SPRS = GC.open_by_key(SHEET_ID)
    STATUS_SPRS = GC.open_by_key(ACCOUNT_STATUS_SHEET_ID)
    
except Exception as e:
    if "429" in str(e):
        st.error("🚨 Google APIの制限を超えました。1分ほど待ってから再読み込みしてください。")
    elif "name 'get_gcs_client'" in str(e):
        st.error("🚨 関数定義が不足しています。修正コードを反映してください。")
    else:
        st.error(f"❌ API接続失敗: {e}")
    st.stop()
    
# 【修正箇所】media引数を追加し、session_stateではなく選択された値を参照するように変更
def gcs_upload_wrapper(uploaded_file, entry, area, store, media):
    try:
        bucket = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
        # 選択された媒体（media）を直接参照
        folder_name = f"デリじゃ {store}" if media == "デリじゃ" else store
        ext = uploaded_file.name.split('.')[-1]
        blob_path = f"{area}/{folder_name}/{entry['投稿時間'].strip()}_{entry['女の子の名前'].strip()}.{ext}"
        blob = bucket.blob(blob_path)
        blob.upload_from_string(uploaded_file.getvalue(), content_type=uploaded_file.type)
        return True
    except Exception as e:
        st.error(f"❌ GCSアップロード失敗: {e}")
        return False

def get_cached_url(blob_name):
    import urllib.parse
    safe_path = urllib.parse.quote(blob_name)
    return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{safe_path}"
    
# --- 3. UI 構築 ---
st.set_page_config(layout="wide", page_title="写メ日記投稿登録")

st.markdown("""
    <style>
    .block-container { padding-top: 0rem !important; padding-bottom: 0rem !important; }
    header[data-testid="stHeader"] { display: none !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; height: 80px; }
    button[data-baseweb="tab"] {
        font-size: 32px !important; font-weight: 800 !important; height: 70px !important;
        padding: 0px 30px !important; background-color: #f0f2f6 !important;
        border-radius: 10px 10px 0px 0px !important; margin-right: 5px !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: white !important; background-color: #FF4B4B !important;
    }
    </style>
""", unsafe_allow_html=True)

if 'diary_entries' not in st.session_state:
    st.session_state.diary_entries = [{h: "" for h in INPUT_HEADERS} for _ in range(40)]

# タブ構成
tab1, tab2, tab3, tab4 = st.tabs([
    "📝 ① データ登録", 
    "📊 ② 店舗アカウント状況", 
    "📚 ③ 使用可能日記文",
    "🖼 ④ 使用可能画像"
])

combined_data = []
acc_summary = {}; acc_counts = {}
try:
    all_ws = SPRS.worksheets()
    ws_dict = {ws.title: ws for ws in all_ws}
    for code, s_name in POSTING_ACCOUNT_SHEETS.items():
        if s_name in ws_dict:
            rows = ws_dict[s_name].get_all_values()
            if len(rows) > 1:
                for i, r in enumerate(rows[1:]):
                    if any(str(c).strip() for c in r[:7]):
                        combined_data.append([code, i+2] + [r[j] if j<len(r) else "" for j in range(7)])
                        a, s, m = str(r[0]).strip(), str(r[1]).strip(), str(r[2]).strip()
                        acc_counts[code] = acc_counts.get(code, 0) + 1
                        if code not in acc_summary: acc_summary[code] = {}
                        if a not in acc_summary[code]: acc_summary[code][a] = set()
                        acc_summary[code][a].add(f"{m} : {s}")
except: pass

# =========================================================
# --- Tab 1: 📝 ① データ登録 ---
# =========================================================
with tab1:
    st.header("1️⃣ 新規データ登録")

    with st.expander("📖 はじめての方へ：新規データ登録の使い方（クリックで開閉）", expanded=False):
        st.markdown("""
        ### 1. 共通情報の入力
        画面上部で **「投稿アカウント」「エリア」「店名」** を入力してください。
        
        ### 2. ログイン情報の登録
        その店舗の投稿用 **IDとパスワード** を入力します。
        
        ### 3. 投稿データの一括入力（最大40件）
        表の各行に **「時間・名前・タイトル・本文」** を入力し、画像をアップロードしてください。
        
        ### 4. 登録の実行
        最下部の **「🔥 データを一括登録する」** を押すと、全データがスプレッドシートとストレージへ同時に保存されます。
        """)
        
    with st.form("diary_input_form", clear_on_submit=False):
        c1, c2, c3, c4 = st.columns(4)
        target_acc = c1.selectbox("👤 投稿アカウント", POSTING_ACCOUNT_OPTIONS, key="sel_acc_f")
        target_media = c2.selectbox("🌐 媒体", MEDIA_OPTIONS, key="sel_media_f")
        global_area = c3.text_input("📍 エリア", key="in_area_f")
        global_store = c4.text_input("🏢 店名", key="in_store_f")
        
        st.subheader("🔑 ログイン情報")
        c5, c6 = st.columns(2)
        login_id = c5.text_input("ID", key="login_id_f")
        login_pw = c6.text_input("パスワード", key="login_pw_f")
        
        st.markdown("---")
        st.subheader("📸 投稿内容入力")

        st.markdown("""
            <div style="display: flex; flex-direction: row; border-bottom: 2px solid #444; background-color: #f0f2f6; padding: 10px; border-radius: 5px 5px 0 0;">
                <div style="flex: 1; font-weight: bold; color: black;">時間</div>
                <div style="flex: 1; font-weight: bold; color: black;">名前</div>
                <div style="flex: 2; font-weight: bold; color: black;">タイトル</div>
                <div style="flex: 3; font-weight: bold; color: black;">本文</div>
                <div style="flex: 2; font-weight: bold; color: black;">画像</div>
            </div>
        """, unsafe_allow_html=True)

        form_entries = []
        for i in range(40):
            cols = st.columns([1, 1, 2, 3, 2])
            e_time = cols[0].text_input(f"t{i}", key=f"f_t_{i}", label_visibility="collapsed")
            e_name = cols[1].text_input(f"n{i}", key=f"f_n_{i}", label_visibility="collapsed")
            e_title = cols[2].text_area(f"ti{i}", key=f"f_ti_{i}", height=68, label_visibility="collapsed")
            e_body = cols[3].text_area(f"b{i}", key=f"f_b_{i}", height=68, label_visibility="collapsed")
            e_img = cols[4].file_uploader(f"g{i}", key=f"f_img_{i}", label_visibility="collapsed")
            
            form_entries.append({'投稿時間': e_time, '女の子の名前': e_name, 'タイトル': e_title, '本文': e_body, 'img': e_img})

        submit_button = st.form_submit_button("🔥 データを一括登録する", type="primary", use_container_width=True)

    if submit_button:
        valid_data = [e for e in form_entries if e['投稿時間'] and e['女の子の名前']]
        if not valid_data or not global_area or not global_store:
            st.error("⚠️ 入力不足：エリア、店名、および少なくとも1件以上の「時間・名前」を入力してください。")
        else:
            progress_text = st.empty()
            try:
                progress_text.info("📸 画像をアップロード中...")
                for e in valid_data:
                    # 【修正箇所】target_mediaを引数に追加
                    if e['img']: gcs_upload_wrapper(e['img'], e, global_area, global_store, target_media)
                
                progress_text.info("📝 日記文を登録中...")
                ws_main = SPRS.worksheet(POSTING_ACCOUNT_SHEETS[target_acc])
                rows_main = [[global_area, global_store, target_media, e['投稿時間'], e['女の子の名前'], e['タイトル'], e['本文']] for e in valid_data]
                ws_main.append_rows(rows_main, value_input_option='USER_ENTERED')
                
                progress_text.info("🔐 ログイン情報を登録中...")
                ws_status = STATUS_SPRS.worksheet(POSTING_ACCOUNT_SHEETS[target_acc])
                ws_status.append_row([global_area, global_store, target_media, login_id, login_pw], value_input_option='USER_ENTERED')
                
                progress_text.empty()
                st.success(f"✅ {len(valid_data)}件のデータを正常に登録しました！")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"❌ 登録エラーが発生しました: {e}")

# =========================================================
# --- Tab 2: 📊 ② 店舗アカウント状況 ---
# =========================================================
with tab2:
    st.markdown("## 📊 店舗アカウント状況")
    if combined_data:
        for acc_code in POSTING_ACCOUNT_OPTIONS:
            count = acc_counts.get(acc_code, 0)
            st.markdown(f"### 👤 投稿{acc_code}アカウント `{count} 件`")
            if acc_code in acc_summary:
                areas = acc_summary[acc_code]
                area_cols = st.columns(len(areas) if len(areas) > 0 else 1)
                for idx, (area_name, shops) in enumerate(areas.items()):
                    with area_cols[idx]:
                        st.info(f"📍 **{area_name}**")
                        for shop in sorted(shops):
                            st.text(f"🏢 {shop}")

# =========================================================
# --- Tab 3: 📚 ③ 使用可能日記文 ---
# =========================================================
with tab3:
    st.header("3️⃣ 使用可能日記文")
    @st.cache_data
    def get_usable_diary_data(update_tick):
        tmp_sprs = GC.open_by_key("1e-iLey43A1t0bIBoijaXP55t5fjONdb0ODiTS53beqM")
        tmp_ws = tmp_sprs.sheet1 
        return tmp_ws.get_all_values()

    if 'tab3_update_tick' not in st.session_state:
        st.session_state.tab3_update_tick = 0

    col_refresh, _ = st.columns([1, 4])
    if col_refresh.button("🔄 データを最新に更新", key="refresh_tab3", use_container_width=True):
        st.session_state.tab3_update_tick += 1
        st.cache_data.clear()
        st.rerun()

    try:
        tmp_data = get_usable_diary_data(st.session_state.tab3_update_tick)
        if len(tmp_data) > 1:
            df_usable = pd.DataFrame(tmp_data[1:], columns=tmp_data[0])
            st.dataframe(df_usable, use_container_width=True, height=600, hide_index=True)
        else:
            st.info("表示できる日記文がありません。")
    except Exception as e:
        st.error(f"読み込みエラー: {e}")

# =========================================================
# --- Tab 4: 🖼 ④ 使用可能画像 ---
# =========================================================
with tab4:
    st.header("🖼 使用可能画像ブラウザ（落ち店）")
    ROOT_PATH = "【落ち店】/"

    @st.cache_data(show_spinner=False)
    def get_ochimise_folders_v9(update_tick):
        blobs = GCS_CLIENT.list_blobs(GCS_BUCKET_NAME, prefix=ROOT_PATH, delimiter='/')
        list(blobs)
        return blobs.prefixes

    if 'tab4_tick' not in st.session_state: st.session_state.tab4_tick = 0

    c_btn, _ = st.columns([1.5, 4])
    if c_btn.button("🔄 店舗リストを強制更新", key="update_4_img"):
        st.session_state.tab4_tick += 1
        st.cache_data.clear()
        st.rerun()

    folders = get_ochimise_folders_v9(st.session_state.tab4_tick)
    show_all = st.checkbox("📂 全画像表示（一括モード）", key="all_check_4")

    @st.fragment
    def ochimise_action_fragment(folders, show_all):
        bucket = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
        
        @st.cache_data(ttl=600, show_spinner=False)
        def get_img_list_fast(path, is_all):
            if is_all:
                blobs = list(bucket.list_blobs(prefix=ROOT_PATH))
            else:
                blobs = list(bucket.list_blobs(prefix=path, delimiter='/'))
            return [bl.name for bl in blobs if bl.name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]

        target_path = ROOT_PATH
        current_label = "一括"
        
        if not show_all:
            if folders:
                folder_opts = {f.replace(ROOT_PATH, "").replace("/", ""): f for f in folders}
                sel = st.selectbox("📁 店舗を選択", ["未選択"] + list(folder_opts.keys()), key="sel_f_4")
                if sel == "未選択": return
                target_path = folder_opts[sel]
                current_label = sel
            else: return

        img_names = get_img_list_fast(target_path, show_all)
        
        if img_names:
            search_q = st.text_input("🔍 絞り込み検索", key="q_4")
            display_imgs = [n for n in img_names if search_q.lower() in n.lower()]

            c1, c2, c3, c4 = st.columns([1, 1, 2, 2])
            if c1.button("✅ 全選択"):
                for n in display_imgs: st.session_state[f"s4_{n}"] = True
                st.rerun()
            if c2.button("⬜️ 解除"):
                for n in display_imgs: st.session_state[f"s4_{n}"] = False
                st.rerun()

            selected = [n for n in display_imgs if st.session_state.get(f"s4_{n}")]

            if selected:
                zip_buf = BytesIO()
                with zipfile.ZipFile(zip_buf, "w") as zf:
                    for p in selected:
                        zf.writestr(p.split('/')[-1], bucket.blob(p).download_as_bytes())
                
                c3.download_button(f"① {len(selected)}枚を保存(ZIP)", zip_buf.getvalue(), f"{current_label}.zip", type="primary", use_container_width=True)
                
                if c4.button(f"② 保存完了・削除実行", key="del_btn_4", type="secondary", use_container_width=True):
                    for n in selected: bucket.blob(n).delete()
                    for n in selected: st.session_state[f"s4_{n}"] = False
                    st.cache_data.clear()
                    st.rerun()
                st.warning("⚠️ 保存後、必ず②を押して消去してください（使い回し防止）")

            cols = st.columns(8)
            for idx, b_name in enumerate(display_imgs):
                with cols[idx % 8]:
                    st.image(get_cached_url(b_name), use_container_width=True)
                    st.checkbox("選", key=f"s4_{b_name}", label_visibility="collapsed")
                    st.caption(f":grey[{b_name.split('/')[-1][:10]}]")

    ochimise_action_fragment(folders, show_all)
