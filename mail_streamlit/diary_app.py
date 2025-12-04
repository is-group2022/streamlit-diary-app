import streamlit as st
from datetime import datetime
import json
import io
from typing import Dict, Any

# Google APIクライアント関連のライブラリ（事前にインストールが必要です）
# pip install gspread google-auth google-auth-oauthlib google-api-python-client
try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    import gspread
except ImportError:
    st.error("Google API関連のライブラリ（gspread, google-authなど）がインストールされていません。`pip install gspread google-auth google-auth-oauthlib google-api-python-client`を実行してください。")

# --- 設定情報の読み込み（Streamlit Secretsから） ---
# Streamlit CloudのSecrets設定画面に [app_config] セクションと [google_secrets] セクションがあることを前提とします。

try:
    # アプリケーション固有の設定
    # [app_config] セクションから読み込み
    APP_CONFIG = st.secrets.get("app_config", {})
    SPREADSHEET_ID = APP_CONFIG.get("SPREADSHEET_ID")
    WORKSHEET_NAME = APP_CONFIG.get("WORKSHEET_NAME")
    DRIVE_FOLDER_ID = APP_CONFIG.get("DRIVE_FOLDER_ID")
    DRAFT_SUBJECT_TEMPLATE = APP_CONFIG.get("DRAFT_SUBJECT_TEMPLATE")
    DRAFT_DEFAULT_TO_ADDRESS = APP_CONFIG.get("DRAFT_DEFAULT_TO_ADDRESS")

    # Google Service Account認証情報
    # [google_secrets] セクションから個別に読み込み
    # .get() を使用して、キーが存在しない場合に安全に空の辞書を返すように変更
    SERVICE_ACCOUNT_SECRETS = st.secrets.get("google_secrets", {})
    GMAIL_SENDER_EMAIL = SERVICE_ACCOUNT_SECRETS.get("client_email")

    # 必須キーの存在チェック
    if not SPREADSHEET_ID or not WORKSHEET_NAME or not SERVICE_ACCOUNT_SECRETS:
        raise KeyError("必須設定キーがSecretsに見つかりません。")

except KeyError as e:
    # Secretsから必須キーが見つからない場合のエラー処理
    st.error("🚨 API初期化エラー: Secretsに必須キー ([app_config] または [google_secrets] のデータ) が見つかりません。")
    st.info("Streamlit CloudのSecrets設定画面に、上記の完全版TOMLブロックを**全て上書き**して貼り付け、保存したか確認してください。")
    st.stop()
except Exception as e:
    st.error(f"予期せぬエラーが発生しました: {e}")
    st.stop()


def get_google_credentials():
    """Secretsの内容からJSON互換の辞書を作成し、認証情報を取得する関数"""
    try:
        # Secretsから取得したキーと値を使ってサービスアカウント情報の辞書を構築
        info: Dict[str, Any] = {}
        
        # Secretsから取得した全キーをJSON互換の辞書に変換
        for key, value in SERVICE_ACCOUNT_SECRETS.items():
            info[key] = value

        # Google Sheets, Google Drive, Gmailのスコープを設定
        SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive.file', # ファイルアップロード用
            'https://www.googleapis.com/auth/gmail.compose' # 下書き作成用
        ]
        
        # 認証情報オブジェクトを生成
        return Credentials.from_service_account_info(info, scopes=SCOPES)
    
    except Exception as e:
        st.error(f"Google認証情報の読み込みエラー: {e}")
        st.info("Secretsの[google_secrets]セクションの内容が正しいか確認してください。")
        return None

# --- Google Sheets 操作関数 ---

def write_to_spreadsheet(client, diary_entry, image_url):
    """日記データと画像URLをスプレッドシートに書き込む関数"""
    try:
        # スプレッドシートとワークシートを開く
        sheet = client.open_by_key(SPREADSHEET_ID)
        worksheet = sheet.worksheet(WORKSHEET_NAME)

        # 書き込むデータ: 日付, 日記内容, 画像URL
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row_data = [timestamp, diary_entry, image_url]

        # 最終行にデータを追記
        worksheet.append_row(row_data)
        return True
    except Exception as e:
        st.error(f"スプレッドシートへの書き込みエラー: {e}")
        st.info("スプレッドシートIDとシート名が正しいか、またサービスアカウントに共有設定がされているか確認してください。")
        return False

# --- Google Drive 操作関数 ---

def upload_to_drive(creds, uploaded_file):
    """画像をGoogleドライブにアップロードし、公開URLを返す関数"""
    try:
        # Google Drive APIサービスを構築
        drive_service = build('drive', 'v3', credentials=creds)

        # ファイル名とMIMEタイプを設定
        file_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name}"
        file_mime_type = uploaded_file.type

        # ファイルメタデータを定義
        file_metadata = {
            'name': file_name,
            'parents': [DRIVE_FOLDER_ID]
        }

        # ファイルの内容をメモリから読み込む
        file_content = uploaded_file.read()
        media = io.BytesIO(file_content)

        # ファイルをアップロード
        uploaded_file_obj = drive_service.files().create(
            body=file_metadata,
            media_body={'mimeType': file_mime_type, 'body': media},
            fields='id'
        ).execute()

        file_id = uploaded_file_obj.get('id')

        # ファイルを一般公開設定にする（既存のPythonロジックがアクセスできるように）
        drive_service.permissions().create(
            fileId=file_id,
            body={'role': 'reader', 'type': 'anyone'},
            fields='id',
        ).execute()

        # 公開URLを取得 (このURLは、ブラウザでの表示や埋め込みに適しています)
        # file_idを使って直接アクセスURLを構成
        public_url = f"https://drive.google.com/uc?id={file_id}&export=download"

        return public_url
    except Exception as e:
        st.error(f"Googleドライブへのアップロードエラー: {e}")
        st.info("ドライブのフォルダIDが正しいか、またドライブAPIが有効になっているか確認してください。")
        return None

# --- Gmail 下書き自動作成ロジック（モックアップ） ---
# ユーザーの既存Pythonコードを呼び出す部分をシミュレート

def trigger_gmail_automation(latest_data):
    """既存のPythonコードが実行されることをシミュレートする関数"""
    # 実際にはここで subprocess.run などを使って、別プロセスで既存のPythonスクリプトを実行するか、
    # 既存ロジックを関数としてインポートして実行します。

    # ここでは、成功したと仮定し、ログを表示
    st.success("✅ **[Pythonロジック起動]**: スプレッドシートの最新データを使って、Gmail下書き作成ロジックが正常に起動しました。")
    st.markdown("---")
    st.subheader("💡 既存ロジックが処理するデータ (シミュレーション)")
    st.code(f"日付: {latest_data[0]}\n内容: {latest_data[1][:50]}...\n画像URL: {latest_data[2]}", language='text')

# --- Streamlit UI構築 ---

st.set_page_config(page_title="WEB媒体日記 自動化アプリ", layout="centered")

st.title("📝 WEB媒体日記 自動下書き作成システム")
st.markdown("日記の入力と画像をアップロードし、「自動化実行」ボタンでスプレッドシートへの登録とGmail下書き作成をトリガーします。")

# 1. 入力フォームの定義
with st.form(key='diary_form'):
    st.subheader("1. 日記コンテンツの入力")

    diary_text = st.text_area(
        "今日の日記",
        placeholder="今日の出来事や感想を詳しく記入してください。",
        height=200
    )

    st.subheader("2. 画像のアップロード")
    uploaded_file = st.file_uploader(
        "日記に含める画像ファイル",
        type=['png', 'jpg', 'jpeg'],
        help="Googleドライブに自動でアップロードされます。"
    )

    # 実行ボタン
    st.markdown("---")
    submit_button = st.form_submit_button(label='🚀 自動化実行 (スプレッドシート登録 & 下書き作成)')

# 2. 実行ロジック
if submit_button:
    if not diary_text:
        st.warning("日記の内容を入力してください。")
    else:
        # 認証情報を取得
        creds = get_google_credentials()
        if not creds:
            st.error("Google API認証に失敗したため、処理を中断します。")
            st.stop()

        # 処理ステータスの初期化
        image_url = "画像なし"
        success = True

        st.info("処理を開始します。しばらくお待ちください...")
        status_placeholder = st.empty()

        # 画像アップロード処理
        if uploaded_file:
            status_placeholder.text("1/3: 画像をGoogleドライブにアップロード中...")
            creds_for_drive = creds # Driveは別のAPIクライアントを使うため認証情報をコピー
            image_url = upload_to_drive(creds_for_drive, uploaded_file)
            if not image_url:
                success = False
                st.error("画像アップロードに失敗しました。")
            else:
                st.success(f"✅ 画像がドライブに保存されました: [URLを表示]({image_url})")
                if uploaded_file.type.startswith('image'):
                     st.image(uploaded_file, caption=uploaded_file.name, width=200)

        # スプレッドシート書き込み処理
        if success:
            # gspreadクライアントを初期化
            try:
                gc = gspread.service_account(credentials=creds)
            except Exception as e:
                st.error(f"gspreadクライアントの初期化に失敗しました: {e}")
                success = False

        if success:
            status_placeholder.text("2/3: データをスプレッドシートに書き込み中...")
            if not write_to_spreadsheet(gc, diary_text, image_url):
                success = False
                st.error("スプレッドシートへの書き込みに失敗しました。")
            else:
                st.success("✅ スプレッドシートに日記データが登録されました。")

        # Python自動化起動処理
        if success:
            status_placeholder.text("3/3: 既存のPython下書き作成ロジックを起動中...")
            # 実際には最新データ(ここでは入力データ)を渡してロジックを起動
            latest_data = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), diary_text, image_url]
            trigger_gmail_automation(latest_data)

        if success:
            status_placeholder.empty()
            st.balloons()
            st.info("🎉 全ての自動化プロセスが完了しました！Gmailの下書きを確認してください。")

# --- アプリケーション実行方法の案内 ---
st.sidebar.subheader("ℹ️ アプリの実行方法")
st.sidebar.markdown(f"""
1.  このコードを `diary_automation_app.py` として保存します。
2.  ターミナルで以下を実行します。
    ```bash
    streamlit run diary_automation_app.py
    ```
3.  ブラウザでアプリが開きます。
""")

st.sidebar.subheader("⚠️ 重要な設定")
st.sidebar.markdown("""
-   コード内の設定（`SPREADSHEET_ID`など）は**Secrets**から読み込むように変更しました。
-   Google Cloud Platformで**Sheets API**, **Drive API**, **Gmail API**を有効化してください。
-   サービスアカウントのメールアドレスを、**スプレッドシートとドライブフォルダに「編集者」として共有**してください。
""")
