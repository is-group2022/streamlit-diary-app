import streamlit as st
from datetime import datetime
import pandas as pd
import json
import io
import time

# Google APIライブラリのインポート
from gspread import service_account, Worksheet
from gspread.exceptions import APIError
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
import google.auth

# ==============================================================================
# ⚠️ 1. 設定情報 (このアプリがアクセスするリソースIDを設定してください)
# ==============================================================================

# スプレッドシートID: 日記マスターシート
SPREADSHEET_ID = "1sEzw59aswIlA-8_CTyUrRBLN7OnrRIJERKUZ_bELMrY"
WORKSHEET_NAME = "実験用" 

# Googleドライブ フォルダID: アップロードされた画像を保存する場所
# 🚨🚨🚨 あなたのGoogleドライブフォルダIDを設定済みです 🚨🚨🚨
DRIVE_FOLDER_ID = "1malvBDg-fIvzFWqxAyvOwL18hoKzzJoN" 

# Gmail 下書き作成時のデフォルトの件名テンプレート
DRAFT_SUBJECT_TEMPLATE = "【日報】{date}の日記更新"
DRAFT_DEFAULT_TO_ADDRESS = "example@mailinglist.com"

# ==============================================================================
# 2. 認証情報の設定 (Streamlit Secretsから取得)
# ==============================================================================

# Secretsからトップレベルのキーを読み込み、認証情報辞書を再構築します
try:
    SERVICE_ACCOUNT_KEY = {
        "type": st.secrets["type"],
        "project_id": st.secrets["project_id"],
        "private_key_id": st.secrets["private_key_id"],
        "private_key": st.secrets["private_key"],
        "client_email": st.secrets["client_email"],
        "client_id": st.secrets["client_id"],
        "auth_uri": st.secrets["auth_uri"],
        "token_uri": st.secrets["token_uri"],
        "auth_provider_x509_cert_url": st.secrets["auth_provider_x509_cert_url"],
        "client_x509_cert_url": st.secrets["client_x509_cert_url"],
        "universe_domain": st.secrets["universe_domain"],
    }
except KeyError as e:
    # ユーザーにSecretsのキーが不足していることを伝えます
    st.error(f"🚨 API初期化エラー: Secretsに必須キー '{e.args[0]}' が見つかりません。")
    st.info("Secrets (金庫) の内容が、上記「Secretsに貼り付ける内容 (最終版)」と異なっていないか確認してください。")
    st.stop()
except Exception as e:
    st.error(f"🚨 API初期化エラー: Googleの認証情報読み込み中に予期せぬエラーが発生しました。詳細: {e}")
    st.stop()


# ==============================================================================
# 3. Googleサービス初期化関数
# ==============================================================================

@st.cache_resource
def init_gspread_client(creds_info):
    """gspreadクライアントを初期化し、Worksheetを返します。"""
    if not creds_info:
        return None, None
    try:
        # 認証情報の読み込み
        creds = Credentials.from_service_account_info(creds_info, 
                                                      scopes=['https://www.googleapis.com/auth/spreadsheets',
                                                              'https://www.googleapis.com/auth/drive'])
        # gspreadクライアントを初期化し、スプレッドシートを開く
        client = service_account(client_email=creds_info["client_email"], creds=creds)
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        return client, worksheet
    except APIError as e:
        st.error(f"🚨 Google Sheets APIエラー: スプレッドシートIDまたはシート名が不正です。権限も確認してください。詳細: {e}")
        return None, None
    except Exception as e:
        st.error(f"🚨 gspreadクライアント初期化エラー: {e}")
        return None, None

@st.cache_resource
def init_drive_service(creds_info):
    """Google DriveとGmailサービスを初期化します。"""
    if not creds_info:
        return None, None
    try:
        creds = Credentials.from_service_account_info(creds_info, 
                                                      scopes=['https://www.googleapis.com/auth/drive',
                                                              'https://www.googleapis.com/auth/gmail.compose'])
        
        # Driveサービス
        drive_service = build('drive', 'v3', credentials=creds)
        # Gmailサービス (メール下書き作成用)
        gmail_service = build('gmail', 'v1', credentials=creds)
        
        return drive_service, gmail_service
    except Exception as e:
        st.error(f"🚨 Google Drive/Gmail サービス初期化エラー: {e}")
        return None, None

# サービスとワークシートの初期化
_, sheet = init_gspread_client(SERVICE_ACCOUNT_KEY)
drive_service, gmail_service = init_drive_service(SERVICE_ACCOUNT_KEY)

if sheet is None or drive_service is None or gmail_service is None:
    st.error("🚨 アプリケーションの初期化に失敗しました。設定を確認してください。")
    st.stop()

# ==============================================================================
# 4. メインアプリケーションロジック
# ==============================================================================

# セッション状態の初期化
if 'data' not in st.session_state:
    st.session_state.data = []

def upload_file_to_drive(file_buffer, file_name, folder_id, drive_service):
    """ファイルをGoogleドライブにアップロードし、共有リンクを返します。"""
    try:
        # アップロード
        file_metadata = {
            'name': file_name,
            'parents': [folder_id],
            'mimeType': file_buffer.type  # ファイルタイプを自動判定
        }
        
        media = MediaIoBaseUpload(file_buffer, file_buffer.type, resumable=True)
        file = drive_service.files().create(body=file_metadata,
                                            media_body=media,
                                            fields='id, webViewLink').execute()

        # 外部公開権限を設定（誰でも閲覧可能にする）
        drive_service.permissions().create(
            fileId=file.get('id'),
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()

        return file.get('webViewLink')
    
    except APIError as e:
        st.error(f"🚨 Google Drive APIエラー: フォルダIDが不正か、権限がありません。詳細: {e}")
        return "アップロード失敗 (APIエラー)"
    except Exception as e:
        st.error(f"🚨 ファイルアップロード中に予期せぬエラーが発生しました: {e}")
        return "アップロード失敗 (予期せぬエラー)"

def create_gmail_draft(to_address, subject, body, gmail_service):
    """Gmailの下書きを作成します。"""
    try:
        # MIMEフォーマットのメッセージを構築
        message = (
            f"To: {to_address}\r\n"
            f"Subject: {subject}\r\n"
            f"Content-Type: text/html; charset=utf-8\r\n"
            f"\r\n"
            f"{body}"
        )
        
        # Base64エンコード
        import base64
        encoded_message = base64.urlsafe_b64encode(message.encode('utf-8')).decode('utf-8')
        
        # 下書き作成APIを呼び出し
        draft = {'message': {'raw': encoded_message}}
        draft = gmail_service.users().drafts().create(userId='me', body=draft).execute()
        
        return True, draft.get('id')
    except Exception as e:
        st.error(f"🚨 Gmail下書き作成エラー: 権限や設定を確認してください。詳細: {e}")
        return False, None


# メイン投稿処理
def post_diary(writer, title, body, uploaded_file):
    """日記データをスプレッドシートに書き込みます。"""
    
    # 画像アップロード処理
    image_link = ""
    if uploaded_file is not None:
        if DRIVE_FOLDER_ID == "YOUR_DRIVE_FOLDER_ID_HERE":
            st.error("⚠️ GoogleドライブのフォルダIDが設定されていません。画像アップロードはスキップします。")
        else:
            with st.spinner('画像をGoogleドライブにアップロード中...'):
                image_link = upload_file_to_drive(uploaded_file, uploaded_file.name, DRIVE_FOLDER_ID, drive_service)
            
            if "アップロード失敗" in image_link:
                st.error(f"画像アップロード失敗: {image_link}")
                return False

    # タイムスタンプと投稿データ
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # データをスプレッドシートに追加する形式
    row_data = [timestamp, writer, title, body, image_link]
    
    # スプレッドシートへの書き込み
    try:
        sheet.append_row(row_data)
        st.session_state.data.append(row_data)
        return True
    except APIError as e:
        st.error(f"🚨 スプレッドシート書き込みエラー: API権限を確認してください。詳細: {e}")
        return False
    except Exception as e:
        st.error(f"🚨 予期せぬ書き込みエラー: {e}")
        return False


# ==============================================================================
# 5. Streamlit UI定義
# ==============================================================================

st.set_page_config(page_title="チーム日記投稿アプリ", layout="wide")

st.title("📝 チーム日報・日記投稿アプリ")
st.markdown("今日の活動や出来事を記録しましょう。画像もGoogleドライブに自動保存されます。")

with st.form("diary_form", clear_on_submit=True):
    # ユーザー入力
    col1, col2 = st.columns(2)
    with col1:
        writer = st.text_input("👤 投稿者名", value=st.session_state.get('writer', ''))
    with col2:
        title = st.text_input("💡 タイトル", value=st.session_state.get('title', ''))

    body = st.text_area("本文 (今日の一言、活動内容など)", height=300)

    st.markdown("---")

    # ファイルアップローダー
    uploaded_file = st.file_uploader("🖼️ 画像をアップロード (オプション)", type=['png', 'jpg', 'jpeg', 'gif'])

    # 投稿ボタン
    submitted = st.form_submit_button("✅ 日記を投稿する")
    
    if submitted:
        if not writer or not title or not body:
            st.warning("投稿者名、タイトル、本文は必須です！")
        else:
            # フォームデータをセッションに保存（次の投稿のために）
            st.session_state.writer = writer
            st.session_state.title = title
            
            # 投稿処理実行
            if post_diary(writer, title, body, uploaded_file):
                st.success("🎉 投稿が成功しました！")
                
                # 下書き作成ボタンをセッションに追加
                st.session_state['last_post'] = {
                    'writer': writer,
                    'title': title,
                    'body': body
                }
            else:
                st.error("投稿に失敗しました。ログを確認してください。")

# 下書き作成機能
if 'last_post' in st.session_state:
    post_data = st.session_state['last_post']
    
    # メールの件名と本文を生成
    subject = DRAFT_SUBJECT_TEMPLATE.format(date=datetime.now().strftime("%Y/%m/%d"))
    
    # HTMLメール本文
    html_body = f"""
    <h2>【{post_data['title']}】</h2>
    <p><strong>投稿者:</strong> {post_data['writer']}</p>
    <hr>
    <p style="white-space: pre-wrap;">{post_data['body']}</p>
    <p>---<br>
    投稿時刻: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    </p>
    """
    
    st.markdown("---")
    st.subheader("メール連携")
    
    # 下書き作成ボタン
    if st.button(f"📧 この内容でGmailの下書きを作成する ({DRAFT_DEFAULT_TO_ADDRESS}宛)"):
        with st.spinner("Gmail下書きを作成中..."):
            success, draft_id = create_gmail_draft(DRAFT_DEFAULT_TO_ADDRESS, subject, html_body, gmail_service)
            if success:
                st.success(f"下書きが作成されました！Gmailで確認してください。")
            else:
                st.error("下書き作成に失敗しました。")

# ==============================================================================
# 6. 履歴表示 (オプション - 負荷軽減のため簡易表示)
# ==============================================================================

st.markdown("---")
st.subheader("📝 最新の日記履歴 (リアルタイムではありません)")

# データをキャッシュから表示
if st.session_state.data:
    df = pd.DataFrame(st.session_state.data, columns=["日時", "投稿者名", "タイトル", "本文", "画像リンク"])
    # 最新の10件を表示
    st.dataframe(df.tail(10).style.set_properties(**{'font-size': '10pt'}), 
                 height=350, 
                 use_container_width=True)
else:
    st.info("まだ投稿がありません。最初の投稿をしましょう！")
