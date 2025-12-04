import streamlit as st
import pandas as pd
from gspread import Client, Worksheet
from google.oauth2.service_account import Credentials
from typing import Dict, Any
import json
import logging

# ログレベルの設定（デバッグ用）
logging.basicConfig(level=logging.INFO)

# スコープ設定
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 
          'https://www.googleapis.com/auth/drive']

# ----------------------------------------------------------------------
# 認証情報の読み込みと整形（Secretsの特殊な形式に対応）
# ----------------------------------------------------------------------

@st.cache_resource
def get_gspread_client() -> Client:
    """
    Streamlit SecretsからGoogleサービスアカウント認証情報を取得し、
    gspreadクライアントを初期化します。

    Secrets設定のTOML形式エラーを回避するため、private_keyをアプリケーション側で整形します。
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
    # TOMLエラーを避けるため、private_keyは改行なしの1行文字列として保存されています。
    # ここで、認証クライアントが期待する正しい形式（改行を含む）に復元します。
    if 'private_key' in info and isinstance(info['private_key'], str):
        pk_content = info['private_key']
        
        # BEGIN PRIVATE KEYとEND PRIVATE KEYの行に改行文字 '\n' を手動で挿入します。
        # 鍵の中身（base64エンコード部分）は改行がなくても認証クライアントは受け付けるため、
        # ヘッダーとフッターの構造を整えることに注力します。
        pk_content = pk_content.replace('-----BEGIN PRIVATE KEY-----', '-----BEGIN PRIVATE KEY-----\n')
        pk_content = pk_content.replace('-----END PRIVATE KEY-----', '\n-----END PRIVATE KEY-----\n')
        
        # 復元した文字列を認証情報として設定
        info['private_key'] = pk_content
        logging.info("private_keyの改行コードを復元しました。")


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
    # private_keyは長いため、表示から除外
    debug_secrets = st.secrets.get("google_secrets", {}).copy()
    if 'private_key' in debug_secrets:
        debug_secrets['private_key'] = debug_secrets['private_key'][:50] + "..." 
    st.json(debug_secrets)
    st.write("認証クライアントオブジェクトの存在確認: OK")
