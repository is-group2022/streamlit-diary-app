import streamlit as st
import pandas as pd
import gspread
from io import BytesIO
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload  

# --- 1. 定数と初期設定 ---
try:
    SHEET_ID = st.secrets["google_resources"]["spreadsheet_id"] 
    DRIVE_FOLDER_ID = st.secrets["google_resources"]["drive_folder_id"] 
    ACCOUNT_STATUS_SHEET_ID = "1_GmWjpypap4rrPGNFYWkwcQE1SoK3QOMJlozEhkBwVM"
    USABLE_DIARY_SHEET_ID = "1e-iLey43A1t0bIBoijaXP55t5fjONdb0ODTSS53beqM"

    SHEET_NAMES = st.secrets["sheet_names"]
    POSTING_ACCOUNT_SHEETS = {
        "A": "投稿Aアカウント",
        "B": "投稿Bアカウント",
        "C": "投稿Cアカウント",
        "D": "投稿Dアカウント"
    }
    
    USABLE_DIARY_SHEET = SHEET_NAMES["usable_diary_sheet"]
    MEDIA_OPTIONS = ["駅ちか", "デリじゃ"]
    POSTING_ACCOUNT_OPTIONS = ["A", "B", "C", "D"] 
    
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
except KeyError:
    st.error("🚨 secrets.tomlの設定を確認してください。")
    st.stop()

REGISTRATION_HEADERS = ["エリア", "店名", "媒体", "投稿時間", "女の子の名前", "タイトル", "本文"]
INPUT_HEADERS = ["投稿時間", "女の子の名前", "タイトル", "本文"]

# --- 2. Google API連携 ---
@st.cache_resource(ttl=3600)
def connect_to_gsheets(sheet_id):
    client = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    return client.open_by_key(sheet_id)

try:
    SPRS = connect_to_gsheets(SHEET_ID)
    STATUS_SPRS = connect_to_gsheets(ACCOUNT_STATUS_SHEET_ID) 
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=SCOPES)
    DRIVE_SERVICE = build('drive', 'v3', credentials=creds)
except Exception as e:
    st.error(f"❌ API接続失敗: {e}"); st.stop()

# --- Drive 補助関数 ---
def get_or_create_folder(name, parent_id):
    query = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed = false"
    results = DRIVE_SERVICE.files().list(q=query, spaces='drive', fields='files(id, name)', supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
    files = results.get('files', [])
    if files: return files[0]['id']
    meta = {'name': name, 'mimeType': 'application/vnd.google-apps.folder', 'parents': [parent_id]}
    return DRIVE_SERVICE.files().create(body=meta, fields='id', supportsAllDrives=True).execute().get('id')

def drive_upload_wrapper(uploaded_file, entry, area, store):
    folder_name = f"デリじゃ {store}" if st.session_state.global_media == "デリじゃ" else store
    area_id = get_or_create_folder(area, DRIVE_FOLDER_ID)
    store_id = get_or_create_folder(folder_name, area_id)
    ext = uploaded_file.name.split('.')[-1]
    new_name = f"{entry['投稿時間'].strip()}_{entry['女の子の名前'].strip()}.{ext}"
    media = MediaIoBaseUpload(BytesIO(uploaded_file.getvalue()), mimetype=uploaded_file.type, resumable=True)
    DRIVE_SERVICE.files().create(body={'name': new_name, 'parents': [store_id]}, media_body=media, supportsAllDrives=True).execute()
    return True

# --- 3. UI 構築 ---
st.set_page_config(layout="wide", page_title="写メ日記投稿管理")

if 'diary_entries' not in st.session_state:
    st.session_state.diary_entries = [{h: "" for h in INPUT_HEADERS} for _ in range(40)]

tab1, tab2, tab3 = st.tabs(["📝 ① データ登録", "📂 ② 投稿データ管理", "📚 ③ 日記全文表示"])

# =========================================================
# --- Tab 1: データ登録 ---
# =========================================================
with tab1:
    st.header("1️⃣ 新規データ登録")
    
    # --- 共通入力エリア ---
    c1, c2, c3, c4 = st.columns(4)
    target_acc = c1.selectbox("👤 投稿アカウント", POSTING_ACCOUNT_OPTIONS)
    st.session_state.global_media = c2.selectbox("🌐 媒体", MEDIA_OPTIONS)
    global_area = c3.text_input("📍 エリア")
    global_store = c4.text_input("🏢 店名")

    # --- ログイン情報（アカウント登録用） ---
    st.markdown("---")
    st.subheader("🔑 ログイン情報（アカウント登録用）")
    c5, c6 = st.columns(2)
    login_id = c5.text_input("ID", key="login_id")
    login_pw = c6.text_input("パスワード", key="login_pw") # type="password"を削除して見えるように

    # --- 投稿内容入力エリア ---
    st.markdown("---")
    st.subheader("📸 投稿内容入力")
    
    with st.form("reg_form"):
        # ヘッダーラベルを表示
        h_cols = st.columns([1, 1, 2, 3, 2])
        h_cols[0].write("**投稿時間**")
        h_cols[1].write("**女の子の名前**")
        h_cols[2].write("**タイトル**")
        h_cols[3].write("**本文**")
        h_cols[4].write("**画像**")

        # 40行の入力欄を生成
        for i in range(40):
            cols = st.columns([1, 1, 2, 3, 2])
            st.session_state.diary_entries[i]['投稿時間'] = cols[0].text_input(f"時間{i}", key=f"t_{i}", label_visibility="collapsed")
            st.session_state.diary_entries[i]['女の子の名前'] = cols[1].text_input(f"名{i}", key=f"n_{i}", label_visibility="collapsed")
            st.session_state.diary_entries[i]['タイトル'] = cols[2].text_area(f"題{i}", key=f"ti_{i}", height=68, label_visibility="collapsed")
            st.session_state.diary_entries[i]['本文'] = cols[3].text_area(f"本{i}", key=f"b_{i}", height=68, label_visibility="collapsed")
            st.session_state.diary_entries[i]['img'] = cols[4].file_uploader(f"画{i}", key=f"img_{i}", label_visibility="collapsed")
        
        if st.form_submit_button("🔥 データを登録する", type="primary"):
            valid_data = [e for e in st.session_state.diary_entries if e['投稿時間'] and e['女の子の名前']]
            if not valid_data: st.error("投稿内容（時間と名前）を入力してください"); st.stop()
            
            # A. 画像アップロード
            for e in valid_data:
                if e['img']: drive_upload_wrapper(e['img'], e, global_area, global_store)
            
            # B. メインシート（投稿内容 A-G列）書き込み
            ws_main = SPRS.worksheet(POSTING_ACCOUNT_SHEETS[target_acc])
            rows_main = [[global_area, global_store, st.session_state.global_media, e['投稿時間'], e['女の子の名前'], e['タイトル'], e['本文']] for e in valid_data]
            ws_main.append_rows(rows_main, value_input_option='USER_ENTERED')
            
            # C. ステータス管理シート（ログイン情報）書き込み
            # エリア,店名,媒体,ID,PASSWORD
            ws_status = STATUS_SPRS.worksheet(POSTING_ACCOUNT_SHEETS[target_acc])
            status_row = [global_area, global_store, st.session_state.global_media, login_id, login_pw]
            ws_status.append_row(status_row, value_input_option='USER_ENTERED')
            
            st.success(f"✅ 投稿データ {len(rows_main)} 件とログイン情報を正常に登録しました！")

# =========================================================
# --- Tab 2: 投稿データ管理 (統合編集) ---
# =========================================================
with tab2:
    st.header("2️⃣ 投稿データ管理 (全アカウント統合編集)")
    
    combined_data = []
    for acc_code, sheet_name in POSTING_ACCOUNT_SHEETS.items():
        try:
            ws = SPRS.worksheet(sheet_name)
            raw_data = ws.get_all_values()
            if len(raw_data) > 1:
                for i, row in enumerate(raw_data[1:]):
                    if any(cell.strip() for cell in row[:7]):
                        combined_data.append([acc_code, i + 2] + row[:7])
        except: continue

    if combined_data:
        df = pd.DataFrame(combined_data, columns=["アカウント", "行番号"] + REGISTRATION_HEADERS)
        edited_df = st.data_editor(df, key="main_editor", use_container_width=True, hide_index=True, disabled=["アカウント", "行番号"], height=600)

        if st.button("💾 変更内容をスプレッドシートに反映する", type="primary"):
            with st.spinner("更新中..."):
                try:
                    for acc_code in POSTING_ACCOUNT_OPTIONS:
                        target_rows = edited_df[edited_df["アカウント"] == acc_code]
                        if target_rows.empty: continue
                        ws = SPRS.worksheet(POSTING_ACCOUNT_SHEETS[acc_code])
                        for _, row in target_rows.iterrows():
                            row_idx = int(row["行番号"])
                            new_values = [str(row[h]) for h in REGISTRATION_HEADERS]
                            ws.update(f"A{row_idx}:G{row_idx}", [new_values], value_input_option='USER_ENTERED')
                    st.success("🎉 スプレッドシートを更新しました！")
                except Exception as e:
                    st.error(f"❌ 更新エラー: {e}")
    else:
        st.info("登録されているデータはありません。")
# =========================================================
# --- Tab 3: テンプレート確認用 (デバッグ・診断版) ---
# =========================================================
with tab3:
    st.header("3️⃣ テンプレート確認用")
    try:
        # 診断1: スプレッドシートを開けるか？
        st.write(f"🔍 スプレッドシート(ID: {USABLE_DIARY_SHEET_ID}) に接続中...")
        tmp_sprs = connect_to_gsheets(USABLE_DIARY_SHEET_ID)
        st.success("✅ スプレッドシート自体の接続に成功しました！")

        # 診断2: 存在するシート名（タブ名）の一覧を取得
        all_worksheets = [ws.title for ws in tmp_sprs.worksheets()]
        st.write(f"📋 見つかったシート名一覧: {all_worksheets}")

        # 診断3: 指定したシート名が存在するか？
        target_name = USABLE_DIARY_SHEET
        if target_name in all_worksheets:
            tmp_ws = tmp_sprs.worksheet(target_name)
            tmp_data = tmp_ws.get_all_values()
            if len(tmp_data) > 1:
                st.dataframe(pd.DataFrame(tmp_data[1:], columns=tmp_data[0]), use_container_width=True)
            else:
                st.info("シートは存在しますが、データが空です。")
        else:
            st.error(f"❌ 指定されたシート名「{target_name}」が見つかりません。上の「見つかったシート名一覧」の中にある名前に secrets.toml を修正してください。")

    except Exception as e:
        st.error(f"🚨 致命的なエラーが発生しました: {e}")
        st.info("ヒント: スプレッドシートIDが正しいか、サービスアカウントに共有されているか確認してください。")
