import streamlit as st
import pandas as pd
import gspread
from io import BytesIO
from google.oauth2.service_account import Credentials
from google.cloud import storage  # 追加
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- 1. 定数と初期設定 ---
try:
    SHEET_ID = st.secrets["google_resources"]["spreadsheet_id"] 
    # ACCOUNT_STATUS_SHEET_ID はログイン情報用
    ACCOUNT_STATUS_SHEET_ID = "1_GmWjpypap4rrPGNFYWkwcQE1SoK3QOMJlozEhkBwVM"
    USABLE_DIARY_SHEET_ID = "1e-iLey43A1t0bIBoijaXP55t5fjONdb0ODiTS53beqM" # 修正済みID
    
    # GCSの設定
    GCS_BUCKET_NAME = "auto-poster-images"

    SHEET_NAMES = st.secrets["sheet_names"]
    POSTING_ACCOUNT_SHEETS = {
        "A": "投稿Aアカウント",
        "B": "投稿Bアカウント",
        "C": "投稿Cアカウント",
        "D": "投稿Dアカウント"
    }
    
    USABLE_DIARY_SHEET = "【使用可能日記文】" # 教えていただいたシート名
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
def connect_to_gsheets(sheet_id):
    client = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    return client.open_by_key(sheet_id)

@st.cache_resource(ttl=3600)
def get_gcs_client():
    return storage.Client.from_service_account_info(st.secrets["gcp_service_account"])

try:
    SPRS = connect_to_gsheets(SHEET_ID)
    STATUS_SPRS = connect_to_gsheets(ACCOUNT_STATUS_SHEET_ID) 
    GCS_CLIENT = get_gcs_client()
except Exception as e:
    st.error(f"❌ API接続失敗: {e}"); st.stop()

# --- GCS 補助関数 ---
def gcs_upload_wrapper(uploaded_file, entry, area, store):
    try:
        bucket = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
        folder_name = f"デリじゃ {store}" if st.session_state.global_media == "デリじゃ" else store
        ext = uploaded_file.name.split('.')[-1]
        blob_path = f"{area}/{folder_name}/{entry['投稿時間'].strip()}_{entry['女の子の名前'].strip()}.{ext}"
        
        blob = bucket.blob(blob_path)
        blob.upload_from_string(uploaded_file.getvalue(), content_type=uploaded_file.type)
        return True
    except Exception as e:
        st.error(f"❌ GCSアップロード失敗: {e}")
        return False

# --- 3. UI 構築 ---
st.set_page_config(layout="wide", page_title="写メ日記投稿管理")

st.markdown("""
    <style>
    /* 1. 余白削除 */
    .block-container { padding-top: 0rem !important; padding-bottom: 0rem !important; }
    header[data-testid="stHeader"] { display: none !important; }

    /* 2. タブデザイン */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; height: 80px; }
    button[data-baseweb="tab"] {
        font-size: 32px !important; font-weight: 800 !important; height: 70px !important;
        padding: 0px 30px !important; background-color: #f0f2f6 !important;
        border-radius: 10px 10px 0px 0px !important; margin-right: 5px !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: white !important; background-color: #FF4B4B !important;
    }

    /* 3. 【修正】見出し固定（赤い線を消し、背景を白に固定） */
    .sticky-header-row {
        position: -webkit-sticky;
        position: sticky;
        top: 0px;
        z-index: 1000;
        background-color: white !important;
        padding: 10px 0px;
        margin-bottom: 5px;
    }
    </style>
""", unsafe_allow_html=True)

if 'diary_entries' not in st.session_state:
    st.session_state.diary_entries = [{h: "" for h in INPUT_HEADERS} for _ in range(40)]

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📝 ① データ登録", 
    "📊 ② 店舗アカウント状況", 
    "📂 ③ 投稿データ管理", 
    "📚 ④ 使用可能日記文",
    "🖼 ⑤ 使用可能画像"
])

# --- データ集計ロジック ---
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
# --- Tab 1: 📝 データ登録 ---
# =========================================================
with tab1:
    st.header("1️⃣ 新規データ登録")
    c1, c2, c3, c4 = st.columns(4)
    target_acc = c1.selectbox("👤 投稿アカウント", POSTING_ACCOUNT_OPTIONS)
    st.session_state.global_media = c2.selectbox("🌐 媒体", MEDIA_OPTIONS)
    global_area = c3.text_input("📍 エリア")
    global_store = c4.text_input("🏢 店名")
    
    st.subheader("🔑 ログイン情報")
    c5, c6 = st.columns(2)
    login_id = c5.text_input("ID", key="login_id")
    login_pw = c6.text_input("パスワード", key="login_pw")
    
    st.markdown("---")
    st.subheader("📸 投稿内容入力")

    # 見出し固定（HTMLで定義）
    st.markdown("""
        <div class="sticky-header-row">
            <div style="display: flex; flex-direction: row; border-bottom: 1px solid #ddd;">
                <div style="flex: 1; font-weight: bold; padding: 5px;">投稿時間</div>
                <div style="flex: 1; font-weight: bold; padding: 5px;">名前</div>
                <div style="flex: 2; font-weight: bold; padding: 5px;">タイトル</div>
                <div style="flex: 3; font-weight: bold; padding: 5px;">本文</div>
                <div style="flex: 2; font-weight: bold; padding: 5px;">画像</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    # フォームを使わず直接配置（Stickyを効かせるため）
    for i in range(40):
        cols = st.columns([1, 1, 2, 3, 2])
        st.session_state.diary_entries[i]['投稿時間'] = cols[0].text_input(f"t{i}", key=f"t_{i}", label_visibility="collapsed")
        st.session_state.diary_entries[i]['女の子の名前'] = cols[1].text_input(f"n{i}", key=f"n_{i}", label_visibility="collapsed")
        st.session_state.diary_entries[i]['タイトル'] = cols[2].text_area(f"ti{i}", key=f"ti_{i}", height=68, label_visibility="collapsed")
        st.session_state.diary_entries[i]['本文'] = cols[3].text_area(f"b{i}", key=f"b_{i}", height=68, label_visibility="collapsed")
        st.session_state.diary_entries[i]['img'] = cols[4].file_uploader(f"g{i}", key=f"img_{i}", label_visibility="collapsed")

    if st.button("🔥 データを登録する", type="primary", use_container_width=True):
        valid_data = [e for e in st.session_state.diary_entries if e['投稿時間'] and e['女の子の名前']]
        if not valid_data: st.error("入力してください"); st.stop()
        for e in valid_data:
            if e['img']: gcs_upload_wrapper(e['img'], e, global_area, global_store)
        ws_main = SPRS.worksheet(POSTING_ACCOUNT_SHEETS[target_acc])
        rows_main = [[global_area, global_store, st.session_state.global_media, e['投稿時間'], e['女の子の名前'], e['タイトル'], e['本文']] for e in valid_data]
        ws_main.append_rows(rows_main, value_input_option='USER_ENTERED')
        ws_status = STATUS_SPRS.worksheet(POSTING_ACCOUNT_SHEETS[target_acc])
        ws_status.append_row([global_area, global_store, st.session_state.global_media, login_id, login_pw], value_input_option='USER_ENTERED')
        st.success("✅ 登録完了！")
# =========================================================
# --- Tab 2: 📊 全アカウント店舗アカウント状況 ---
# =========================================================
with tab2:
    st.markdown("## 📊 全アカウント店舗アカウント状況")
    
    # データを構造化する辞書
    # acc_summary: { アカウント: { エリア: {店舗情報のセット} } }
    # acc_counts: { アカウント: 合計件数 }
    acc_summary = {}
    acc_counts = {}

    if combined_data:
        # データ集計
        for row in combined_data:
            acc_code = row[0]
            area = str(row[2]).strip()   # エリア
            store = str(row[3]).strip()  # 店名
            media = str(row[4]).strip()  # 媒体
            
            # 件数カウント
            acc_counts[acc_code] = acc_counts.get(acc_code, 0) + 1
            
            # 構造化
            if acc_code not in acc_summary:
                acc_summary[acc_code] = {}
            if area not in acc_summary[acc_code]:
                acc_summary[acc_code][area] = set()
            
            acc_summary[acc_code][area].add(f"{media} : {store}")

        # アカウントごとに表示
        for acc_code in POSTING_ACCOUNT_OPTIONS:
            count = acc_counts.get(acc_code, 0)
            
            # ヘッダー部分：アカウント名と件数を横並びに
            st.markdown(f"### 👤 投稿{acc_code}アカウント　`{count} 件`")
            
            if acc_code in acc_summary:
                areas = acc_summary[acc_code]
                # エリアごとにカラムを分ける
                area_cols = st.columns(len(areas) if len(areas) > 0 else 1)
                
                for idx, (area_name, shops) in enumerate(areas.items()):
                    with area_cols[idx]:
                        st.info(f"📍 **{area_name}**")
                        for shop in sorted(shops):
                            st.write(f"　└ {shop}")
            else:
                st.caption("稼働データなし")
            
            st.markdown("---") # アカウントごとの区切り線
    else:
        st.info("現在稼働中のデータはありません。")

# =========================================================
# --- Tab 3: 📂 投稿データ管理 ---
# =========================================================
with tab3:
    st.markdown("### 📂 投稿データ管理 (一括編集)")
    if combined_data:
        df = pd.DataFrame(combined_data, columns=["アカウント", "行番号"] + REGISTRATION_HEADERS)
        edited_df = st.data_editor(df, key="main_editor", use_container_width=True, hide_index=True, disabled=["アカウント", "行番号"], height=600)
        if st.button("🔥 変更内容をスプレッドシートに一括反映する", type="primary", use_container_width=True):
            with st.spinner("保存中..."):
                try:
                    for acc_code in POSTING_ACCOUNT_OPTIONS:
                        target_rows = edited_df[edited_df["アカウント"] == acc_code]
                        if target_rows.empty: continue
                        ws = SPRS.worksheet(POSTING_ACCOUNT_SHEETS[acc_code])
                        for _, row in target_rows.iterrows():
                            row_idx = int(row["行番号"])
                            new_values = [str(row[h]) for h in REGISTRATION_HEADERS]
                            ws.update(f"A{row_idx}:G{row_idx}", [new_values], value_input_option='USER_ENTERED')
                    st.success("🎉 更新完了！"); st.rerun()
                except Exception as e: st.error(f"エラー: {e}")
    else:
        st.info("編集可能なデータはありません。")

# =========================================================
# --- Tab 4: 📚 使用可能日記文表示 ---
# =========================================================
with tab4:
    st.header("4️⃣ 使用可能日記文")
    try:
        tmp_sprs = connect_to_gsheets(USABLE_DIARY_SHEET_ID)
        tmp_ws = tmp_sprs.worksheet("【使用可能日記文】")
        tmp_data = tmp_ws.get_all_values()
        if len(tmp_data) > 1:
            st.dataframe(pd.DataFrame(tmp_data[1:], columns=tmp_data[0]), use_container_width=True, height=600)
    except Exception as e: st.error(f"読み込みエラー: {e}")

# =========================================================
# --- Tab 5: 🖼 ⑤ 使用可能画像 ---
# =========================================================
with tab5:
    st.header("🖼 使用可能画像ブラウザ（落ち店）")
    
    ROOT_PATH = "落ち店/"

    # --- フォルダ一覧を取得 ---
    try:
        bucket = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
        # delimiter='/' を使うことで「フォルダ（プレフィックス）」を取得できる
        blobs = GCS_CLIENT.list_blobs(GCS_BUCKET_NAME, prefix=ROOT_PATH, delimiter='/')
        list(blobs) # イテレータを回して prefixes を確定させる
        folders = blobs.prefixes
    except Exception as e:
        st.error(f"GCS接続エラー: {e}")
        folders = []

    if folders:
        # フォルダ選択（表示用に整形）
        folder_options = {f.replace(ROOT_PATH, "").replace("/", ""): f for f in folders}
        selected_key = st.selectbox("📁 表示するフォルダ（店舗）を選択", ["選択してください"] + list(folder_options.keys()))
        
        if selected_key != "選択してください":
            target_path = folder_options[selected_key]
            
            # --- 画像ファイルを取得 ---
            images = list(bucket.list_blobs(prefix=target_path))
            valid_extensions = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
            image_blobs = [b for b in images if b.name.lower().endswith(valid_extensions)]
            
            if image_blobs:
                st.write(f"### 📍 {selected_key} の画像（{len(image_blobs)}枚）")
                cols = st.columns(3)
                for idx, blob in enumerate(image_blobs):
                    with cols[idx % 3]:
                        try:
                            # 署名付きURLを発行
                            # ※ここでエラーが出る場合は権限不足の可能性大
                            img_url = blob.generate_signed_url(
                                version="v4",
                                expiration=3600, # 1時間有効
                                method="GET"
                            )
                            st.image(img_url, use_container_width=True)
                            st.caption(f"📄 {blob.name.split('/')[-1]}")
                        except Exception as e:
                            st.error(f"画像生成失敗: {blob.name.split('/')[-1]}")
                            # 権限がない場合に備えて詳細なエラーを出したい場合はここを表示
                            # st.caption(f"Error: {e}")
            else:
                st.info("このフォルダ内に画像が見つかりませんでした。")
    else:
        st.warning(f"'{ROOT_PATH}' 内にフォルダが見つかりません。")








