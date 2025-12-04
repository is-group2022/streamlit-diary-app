import streamlit as st
import base64
import json
from google.oauth2 import service_account

# Streamlitのsecretsからエンコードされたキー文字列を読み込み、
# Googleサービスアカウントの認証情報（credentials）を生成する関数。

def get_google_credentials():
    """
    Streamlit secretsからBase64エンコードされた秘密鍵を読み込み、
    Googleサービスアカウントの認証情報を返します。
    
    Secretsファイルには以下の形式でキーが保存されている必要があります:
    [google_secrets]
    ENCODED_KEY_STRING = "..."
    """
    
    # Secrets設定が読み込まれているか確認
    if 'google_secrets' not in st.secrets or 'ENCODED_KEY_STRING' not in st.secrets.google_secrets:
        st.error("🚨 エラー: Streamlit secretsに 'google_secrets.ENCODED_KEY_STRING' が見つかりません。")
        return None

    encoded_key = st.secrets.google_secrets['ENCODED_KEY_STRING']
    
    try:
        # Base64でエンコードされたキーをデコード
        # バイト列 (bytes) に変換
        decoded_bytes = base64.b64decode(encoded_key)
        
        # JSON文字列に変換し、さらにPython辞書（サービスアカウント情報）にパース
        service_account_info = json.loads(decoded_bytes.decode('utf-8'))
        
        # サービスアカウント情報から認証情報オブジェクトを生成
        credentials = service_account.Credentials.from_service_account_info(service_account_info)
        
        return credentials
        
    except Exception as e:
        st.error(f"🚨 認証情報のデコード中にエラーが発生しました。Secretsキーの形式を確認してください: {e}")
        return None

# --- アプリケーションでの使用例 (この部分を実際のアプリに組み込んでください) ---
# if __name__ == '__main__':
#     st.title("GCP認証テスト")
    
#     credentials = get_google_credentials()
    
#     if credentials:
#         st.success("✅ Google Cloud 認証情報が正常に読み込まれ、デコードされました！")
#         # 例: credentialsを使ってGoogle BigQueryやGCPのサービスを呼び出す
#     else:
#         st.warning("⚠️ 認証情報の取得に失敗しました。上記のエラーメッセージを確認してください。")
