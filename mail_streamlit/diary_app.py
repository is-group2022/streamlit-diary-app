import streamlit as st
import json
import base64
# Google Sheets/Drive 連携に必要なライブラリ
try:
    from google.oauth2.service_account import Credentials
    import gspread
    # 他に必要なライブラリがあればここでインポート
except ImportError:
    st.error("❌ Google API連携ライブラリ（gspread, google-authなど）が不足しています。")
    st.info("ローカル実行の場合: `pip install gspread google-auth` を実行してください。")

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
        # [google_secrets]セクションの内容全体をStreamlitのSecretsから取得
        # private_keyはTOMLで三重引用符を使っているため、改行が保持された状態で読み込まれます。
        service_account_info = st.secrets["google_secrets"].to_dict()

        if not service_account_info or 'private_key' not in service_account_info:
            # 必須情報がない場合はエラーを出す
            st.error("❌ エラー: `.streamlit/secrets.toml`の`[google_secrets]`セクションにサービスアカウント情報がありません。")
            st.info("➡️ `secrets.toml`ファイルの内容が正しいか確認してください。")
            return None, None

        # gspreadクライアントを初期化
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
        st.error(f"⚠️ 設定ファイル `.streamlit/secrets.toml`にキーが見つかりません: {e}")
        st.caption("ファイル名やセクション名（[google_secrets]など）を確認してください。")
        return None, None
    except Exception as e:
        st.error(f"❌ Google認証情報の初期化中にエラーが発生しました: {e}")
        st.caption("Secretsの内容が正しいサービスアカウントのJSON形式（TOMLに変換したもの）であるか確認してください。")
        return None, None

# =================================================================
# アプリケーション本体
# =================================================================

st.set_page_config(page_title="日記管理アプリ", layout="wide")

st.header("日報・連絡先 Streamlit アプリ (設定確認と連携基盤)")
st.markdown("このアプリは、Google Sheets/Drive連携の基盤となる設定と認証チェックを行います。")

# --- 1. アプリケーション設定の表示 ---
st.header("1. Googleリソース設定 (`app_config`)")
app_config = st.secrets.get("app_config", {})

if app_config:
    st.subheader("Spreadsheet ID / Drive Folder ID")
    st.json({
        "SPREADSHEET_ID": app_config.get("SPREADSHEET_ID", "N/A"),
        "DRIVE_ROOT_FOLDER_ID": app_config.get("DRIVE_ROOT_FOLDER_ID", "N/A")
    })

    st.subheader("ワークシート名リスト")
    worksheet_keys = [k for k in app_config.keys() if k.startswith("WORKSHEET_")]
    worksheet_data = {
        "設定項目": worksheet_keys,
        "設定値": [app_config[k] for k in worksheet_keys]
    }
    st.table(worksheet_data)

    st.info("💡 **重要:** 上記のワークシート名がスプレッドシート内のタブ名と**完全に一致**しているか確認してください。")
else:
    st.error("エラー: `app_config`セクションの設定を読み込めませんでした。`secrets.toml`を確認してください。")


# --- 2. サービスアカウントの認証 ---
st.header("2. 認証情報と接続準備")
gc, creds = get_google_sheets_client()

if gc and creds:
    service_account_email = st.secrets["google_secrets"].get('client_email', 'N/A')
    st.code(f"認証メールアドレス: {service_account_email}", language="python")

    # --- 3. 接続テストとデータ操作 ---
    st.subheader("3. 接続テストとデータ操作")
    st.success("👏 認証情報の準備完了！")
    st.markdown("""
    ---
    #### ⚙️ **次のステップ**
    `gc` (gspreadクライアント) や `creds` (認証情報オブジェクト) を使って、
    **スプレッドシートへのデータ書き込み**や**Driveへのファイル保存**といった
    実際のロジックをこの下に実装していきます。
    ---
    """)
