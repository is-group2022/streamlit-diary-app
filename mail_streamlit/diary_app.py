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
    .stTabs [data-baseweb="tab-list"] { gap: 10px; height: 80px; }
    button[data-baseweb="tab"] {
        font-size: 32px !important; font-weight: 800 !important; height: 70px !important;
        padding: 0px 30px !important; background-color: #f0f2f6 !important; border-radius: 10px 10px 0px 0px !important;
        margin-right: 5px !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: white !important; background-color: #FF4B4B !important; border-bottom: 5px solid #b33232 !important;
    }
    button[data-baseweb="tab"]:hover { background-color: #e0e2e6 !important; color: #FF4B4B !important; }
    </style>
""", unsafe_allow_html=True)

if 'diary_entries' not in st.session_state:
    st.session_state.diary_entries = [{h: "" for h in INPUT_HEADERS} for _ in range(40)]

# タブ構成の変更
tab1, tab2, tab3, tab4 = st.tabs(["📝 ① データ登録", "📊 ② 店舗アカウント状況", "📂 ③ 投稿データ管理", "📚 ④ 使用可能日記文"])

# 共通データ取得（Tab2とTab3で使用）
combined_data = []
area_summary = {}
try:
    all_worksheets = SPRS.worksheets()
    ws_dict = {ws.title: ws for ws in all_worksheets}
    for acc_code, sheet_name in POSTING_ACCOUNT_SHEETS.items():
        if sheet_name in ws_dict:
            ws = ws_dict[sheet_name]
            raw_data = ws.get_all_values()
            if len(raw_data) > 1:
                for i, row in enumerate(raw_data[1:]):
                    if any(str(cell).strip() for cell in row[:7]):
                        row_full = [row[j] if j < len(row) else "" for j in range(7)]
                        combined_data.append([acc_code, i + 2] + row_full)
                        a, s, m = str(row[0]).strip(), str(row[1]).strip(), str(row[2]).strip()
                        if a:
                            if a not in area_summary: area_summary[a] = set()
                            area_summary[a].add(f"【{acc_code}】{m} : {s}")
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
    st.markdown("---")
    st.subheader("🔑 ログイン情報（アカウント登録用）")
    c5, c6 = st.columns(2)
    login_id = c5.text_input("ID", key="login_id")
    login_pw = c6.text_input("パスワード", key="login_pw")
    st.markdown("---")
    st.subheader("📸 投稿内容入力")
    with st.form("reg_form"):
        h_cols = st.columns([1, 1, 2, 3, 2])
        h_cols[0].write("**投稿時間**"); h_cols[1].write("**女の子の名前**"); h_cols[2].write("**タイトル**"); h_cols[3].write("**本文**"); h_cols[4].write("**画像**")
        for i in range(40):
            cols = st.columns([1, 1, 2, 3, 2])
            st.session_state.diary_entries[i]['投稿時間'] = cols[0].text_input(f"時間{i}", key=f"t_{i}", label_visibility="collapsed")
            st.session_state.diary_entries[i]['女の子の名前'] = cols[1].text_input(f"名{i}", key=f"n_{i}", label_visibility="collapsed")
            st.session_state.diary_entries[i]['タイトル'] = cols[2].text_area(f"題{i}", key=f"ti_{i}", height=68, label_visibility="collapsed")
            st.session_state.diary_entries[i]['本文'] = cols[3].text_area(f"本{i}", key=f"b_{i}", height=68, label_visibility="collapsed")
            st.session_state.diary_entries[i]['img'] = cols[4].file_uploader(f"画{i}", key=f"img_{i}", label_visibility="collapsed")
        if st.form_submit_button("🔥 データを登録する", type="primary"):
            valid_data = [e for e in st.session_state.diary_entries if e['投稿時間'] and e['女の子の名前']]
            if not valid_data: st.error("入力してください"); st.stop()
            for e in valid_data:
                if e['img']: gcs_upload_wrapper(e['img'], e, global_area, global_store)
            ws_main = SPRS.worksheet(POSTING_ACCOUNT_SHEETS[target_acc])
            rows_main = [[global_area, global_store, st.session_state.global_media, e['投稿時間'], e['女の子の名前'], e['タイトル'], e['本文']] for e in valid_data]
            ws_main.append_rows(rows_main, value_input_option='USER_ENTERED')
            ws_status = STATUS_SPRS.worksheet(POSTING_ACCOUNT_SHEETS[target_acc])
            status_row = [global_area, global_store, st.session_state.global_media, login_id, login_pw]
            ws_status.append_row(status_row, value_input_option='USER_ENTERED')
            st.success("✅ 登録完了！")

申し訳ありません、おっしゃる通り各アカウントの中でエリアがバラバラに表示されると非常に管理しづらいですね。

**「アカウントごとに枠を作り、その中でエリアごとに店舗をグループ化する」**という形にUIを修正しました。これにより、どのアカウントがどのエリアでどの店を管理しているかが一目で分かります。

修正版：Tab 2（アカウント別・エリア集計UI）
このコードを Tab 2 の部分に上書きしてください。

Python

# =========================================================
# --- Tab 2: 📊 全アカウント店舗アカウント状況 ---
# =========================================================
with tab2:
    st.markdown("## 📊 全アカウント店舗アカウント状況")
    
    # データをアカウントごとに整理する辞書
    # 構造: { "A": { "石巻": {"店A", "店B"}, "仙台": {"店C"} }, "B": ... }
    acc_summary = {}

    if combined_data:
        # 取得済みの combined_data から構造化データを生成
        for row in combined_data:
            acc_code = row[0]
            area = str(row[2]).strip()   # エリア
            store = str(row[3]).strip()  # 店名
            media = str(row[4]).strip()  # 媒体
            
            if acc_code not in acc_summary:
                acc_summary[acc_code] = {}
            
            if area not in acc_summary[acc_code]:
                acc_summary[acc_code][area] = set()
            
            acc_summary[acc_code][area].add(f"{media} : {store}")

        # アカウントごとに表示
        for acc_code in POSTING_ACCOUNT_OPTIONS:
            if acc_code in acc_summary:
                with st.container():
                    # アカウント名を強調
                    st.markdown(f"### 👤 投稿{acc_code}アカウント")
                    
                    # そのアカウント内のエリアを横並び、または整理して表示
                    areas = acc_summary[acc_code]
                    area_cols = st.columns(len(areas) if len(areas) > 0 else 1)
                    
                    for idx, (area_name, shops) in enumerate(areas.items()):
                        with area_cols[idx]:
                            # エリアごとにカード状に表示
                            st.info(f"📍 **{area_name}**")
                            for shop in sorted(shops):
                                st.write(f"　└ {shop}")
                    st.markdown("---") # アカウントごとの区切り線
            else:
                st.markdown(f"### 👤 投稿{acc_code}アカウント")
                st.caption("稼働データなし")
                st.markdown("---")
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

