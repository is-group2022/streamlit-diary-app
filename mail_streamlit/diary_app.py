import streamlit as st
import json
from datetime import datetime
from typing import Dict, Any, List
import io
import time

# Google APIクライアント関連のライブラリ（事前にインストールが必要です）
try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    import gspread
except ImportError:
    st.error("Google API関連のライブラリ（gspread, google-authなど）がインストールされていません。")
    st.info("コマンド: `pip install gspread google-auth google-auth-oauthlib google-api-python-client`")
    st.stop()

# --- 1. 設定情報の読み込み（Streamlit Secretsから） ---
# 🚨 必須設定キーのチェック
try:
    APP_CONFIG = st.secrets.get("app_config", {})
    SERVICE_ACCOUNT_SECRETS = st.secrets.get("google_secrets", {})

    # スプレッドシート関連の設定
    SPREADSHEET_ID = APP_CONFIG.get("SPREADSHEET_ID")
    WORKSHEET_NAMES = {
        "REGISTER": APP_CONFIG.get("WORKSHEET_REGISTER_NAME"),       # 登録用シート
        "FULL_HISTORY": APP_CONFIG.get("WORKSHEET_FULL_HISTORY_NAME"), # 全店舗データシート
        "USABLE_TEMPLATE": APP_CONFIG.get("WORKSHEET_USABLE_NAME"),   # 使用可日記データシート
        "CONTACT_ADDRESS": APP_CONFIG.get("WORKSHEET_CONTACT_NAME"),   # 連絡先登録用シート
    }
    DRIVE_ROOT_FOLDER_ID = APP_CONFIG.get("DRIVE_ROOT_FOLDER_ID") # 写メ日記画像用フォルダID

    if not SPREADSHEET_ID or not all(WORKSHEET_NAMES.values()) or not SERVICE_ACCOUNT_SECRETS or not DRIVE_ROOT_FOLDER_ID:
        raise KeyError("必須設定キーがSecretsに見つかりません。")

    GMAIL_SENDER_EMAIL = SERVICE_ACCOUNT_SECRETS.get("client_email")

except KeyError as e:
    st.error("🚨 API初期化エラー: Secretsに必須キーが見つかりません。")
    st.info("Streamlit CloudのSecrets設定画面に、[app_config] と [google_secrets] の完全なTOMLブロックを貼り付けているか確認してください。")
    st.stop()
except Exception as e:
    st.error(f"予期せぬエラーが発生しました: {e}")
    st.stop()


# --- 2. Google API認証情報取得関数 ---

@st.cache_resource
def get_google_credentials():
    """Secretsの内容からJSON互換の辞書を作成し、認証情報を取得する関数"""
    try:
        info: Dict[str, Any] = {}
        # Secretsから取得した全キーをJSON互換の辞書に変換
        for key, value in SERVICE_ACCOUNT_SECRETS.items():
            info[key] = value

        # 必要なAPIスコープを設定
        SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive', # ドライブのメタデータ操作、フォルダ作成に必要なフルスコープ
            'https://www.googleapis.com/auth/gmail.compose', # 下書き作成用
            'https://www.googleapis.com/auth/gmail.modify'   # 下書き修正・削除用
        ]
        
        return Credentials.from_service_account_info(info, scopes=SCOPES)
    
    except Exception as e:
        st.error(f"Google認証情報の読み込みエラー: {e}")
        st.info("Secretsの[google_secrets]セクションの内容が正しいか確認してください。")
        return None

# 認証情報の取得（アプリ全体で共有）
CREDENTIALS = get_google_credentials()
if not CREDENTIALS:
    st.stop()

@st.cache_resource
def get_gspread_client(creds):
    """gspreadクライアントを取得する関数"""
    try:
        return gspread.service_account(credentials=creds)
    except Exception as e:
        st.error(f"gspreadクライアントの初期化エラー: {e}")
        return None

@st.cache_resource
def get_drive_service(creds):
    """Google Drive APIサービスを取得する関数"""
    try:
        return build('drive', 'v3', credentials=creds)
    except Exception as e:
        st.error(f"Google Drive APIサービスの初期化エラー: {e}")
        return None

# APIクライアントの初期化
GS_CLIENT = get_gspread_client(CREDENTIALS)
DRIVE_SERVICE = get_drive_service(CREDENTIALS)
if not GS_CLIENT or not DRIVE_SERVICE:
    st.stop()

# --- 3. Google Sheets/Drive 共通関数（データ処理ロジック） ---

def get_worksheet_data(worksheet_name_key):
    """指定されたワークシートの全データをヘッダー付きで取得する関数"""
    try:
        worksheet_name = WORKSHEET_NAMES[worksheet_name_key]
        sheet = GS_CLIENT.open_by_key(SPREADSHEET_ID)
        worksheet = sheet.worksheet(worksheet_name)
        # ヘッダーとデータを取得
        data = worksheet.get_all_values()
        if not data:
            return [], []
        
        headers = data[0]
        rows = data[1:]
        
        # データの行番号を保持するよう辞書リストに変換
        records = []
        for i, row in enumerate(rows):
            record = dict(zip(headers, row))
            record['_row_index'] = i + 2 # スプレッドシート上の実際の行番号 (ヘッダーが1行目, データが2行目から始まるため +2)
            records.append(record)
        
        return headers, records
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"ワークシート '{WORKSHEET_NAMES[worksheet_name_key]}' が見つかりません。")
        return [], []
    except Exception as e:
        st.error(f"スプレッドシートのデータ取得エラー ({worksheet_name_key}): {e}")
        return [], []

def get_drive_folder_id(parent_id, folder_name):
    """指定されたフォルダID（親）の中に、指定された名前のフォルダが存在するか検索し、IDを返す。存在しない場合は作成する。"""
    try:
        # フォルダ検索クエリ: 親フォルダID内にある、指定された名前のフォルダ
        query = (
            f"'{parent_id}' in parents and "
            f"name='{folder_name}' and "
            "mimeType='application/vnd.google-apps.folder' and "
            "trashed=false"
        )
        
        response = DRIVE_SERVICE.files().list(
            q=query,
            fields='files(id)'
        ).execute()
        
        files = response.get('files', [])
        
        if files:
            # フォルダが存在する場合、そのIDを返す
            return files[0]['id']
        else:
            # フォルダが存在しない場合、新規作成
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            folder = DRIVE_SERVICE.files().create(
                body=file_metadata,
                fields='id'
            ).execute()
            return folder.get('id')

    except Exception as e:
        st.error(f"Googleドライブのフォルダ操作エラー: {e}")
        return None

def upload_and_save_image(file_data: io.BytesIO, file_name: str, mime_type: str, area: str, store_name: str, media: str):
    """画像をドライブにアップロードし、公開URLを返す関数"""
    
    # 1. フォルダパスの決定と作成
    
    # A. ルートフォルダ: 写メ日記画像用
    current_parent_id = DRIVE_ROOT_FOLDER_ID
    
    # B. 階層2: エリア（場所）フォルダ
    area_folder_id = get_drive_folder_id(current_parent_id, area)
    if not area_folder_id:
        st.error("エリアフォルダの作成/取得に失敗しました。")
        return None
    current_parent_id = area_folder_id

    # C. 階層3: 店舗フォルダ（デリじゃの場合はリネーム）
    store_folder_name = store_name
    if media == "デリじゃ":
        store_folder_name = f"デリじゃ {store_name}"
    
    store_folder_id = get_drive_folder_id(current_parent_id, store_folder_name)
    if not store_folder_id:
        st.error(f"店舗フォルダ ({store_folder_name}) の作成/取得に失敗しました。")
        return None
    
    # 2. ファイルのアップロード
    try:
        # ファイルメタデータを定義
        file_metadata = {
            'name': file_name,
            'parents': [store_folder_id] # 最終的な店舗フォルダIDを指定
        }

        # ファイルをアップロード
        uploaded_file_obj = DRIVE_SERVICE.files().create(
            body=file_metadata,
            media_body={'mimeType': mime_type, 'body': file_data},
            fields='id'
        ).execute()

        file_id = uploaded_file_obj.get('id')

        # ファイルを一般公開設定にする (ブラウザでの表示用)
        DRIVE_SERVICE.permissions().create(
            fileId=file_id,
            body={'role': 'reader', 'type': 'anyone'},
            fields='id',
        ).execute()

        # 公開URLを取得
        # Google Docs/Spreadsheetsで埋め込み表示が容易なURL形式
        public_url = f"https://drive.google.com/uc?id={file_id}"

        return public_url
    
    except Exception as e:
        st.error(f"Googleドライブへの画像アップロードエラー: {e}")
        return None

def append_to_register_sheet(data_rows: List[Dict[str, str]]):
    """登録用シートにデータを一括追記する関数"""
    try:
        worksheet_name = WORKSHEET_NAMES["REGISTER"]
        sheet = GS_CLIENT.open_by_key(SPREADSHEET_ID)
        worksheet = sheet.worksheet(worksheet_name)
        
        # ヘッダー順に値のリストを作成
        headers, _ = get_worksheet_data("REGISTER")
        if not headers:
            st.warning("登録用シートのヘッダーが取得できませんでした。")
            return False

        # 書き込む行データを整形
        values_to_append = []
        for row_data in data_rows:
            # 11項目をヘッダー順に並べる
            row_list = [row_data.get(h, '') for h in headers]
            values_to_append.append(row_list)

        # 最終行にデータを追記
        worksheet.append_rows(values_to_append, value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        st.error(f"スプレッドシートへの書き込みエラー: {e}")
        st.info("スプレッドシートIDとシート名が正しいか、サービスアカウントに共有設定がされているか確認してください。")
        return False

def move_rows_and_delete(source_key, target_key, row_indices_to_move: List[int]):
    """ソースシートからターゲットシートへ行を移動し、ソースシートから削除する関数"""
    
    # 行番号（スプレッドシート上の行数）の逆順リストを生成（削除時にインデックスがずれるのを防ぐため）
    sorted_indices_desc = sorted(row_indices_to_move, reverse=True)
    
    source_name = WORKSHEET_NAMES[source_key]
    target_name = WORKSHEET_NAMES[target_key]
    
    try:
        sheet = GS_CLIENT.open_by_key(SPREADSHEET_ID)
        source_ws = sheet.worksheet(source_name)
        target_ws = sheet.worksheet(target_name)
        
        # 1. ソースからデータを読み込む
        # GSpreadのbatch_getで指定行のデータを取得（A1表記を使用）
        # 行番号は1から始まるため、A{index}表記を使用
        ranges = [f"A{idx}:{gspread.utils.rowcol_to_a1(idx, source_ws.col_count)}" for idx in row_indices_to_move]
        
        # バッチ処理でデータを取得
        batch_values = source_ws.batch_get(ranges)
        
        if not batch_values:
             st.warning(f"移動対象のデータがソースシート ({source_name}) から見つかりませんでした。")
             return False
        
        # 2. ターゲットシートにデータを追記
        values_to_append = [row[0] for row in batch_values]
        target_ws.append_rows(values_to_append, value_input_option='USER_ENTERED')
        
        # 3. ソースシートから行を削除（逆順に）
        for index in sorted_indices_desc:
            source_ws.delete_rows(index)

        return True
    
    except Exception as e:
        st.error(f"シート間のデータ移動エラー: {e}")
        return False


# --- 4. Streamlit UI構築 ---

st.set_page_config(
    page_title="WEB媒体日記 自動運用システム", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.title("📝 日記自動化・運用管理アプリ")
st.markdown("---")

# タブの定義
tab1, tab2, tab3 = st.tabs([
    "① 新規データ登録・画像アップロード (40件)", 
    "② 下書き作成・実行 (Pythonコード連携)", 
    "③ 履歴の検索・修正・アーカイブ"
])

# --- Tab I: 新規データ登録・画像アップロード ---
with tab1:
    st.header("1. 新規データ登録と画像アップロード")
    st.info("40件の日記データ（テキストと画像）を入力し、スプレッドシートとドライブに登録します。")
    
    # 初期データ構造の定義（40行）
    # Streamlitのセッションステートで状態を保持
    if 'diary_data' not in st.session_state:
        # スプレッドシートの入力8項目（画像URLは裏で処理されるため除外）
        initial_headers = ["投稿時間", "女の子の名前", "タイトル", "本文"]
        st.session_state.diary_data = [
            {'投稿時間': '', '女の子の名前': '', 'タイトル': '', '本文': '', 'image': None}
        ] * 40

    if 'common_config' not in st.session_state:
        st.session_state.common_config = {
            'エリア': '',
            '店名': '',
            '媒体': '駅ちか', # デフォルト値
            '担当アカウント': 'A', # デフォルト値
        }

    # --- 1-A. 共通設定フォーム ---
    with st.container(border=True):
        st.subheader("1-A. 共通設定 (40件すべてに適用)")
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        
        with col_c1:
            st.session_state.common_config['エリア'] = st.text_input(
                "エリア", 
                value=st.session_state.common_config['エリア'], 
                key="input_area"
            )
        with col_c2:
            st.session_state.common_config['店名'] = st.text_input(
                "店名", 
                value=st.session_state.common_config['店名'], 
                key="input_store"
            )
        with col_c3:
            st.session_state.common_config['媒体'] = st.selectbox(
                "媒体", 
                options=['駅ちか', 'デリじゃ'], 
                index=['駅ちか', 'デリじゃ'].index(st.session_state.common_config['媒体']),
                key="select_media"
            )
        with col_c4:
            st.session_state.common_config['担当アカウント'] = st.selectbox(
                "担当アカウント", 
                options=['A', 'B', 'SUB'],
                index=['A', 'B', 'SUB'].index(st.session_state.common_config['担当アカウント']),
                key="select_account"
            )

    # --- 1-B. テンプレート参照機能 ---
    with st.expander("テンプレート（使用可日記データ）参照・コピペ", expanded=False):
        try:
            template_headers, template_records = get_worksheet_data("USABLE_TEMPLATE")
            
            if template_records:
                st.subheader("使用可テンプレート一覧")
                
                # フィルターUI
                temp_col1, temp_col2 = st.columns(2)
                
                # 存在チェック
                if '日記種類' in template_headers:
                    with temp_col1:
                        # 日記種類 (出勤, 退勤, その他)
                        selected_kind = st.selectbox("日記種類で絞り込み", 
                                                    options=['全て'] + sorted(list(set(r['日記種類'] for r in template_records if r.get('日記種類')))), 
                                                    key="template_kind_filter")
                else:
                    selected_kind = '全て'
                    
                if 'タイプ種類' in template_headers:
                     with temp_col2:
                        # タイプ種類 (若, 妻, おば)
                        selected_type = st.selectbox("タイプ種類で絞り込み", 
                                                    options=['全て'] + sorted(list(set(r['タイプ種類'] for r in template_records if r.get('タイプ種類')))), 
                                                    key="template_type_filter")
                else:
                    selected_type = '全て'
                    
                
                # フィルタリング
                filtered_templates = [r for r in template_records if 
                                      (selected_kind == '全て' or r.get('日記種類') == selected_kind) and
                                      (selected_type == '全て' or r.get('タイプ種類') == selected_type)]
                                      
                
                # コピペしやすいデータエディタで表示
                # ユーザーの要望に応じて、表示列を「タイトル」「本文」中心に
                display_cols = ['タイトル', '本文', '日記種類', 'タイプ種類']
                display_data = [{k: v for k, v in r.items() if k in display_cols} for r in filtered_templates]

                st.markdown("##### フィルター結果 (ここからタイトル/本文をコピーしてください)")
                st.dataframe(
                    display_data,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("「使用可日記データシート」にデータがありません。")

        except Exception as e:
            st.warning(f"テンプレートデータの読み込み中にエラーが発生しました: {e}")

    # --- 1-C. 40件の個別データ入力と画像アップロード ---
    st.subheader("1-C. 個別データ入力 (40件)")
    st.warning("40件分のデータと画像は、**順番が一致している**ことを確認しながら入力してください。")

    # 40件のテキスト入力エリア（コピペしやすいようにデータエディタを使用）
    st.markdown("##### 📝 テキストデータ入力 (投稿時間, 女の子の名前, タイトル, 本文)")
    
    # data_editorのOnChangeイベントでst.session_state.diary_dataを更新
    edited_data = st.data_editor(
        st.session_state.diary_data,
        column_order=["投稿時間", "女の子の名前", "タイトル", "本文"],
        column_config={
            "投稿時間": st.column_config.TextColumn("投稿時間 (hhmm)", width="small", help="例: 1010"),
            "女の子の名前": st.column_config.TextColumn("女の子の名前", width="small"),
            "タイトル": st.column_config.TextColumn("タイトル", width="medium"),
            "本文": st.column_config.TextColumn("本文", width="large"),
        },
        num_rows="fixed",
        use_container_width=True,
        key="data_editor_40"
    )
    # data_editorはリストのリストを返すため、元の構造に戻す
    # imageフィールドが失われるため、テキストデータのみを更新
    for i, row in enumerate(edited_data):
        st.session_state.diary_data[i].update({
            "投稿時間": row["投稿時間"],
            "女の子の名前": row["女の子の名前"],
            "タイトル": row["タイトル"],
            "本文": row["本文"],
        })

    
    st.markdown("---")
    st.markdown("##### 🖼️ 個別画像アップロード (40件のデータと紐づけ)")
    
    # 40個の個別アップローダーを動的に生成
    image_cols = st.columns(4) # 4列表示
    for i in range(40):
        with image_cols[i % 4]:
            
            # 紐づけるテキストデータを取得
            row_data = st.session_state.diary_data[i]
            hhmm = row_data.get('投稿時間', '時刻未定')
            name = row_data.get('女の子の名前', '名前未定')
            
            # ファイル名生成（ドライブのリネームに使われる）
            upload_name = f"**{i+1}. {hhmm}_{name}**"
            
            # 画像アップローダー
            uploaded_file = st.file_uploader(
                upload_name,
                type=['png', 'jpg', 'jpeg'],
                key=f"image_uploader_{i}",
                help="画像をドラッグ&ドロップしてください。"
            )
            # 画像ファイルをセッションステートに保存
            st.session_state.diary_data[i]['image'] = uploaded_file

    st.markdown("---")
    
    # --- 1-D. 実行ボタン ---
    if st.button("🚀 データ登録と画像アップロードを実行 (Tab I)", type="primary"):
        st.session_state.processing_status = "開始"
        
        # 必須入力チェック
        if not st.session_state.common_config['エリア'] or not st.session_state.common_config['店名']:
            st.error("🚨 エリアと店名は共通設定として必ず入力してください。")
            st.stop()
            
        
        # 40件のデータと画像の整合性チェック
        valid_rows = [r for r in st.session_state.diary_data if 
                      r['投稿時間'] and r['女の子の名前'] and r['タイトル'] and r['本文'] and r['image']]

        if len(valid_rows) == 0:
            st.error("🚨 有効なデータ行（テキストと画像が全て揃っている行）が見つかりませんでした。")
            st.stop()
            
        if len(valid_rows) != 40:
            st.warning(f"🚨 40件全てのデータ入力と画像アップロードが必要です。現在 {len(valid_rows)} 件しか完了していません。")
            st.info("データと画像の両方が揃っている行だけが処理されます。")
            # 警告後も処理を続行するかどうか選択させる
            if not st.button("警告を無視して続行"):
                st.stop()
        
        # 処理開始
        progress_bar = st.progress(0, text="処理進捗: 0/40 件")
        all_success = True
        
        # スプレッドシートに書き込むデータ格納リスト
        sheet_rows_to_append = []

        for i, row_data in enumerate(valid_rows):
            status_text = f"処理進捗: {i+1}/{len(valid_rows)} 件 - {row_data['女の子の名前']} さんの日記を処理中..."
            progress_bar.progress((i + 1) / 40, text=status_text)
            
            # 1. 画像アップロード
            file_to_upload = row_data['image']
            
            # リネーム後のファイル名: hhmm_女の子の名前.拡張子
            file_extension = file_to_upload.name.split('.')[-1] if '.' in file_to_upload.name else 'jpg'
            new_file_name = f"{row_data['投稿時間']}_{row_data['女の子の名前']}.{file_extension}"
            
            # ファイルの内容をメモリに格納 (Drive APIはバイトデータが必要)
            file_to_upload.seek(0)
            file_bytes = io.BytesIO(file_to_upload.read())

            image_url = upload_and_save_image(
                file_bytes,
                new_file_name,
                file_to_upload.type,
                st.session_state.common_config['エリア'],
                st.session_state.common_config['店名'],
                st.session_state.common_config['媒体']
            )

            # 2. スプレッドシート用データ準備
            if image_url:
                sheet_row = {
                    'エリア': st.session_state.common_config['エリア'],
                    '店名': st.session_state.common_config['店名'],
                    '媒体': st.session_state.common_config['媒体'],
                    '投稿時間': row_data['投稿時間'],
                    '女の子の名前': row_data['女の子の名前'],
                    'タイトル': row_data['タイトル'],
                    '本文': row_data['本文'],
                    '担当アカウント': st.session_state.common_config['担当アカウント'],
                    '下書き登録確認': '',        # Pythonコードが記入
                    '画像添付確認': image_url,  # 画像URLを記入
                    '宛先登録確認': '',        # Pythonコードが記入
                }
                sheet_rows_to_append.append(sheet_row)
            else:
                all_success = False
                st.error(f"❌ {row_data['女の子の名前']} さんの画像のドライブ登録に失敗しました。この行はスキップされます。")
                
            time.sleep(0.1) # UI更新のための待ち時間

        # 3. スプレッドシートへの書き込み
        if sheet_rows_to_append:
            progress_bar.progress(1.0, text="処理進捗: スプレッドシートにデータを書き込み中...")
            if append_to_register_sheet(sheet_rows_to_append):
                st.success(f"🎉 成功！ {len(sheet_rows_to_append)} 件の日記データが登録用シートに書き込まれました。")
                # フォームをクリア
                st.session_state.diary_data = [{'投稿時間': '', '女の子の名前': '', 'タイトル': '', '本文': '', 'image': None}] * 40
                st.rerun() # UIリセット
            else:
                st.error("🚨 スプレッドシートへの書き込みに失敗しました。")
        else:
            st.warning("処理に成功したデータ行がなかったため、スプレッドシートへの書き込みはスキップされました。")
            
        progress_bar.empty()
        
# --- Tab II: 下書き作成・実行 ---
with tab2:
    st.header("2. 下書き作成・実行 (Pythonコード連携)")
    st.info("このタブは、ローカルPCのPythonスクリプトを実行するタイミングを管理します。")

    with st.container(border=True):
        st.subheader("⚠️ 実行前の最終確認 (Step 0)")
        st.error("【重要】ローカルPCのPythonコードを実行する前に、必ず以下の準備をしてください。")
        
        # 連絡先シートの注意喚起
        st.markdown(f"""
            -   **連絡先シートの確認**: 「**{WORKSHEET_NAMES["CONTACT_ADDRESS"]}**」シートに、必要な投稿用メールアドレスが全て入力されているか確認しましたか？
            -   **ローカル実行**: これらのステップは、Streamlit上では**起動シミュレーション**であり、実際にローカルPCでコマンドを叩く必要があります。
        """)
    
    st.markdown("---")
    st.subheader("📚 実行ステータスとボタン")
    
    # 登録用シートから未実行データを取得
    _, register_records = get_worksheet_data("REGISTER")
    
    if not register_records:
        st.success("「登録用シート」に実行待機中のデータはありません。")
    else:
        st.info(f"現在、**{len(register_records)} 件**のデータが実行待機中です。")
        
        # 実行対象データの表示（見やすさのために一部列のみ表示）
        display_cols = ['エリア', '店名', '女の子の名前', '投稿時間', '担当アカウント', '画像添付確認', '下書き登録確認', '宛先登録確認']
        display_data = [{k: v for k, v in r.items() if k in display_cols} for r in register_records]
        
        st.dataframe(
            display_data,
            use_container_width=True,
            hide_index=True,
            column_order=display_cols
        )
        st.markdown("---")
        
        # 実行ボタンのエリア
        st.subheader("▶️ 外部 Python スクリプトの実行")
        st.warning("以下のボタンは、ローカルPCでの**コマンド実行**をトリガーするためのものです。必ず順番に実行してください。")

        # 実行ボタンのロジック（実際にはsubprocess.runなどをシミュレーション）
        def run_script_simulation(script_name, args=""):
            st.success(f"✅ Pythonスクリプトの実行をシミュレーション: `{script_name} {args}`")
            st.code(f"cd ...\npython {script_name} {args}", language='bash')
            st.info("→ 実行結果に基づき、スプレッドシートのステータス（下書き登録確認など）が更新されたことを確認してください。")
            
            # 強制再読み込みトリガー
            # on_finish_rerun()
            

        # 実行ボタンの配置
        col_r1, col_r2, col_r3 = st.columns(3)
        
        with col_r1:
            st.markdown("##### 1. 連絡先アドレス更新")
            if st.button("メアド抽出＆連絡先作成", key="run_contact_updater", type="secondary"):
                run_script_simulation("mail_address_extractor.py")
                run_script_simulation("contact_updater.py", "A")
                run_script_simulation("contact_updater.py", "B")
                run_script_simulation("contact_updater.py", "SUB")

        with col_r2:
            st.markdown("##### 2. 下書き作成と画像・宛先登録")
            if st.button("下書き作成＆登録", key="run_draft_creator", type="secondary"):
                run_script_simulation("draft_creator.py", "A")
                run_script_simulation("draft_creator.py", "B")
                run_script_simulation("draft_creator.py", "SUB")
                run_script_simulation("image_uploader.py")
                run_script_simulation("draft_updater.py", "A")
                run_script_simulation("draft_updater.py", "B")
                run_script_simulation("draft_updater.py", "SUB")

        # --- 履歴への移動ボタン（実行とは分離） ---
        with col_r3:
            st.markdown("##### 3. 実行完了データの移動")
            # 移動対象の抽出（ここでは簡単のため全データを対象とする）
            move_target_records = [r for r in register_records if r.get('下書き登録確認') in ['OK', '実行済', '完了']]
            
            if st.button(f"履歴へ移動 ({len(move_target_records)} 件)", key="move_to_history", type="primary", disabled=not move_target_records):
                if not move_target_records:
                    st.warning("移動対象（下書き登録確認がOKなどのデータ）が見つかりません。")
                else:
                    # スプレッドシート上の行番号を取得
                    row_indices = [r['_row_index'] for r in move_target_records]
                    
                    st.info(f"✨ 実行済の {len(row_indices)} 行を履歴シートへ移動中...")
                    
                    if move_rows_and_delete("REGISTER", "FULL_HISTORY", row_indices):
                        st.success(f"🎉 移動完了！ {len(row_indices)} 件のデータが履歴シートに移動されました。")
                        st.rerun()
                    else:
                        st.error("🚨 データ移動中にエラーが発生しました。ログを確認してください。")


# --- Tab III: 履歴の検索・修正・アーカイブ ---
with tab3:
    st.header("3. 履歴の検索・修正・アーカイブ")
    st.info("過去の投稿履歴（全店舗データシート）を参照・修正したり、店舗を閉めた際のアーカイブ処理を行います。")
    
    # 全店舗履歴データを取得
    history_headers, history_records = get_worksheet_data("FULL_HISTORY")

    if not history_records:
        st.warning("履歴データ（全店舗データシート）が空です。")
    else:
        # --- 検索・フィルタリング UI ---
        st.subheader("3-A. 履歴データの検索と修正")
        
        # フィルターの選択肢を動的に生成
        all_areas = sorted(list(set(r['エリア'] for r in history_records if r.get('エリア'))))
        all_stores = sorted(list(set(r['店名'] for r in history_records if r.get('店名'))))
        all_names = sorted(list(set(r['女の子の名前'] for r in history_records if r.get('女の子の名前'))))

        # フィルターのUI
        fcol1, fcol2, fcol3 = st.columns(3)
        with fcol1:
            selected_area = st.selectbox("エリアで絞り込み", ['全て'] + all_areas, key="filter_area")
        with fcol2:
            selected_store = st.selectbox("店名で絞り込み", ['全て'] + all_stores, key="filter_store")
        with fcol3:
            selected_name = st.selectbox("女の子の名前で絞り込み", ['全て'] + all_names, key="filter_name")

        # フィルタリングロジック
        filtered_history = [r for r in history_records if 
                            (selected_area == '全て' or r.get('エリア') == selected_area) and
                            (selected_store == '全て' or r.get('店名') == selected_store) and
                            (selected_name == '全て' or r.get('女の子の名前') == selected_name)]
                            
        st.markdown(f"**表示件数:** {len(filtered_history)} 件")

        # 修正可能なデータエディタで表示
        # 修正されたデータは、スプレッドシートの該当行に上書きされる
        editable_history = st.data_editor(
            filtered_history,
            use_container_width=True,
            num_rows="fixed",
            hide_index=True,
            key="history_editor"
        )
        
        # 修正ロジック（未実装: Gmail連動含む）
        # if st.button("💾 修正を保存 (スプレッドシート上書き) & Gmail下書き修正", type="primary"):
        #     st.error("機能B: 修正時のGmail下書き連動機能は現在未実装です。")
        #     st.info("（後日、Gmail APIとの連携ロジックを実装します。）")


        # --- 3-B. 店舗閉め・アーカイブ機能 ---
        st.markdown("---")
        st.subheader("3-B. 店舗閉め・アーカイブ (使用可シートへ移動)")
        
        archive_cols = st.columns([0.4, 0.6])
        with archive_cols[0]:
            # アーカイブ対象の店名を選択
            archive_store = st.selectbox("アーカイブする店舗を選択", all_stores, key="archive_store")

        with archive_cols[1]:
            st.markdown("<br>", unsafe_allow_html=True) # レイアウト調整
            archive_target_records = [r for r in history_records if r.get('店名') == archive_store]

            if st.button(f"🗑️ {archive_store} の全データをアーカイブ ({len(archive_target_records)} 件を移動)", type="secondary", disabled=not archive_target_records):
                
                # スプレッドシート上の行番号を取得
                row_indices = [r['_row_index'] for r in archive_target_records]
                
                st.info(f"✨ {archive_store} の全データを履歴シートからテンプレートシートへ移動中...")
                
                # 行移動と削除を実行
                if move_rows_and_delete("FULL_HISTORY", "USABLE_TEMPLATE", row_indices):
                    st.success(f"🎉 アーカイブ完了！ {len(row_indices)} 件のデータがテンプレートシートに移動されました。")
                    st.rerun()
                else:
                    st.error("🚨 アーカイブ処理中にエラーが発生しました。ログを確認してください。")
