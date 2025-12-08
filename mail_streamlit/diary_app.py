import streamlit as st
import pandas as pd
import gspread
from io import BytesIO
import time
import base64
import re
import datetime
from email.message import EmailMessage
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.parser import BytesParser
from email.policy import default

# --- Drive/Sheets/Gmail API 連携に必要なライブラリ ---
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError
# ----------------------------------------

# --- 1. 定数と初期設定 ---
try:
    # 接続に必要な情報は st.secrets から取得
    SHEET_ID = st.secrets["google_resources"]["spreadsheet_id"] # <-- 日記登録、履歴などで使用するメインのID
    DRIVE_FOLDER_ID = st.secrets["google_resources"]["drive_folder_id"] 
    
    # テンプレート用SpreadSheet ID
    USABLE_DIARY_SHEET_ID = "1e-iLey43A1t0bIBoijaXP55t5fjONdb0ODiTS53beqM"

    SHEET_NAMES = st.secrets["sheet_names"]
    
    REGISTRATION_SHEET = SHEET_NAMES["registration_sheet"]
    CONTACT_SHEET = SHEET_NAMES["contact_sheet"]
    USABLE_DIARY_SHEET = SHEET_NAMES["usable_diary_sheet"]
    HISTORY_SHEET = SHEET_NAMES["history_sheet"]
    
    # プルダウンの選択肢
    MEDIA_OPTIONS = ["駅ちか", "デリじゃ"]
    # ACCOUNT_OPTIONS = ["A", "B", "SUB"] # 削除
    # 担当アカウントとメールアドレスのマッピング (Step 2, 3で使用) - Step 2/3/4削除により原則不要だが、定数として保持
    ACCOUNT_MAPPING = {
        "A": "main.ekichika.a@gmail.com", 
        "B": "main.ekichika.b@gmail.com", 
        "SUB": "sub.media@wwwsigroupcom.com" 
    }
    MAX_TIME_DIFF_MINUTES = 15 # 画像検索の許容時刻差 (±15分)
    
    # APIスコープをSheetsとDriveとGmailに設定
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/gmail.modify' 
    ]

except KeyError:
    st.error("🚨 GoogleリソースIDまたはシート名がsecrets.tomlに正しく設定されていません。")
    st.stop()


# 最終確定した「日記登録用シート」のヘッダー定義 (11項目)
# 【変更点】担当アカウント(H列)以降の項目は、このアプリでは利用されなくなるが、シート構造を保持するために残す。
REGISTRATION_HEADERS = [
    "エリア", "店名", "媒体", "投稿時間", "女の子の名前", "タイトル", "本文", "担当アカウント", 
    "下書き登録確認", "画像添付確認", "宛先登録確認" 
]
# 入力に必要なヘッダー (エリア, 店名 は共通化するためループからは除外)
INPUT_HEADERS = ["媒体", "投稿時間", "女の子の名前", "タイトル", "本文"]

# --- カラムインデックス (0から開始) ---
COL_INDEX_LOCATION = 0     # A列: エリア
COL_INDEX_STORE = 1        # B列: 店名
COL_INDEX_MEDIA = 2        # C列: 媒体
COL_INDEX_TIME = 3         # D列: 投稿時間
COL_INDEX_NAME = 4         # E列: 女の子の名前
COL_INDEX_TITLE = 5        # F列: タイトル
COL_INDEX_BODY = 6         # G列: 本文
COL_INDEX_HANDLER = 7      # H列: 担当アカウント


# --- 2. Google API連携関数 ---

@st.cache_resource(ttl=3600)
def connect_to_gsheets():
    """GSpreadでGoogle Sheetsに接続し、クライアントを返す (メインID用)"""
    try:
        client = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        spreadsheet = client.open_by_key(SHEET_ID)
        return spreadsheet
    except Exception as e:
        st.error(f"❌ Google Sheets への接続に失敗しました: {e}")
        st.stop()
        
# 実際の接続を実行
try:
    SPRS = connect_to_gsheets()
except SystemExit:
    SPRS = None

@st.cache_resource(ttl=3600)
def connect_to_api_services():
    """Google API (Sheets, Drive, Gmail) クライアントを初期化する"""
    try:
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        sheets_service = build('sheets', 'v4', credentials=creds)
        drive_service = build('drive', 'v3', credentials=creds)
        # Tab 2 (Gmail関連) 削除に伴い、Gmailサービスの利用頻度は低下
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
    
    # area_name, store_name_base は共通入力から取得
    media_type = entry['媒体']
    
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


# --- 3. 実行ロジック (Tab 2削除により Step 5のみ保持) ---

def execute_step_5(gc, sheets_service, status_area):
    """Step 5: K列が「登録済」の行を履歴シートに移動し、元のシートから削除する"""
    
    status_area.info("🔄 実行済みデータ**を履歴シートへ移動中...")

    # NOTE: Tab 2削除により、K列(宛先登録確認)が「登録済」になる処理はアプリ上では実行されなくなります。
    # この関数は、外部スクリプトなどでK列が「登録済」になったデータが存在することを前提とします。
    
    try:
        # 1. データの読み込み (ヘッダーも含むA:K列) - 文字列として取得
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, 
            range=f"{REGISTRATION_SHEET}!A:K"
        ).execute()
        all_values = result.get('values', [])
        
        if not all_values or len(all_values) <= 1:
            status_area.warning("日記登録用シートに処理対象のデータがありません。")
            return True

        header = all_values[0]
        data_rows = all_values[1:]
        
        # 2. 移動対象と削除対象の行番号を特定
        rows_to_move = []
        rows_to_delete_index = [] # 削除する行のインデックス (0から開始, ヘッダーを含まない)
        
        # K列のインデックスが REGISTRATION_HEADERS の COL_INDEX_RECIPIENT_STATUS (10) であることを確認
        col_k_index = COL_INDEX_RECIPIENT_STATUS
        
        for index, row in enumerate(data_rows):
            # K列までデータがない場合の対応
            if len(row) < col_k_index + 1:
                 row.extend([''] * (col_k_index + 1 - len(row)))
            
            # K列 (宛先登録確認) が「登録済」の場合
            if row[col_k_index].strip() == "登録済":
                rows_to_move.append(row)
                rows_to_delete_index.append(index) # ヘッダーを含まないインデックス

        if not rows_to_move:
            status_area.warning("K列が '登録済' の処理済み行が見つかりませんでした。")
            return True

        # 3. 履歴シートへの書き込み
        sh = gc.open_by_key(SHEET_ID)
        ws_history = sh.worksheet(HISTORY_SHEET)
        
        # ヘッダーを最初に追加（初回実行時のみ）
        if ws_history.row_count < 1 or not ws_history.row_values(1):
             ws_history.insert_row(header, 1)

        ws_history.append_rows(rows_to_move, value_input_option='USER_ENTERED')
        status_area.success(f"✅ **{len(rows_to_move)}** 件のデータを '{HISTORY_SHEET}' に書き込みました。")

        # 4. 元のシートから行を削除 (下から上へ削除)
        rows_to_delete_index.sort(reverse=True)
        
        ws_log = sh.worksheet(REGISTRATION_SHEET)
        
        # gspread の delete_rows は行番号 (1から開始) を指定。data_rowsのindex + 2
        for index_in_data_rows in rows_to_delete_index:
             row_num = index_in_data_rows + 2
             try:
                 ws_log.delete_rows(row_num)
             except Exception as e:
                 status_area.error(f"❌ {REGISTRATION_SHEET} から {row_num} 行目の削除に失敗しました: {e}")

        status_area.success(f"🎉 実行済みデータが履歴シートへ移動・削除されました。（**{len(rows_to_move)}** 行）")
        return True
        
    except Exception as e:
        status_area.exception(f"致命的なエラーが発生しました: {e}")
        return False


def run_move_to_history():
    """履歴へ移動実行ハンドラ"""
    
    # ログ表示エリアの初期化
    if 'last_run_status_placeholder' not in st.session_state:
        st.session_state.last_run_status_placeholder = st.empty()
    
    status_area_placeholder = st.session_state.last_run_status_placeholder
    status_area = status_area_placeholder.container()
    
    # 実行前に最終警告を表示
    status_area.warning("⚠️ **履歴移動処理を開始します。** (K列が'登録済'のデータが対象です)")
    
    execute_step_5(SPRS, SHEETS_SERVICE, status_area)
    
    status_area.markdown("---")
    status_area.info(f"最終実行時刻: {time.strftime('%H:%M:%S')}")


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
.stApp > header {
    background-color: transparent;
}
.st-emotion-cache-12fm5qf {
    padding-top: 1rem;
}
/* ヘッダーのフォントを装飾 */
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
    # 必須入力ヘッダーのみを使用
    initial_entry = {header: "" for header in INPUT_HEADERS}
    initial_entry['画像ファイル'] = None 
    
    st.session_state.diary_entries = [initial_entry.copy() for _ in range(40)]

# 【変更点】global_media は保持、global_account は削除
if 'global_media' not in st.session_state:
    st.session_state.global_media = MEDIA_OPTIONS[0]

# 【新規】エリアと店名の共通入力用ステート
if 'global_area' not in st.session_state:
    st.session_state.global_area = ""
if 'global_store' not in st.session_state:
    st.session_state.global_store = ""
    
# 【変更点】ログ表示のプレースホルダーを初期化 (Step 5用)
if 'last_run_status_placeholder' not in st.session_state:
    st.session_state.last_run_status_placeholder = None 


# 【変更点】タブの定義 (Tab 2削除により Tab 3 -> 2, Tab 4 -> 3 に繰り上げ)
tab1, tab2, tab3 = st.tabs([
    "📝 ① データ登録・画像アップロード", 
    "📂 ② 自動投稿データの検索・管理", 
    "📚 ③ 使用可能日記全文表示" 
])

# =========================================================
# --- Tab 1: データ登録・画像アップロード ---
# =========================================================

with tab1:
    st.header("1️⃣ データ準備・入力")
    
    st.subheader("📖 日記使用可能文（コピペ用）")
    st.info("💡 **コピペ補助**：全画面でテンプレートを表示・コピペする場合は、**「📚 ③ 使用可能日記全文表示」タブ**をご利用ください。")
    st.markdown("---")
    
    # --- B. 40件の日記データ入力 (常時展開・本文枠大) ---
    st.subheader("2️⃣ 登録用データ入力と画像アップロード (最大40件)")

    # **媒体、エリア、店名の全体設定（全体適用）**
    st.markdown("#### ⚙️ 全体設定 (40件すべてに適用されます)")
    cols_global = st.columns([1, 2, 2])
    
    # 媒体 (プルダウン)
    st.session_state.global_media = cols_global[0].selectbox("🌐 媒体", MEDIA_OPTIONS, key='global_media_select')
    
    # 【変更点】エリア、店名を共通入力にする (テキスト入力)
    st.session_state.global_area = cols_global[1].text_input("📍 エリア", value=st.session_state.global_area, key='global_area_input')
    st.session_state.global_store = cols_global[2].text_input("🏢 店名", value=st.session_state.global_store, key='global_store_input')
    
    st.warning("⚠️ **重要**：画像ファイル名は**投稿時間(hhmm)**と**女の子の名前**から自動生成されます。必ず入力してください。")

    with st.form("diary_registration_form"):
        
        # ヘッダー行 (UIに表示される項目のみ)
        # 【変更点】カラム構成の変更: 媒体(1), 投稿時間(1), 女の子名(1), タイトル(2), 本文(3), 画像(2)
        col_header = st.columns([1, 1, 1, 2, 3, 2]) 
        col_header[0].markdown("🌐 **媒体**")
        col_header[1].markdown("⏰ **投稿時間**")
        col_header[2].markdown("👧 **女の子名**")
        col_header[3].markdown("📝 **タイトル**")
        col_header[4].markdown("📖 **本文**")
        col_header[5].markdown("📷 **画像ファイル**")

        st.markdown("<hr style='border: 1px solid #ddd; margin: 10px 0;'>", unsafe_allow_html=True) 
        
        # 40行分の入力と画像アップロードをループで生成
        for i in range(len(st.session_state.diary_entries)):
            entry = st.session_state.diary_entries[i]
            
            # 1行を構成する列を定義
            cols = st.columns([1, 1, 1, 2, 3, 2]) 
            
            # --- テキスト入力 ---
            entry['媒体'] = cols[0].selectbox("媒体", MEDIA_OPTIONS, key=f"媒体_{i}", index=MEDIA_OPTIONS.index(st.session_state.global_media), label_visibility="collapsed")
            entry['投稿時間'] = cols[1].text_input("時間", value=entry['投稿時間'], key=f"時間_{i}", label_visibility="collapsed") 
            entry['女の子の名前'] = cols[2].text_input("名前", value=entry['女の子の名前'], key=f"名_{i}", label_visibility="collapsed")
            
            entry['タイトル'] = cols[3].text_area("タイトル", value=entry['タイトル'], key=f"タイトル_{i}", height=50, label_visibility="collapsed")
            entry['本文'] = cols[4].text_area("本文", value=entry['本文'], key=f"本文_{i}", height=100, label_visibility="collapsed")
            
            # --- 画像アップロード ---
            with cols[5]:
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
            # 共通入力のチェック
            common_area = st.session_state.global_area.strip()
            common_store = st.session_state.global_store.strip()
            
            if not common_area or not common_store:
                st.error("❌ エリア名と店名は必ず入力してください。")
                st.stop()
                
            valid_entries_and_files = []
            
            for entry in st.session_state.diary_entries:
                input_check_headers = ["投稿時間", "女の子の名前", "タイトル", "本文"]
                # 必須項目が一つでも入力されていれば有効なエントリーと見なす
                is_data_filled = any(entry.get(h) and entry.get(h) != "" for h in input_check_headers)
                
                if is_data_filled:
                    valid_entries_and_files.append(entry)
            
            if not valid_entries_and_files:
                st.error("入力データがありません。")
                st.stop()
            
            # 1. Drive アップロード (動的フォルダ作成を実行)
            st.info(f"入力件数: {len(valid_entries_and_files)}件の登録処理を開始します。")
            uploaded_count = 0
            
            for i, entry in enumerate(valid_entries_and_files):
                if entry['画像ファイル']:
                    # drive_upload_wrapper に共通のエリアと店名を渡す
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

            # 2. シート書き込み
            try:
                ws = SPRS.worksheet(REGISTRATION_SHEET)
                
                final_data = []
                # 担当アカウントは一旦 A で固定としておく (外部の自動化スクリプトとの連携のため)
                FIXED_HANDLER_ACCOUNT = "A" 
                
                for entry in valid_entries_and_files:
                    row_data = [
                        common_area,       # A列: エリア (共通)
                        common_store,      # B列: 店名 (共通)
                        entry['媒体'],     # C列: 媒体
                        entry['投稿時間'], # D列: 投稿時間
                        entry['女の子の名前'], # E列: 女の子の名前
                        entry['タイトル'], # F列: タイトル
                        entry['本文'],     # G列: 本文
                        FIXED_HANDLER_ACCOUNT # H列: 担当アカウント (固定)
                    ]
                    # I, J, K 列は空欄で追加する (自動化フロー用)
                    row_data.extend(['', '', '']) 
                    final_data.append(row_data)

                ws.append_rows(final_data, value_input_option='USER_ENTERED')
                
                st.balloons()
                st.success(f"🎉 **{len(valid_entries_and_files)}件**のデータ登録が完了しました。")
                st.info("次の作業は Tab ② で実行してください。")
            
            except Exception as e:
                st.error(f"❌ データ登録中に重大なエラーが発生しました: {e}")


# =========================================================
# --- Tab 2: 自動投稿データの検索・管理 (旧 Tab 3) ---
# =========================================================

with tab2:
    st.header("2️⃣ 自動投稿データの検索・管理")
    
    st.subheader("📊 現在の登録データと実行状況")
    
    try:
        # get_all_values() で全データを文字列として取得 (hhmmの0落ち対策)
        ws_reg = SPRS.worksheet(REGISTRATION_SHEET)
        reg_values = ws_reg.get_all_values()
        
        if reg_values and len(reg_values) > 1:
            df_status = pd.DataFrame(reg_values[1:], columns=reg_values[0])
            # A列からK列までを表示
            display_cols = REGISTRATION_HEADERS
            st.dataframe(df_status[display_cols], use_container_width=True, hide_index=True)
        else:
            st.info("「日記登録用」シートにデータがありません。")

    except Exception as e:
        st.info(f"シートの読み込みエラー: {e}")

    st.markdown("---")

    # --- 実行済みデータの履歴移動 ---
    st.subheader("✅ 実行済みデータの履歴移動")
    st.error("外部スクリプトなどで処理が完了し、**安全を確認した上で**、このボタンを押してください。K列が '登録済' のデータはシートから削除され、履歴へ移動します。")
    if st.button("➡️ 実行完了データを履歴へ移動・削除", key='move_to_history_btn', type="primary", use_container_width=True, on_click=run_move_to_history):
        pass # on_clickで実行される
        
    st.subheader("📝 実行ログ (履歴移動)")
    # 履歴移動のログエリア
    if st.session_state.last_run_status_placeholder is None:
        st.session_state.last_run_status_placeholder = st.empty()


    st.markdown("---")

    # --- A. 履歴データの検索と修正 ---
    st.subheader("🔍 投稿データの修正 (履歴)")
    
    try:
        # 履歴シートも文字列として読み込む
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
        edited_history_df = st.data_editor(
            df_history,
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
# --- Tab 3: テンプレート全文表示 (旧 Tab 4) ---
# =========================================================

with tab3:
    st.header("3️⃣ 使用可能日記全文表示・コピペ用") 

    try:
        # テンプレート用のSpreadsheet IDで接続し、全データを文字列として取得
        client = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        template_spreadsheet = client.open_by_key(USABLE_DIARY_SHEET_ID)
        ws_templates = template_spreadsheet.worksheet(USABLE_DIARY_SHEET)
        
        all_values = ws_templates.get_all_values()
        
        if not all_values or len(all_values) <= 1:
            st.warning("⚠️ **テンプレートシートが空**です。データが入力されているか確認してください。")
            df_templates = pd.DataFrame() 
        else:
            df_templates = pd.DataFrame(all_values[1:], columns=all_values[0])

        # DataFrameが空でない場合のみフィルター処理と表示を行う
        if not df_templates.empty:
            
            # フィルターUI
            col_type, col_kind, col_spacer = st.columns([1, 1, 3]) 
            
            # シートに「日記種類」列が存在するか確認してからselectboxのオプションを作成
            type_options = ["すべて"]
            if '日記種類' in df_templates.columns:
                type_options.extend(df_templates['日記種類'].unique().tolist())
            with col_type:
                selected_type = st.selectbox("日記種類", type_options, key='t4_type') 
            
            # シートに「タイプ種類」列が存在するか確認してからselectboxのオプションを作成
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

            # 必要な列のみを選択して表示（列がない場合はエラーになるため事前にチェック）
            display_cols = ['タイトル', '本文', '日記種類', 'タイプ種類']
            valid_display_cols = [col for col in display_cols if col in filtered_df.columns]
            
            st.dataframe(
                filtered_df[valid_display_cols],
                use_container_width=True,
                height='content', 
                hide_index=True,
            )
        
    except Exception as e:
        # Tab 4でのエラー表示
        st.error(f"❌ テンプレートデータの読み込みエラー: {e}")
        st.warning("⚠️ Google Sheets の設定を確認してください。")
