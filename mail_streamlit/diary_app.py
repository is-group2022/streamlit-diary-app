import streamlit as st
import json
import base64
# import gspread # ★ 実際にはgspreadやpydriveなどのライブラリをインストールして使います

# =================================================================
# 認証情報のデコード処理
# =================================================================

@st.cache_resource
def decode_and_get_service_account_info():
    """
    secrets.tomlからBase64エンコードされたキー文字列を読み込み、デコードして
    Googleサービスアカウント情報（JSONオブジェクト）を返します。
    """
    st.write("認証情報をデコードしています...")
    try:
        # secrets.tomlからエンコードされた文字列を取得
        encoded_key = st.secrets["google_secrets"]["ENCODED_KEY_STRING"]

        if "LS0tLS1CRUd" in encoded_key:
            st.error("❌ エラー: secrets.tomlの`ENCODED_KEY_STRING`がダミーのままです。")
            st.info("➡️ 実際の完全なBase64エンコードキー文字列に置き換えてから実行してください。")
            return None

        # Base64デコード
        decoded_bytes = base64.b64decode(encoded_key)

        # JSON文字列をPythonの辞書に変換
        service_account_info = json.loads(decoded_bytes.decode('utf-8'))

        st.success("✅ サービスアカウントキーのデコードに成功しました。")
        return service_account_info

    except KeyError as e:
        st.error(f"⚠️ 設定ファイル `.streamlit/secrets.toml`にキーが見つかりません: {e}")
        st.caption("ファイル名やセクション名（[app_config]など）を確認してください。")
        return None
    except Exception as e:
        st.error(f"❌ キーのデコード処理中にエラーが発生しました: {e}")
        st.caption("Base64文字列が正しくエンコードされているか確認してください。")
        return None

# =================================================================
# アプリケーション本体
# =================================================================

st.set_page_config(page_title="日記管理アプリ", layout="wide")

st.title("日報・連絡先 Streamlit アプリ (設定確認)")
st.markdown("このアプリは、`.streamlit/secrets.toml`から設定を読み込み、Google Sheets/Driveと連携する基盤です。")

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
    st.table({
        "設定項目": [k for k in app_config.keys() if k.startswith("WORKSHEET_")],
        "設定値": [v for k, v in app_config.items() if k.startswith("WORKSHEET_")]
    })

    st.info("💡 **重要:** 上記のワークシート名がスプレッドシート内のタブ名と**完全に一致**しているか確認してください（全角/半角、スペース、記号に注意）。")
else:
    st.error("エラー: `app_config`セクションの設定を読み込めませんでした。`secrets.toml`を確認してください。")


# --- 2. サービスアカウントの認証 ---
st.header("2. 認証情報と接続準備")
service_account_json = decode_and_get_service_account_info()

if service_account_json:
    st.code(f"認証メールアドレス: {service_account_json.get('client_email', 'N/A')}", language="python")

    # --- 3. Google Sheets/Drive 接続ロジック（ここに実装） ---
    st.subheader("3. 接続テストとデータ操作")
    st.markdown("""
    ---
    #### ⚙️ **実際の連携手順**
    1.  `service_account_json`を使って `gspread.service_account_from_dict()` でクライアントを初期化。
    2.  `SPREADSHEET_ID`でスプレッドシートを開く。
    3.  `WORKSHEET_REGISTER_NAME`などの名前で各シートにアクセスする。
    4.  Drive連携には `pydrive` などのライブラリを使用し、同様に認証情報を使って初期化します。
    ---
    """)

    # 例: 成功した場合のメッセージ
    st.success("👏 認証情報の準備完了！ここから下の行に、Google Sheets/Driveを操作するロジックを実装してください。")
