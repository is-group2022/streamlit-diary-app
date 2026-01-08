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
    
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
except KeyError:
    st.error("🚨 secrets.tomlの設定を確認してください。")
    st.stop()

# ヘッダー定義 (G列までの7項目)
REGISTRATION_HEADERS = ["エリア", "店名", "媒体", "投稿時間", "女の子の名前", "タイトル", "本文"]
INPUT_HEADERS = ["投稿時間", "女の子の名前", "タイトル", "本文"]

# --- 2. Google API連携関数 ---

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
    st.error(f"❌ API接続失敗: {e}")
    st.stop()

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

# セッション状態管理
if 'diary_entries' not in st.session_state:
    st.session_state.diary_entries = [{h: "" for h in INPUT_HEADERS} for _ in range(40)]

tab1, tab2, tab3 = st.tabs(["📝 ① データ登録", "📂 ② 投稿データ管理", "📚 ③ 日記全文表示"])

# =========================================================
# --- Tab 1: データ登録 ---
# =========================================================
with tab1:
    st.header("1️⃣ 新規データ登録")
    
    c1, c2, c3, c4 = st.columns(4)
    target_acc = c1.selectbox("👤 投稿アカウント", POSTING_ACCOUNT_OPTIONS)
    st.session_state.global_media = c2.selectbox("🌐 媒体", MEDIA_OPTIONS)
    global_area = c3.text_input("📍 エリア")
    global_store = c4.text_input("🏢 店名")

    with st.form("reg_form"):
        for i in range(40):
            cols = st.columns([1, 1, 2, 3, 2])
            st.session_state.diary_entries[i]['投稿時間'] = cols[0].text_input("時間", key=f"t_{i}", label_visibility="collapsed")
            st.session_state.diary_entries[i]['女の子の名前'] = cols[1].text_input("名", key=f"n_{i}", label_visibility="collapsed")
            st.session_state.diary_entries[i]['タイトル'] = cols[2].text_area("題", key=f"ti_{i}", height=50, label_visibility="collapsed")
            st.session_state.diary_entries[i]['本文'] = cols[3].text_area("本", key=f"b_{i}", height=50, label_visibility="collapsed")
            st.session_state.diary_entries[i]['img'] = cols[4].file_uploader("画", key=f"img_{i}", label_visibility="collapsed")
        
        if st.form_submit_button("🔥 データを登録する", type="primary"):
            valid_data = [e for e in st.session_state.diary_entries if e['投稿時間'] and e['女の子の名前']]
            if not valid_data: st.error("データを入力してください"); st.stop()
            
            # 画像アップロード
            for e in valid_data:
                if e['img']: drive_upload_wrapper(e['img'], e, global_area, global_store)
            
            # シート書き込み
            ws = SPRS.worksheet(POSTING_ACCOUNT_SHEETS[target_acc])
            rows = [[global_area, global_store, st.session_state.global_media, e['投稿時間'], e['女の子の名前'], e['タイトル'], e['本文']] for e in valid_data]
            ws.append_rows(rows, value_input_option='USER_ENTERED')
            st.success(f"✅ {len(rows)}件登録完了！")

# =========================================================
# --- Tab 2: 投稿データ管理 (空行を除外して表示) ---
# =========================================================
with tab2:
    st.header("2️⃣ 投稿データ管理 (全アカウント統合編集)")
    st.info("💡 データが入っている行のみ表示しています。編集後、下のボタンで保存してください。")

    # 1. データ読み込みとフィルタリング
    combined_data = []
    for acc_code, sheet_name in POSTING_ACCOUNT_SHEETS.items():
        try:
            ws = SPRS.worksheet(sheet_name)
            raw_data = ws.get_all_values()
            
            if len(raw_data) > 1:
                header = raw_data[0]
                for i, row in enumerate(raw_data[1:]):
                    # --- 修正ポイント：空行判定 ---
                    # A列〜G列（0〜6番目）のうち、一つでも文字が入っているか確認
                    # 全く入力がない行、またはスペースだけの行はスキップします
                    if any(cell.strip() for cell in row[:7]):
                        # 元のシート名と行番号(1-based, header含む)を保持
                        # row[:7] で確実にG列までを取得
                        combined_data.append([acc_code, i + 2] + row[:7])
        except Exception as e:
            continue

    # 2. テーブル表示と保存処理
    if combined_data:
        # 表示用カラム定義（ID代わりのアカウント・行番号 + 登録用ヘッダー）
        df = pd.DataFrame(combined_data, columns=["アカウント", "行番号"] + REGISTRATION_HEADERS)
        
        # 編集可能なテーブルを表示
        edited_df = st.data_editor(
            df,
            key="main_editor",
            use_container_width=True,
            hide_index=True,
            disabled=["アカウント", "行番号"], # 編集不可
            height=600,
            # カラムごとの表示幅や設定（お好みで）
            column_config={
                "本文": st.column_config.TextColumn("本文", width="large"),
                "タイトル": st.column_config.TextColumn("タイトル", width="medium"),
            }
        )

        st.markdown("---")
        
        # 保存ボタン
        if st.button("💾 変更内容をスプレッドシートに反映する", type="primary"):
            with st.spinner("スプレッドシートを更新中..."):
                try:
                    # 更新が必要な行を特定して書き込み
                    for acc_code in POSTING_ACCOUNT_OPTIONS:
                        # 編集後のデータから、該当アカウントの行だけを抽出
                        target_rows = edited_df[edited_df["アカウント"] == acc_code]
                        if target_rows.empty:
                            continue
                        
                        ws = SPRS.worksheet(POSTING_ACCOUNT_SHEETS[acc_code])
                        
                        for _, row in target_rows.iterrows():
                            row_idx = int(row["行番号"])
                            # 画面で編集した A-G列のデータをリスト化
                            new_values = [
                                str(row["エリア"]),
                                str(row["店名"]),
                                str(row["媒体"]),
                                str(row["投稿時間"]),
                                str(row["女の子の名前"]),
                                str(row["タイトル"]),
                                str(row["本文"])
                            ]
                            
                            # ピンポイントでその行（A:G）を更新
                            cell_range = f"A{row_idx}:G{row_idx}"
                            ws.update(cell_range, [new_values], value_input_option='USER_ENTERED')
                    
                    st.success("🎉 すべての変更が反映されました！")
                    st.balloons()
                except Exception as e:
                    st.error(f"❌ 更新中にエラーが発生しました: {e}")
    else:
        st.info("現在、どのアカウントにも投稿待ちデータはありません。")

# =========================================================
# --- Tab 3: テンプレート全文表示 ---
# =========================================================
with tab3:
    st.header("3️⃣ テンプレート確認用")
    try:
        tmp_sprs = connect_to_gsheets(USABLE_DIARY_SHEET_ID)
        tmp_ws = tmp_sprs.worksheet(USABLE_DIARY_SHEET)
        tmp_data = tmp_ws.get_all_values()
        if len(tmp_data) > 1:
            st.dataframe(pd.DataFrame(tmp_data[1:], columns=tmp_data[0]), use_container_width=True)
    except: st.warning("テンプレート読み込み失敗")

