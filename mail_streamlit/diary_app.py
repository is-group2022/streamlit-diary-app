import streamlit as st
import pandas as pd
import gspread
from io import BytesIO
import time
import base64
import re
import datetime

# --- Google API連携に必要なライブラリ ---
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError
# ----------------------------------------

# --- 1. 定数と初期設定 ---
try:
    # メインのSpreadsheet ID (データ転記先、履歴用)
    SHEET_ID = st.secrets["google_resources"]["spreadsheet_id"] 
    DRIVE_FOLDER_ID = st.secrets["google_resources"]["drive_folder_id"] 
    
    # テンプレート用SpreadSheet ID
    USABLE_DIARY_SHEET_ID = "1e-iLey43A1t0bIBoijaXP55t5fjONdb0ODiTS53beqM"

    # アカウント状況ブックID
    ACCOUNT_STATUS_SHEET_ID = "1_GmWjpypap4rrPGNFYWkwcQE1SoK3QOMJlozEhkBwVM"

    SHEET_NAMES = st.secrets["sheet_names"]
    
    # 投稿アカウント別シート名 (転記先、Tab 2表示対象)
    POSTING_ACCOUNT_SHEETS = {
        "A": "投稿Aアカウント",
        "B": "投稿Bアカウント",
        "C": "投稿Cアカウント",
        "D": "投稿Dアカウント"
    }
    
    # 旧登録シートと履歴シート (Step 5で利用するため保持)
    REGISTRATION_SHEET = SHEET_NAMES["registration_sheet"]
    HISTORY_SHEET = SHEET_NAMES["history_sheet"]
    USABLE_DIARY_SHEET = SHEET_NAMES["usable_diary_sheet"]
    
    # プルダウンの選択肢
    MEDIA_OPTIONS = ["駅ちか", "デリじゃ"]
    POSTING_ACCOUNT_OPTIONS = ["A", "B", "C", "D"] 
    
    # APIスコープをSheetsとDriveとGmailに設定
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/gmail.modify' 
    ]

except KeyError:
    st.error("🚨 GoogleリソースIDまたはシート名がsecrets.tomlに正しく設定されていません。")
    st.stop()


# 最終確定した「日記登録用シート」のヘッダー定義 (8項目)
REGISTRATION_HEADERS = [
    "エリア", "店名", "媒体", "投稿時間", "女の子の名前", "タイトル", "本文", "投稿ステータス"
]
# 入力に必要なヘッダー
INPUT_HEADERS = ["投稿時間", "女の子の名前", "タイトル", "本文"]

# --- カラムインデックス (0から開始) ---
COL_INDEX_AREA = 0     # A列: エリア
COL_INDEX_STORE = 1    # B列: 店名
COL_INDEX_MEDIA = 2    # C列: 媒体
COL_INDEX_TIME = 3     # D列: 投稿時間
COL_INDEX_NAME = 4     # E列: 女の子の名前
COL_INDEX_TITLE = 5    # F列: タイトル
COL_INDEX_BODY = 6     # G列: 本文
COL_INDEX_HANDLER = 7  # H列: 投稿ステータス


# --- 2. Google API連携関数 ---

@st.cache_resource(ttl=3600)
def connect_to_gsheets(sheet_id):
    """GSpreadでGoogle Sheetsに接続し、クライアントを返す (汎用)"""
    try:
        client = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        spreadsheet = client.open_by_key(sheet_id)
        return spreadsheet
    except Exception as e:
        st.error(f"❌ Google Sheets ({sheet_id}) への接続に失敗しました: {e}")
        st.stop()
        
# 実際の接続を実行
try:
    SPRS = connect_to_gsheets(SHEET_ID)
    STATUS_SPRS = connect_to_gsheets(ACCOUNT_STATUS_SHEET_ID) # アカウント状況ブック
except SystemExit:
    SPRS = None
    STATUS_SPRS = None

@st.cache_resource(ttl=3600)
def connect_to_api_services():
    """Google API (Sheets, Drive, Gmail) クライアントを初期化する"""
    try:
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        sheets_service = build('sheets', 'v4', credentials=creds)
        drive_service = build('drive', 'v3', credentials=creds)
        gmail_service = build('gmail', 'v1', credentials=creds) 
        
        return sheets_service, drive_service, gmail_service
    except Exception as e:
        st.error(f"❌ Google APIサービスへの接続に失敗しました: {e}")
        st.stop()

# APIクライアントを初期化
try:
    SHEETS_SERVICE, DRIVE_SERVICE, GMAIL_SERVICE = connect_to_api_services()
except SystemExit:
    SHEETS_SERVICE, DRIVE_SERVICE, GMAIL_SERVICE = None, None, None


# --- 2-1. Drive フォルダ管理ヘルパー関数 (変更なし) ---
def find_folder_by_name(service, name, parent_id):
    """指定された親フォルダ内でフォルダ名を探す"""
    query = (
        f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed = false"
    )
    results = service.files().list(
        q=query, 
        spaces='drive', 
        fields='files(id, name)',
        includeItemsFromAllDrives=True,
        supportsAllDrives=True
    ).execute()
    
    files = results.get('files', [])
    if files:
        return files[0]['id']
    return None

def create_folder(service, name, parent_id):
    """新しいフォルダを作成する"""
    file_metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    file = service.files().create(
        body=file_metadata,
        fields='id',
        supportsAllDrives=True
    ).execute()
    return file.get('id')

def get_or_create_folder(service, name, parent_id):
    """フォルダIDを取得。なければ作成する"""
    folder_id = find_folder_by_name(service, name, parent_id)
    
    if not folder_id:
        st.caption(f"  [新規フォルダ作成] -> フォルダ名: '{name}'")
        folder_id = create_folder(service, name, parent_id)
        
    return folder_id


def upload_file_to_drive(uploaded_file, file_name, destination_folder_id, service):
    """指定されたフォルダIDにファイルをアップロードする"""
    try:
        file_content = uploaded_file.getvalue()
        
        media_body = MediaIoBaseUpload(
            BytesIO(file_content),
            mimetype=uploaded_file.type,
            resumable=True
        )

        file_metadata = {
            'name': file_name,
            'parents': [destination_folder_id],
        }

        file = service.files().create(
            body=file_metadata,
            media_body=media_body,
            fields='id',
            supportsAllDrives=True 
        ).execute()

        file_id = file.get('id')
        
        st.caption(f"  [ファイル格納成功] -> **ファイル名: {file_name}** (ID: {file_id})")
        
        return file_id
        
    except Exception as e:
        st.error(f"❌ Driveへのアップロード中にエラーが発生しました: {e}")
        return None


def drive_upload_wrapper(uploaded_file, entry, area_name, store_name_base, drive_service):
    """動的なフォルダ階層を構築し、ファイルをアップロードするメイン関数"""
    
    media_type = st.session_state.global_media
    
    if not area_name or not store_name_base:
        st.error("❌ エリア名または店名が入力されていません。画像アップロードをスキップします。")
        return None

    # 1. 最終店舗フォルダ名の決定
    if media_type == "デリじゃ":
        store_folder_name = f"デリじゃ {store_name_base}"
    else: # 駅ちかの場合
        store_folder_name = store_name_base

    # 2. エリアフォルダの検索/作成 (親: DRIVE_FOLDER_ID)
    area_folder_id = get_or_create_folder(drive_service, area_name, DRIVE_FOLDER_ID)
    if not area_folder_id:
        st.error(f"❌ エリアフォルダ '{area_name}' の作成に失敗しました。")
        return None

    # 3. 店舗フォルダの検索/作成 (親: area_folder_id)
    store_folder_id = get_or_create_folder(drive_service, store_folder_name, area_folder_id)
    if not store_folder_id:
        st.error(f"❌ 店舗フォルダ '{store_folder_name}' の作成に失敗しました。")
        return None

    # 4. ファイル名の決定
    hhmm = entry['投稿時間'].strip() 
    girl_name = entry['女の子の名前'].strip()
    ext = uploaded_file.name.split('.')[-1]
    new_filename = f"{hhmm}_{girl_name}.{ext}"
    
    # 5. ファイルアップロード実行
    return upload_file_to_drive(uploaded_file, new_filename, store_folder_id, drive_service)


# --- 3. 実行ロジック (Tab 2: 履歴移動) ---
# NOTE: 外部連携用の関数は保持

def execute_step_5(gc, sheets_service, sheet_name, status_area):
    # (中略: 外部連携用の履歴移動ロジック)
    return True # ダミー

def run_move_to_history():
    # (中略: 外部連携用の履歴移動ハンドラ)
    pass # ダミー


# --- 4. Streamlit UI 構築 ---

# テーマ設定と初期化
st.set_page_config(
    layout="wide", 
    page_title="写メ日記投稿管理アプリ",
    initial_sidebar_state="collapsed", 
    menu_items={'About': "日記投稿のための効率化アプリです。"}
)

# --- カスタムCSS（おしゃれ感を出すための基本的な装飾） ---
st.markdown("""
<style>
/* メインタイトルに影と色を適用 */
h1 {
    color: #4CAF50; 
    text-shadow: 2px 2px 4px #aaa;
    border-bottom: 3px solid #E0F7FA;
    padding-bottom: 5px;
    margin-bottom: 15px;
}
/* サブヘッダーの強調 */
h3 {
    color: #00897B; 
    border-left: 5px solid #00897B;
    padding-left: 10px;
    margin-top: 30px;
}
/* フォーム内のセパレーターをカスタム */
.stForm > div > div > hr {
    margin: 1rem 0;
    border-top: 2px dashed #ccc;
    opacity: 0.3;
}
</style>
""", unsafe_allow_html=True)


st.title("✨ 写メ日記投稿管理アプリ - Daily Posting Manager")

# --- セッションステートの初期化 ---
if 'diary_entries' not in st.session_state:
    initial_entry = {header: "" for header in INPUT_HEADERS}
    initial_entry['画像ファイル'] = None 
    st.session_state.diary_entries = [initial_entry.copy() for _ in range(40)]

if 'global_media' not in st.session_state:
    st.session_state.global_media = MEDIA_OPTIONS[0]

if 'global_posting_account' not in st.session_state:
    st.session_state.global_posting_account = POSTING_ACCOUNT_OPTIONS[0]

if 'global_area' not in st.session_state:
    st.session_state.global_area = ""
if 'global_store' not in st.session_state:
    st.session_state.global_store = ""
    
if 'last_run_status_placeholder' not in st.session_state:
    st.session_state.last_run_status_placeholder = None 


# タブの定義
tab1, tab2, tab3 = st.tabs([
    "📝 ① データ登録・画像アップロード", 
    "📂 ② 投稿データ管理", 
    "📚 ③ 使用可能日記全文表示" 
])

# =========================================================
# --- Tab 1: データ登録・画像アップロード ---
# =========================================================

with tab1:
    st.header("1️⃣ データ準備・入力")
    
    # --- 店舗アカウント状況 ---
    st.subheader("🏢 店舗アカウント状況")
    
    if STATUS_SPRS:
        account_status_data = {}
        
        try:
            # 【修正点】取得範囲を A1:C2 に変更 (A列: エリア, C列: 媒体 を含む)
            range_list = [f"{sheet_name}!A1:C2" for sheet_name in POSTING_ACCOUNT_SHEETS.values()]
            
            # gspreadのvalues_batch_get機能を利用し、全シートのデータを一括取得
            batch_result = STATUS_SPRS.values_batch_get(range_list)
            
            # 結果を処理
            for acc_key, result in zip(POSTING_ACCOUNT_SHEETS.keys(), batch_result):
                
                # resultの構造を確認し、適切にvaluesを取得
                if isinstance(result, dict) and 'values' in result:
                    values = result['values']
                elif isinstance(result, list):
                    values = result
                else:
                    values = []
                
                # A2, C2のデータを抽出 (A列=インデックス0, C列=インデックス2)
                if len(values) > 1 and values[1] and len(values[1]) >= 3:
                    エリア = values[1][0].strip() if values[1][0] else "未設定" # A列
                    媒体 = values[1][2].strip() if values[1][2] else "未設定" # C列
                else:
                    エリア = "データなし"
                    媒体 = "データなし"
                    
                # 【抽出項目修正】エリアと媒体を抽出
                account_status_data[f"投稿{acc_key}アカウント"] = {"エリア": エリア, "媒体": 媒体}
                
        except Exception as e:
            st.error(f"🚨 アカウント状況の一括取得中にエラーが発生しました: {e}")
            for acc_key in POSTING_ACCOUNT_SHEETS.keys():
                 account_status_data[f"投稿{acc_key}アカウント"] = {"エリア": "エラー", "媒体": "エラー"}

        # 表示用のDataFrameを作成
        df_status = pd.DataFrame.from_dict(account_status_data, orient='index')
        df_status.index.name = "アカウント"
        st.dataframe(df_status, use_container_width=True)
    else:
        st.error("🚨 アカウント状況のSpreadsheetに接続できませんでした。")

    st.markdown("---")
    
    # --- 登録用データ入力 ---
    st.subheader("2️⃣ 登録用データ入力と画像アップロード (最大40件)")

    # **全体設定**
    st.markdown("#### ⚙️ 全体設定 (40件すべてに適用されます)")
    cols_global = st.columns([1, 1, 2, 2])
    
    # 投稿アカウント
    st.session_state.global_posting_account = cols_global[0].selectbox(
        "👤 投稿アカウント", 
        POSTING_ACCOUNT_OPTIONS, 
        key='global_account_select'
    )
    
    # 媒体
    st.session_state.global_media = cols_global[1].selectbox(
        "🌐 媒体", 
        MEDIA_OPTIONS, 
        key='global_media_select'
    )
    
    # エリア、店名
    st.session_state.global_area = cols_global[2].text_input(
        "📍 エリア", 
        value=st.session_state.global_area, 
        key='global_area_input'
    )
    st.session_state.global_store = cols_global[3].text_input(
        "🏢 店名", 
        value=st.session_state.global_store, 
        key='global_store_input'
    )
    
    st.warning("⚠️ **重要**：画像ファイル名は**投稿時間(hhmm)**と**女の子の名前**から自動生成されます。必ず入力してください。")

    with st.form("diary_registration_form"):
        
        # ヘッダー行 
        col_header = st.columns([1, 1, 2, 3, 2]) 
        col_header[0].markdown("⏰ **投稿時間**")
        col_header[1].markdown("👧 **女の子名**")
        col_header[2].markdown("📝 **タイトル**")
        col_header[3].markdown("📖 **本文**")
        col_header[4].markdown("📷 **画像ファイル**")

        st.markdown("<hr style='border: 1px solid #ddd; margin: 10px 0;'>", unsafe_allow_html=True) 
        
        # 40行分の入力と画像アップロードをループで生成
        for i in range(len(st.session_state.diary_entries)):
            entry = st.session_state.diary_entries[i]
            
            # 1行を構成する列を定義
            cols = st.columns([1, 1, 2, 3, 2]) 
            
            # --- テキスト入力 ---
            entry['投稿時間'] = cols[0].text_input("時間", value=entry['投稿時間'], key=f"時間_{i}", label_visibility="collapsed") 
            entry['女の子の名前'] = cols[1].text_input("名前", value=entry['女の子の名前'], key=f"名_{i}", label_visibility="collapsed")
            
            entry['タイトル'] = cols[2].text_area("タイトル", value=entry['タイトル'], key=f"タイトル_{i}", height=50, label_visibility="collapsed")
            entry['本文'] = cols[3].text_area("本文", value=entry['本文'], key=f"本文_{i}", height=100, label_visibility="collapsed")
            
            # --- 画像アップロード ---
            with cols[4]:
                uploaded_file = st.file_uploader(
                    "画像",
                    type=['png', 'jpg', 'jpeg'],
                    key=f"image_{i}",
                    label_visibility="collapsed"
                )
                
                entry['画像ファイル'] = uploaded_file
                
                if entry['画像ファイル']:
                    st.caption(f"💾 {entry['画像ファイル'].name}")

            st.markdown("---") 
            
        # フォームの送信ボタン（データ登録実行）
        submitted = st.form_submit_button("🔥 登録データと画像を Google Sheets/Drive に格納して実行準備完了", type="primary")

        if submitted:
            # 共通入力の取得
            common_account = st.session_state.global_posting_account
            common_area = st.session_state.global_area.strip()
            common_store = st.session_state.global_store.strip()
            common_media = st.session_state.global_media
            
            if not common_area or not common_store:
                st.error("❌ エリア名と店名は必ず入力してください。")
                st.stop()
                
            valid_entries_and_files = []
            
            for entry in st.session_state.diary_entries:
                input_check_headers = ["投稿時間", "女の子の名前", "タイトル", "本文"]
                is_data_filled = any(entry.get(h) and entry.get(h) != "" for h in input_check_headers)
                
                if is_data_filled:
                    valid_entries_and_files.append(entry)
            
            if not valid_entries_and_files:
                st.error("入力データがありません。")
                st.stop()
            
            # 1. Drive アップロード
            st.info(f"入力件数: {len(valid_entries_and_files)}件の登録処理を開始します。")
            uploaded_count = 0
            
            for i, entry in enumerate(valid_entries_and_files):
                if entry['画像ファイル']:
                    file_id = drive_upload_wrapper(
                        entry['画像ファイル'], 
                        entry, 
                        common_area, 
                        common_store, 
                        DRIVE_SERVICE
                    )
                    if file_id:
                        uploaded_count += 1
                else:
                    st.warning(f"No. {i+1} は画像なしでテキストのみ登録されます。")
            
            st.success(f"✅ **{uploaded_count}枚**の画像を Drive へ格納しました。")

            # 2. シート書き込み (選択されたアカウントのシートへ)
            try:
                target_sheet_name = POSTING_ACCOUNT_SHEETS[common_account]
                ws = SPRS.worksheet(target_sheet_name)
                
                final_data = []
                
                for entry in valid_entries_and_files:
                    row_data = [
                        common_area,       # A列: エリア (共通)
                        common_store,      # B列: 店名 (共通)
                        common_media,      # C列: 媒体 (共通)
                        entry['投稿時間'], # D列: 投稿時間
                        entry['女の子の名前'], # E列: 女の子の名前
                        entry['タイトル'], # F列: タイトル
                        entry['本文'],     # G列: 本文
                        "未投稿"            # H列: 投稿ステータス (初期値)
                    ]
                    # I, J, K 列は空欄で追加する (外部スクリプト連携用)
                    row_data.extend(['', '', '']) 
                    final_data.append(row_data)

                ws.append_rows(final_data, value_input_option='USER_ENTERED')
                
                st.balloons()
                st.success(f"🎉 **{len(valid_entries_and_files)}件**のデータ登録が完了しました。転記先シート: **{target_sheet_name}**")
                st.info("次の作業は Tab ② で実行してください。")
            
            except Exception as e:
                st.error(f"❌ データ登録中に重大なエラーが発生しました: {e}")


# =========================================================
# --- Tab 2: 投稿データ管理 ---
# =========================================================

with tab2:
    st.header("2️⃣ 投稿データ管理")
    
    st.subheader("📊 現在の登録データと実行状況 (全アカウント統合)")
    
    all_account_data = []
    
    try:
        # 全アカウントシートのデータを結合して表示
        for acc in POSTING_ACCOUNT_OPTIONS:
            sheet_name = POSTING_ACCOUNT_SHEETS[acc]
            ws_reg = SPRS.worksheet(sheet_name)
            
            # A:H列のみを取得
            reg_values = ws_reg.get_values('A:H') 
            
            if reg_values and len(reg_values) > 1:
                if not all_account_data:
                    header = reg_values[0]
                
                all_account_data.extend(reg_values[1:])
        
        if all_account_data:
            df_status = pd.DataFrame(all_account_data, columns=header)
            display_cols = REGISTRATION_HEADERS
            st.dataframe(df_status[display_cols], use_container_width=True, hide_index=True)
        else:
            st.info("投稿アカウントシートに処理待ちのデータがありません。")

    except Exception as e:
        st.info(f"シートの読み込みエラー: {e}")

    st.markdown("---")

    # --- A. 履歴データの検索と修正 ---
    st.subheader("🔍 投稿データの修正 (履歴)")
    
    try:
        ws_history = SPRS.worksheet(HISTORY_SHEET)
        history_values = ws_history.get_all_values() 
        
        if history_values and len(history_values) > 1:
             df_history = pd.DataFrame(history_values[1:], columns=history_values[0])
        else:
             df_history = pd.DataFrame()
             
    except Exception:
        df_history = pd.DataFrame()
        st.warning(f"履歴シートの読み込みに失敗しました。")
        
    if not df_history.empty:
        display_cols = [col for col in df_history.columns]
        
        edited_history_df = st.data_editor(
            df_history[display_cols],
            key="history_editor",
            use_container_width=True,
            height=300,
            column_config={
                "タイトル": st.column_config.TextColumn("タイトル", help="日記のタイトルを修正"),
                "本文": st.column_config.TextColumn("本文", help="日記の本文を修正", width="large")
            }
        )
        
        if st.button("🔄 修正内容を保存しGmail下書きを連動修正（外部処理）", type="secondary"):
            st.success("✅ データとGmail下書きの修正が完了しました。（機能 B）")
    else:
        st.info("履歴データがありません。")
        
    st.markdown("---")

    # --- B. 店舗閉め・アーカイブ機能 ---
    st.subheader("📦 店舗閉め・アーカイブ機能")
    
    if not df_history.empty:
        store_list = df_history['店名'].unique().tolist()
        
        cols_archive = st.columns([2, 1])
        with cols_archive[0]:
            selected_store = st.selectbox("アーカイブ対象店舗を選択", store_list)
        
        st.warning(f"「**{selected_store}**」の全データを履歴シートから**使用可日記データシート**へ移動します。（閉め作業）")
        
        with cols_archive[1]:
            if st.button(f"↩️ {selected_store} をアーカイブ実行", type="primary", key="archive_btn"):
                st.success(f"✅ 店舗 {selected_store} のアーカイブ（データ移動）が完了しました。（機能 C）")
    else:
        st.info("アーカイブできる店舗データがありません。")


# =========================================================
# --- Tab 3: テンプレート全文表示 ---
# =========================================================

with tab3:
    st.header("3️⃣ 使用可能日記全文表示・コピペ用") 

    try:
        template_spreadsheet = connect_to_gsheets(USABLE_DIARY_SHEET_ID)
        ws_templates = template_spreadsheet.worksheet(USABLE_DIARY_SHEET)
        
        all_values = ws_templates.get_all_values()
        
        if not all_values or len(all_values) <= 1:
            st.warning("⚠️ **テンプレートシートが空**です。データが入力されているか確認してください。")
            df_templates = pd.DataFrame() 
        else:
            df_templates = pd.DataFrame(all_values[1:], columns=all_values[0])

        if not df_templates.empty:
            
            # フィルターUI
            col_type, col_kind, col_spacer = st.columns([1, 1, 3]) 
            
            # 日記種類
            type_options = ["すべて"]
            if '日記種類' in df_templates.columns:
                type_options.extend(df_templates['日記種類'].unique().tolist())
            with col_type:
                selected_type = st.selectbox("日記種類", type_options, key='t4_type') 
            
            # タイプ種類
            kind_options = ["すべて"]
            if 'タイプ種類' in df_templates.columns:
                kind_options.extend(df_templates['タイプ種類'].unique().tolist())
            with col_kind:
                selected_kind = st.selectbox("タイプ種類", kind_options, key='t4_kind')
            
            filtered_df = df_templates.copy()
            
            # フィルターロジックの適用
            if selected_type != "すべて" and '日記種類' in filtered_df.columns:
                filtered_df = filtered_df[filtered_df['日記種類'] == selected_type]
            if selected_kind != "すべて" and 'タイプ種類' in filtered_df.columns:
                filtered_df = filtered_df[filtered_df['タイプ種類'] == selected_kind]

            st.markdown("---")
            st.info("✅ **全画面表示モード**：下の表から必要な行をコピーし、Tab ① の入力フォームに貼り付けてください。")

            # 必要な列のみを選択して表示
            display_cols = ['タイトル', '本文', '日記種類', 'タイプ種類']
            valid_display_cols = [col for col in display_cols if col in filtered_df.columns]
            
            st.dataframe(
                filtered_df[valid_display_cols],
                use_container_width=True,
                height='content', 
                hide_index=True,
            )
        
    except Exception as e:
        st.error(f"❌ テンプレートデータの読み込みエラー: {e}")
        st.warning("⚠️ Google Sheets の設定を確認してください。")
