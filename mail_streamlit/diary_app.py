import streamlit as st
import pandas as pd
import gspread
from io import BytesIO
import time 
import traceback 
# --- Drive API 連携に必要なライブラリ ---
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
# ----------------------------------------

# --- 1. 定数と初期設定 ---
try:
    # 接続に必要な情報は st.secrets から取得
    SHEET_ID = st.secrets["google_resources"]["spreadsheet_id"]
    # DRIVE_FOLDER_ID は「写メ日記画像用」フォルダのID（共有ドライブ内の最上位フォルダ）
    DRIVE_FOLDER_ID = st.secrets["google_resources"]["drive_folder_id"] 
    SHEET_NAMES = st.secrets["sheet_names"]
    
    REGISTRATION_SHEET = SHEET_NAMES["registration_sheet"]
    CONTACT_SHEET = SHEET_NAMES["contact_sheet"]
    USABLE_DIARY_SHEET = SHEET_NAMES["usable_diary_sheet"]
    HISTORY_SHEET = SHEET_NAMES["history_sheet"]
    
    # プルダウンの選択肢
    MEDIA_OPTIONS = ["駅ちか", "デリじゃ"]
    ACCOUNT_OPTIONS = ["A", "B", "SUB"]
    
    # APIスコープをSheetsとDriveの両方に設定
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]

except KeyError:
    st.error("🚨 GoogleリソースIDまたはシート名がsecrets.tomlに正しく設定されていません。")
    st.stop()


# 最終確定した「日記登録用シート」のヘッダー定義 (11項目)
REGISTRATION_HEADERS = [
    "エリア", "店名", "媒体", "投稿時間", "女の子の名前", "タイトル", "本文", "担当アカウント", 
    "下書き登録確認", "画像添付確認", "宛先登録確認" 
]
INPUT_HEADERS = REGISTRATION_HEADERS[:8] 


# --- 2. Google API連携関数 ---

@st.cache_resource(ttl=3600)
def connect_to_gsheets():
    """GSpreadでGoogle Sheetsに接続し、クライアントを返す"""
    try:
        # サービスの認証情報をsecretsから取得して接続
        client = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        spreadsheet = client.open_by_key(SHEET_ID)
        return spreadsheet
    except Exception as e:
        st.error(f"❌ Google Sheets への接続に失敗しました: {e}")
        st.stop()
        
# 実際の接続を実行
SPRS = connect_to_gsheets()


@st.cache_resource(ttl=3600)
def connect_to_drive():
    """Google Drive API クライアントを初期化する"""
    try:
        # サービスの認証情報を作成
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        
        # Drive API サービスをビルド
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        st.error(f"❌ Google Drive API への接続に失敗しました: {e}")
        st.stop()

# Drive APIクライアントを初期化
try:
    DRIVE_SERVICE = connect_to_drive()
except SystemExit:
    pass

# --- 2-1. Drive フォルダ管理ヘルパー関数 ---

def find_folder_by_name(service, name, parent_id):
    """指定された親フォルダ内でフォルダ名を探す"""
    query = (
        f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed = false"
    )
    results = service.files().list(
        q=query, 
        spaces='drive', 
        fields='files(id, name)'
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
        fields='id'
    ).execute()
    return file.get('id')

def get_or_create_folder(service, name, parent_id):
    """フォルダIDを取得。なければ作成する"""
    folder_id = find_folder_by_name(service, name, parent_id)
    
    if not folder_id:
        st.caption(f"  [新規フォルダ作成] -> 親ID: {parent_id}, フォルダ名: '{name}'")
        folder_id = create_folder(service, name, parent_id)
        
    return folder_id


def upload_file_to_drive(uploaded_file, file_name, destination_folder_id, service):
    """
    指定されたフォルダIDにファイルをアップロードする
    """
    try:
        file_content = uploaded_file.getvalue()
        
        # StreamlitのUploadedFileオブジェクトからファイルストリームを作成
        media_body = MediaIoBaseUpload(
            BytesIO(file_content),
            mimetype=uploaded_file.type,
            resumable=True
        )

        # ファイルメタデータ
        file_metadata = {
            'name': file_name,
            'parents': [destination_folder_id],  # 最終格納先フォルダID
        }

        # アップロード実行
        file = service.files().create(
            body=file_metadata,
            media_body=media_body,
            fields='id'
        ).execute()

        file_id = file.get('id')
        
        st.caption(f"  [ファイル格納成功] -> **ファイル名: {file_name}** (ID: {file_id})")
        
        return file_id
        
    except Exception as e:
        # ここで発生する 403 エラーを捕捉
        st.error(f"❌ Driveへのアップロード中にエラーが発生しました: {e}")
        return None


def drive_upload_wrapper(uploaded_file, entry, drive_service):
    """
    動的なフォルダ階層を構築し、ファイルをアップロードするメイン関数
    """
    # 1. データ抽出
    area_name = entry['エリア'].strip()
    store_name_base = entry['店名'].strip()
    media_type = entry['媒体']
    
    if not area_name or not store_name_base:
        st.error("❌ エリア名または店名が入力されていません。画像アップロードをスキップします。")
        return None

    # 2. 最終店舗フォルダ名の決定
    if media_type == "デリじゃ":
        store_folder_name = f"デリじゃ {store_name_base}"
    else: # 駅ちかの場合
        store_folder_name = store_name_base

    # 3. エリアフォルダの検索/作成 (親: DRIVE_FOLDER_ID = 写メ日記画像用)
    area_folder_id = get_or_create_folder(drive_service, area_name, DRIVE_FOLDER_ID)
    if not area_folder_id:
        st.error(f"❌ エリアフォルダ '{area_name}' の作成に失敗しました。")
        return None

    # 4. 店舗フォルダの検索/作成 (親: area_folder_id)
    store_folder_id = get_or_create_folder(drive_service, store_folder_name, area_folder_id)
    if not store_folder_id:
        st.error(f"❌ 店舗フォルダ '{store_folder_name}' の作成に失敗しました。")
        return None

    # 5. ファイル名の決定
    hhmm = entry['投稿時間'].strip() 
    girl_name = entry['女の子の名前'].strip()
    ext = uploaded_file.name.split('.')[-1]
    new_filename = f"{hhmm}_{girl_name}.{ext}"
    
    # 6. ファイルアップロード実行
    return upload_file_to_drive(uploaded_file, new_filename, store_folder_id, drive_service)


# --- 3. 実行ロジック (プレースホルダー関数) ---
# (中略：変更なし)
def run_step(step_num, action_desc, sheet_name=REGISTRATION_SHEET):
    """実行ステップのシミュレーションとシート更新のプレースホルダー"""
    st.info(f"🔄 Step {step_num}: **{action_desc}** を実行中...")
    time.sleep(1.5) 
    st.success(f"✅ Step {step_num}: **{action_desc}** が完了しました。")
    return True

def run_step_5_move_to_history():
    """Step 5: 履歴へ移動（新規機能）"""
    st.info("🔄 Step 5: **実行済みデータ**を履歴シートへ移動中...")
    time.sleep(2) 
    st.success("✅ Step 5: 実行済みデータが履歴シートへ移動・削除されました。")


# --- 4. Streamlit UI 構築 ---
# (中略：UI設定、CSS、セッションステートの初期化は変更なし)

st.set_page_config(
    layout="wide", 
    page_title="写メ日記投稿管理アプリ",
    initial_sidebar_state="collapsed", 
    menu_items={'About': "日記投稿のための効率化アプリです。"}
)

st.markdown("""<style>...</style>""", unsafe_allow_html=True) # CSSは省略
st.title("✨ 写メ日記投稿管理アプリ - Daily Posting Manager")

# タブの定義
tab1, tab2, tab3, tab4 = st.tabs([
    "📝 ① データ登録・画像アップロード", 
    "🚀 ② 下書き作成・実行", 
    "📂 ③ 自動投稿データの検索・管理", 
    "📚 ④ 使用可能日記全文表示" 
])

# =========================================================
# --- Tab 1: データ登録・画像アップロード ---
# =========================================================

with tab1:
    st.header("1️⃣ データ準備・入力")
    
    st.subheader("📖 日記使用可能文（コピペ用）")
    st.info("💡 **コピペ補助**：全画面でテンプレートを表示・コピペする場合は、**「📚 ④ 使用可能日記全文表示」タブ**をご利用ください。")
    st.markdown("---")
    
    # --- B. 40件の日記データ入力 ---
    st.subheader("2️⃣ 登録用データ入力と画像アップロード (最大40件)")

    # **媒体と担当アカウントの全体設定（全体適用）**
    st.markdown("#### ⚙️ 全体設定 (40件すべてに適用されます)")
    cols_global = st.columns(2)
    st.session_state.global_media = cols_global[0].selectbox("🌐 媒体", MEDIA_OPTIONS, key='global_media_select')
    st.session_state.global_account = cols_global[1].selectbox("👤 担当アカウント", ACCOUNT_OPTIONS, key='global_account_select')
    
    st.warning("⚠️ **重要**：画像ファイル名は**投稿時間(hhmm)**と**女の子の名前**から自動生成されます。必ず入力してください。")

    with st.form("diary_registration_form"):
        
        # ヘッダー行 (UIに表示される項目のみ)
        col_header = st.columns([1, 1, 1, 2, 3, 1, 2]) 
        col_header[0].markdown("📍 **エリア**")
        # ... (ヘッダー定義は省略)
        col_header[6].markdown("📷 **画像ファイル**")

        st.markdown("<hr style='border: 1px solid #ddd; margin: 10px 0;'>", unsafe_allow_html=True) 
        
        # 40行分の入力と画像アップロードをループで生成 (UI入力部分は変更なし)
        for i in range(len(st.session_state.diary_entries)):
            entry = st.session_state.diary_entries[i]
            cols = st.columns([1, 1, 1, 2, 3, 1, 2]) 
            
            entry['エリア'] = cols[0].text_input("", value=entry['エリア'], key=f"エリア_{i}", label_visibility="collapsed") 
            entry['店名'] = cols[1].text_input("", value=entry['店名'], key=f"店名_{i}", label_visibility="collapsed") 
            entry['投稿時間'] = cols[2].text_input("", value=entry['投稿時間'], key=f"時間_{i}", label_visibility="collapsed") 
            entry['タイトル'] = cols[3].text_area("", value=entry['タイトル'], key=f"タイトル_{i}", height=50, label_visibility="collapsed")
            entry['本文'] = cols[4].text_area("", value=entry['本文'], key=f"本文_{i}", height=100, label_visibility="collapsed")
            entry['女の子の名前'] = cols[5].text_input("", value=entry['女の子の名前'], key=f"名_{i}", label_visibility="collapsed") 
            
            with cols[6]:
                uploaded_file = st.file_uploader("画像", type=['png', 'jpg', 'jpeg'], key=f"image_{i}", label_visibility="collapsed")
                entry['画像ファイル'] = uploaded_file
                if entry['画像ファイル']:
                    st.caption(f"💾 {entry['画像ファイル'].name}")

            st.markdown("---") 
            
        # フォームの送信ボタン（データ登録実行）
        submitted = st.form_submit_button("🔥 登録データと画像を Google Sheets/Drive に格納して実行準備完了", type="primary")

        if submitted:
            valid_entries_and_files = []
            # ... (valid_entries_and_files の抽出ロジックは変更なし)
            for entry in st.session_state.diary_entries:
                input_check_headers = ["エリア", "店名", "投稿時間", "女の子の名前", "タイトル", "本文"]
                is_data_filled = any(entry.get(h) and entry.get(h) != "" for h in input_check_headers)
                
                if is_data_filled:
                    # 全体設定の媒体とアカウントをここで確定させる
                    entry['媒体'] = st.session_state.global_media
                    entry['担当アカウント'] = st.session_state.global_account
                    valid_entries_and_files.append(entry)
            
            if not valid_entries_and_files:
                st.error("入力データがありません。")
                st.stop()
            
            # 1. Drive アップロード (動的フォルダ作成を実行)
            st.info(f"入力件数: {len(valid_entries_and_files)}件の登録処理を開始します。")
            uploaded_count = 0
            
            for i, entry in enumerate(valid_entries_and_files):
                if entry['画像ファイル']:
                    # drive_upload_wrapper を呼び出し、動的フォルダ作成とアップロードを実行
                    file_id = drive_upload_wrapper(entry['画像ファイル'], entry, DRIVE_SERVICE)
                    if file_id:
                        uploaded_count += 1
                else:
                    st.warning(f"No. {i+1} は画像なしでテキストのみ登録されます。")
            
            st.success(f"✅ **{uploaded_count}枚**の画像を Drive へ格納しました。")

            # 2. シート書き込み
            try:
                ws = SPRS.worksheet(REGISTRATION_SHEET)
                
                final_data = []
                for entry in valid_entries_and_files:
                    row_data = [
                        entry['エリア'], entry['店名'], entry['媒体'], # 媒体も使用
                        entry['投稿時間'], entry['女の子の名前'], entry['タイトル'],
                        entry['本文'], entry['担当アカウント'] 
                    ]
                    # I, J, K 列は空白で追加する (修正済み)
                    row_data.extend(['', '', '']) 
                    final_data.append(row_data)

                ws.append_rows(final_data, value_input_option='USER_ENTERED')
                
                st.balloons()
                st.success(f"🎉 **{len(valid_entries_and_files)}件**のデータ登録が完了しました。")
                st.info("次の作業は Tab ② で実行してください。")
            
            except Exception as e:
                st.error(f"❌ データ登録中に重大なエラーが発生しました: {e}")


# =========================================================
# --- Tab 2, 3, 4: (変更なし) ---
# =========================================================

# Tab 2, 3, 4 のコードは変更がないため、この回答では省略します。
