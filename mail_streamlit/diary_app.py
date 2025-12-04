import streamlit as st
import pandas as pd
from gspread import Client, Worksheet
from google.oauth2.service_account import Credentials
from typing import Dict, Any
import logging
import base64

# ログレベルの設定（デバッグ用）
logging.basicConfig(level=logging.INFO)

# スコープ設定
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 
          'https://www.googleapis.com/auth/drive']

# ----------------------------------------------------------------------
# 認証情報の読み込みと整形（BASE64エンコードされたSecretsに対応）
# ----------------------------------------------------------------------

@st.cache_resource
def get_gspread_client() -> Client:
    """
    Streamlit SecretsからGoogleサービスアカウント認証情報を取得し、
    gspreadクライアントを初期化します。
    
    Secrets設定のTOMLエラーを回避するため、private_key_base64をデコードして整形します。
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
    # private_key_base64キーを探し、値をデコードして private_key キーに設定し直します。
    if 'private_key_base64' in info and isinstance(info['private_key_base64'], str):
        try:
            # BASE64文字列をデコードし、バイト列からUTF-8文字列に変換
            pk_base64_decoded = base64.b64decode(info['private_key_base64']).decode('utf-8')
            
            # 認証クライアントが期待する private_key キーに設定
            info['private_key'] = pk_base64_decoded
            
            # デバッグのためにBASE64キーは削除（必須ではないが推奨）
            del info['private_key_base64'] 
            logging.info("private_key_base64をデコードし、認証情報に復元しました。")
        except Exception as e:
            st.error(f"BASE64デコード処理に失敗しました。キーの値が正しいBASE64形式か確認してください。エラー詳細: {e}")
            st.stop()
    else:
        st.error("Secretsに 'private_key_base64' キーが見つかりません。Secretsの設定を確認してください。")
        st.stop()


    # gspreadクライアントを認証情報から直接生成
    try:
        # Credentials.from_service_account_info は JSON 形式の辞書を期待します
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        return Client(auth=creds)
    except Exception as e:
        st.error(f"Google認証情報の初期化に失敗しました。Secretsの内容が正しいか確認してください。エラー詳細: {e}")
        st.code(info) # 認証情報の内容を表示してデバッグを容易にする
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
    st.warning("上記のエラーメッセージを参照してください。Secretsの設定が原因の可能性が高いです。")
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
    # private_key_base64を表示
    debug_secrets = st.secrets.get("google_secrets", {}).copy()
    if 'private_key_base64' in debug_secrets:
        debug_secrets['private_key_base64'] = debug_secrets['private_key_base64'][:50] + "..." 
    st.json(debug_secrets)
    st.write("認証クライアントオブジェクトの存在確認: OK")
