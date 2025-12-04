import streamlit as st
import pandas as pd
from gspread import Client, Worksheet
from google.oauth2.service_account import Credentials
from typing import Dict, Any
import logging
import base64 
import re # 正規表現モジュールをインポート

# ログレベルの設定（デバッグ用）
logging.basicConfig(level=logging.INFO)

# スコープ設定
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 
          'https://www.googleapis.com/auth/drive']

# ----------------------------------------------------------------------
# 認証情報の読み込みと整形（Base64エンコードされたキーに対応）
# ----------------------------------------------------------------------

@st.cache_resource
def get_gspread_client() -> Client:
    """
    Streamlit SecretsからGoogleサービスアカウント認証情報を取得し、
    gspreadクライアントを初期化します。

    Secretsに保存されたBase64エンコードされたキーをデコードします。
    """
    
    # 認証情報を取得
    service_account_secrets = st.secrets.get("google_secrets", {})
    
    if not service_account_secrets:
        st.error("Google認証情報の読み込みエラー: Secretsの[google_secrets]セクションの内容が正しいか確認してください。")
        raise ConnectionError("Secrets is empty.")

    info: Dict[str, Any] = {}
    
    # Secretsの内容を辞書にコピー
    for key, value in service_account_secrets.items():
        info[key] = value

    # 🚨 修正ロジック：
    # Base64エンコードされたキー('ENCODED_KEY_STRING')を探し、デコードして 'private_key' キーに設定し直します。
    if 'ENCODED_KEY_STRING' in info and isinstance(info['ENCODED_KEY_STRING'], str):
        try:
            encoded_key = info['ENCODED_KEY_STRING']
            
            # Base64文字列をデコードし、元の秘密鍵文字列（改行含む）に復元
            decoded_key_bytes = base64.b64decode(encoded_key)
            decoded_key_string = decoded_key_bytes.decode('utf-8')
            
            # 認証クライアントが期待する private_key キーに設定
            info['private_key'] = decoded_key_string
            
            # RAWキー（エンコードされたキー）は削除
            del info['ENCODED_KEY_STRING'] 
            logging.info("Base64エンコードされたキーから認証情報に復元しました。")
        except Exception as e:
            st.error(f"Base64デコードまたはprivate_keyの復元に失敗しました。キーの値が正しいか確認してください。エラー詳細: {e}")
            st.stop()
    else:
        st.error("Secretsに 'ENCODED_KEY_STRING' キーが見つかりません。Secretsの設定を確認してください。")
        st.stop()


    # gspreadクライアントを認証情報から直接生成
    try:
        # Credentials.from_service_account_info は JSON 形式の辞書を期待します
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        return Client(auth=creds)
    except Exception as e:
        # 認証情報の内容を表示してデバッグを容易にする (private_keyは表示しない)
        debug_info = info.copy()
        if 'private_key' in debug_info:
            # private_keyは長いため、最初の50文字と最後の50文字のみ表示
            pk = debug_info['private_key']
            debug_info['private_key'] = pk[:50] + "..." + pk[-50:]
            
        st.error(f"Google認証情報の初期化に失敗しました。Secretsの内容が正しいか確認してください。エラー詳細: {e}")
        st.code(debug_info) 
        st.stop()

# ----------------------------------------------------------------------
# アプリケーション本体
# ----------------------------------------------------------------------

try:
    gc = get_gspread_client()
    spreadsheet_id = st.secrets["app_config"]["SPREADSHEET_ID"]
    spreadsheet = gc.open_by_key(spreadsheet_id)
    st.success("🎉 Google認証とスプレッドシートへの接続に成功しました！")
except Exception as e:
    st.title("認証エラー")
    st.warning("上記のエラーメッセージを参照してください。Secretsの設定または権限が原因の可能性があります。")
    st.stop() # 接続に失敗した場合はアプリの実行を停止

# --- アプリケーションのUI ---
st.title("簡易日記登録アプリ")

# 動作確認のためのタブ表示
tab1, tab2 = st.tabs(["日記登録", "設定確認"])

with tab1:
    st.header("新しい日記を登録")
    diary_content = st.text_area("日記の内容を入力してください", height=150)
    if st.button("登録"):
        try:
            worksheet = spreadsheet.worksheet(st.secrets["app_config"]["WORKSHEET_REGISTER_NAME"])
            # 簡易な登録処理
            worksheet.append_row([pd.Timestamp.now().strftime("%Y/%m/%d %H:%M:%S"), diary_content])
            st.success("日記が正常に「日記登録用」シートに登録されました！")
        except Exception as e:
            st.error(f"データの書き込み中にエラーが発生しました。Secretsのシート名が正しいか確認してください。エラー詳細: {e}")

with tab2:
    st.header("現在のSecrets設定値（デバッグ用）")
    st.subheader("[app_config] 設定")
    st.json(st.secrets.get("app_config", {}))
    st.subheader("[google_secrets] のキー情報")
    # ENCODED_KEY_STRINGを表示
    debug_secrets = st.secrets.get("google_secrets", {}).copy()
    if 'ENCODED_KEY_STRING' in debug_secrets:
        raw_key = debug_secrets['ENCODED_KEY_STRING']
        debug_secrets['ENCODED_KEY_STRING'] = raw_key[:50] + "..." + raw_key[-50:]
    st.json(debug_secrets)
    st.write("認証クライアントオブジェクトの存在確認: OK")
