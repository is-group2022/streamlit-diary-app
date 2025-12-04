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
# 認証情報の読み込みと整形（改行なしのRAW文字列に対応）
# ----------------------------------------------------------------------

@st.cache_resource
def get_gspread_client() -> Client:
    """
    Streamlit SecretsからGoogleサービスアカウント認証情報を取得し、
    gspreadクライアントを初期化します。

    Secrets設定のTOML形式エラーを回避するため、private_key_rawから改行コードを復元します。
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
    # private_key_rawキーを探し、改行コードを復元して private_key キーに設定し直します。
    if 'private_key_raw' in info and isinstance(info['private_key_raw'], str):
        try:
            pk_content = info['private_key_raw']
            
            # --- 最終修正：文字列のクリーンアップを追加 ---
            
            # 1. Base64文字列の本体を抽出するためにヘッダーとフッターを削除し、改行・スペース・制御文字を全て除去
            pk_content = pk_content.replace('-----BEGIN PRIVATE KEY-----', '')
            pk_content = pk_content.replace('-----END PRIVATE KEY-----', '')
            
            # Base64文字以外のすべて（スペース、タブ、改行など）を削除
            # gspread/google-authが期待する形式（改行を挟んだ形式）に戻す
            key_body_clean = re.sub(r'[^\w+/=]', '', pk_content) 
            
            # 64文字ごとに改行を挿入して、元のPEM形式（改行あり）に復元
            reformatted_key_body = '\n'.join([key_body_clean[i:i+64] for i in range(0, len(key_body_clean), 64)])
            
            # 全体を結合
            pk_reformatted = "-----BEGIN PRIVATE KEY-----\n" + reformatted_key_body + "\n-----END PRIVATE KEY-----\n"
            
            # 認証クライアントが期待する private_key キーに設定
            info['private_key'] = pk_reformatted
            
            # デバッグのためにRAWキーは削除
            del info['private_key_raw'] 
            logging.info("private_key_rawから認証情報に復元しました。")
        except Exception as e:
            st.error(f"private_keyの文字列処理に失敗しました。キーの値が正しいか確認してください。エラー詳細: {e}")
            st.stop()
    else:
        st.error("Secretsに 'private_key_raw' キーが見つかりません。Secretsの設定を確認してください。")
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
    # private_key_rawを表示
    debug_secrets = st.secrets.get("google_secrets", {}).copy()
    if 'private_key_raw' in debug_secrets:
        debug_secrets['private_key_raw'] = debug_secrets['private_key_raw'][:50] + "..." 
    st.json(debug_secrets)
    st.write("認証クライアントオブジェクトの存在確認: OK")
