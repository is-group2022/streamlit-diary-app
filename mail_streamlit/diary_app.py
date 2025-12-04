import streamlit as st
import json
import base64
# gspread, google-auth などの Google API クライアントライブラリを使用する場合は、
# 事前にインストールが必要です: pip install gspread google-auth
try:
    from google.oauth2.service_account import Credentials
    import gspread
    # pydriveなどを使う場合はこちらもインポート
except ImportError:
    # 連携ライブラリがない場合でもアプリは動作させ、エラーメッセージを表示
    st.warning("Google API連携ライブラリ（gspread, google-authなど）がインポートできません。`requirements.txt`を確認してください。")


# =================================================================
# 認証情報とクライアントの取得処理
# =================================================================

@st.cache_resource
def get_google_sheets_client():
    """
    secrets.tomlからサービスアカウント情報を取得し、gspreadクライアントを初期化します。
    """
    st.write("認証情報をロードしています...")
    try:
        # [google_secrets]セクションの内容全体を取得 (TOML形式でキーと値のペアが直接記述されている前提)
        service_account_info = st.secrets["google_secrets"].to_dict()

        if not service_account_info or 'private_key' not in service_account_info:
            st.error("❌ エラー: `.streamlit/secrets.toml`の`[google_secrets]`セクションにサービスアカウント情報がありません。")
            st.info("➡️ Streamlit CloudのSecrets UIに、`[google_secrets]`以下のすべてのキーと値を貼り付けてください。")
            return None, None

        # gspreadクライアントを初期化
        # StreamlitのSecretsはTOML形式で文字列を読み込むため、private_key内の改行(\n)が保持されます。
        gc = gspread.service_account_from_dict(service_account_info)
        
        # 認証情報オブジェクトを作成 (Drive APIなどで使用するため)
        SCOPES = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive.file', # 必要に応じて追加
        ]
        creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)


        st.success("✅ Google Sheets/Drive 認証に成功しました。")
        return gc, creds

    except KeyError as e:
        st.error(f"⚠️ 設定ファイル `.streamlit/secrets.toml`に必須キーが見つかりません: {e}")
        st.caption("Streamlit CloudのSecrets設定画面を確認してください。")
        return None, None
    except Exception as e:
        st.error(f"❌ Google認証情報の初期化中にエラーが発生しました: {e}")
        st.caption("Secretsの内容が正しいJSON互換のTOML形式であるか確認してください。")
        return None, None

# =================================================================
# アプリケーション本体
# =================================================================

st.set_page_config(page_title="日記管理アプリ", layout="wide")

st.title("日報・連絡先 Streamlit アプリ (設定確認と連携基盤)")
st.markdown("このアプリは、`.streamlit/secrets.toml`から設定を読み込み、Google Sheets/Driveと連携するための準備を行います。")

# --- 1. アプリケーション設定の表示 ---
st.header("1. Googleリソース設定 (`app_config`)")
app_config = st.secrets.get("app_config", {})

if app_config:
    st.subheader("Spreadsheet ID / Drive Folder ID")
    st.json({
        "SPREADSHEET_ID": app_config.get("SPREADSHEET_ID", "N/A"),
        "DRIVE_FOLDER_ID": app_config.get("DRIVE_FOLDER_ID", "N/A"),
        # 新しい設定ファイルにはWORKSHEET_NAMEのみが含まれているため修正
        "WORKSHEET_NAME": app_config.get("WORKSHEET_NAME", "N/A"),
    })

    st.info("💡 **重要:** 上記の設定IDとシート名がスプレッドシートやドライブの実際の値と**完全に一致**しているか確認してください。")
else:
    st.error("エラー: `app_config`セクションの設定を読み込めませんでした。`secrets.toml`を確認してください。")


# --- 2. サービスアカウントの認証 ---
st.header("2. 認証情報と接続準備")
# gspreadクライアントと認証情報オブジェクトを取得
gc, creds = get_google_sheets_client()

if gc and creds:
    service_account_email = st.secrets["google_secrets"].get('client_email', 'N/A')
    st.code(f"認証メールアドレス: {service_account_email}", language="python")

    # --- 3. Google Sheets/Drive 接続ロジック（ここに実装） ---
    st.subheader("3. 接続テストとデータ操作")
    st.markdown("""
    ---
    #### ⚙️ **実際の連携手順**
    1.  **gspreadクライアント (gc) の利用:**
        * スプレッドシートを開く: `spreadsheet = gc.open_by_key(st.secrets.app_config.SPREADSHEET_ID)`
        * シートにアクセス: `worksheet = spreadsheet.worksheet(st.secrets.app_config.WORKSHEET_NAME)`
        * データを読み書きする。
    2.  **Google Drive APIクライアント (creds) の利用:**
        * `googleapiclient.discovery.build('drive', 'v3', credentials=creds)` でサービスを構築し、ファイル操作（アップロードなど）を行う。
    ---
    """)

    # 例: 成功した場合のメッセージ
    st.success("👏 認証情報の準備完了！ここから下の行に、Google Sheets/Driveを操作するロジックを実装してください。")
