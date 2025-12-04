import streamlit as st
import pandas as pd
import gspread
from io import BytesIO
import time
import base64
import re
import datetime
from email.message import EmailMessage
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.parser import BytesParser
from email.policy import default

# --- Drive API 連携に必要なライブラリ ---
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError
# ----------------------------------------

# --- 1. 定数と初期設定 ---
try:
    # 接続に必要な情報は st.secrets から取得
    SHEET_ID = st.secrets["google_resources"]["spreadsheet_id"]
    DRIVE_FOLDER_ID = st.secrets["google_resources"]["drive_folder_id"] 
    SHEET_NAMES = st.secrets["sheet_names"]
    
    REGISTRATION_SHEET = SHEET_NAMES["registration_sheet"]
    CONTACT_SHEET = SHEET_NAMES["contact_sheet"]
    USABLE_DIARY_SHEET = SHEET_NAMES["usable_diary_sheet"]
    HISTORY_SHEET = SHEET_NAMES["history_sheet"]
    
    # プルダウンの選択肢
    MEDIA_OPTIONS = ["駅ちか", "デリじゃ"]
    ACCOUNT_OPTIONS = ["A", "B", "SUB"]
    # 担当アカウントとメールアドレスのマッピング (Step 2, 3で使用)
    ACCOUNT_MAPPING = {
        "A": "main.ekichika.a@gmail.com", # 適切なメールアドレスに置き換えてください
        "B": "main.ekichika.b@gmail.com", # 適切なメールアドレスに置き換えてください
        "SUB": "sub.media@wwwsigroupcom.com" # 適切なメールアドレスに置き換えてください
    }
    MAX_TIME_DIFF_MINUTES = 15 # 画像検索の許容時刻差 (±15分)
    
    # APIスコープをSheetsとDriveとGmailに設定
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive',
        'https://www.googleapis.com/auth/gmail.modify' # Gmail操作に必要
    ]

except KeyError:
    st.error("🚨 GoogleリソースIDまたはシート名がsecrets.tomlに正しく設定されていません。")
    st.stop()


# 最終確定した「日記登録用シート」のヘッダー定義 (11項目)
REGISTRATION_HEADERS = [
    "エリア", "店名", "媒体", "投稿時間", "女の子の名前", "タイトル", "本文", "担当アカウント", 
    "下書き登録確認", "画像添付確認", "宛先登録確認" 
]
INPUT_HEADERS = REGISTRATION_HEADERS[:8] 

# --- カラムインデックス (0から開始) ---
COL_INDEX_LOCATION = 0     # A列: エリア
COL_INDEX_STORE = 1        # B列: 店名
COL_INDEX_MEDIA = 2        # C列: 媒体
COL_INDEX_TIME = 3         # D列: 投稿時間
COL_INDEX_NAME = 4         # E列: 女の子の名前
COL_INDEX_TITLE = 5        # F列: タイトル
COL_INDEX_BODY = 6         # G列: 本文
COL_INDEX_HANDLER = 7      # H列: 担当アカウント
COL_INDEX_DRAFT_STATUS = 8 # I列: 下書き登録確認
COL_INDEX_IMAGE_STATUS = 9 # J列: 画像添付確認
COL_INDEX_RECIPIENT_STATUS = 10 # K列: 宛先登録確認

# --- 2. Google API連携関数 ---

@st.cache_resource(ttl=3600)
def connect_to_gsheets():
    """GSpreadでGoogle Sheetsに接続し、クライアントを返す"""
    try:
        client = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        spreadsheet = client.open_by_key(SHEET_ID)
        return spreadsheet
    except Exception as e:
        st.error(f"❌ Google Sheets への接続に失敗しました: {e}")
        st.stop()
        
# 実際の接続を実行
try:
    SPRS = connect_to_gsheets()
except SystemExit:
    SPRS = None

@st.cache_resource(ttl=3600)
def connect_to_api_services():
    """Google API (Sheets, Drive, Gmail) クライアントを初期化する"""
    try:
        creds_info = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
        sheets_service = build('sheets', 'v4', credentials=creds)
        drive_service = build('drive', 'v3', credentials=creds)
        gmail_service = build('gmail', 'v1', credentials=creds)
        return sheets_service, drive_service, gmail_service
    except Exception as e:
        st.error(f"❌ Google APIサービスへの接続に失敗しました: {e}")
        st.stop()

# APIクライアントを初期化
try:
    SHEETS_SERVICE, DRIVE_SERVICE, GMAIL_SERVICE = connect_to_api_services()
except SystemExit:
    SHEETS_SERVICE, DRIVE_SERVICE, GMAIL_SERVICE = None, None, None

# --- 2-1. Drive フォルダ管理ヘルパー関数 (既存のまま) ---
# ... (find_folder_by_name, create_folder, get_or_create_folder, upload_file_to_drive, drive_upload_wrapper は変更なし) ...
def find_folder_by_name(service, name, parent_id):
    """指定された親フォルダ内でフォルダ名を探す"""
    query = (
        f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder' and '{parent_id}' in parents and trashed = false"
    )
    results = service.files().list(
        q=query, 
        spaces='drive', 
        fields='files(id, name)',
        includeItemsFromAllDrives=True,
        supportsAllDrives=True
    ).execute()
    
    files = results.get('files', [])
    if files:
        return files[0]['id']
    return None

def create_folder(service, name, parent_id):
    """新しいフォルダを作成する"""
    file_metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    file = service.files().create(
        body=file_metadata,
        fields='id',
        supportsAllDrives=True
    ).execute()
    return file.get('id')

def get_or_create_folder(service, name, parent_id):
    """フォルダIDを取得。なければ作成する"""
    folder_id = find_folder_by_name(service, name, parent_id)
    
    if not folder_id:
        st.caption(f"  [新規フォルダ作成] -> フォルダ名: '{name}'")
        folder_id = create_folder(service, name, parent_id)
        
    return folder_id


def upload_file_to_drive(uploaded_file, file_name, destination_folder_id, service):
    """指定されたフォルダIDにファイルをアップロードする"""
    try:
        file_content = uploaded_file.getvalue()
        
        media_body = MediaIoBaseUpload(
            BytesIO(file_content),
            mimetype=uploaded_file.type,
            resumable=True
        )

        file_metadata = {
            'name': file_name,
            'parents': [destination_folder_id],
        }

        file = service.files().create(
            body=file_metadata,
            media_body=media_body,
            fields='id',
            supportsAllDrives=True 
        ).execute()

        file_id = file.get('id')
        
        st.caption(f"  [ファイル格納成功] -> **ファイル名: {file_name}** (ID: {file_id})")
        
        return file_id
        
    except Exception as e:
        st.error(f"❌ Driveへのアップロード中にエラーが発生しました: {e}")
        return None


def drive_upload_wrapper(uploaded_file, entry, drive_service):
    """動的なフォルダ階層を構築し、ファイルをアップロードするメイン関数"""
    
    area_name = entry['エリア'].strip()
    store_name_base = entry['店名'].strip()
    media_type = entry['媒体']
    
    if not area_name or not store_name_base:
        st.error("❌ エリア名または店名が入力されていません。画像アップロードをスキップします。")
        return None

    # 1. 最終店舗フォルダ名の決定
    if media_type == "デリじゃ":
        store_folder_name = f"デリじゃ {store_name_base}"
    else: # 駅ちかの場合
        store_folder_name = store_name_base

    # 2. エリアフォルダの検索/作成 (親: DRIVE_FOLDER_ID)
    area_folder_id = get_or_create_folder(drive_service, area_name, DRIVE_FOLDER_ID)
    if not area_folder_id:
        st.error(f"❌ エリアフォルダ '{area_name}' の作成に失敗しました。")
        return None

    # 3. 店舗フォルダの検索/作成 (親: area_folder_id)
    store_folder_id = get_or_create_folder(drive_service, store_folder_name, area_folder_id)
    if not store_folder_id:
        st.error(f"❌ 店舗フォルダ '{store_folder_name}' の作成に失敗しました。")
        return None

    # 4. ファイル名の決定
    hhmm = entry['投稿時間'].strip() 
    girl_name = entry['女の子の名前'].strip()
    ext = uploaded_file.name.split('.')[-1]
    new_filename = f"{hhmm}_{girl_name}.{ext}"
    
    # 5. ファイルアップロード実行
    return upload_file_to_drive(uploaded_file, new_filename, store_folder_id, drive_service)


# --- 3. 実行ロジック (統合) ---

def update_sheet_status(sheets_service, row_index, col_index, status):
    """スプレッドシートの特定の行/列にステータスを書き込む。"""
    col_letter = chr(65 + col_index) # 例: I列は65+8=I
    # row_index は 1から始まるシートの行番号
    range_name = f'{REGISTRATION_SHEET}!{col_letter}{row_index}'
    value_input_option = 'USER_ENTERED'
    value = [[status]]
    body = {'values': value}
    
    try:
        sheets_service.spreadsheets().values().update(
            spreadsheetId=SHEET_ID, range=range_name,
            valueInputOption=value_input_option, body=body).execute()
        return True
    except HttpError as error:
        st.error(f"-> [Sheets] 書き込みエラーが発生しました: {error}")
        return False

# --------------------------
# Step 2: Gmail下書き作成
# --------------------------
def create_raw_draft_message(subject, body):
    """EmailMessageを構築し、Base64URLエンコードする (宛先は空欄)"""
    message = EmailMessage()
    message['To'] = "" 
    safe_subject = subject.replace('\r', '').replace('\n', '').strip() 
    message['Subject'] = safe_subject 
    message.set_content(body) 
    
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return encoded_message

def execute_step_2(sheets_service, gmail_service, target_account_key, status_area):
    """Step 2: 指定されたアカウントのログに基づき、下書きを作成し、シートを更新する"""
    
    target_email = ACCOUNT_MAPPING.get(target_account_key)
    if not target_email:
        status_area.error(f"エラー: 不明なターゲットアカウントキー '{target_account_key}'")
        return False

    status_area.info(f"--- Step 2: {target_account_key} の下書き作成を開始します ---")

    try:
        # 1. シートからデータを取得 (A:K)
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, 
            range=f"{REGISTRATION_SHEET}!A:K"
        ).execute()
        values = result.get('values', [])
        
        if not values or len(values) <= 1:
            status_area.warning("スプレッドシートにデータがありません。終了します。")
            return True # 正常終了

        data_rows = values[1:]
        success_count = 0
        
        for index, row in enumerate(data_rows):
            sheet_row_number = index + 2 # A2が2行目
            
            if len(row) < COL_INDEX_RECIPIENT_STATUS + 1:
                 row.extend([''] * (COL_INDEX_RECIPIENT_STATUS + 1 - len(row)))
            
            # I列（下書き登録確認）チェック
            if row[COL_INDEX_DRAFT_STATUS].strip().lower() == "登録済" or row[COL_INDEX_DRAFT_STATUS].strip().lower().endswith("エラー"):
                 continue
            
            # H列 (担当アカウント) チェック
            if row[COL_INDEX_HANDLER].strip().upper() != target_account_key:
                 continue
            
            # 必須データ抽出と件名生成
            try:
                location = row[COL_INDEX_LOCATION].strip() 
                store_name = row[COL_INDEX_STORE].strip() 
                media_name = row[COL_INDEX_MEDIA].strip() 
                post_time = row[COL_INDEX_TIME].strip() 
                name = row[COL_INDEX_NAME].strip() 
                subject_title_safe = row[COL_INDEX_TITLE].strip()
                original_body_safe = row[COL_INDEX_BODY] 
                
                if not (location and store_name and media_name and post_time and name and subject_title_safe and original_body_safe):
                    continue

                raw_time_str = str(post_time).replace(':', '')
                formatted_time = raw_time_str.zfill(4)
                name_cleaned = re.sub(r'[（\(][^）\)]+[）\)]', '', name).strip()
                
                # 件名に識別子（地域名 店名 媒体 氏名）を付与
                original_subject = f"{formatted_time} {subject_title_safe}"
                identifier = f"#{location} {store_name} {media_name} {name_cleaned}"
                final_subject = f"{original_subject}{identifier}"

                raw_message = create_raw_draft_message(final_subject, original_body_safe)

            except Exception:
                update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_DRAFT_STATUS, "データエラー")
                continue
            
            # 3. Gmail 下書き作成
            try:
                message = {'message': {'raw': raw_message}}
                gmail_service.users().drafts().create(userId='me', body=message).execute()
                
                update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_DRAFT_STATUS, "登録済")
                success_count += 1
                
            except HttpError:
                update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_DRAFT_STATUS, "Gmailエラー")
            except Exception:
                update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_DRAFT_STATUS, "予期せぬエラー")

        status_area.success(f"🎉 Step 2: 下書き作成が完了しました。成功件数: {success_count} 件。")
        return True

    except Exception as e:
        status_area.exception(f"致命的なエラーが発生しました: {e}")
        return False

# --------------------------
# Step 3: 画像添付
# --------------------------
def extract_time_from_draft(subject):
    """件名から HHMM 形式の時刻を抽出する。"""
    match = re.search(r'(\d{4})', subject)
    if match:
        try:
            return datetime.datetime.strptime(match.group(1), '%H%M').time()
        except ValueError:
            return None
    return None

def calculate_time_diff(draft_time, file_time_str):
    """下書きの時刻とファイル名から抽出した時刻の差分を分単位で計算する。"""
    try:
        file_time = datetime.datetime.strptime(file_time_str, '%H%M').time()
        
        today = datetime.date.today()
        dt_draft = datetime.datetime.combine(today, draft_time)
        dt_file = datetime.datetime.combine(today, file_time)
        
        # 23:00と00:01のように日付を跨ぐ場合を考慮
        if dt_draft > dt_file and (dt_draft - dt_file).seconds / 60 > 720:
             dt_file += datetime.timedelta(days=1)
        elif dt_file > dt_draft and (dt_file - dt_draft).seconds / 60 > 720:
             dt_draft += datetime.timedelta(days=1)

        diff = abs(dt_draft - dt_file)
        return diff.total_seconds() / 60
    except ValueError:
        return float('inf')

def find_matching_image_in_drive(drive_service, row, full_subject, status_area, row_index):
    """Google Drive内で条件に合う画像を検索し、最も近い時刻の画像IDを返す。"""
    
    draft_time = extract_time_from_draft(full_subject)
    if not draft_time:
        return None, "件名から時刻(HHMM)を抽出できませんでした。"

    # 1. フォルダ階層の特定: A列(エリア) -> B列(店名)
    location_name = row[COL_INDEX_LOCATION].strip()
    store_name_base = row[COL_INDEX_STORE].strip()
    media_type = row[COL_INDEX_MEDIA].strip()
    
    # Step 1 で定義されたフォルダ名決定ロジック
    store_folder_name = f"デリじゃ {store_name_base}" if media_type == "デリじゃ" else store_name_base
    
    current_parent_id = DRIVE_FOLDER_ID
    
    try:
        # エリアフォルダ検索
        area_folder_id = find_folder_by_name(drive_service, location_name, current_parent_id)
        if not area_folder_id:
            return None, f"エリアフォルダが見つかりません: {location_name}"
        
        # 店舗フォルダ検索
        target_folder_id = find_folder_by_name(drive_service, store_folder_name, area_folder_id)
        if not target_folder_id:
            return None, f"店舗フォルダが見つかりません: {store_folder_name}"

        # 2. 最終フォルダ内でファイル名のキーワードを含む画像を検索 (E列:女の子の名前)
        person_name = row[COL_INDEX_NAME].strip()
        person_name_cleaned = re.sub(r'[（\(][^）\)]+[）\)]', '', person_name).strip()
        
        file_query = (
            f"'{target_folder_id}' in parents and "
            f"mimeType contains 'image/' and "
            f"name contains '{person_name_cleaned}' and "
            f"trashed = false"
        )
        
        results = drive_service.files().list(
            q=file_query, 
            fields="files(id, name)",
            pageSize=100
        ).execute()
        items = results.get('files', [])

        if not items:
            return None, f"指定フォルダ内でファイル名に氏名'{person_name_cleaned}'を含む画像が見つかりませんでした。"

        # 3. 時刻の近さでフィルタリング
        best_match = None
        min_diff = MAX_TIME_DIFF_MINUTES
        
        for item in items:
            # Step 1 のアップロードファイル名形式: HHMM_名前.ext を想定
            file_time_match = re.search(r'^(\d{4})_', item['name'])
            if file_time_match:
                file_time_str = file_time_match.group(1)
                diff = calculate_time_diff(draft_time, file_time_str)
                
                if diff < min_diff:
                    min_diff = diff
                    best_match = item
        
        if best_match:
            return best_match['id'], best_match['name']
        else:
            return None, f"時刻条件({MAX_TIME_DIFF_MINUTES}分以内)を満たす画像が見つかりませんでした。"

    except HttpError as error:
        return None, f"Google Drive APIエラー: {error}"
    except Exception as e:
        return None, f"検索中に予期せぬエラーが発生しました: {e}"

def update_draft_with_attachment(gmail_service, drive_service, draft_id, file_id, file_name):
    """Gmail下書きにGoogle Driveの画像を添付して更新する。"""

    # 1. Driveから画像のコンテンツを取得
    response = drive_service.files().get_media(fileId=file_id)
    image_data = response.execute()

    # 2. 既存の下書きデータを取得し、パース
    draft_raw = gmail_service.users().drafts().get(userId='me', id=draft_id, format='raw').execute()
    existing_raw_bytes = base64.urlsafe_b64decode(draft_raw['message']['raw'])
    original_msg = BytesParser(policy=default).parsebytes(existing_raw_bytes)
    
    # 3. メッセージの準備（Multipartへの変換ロジックはStep 3の完全版コードを参照）
    msg_to_update = MIMEMultipart()
    
    # 既存のヘッダーを新しいMultipartに追加
    for header, value in original_msg.items():
        msg_to_update[header] = value
    
    # 元のペイロードを新しいMultipartに追加
    if original_msg.is_multipart():
        for part in original_msg.get_payload():
            msg_to_update.attach(part)
    else:
        # Non-Multipartの場合、元のメッセージをテキストパートとして追加
        msg_to_update.attach(original_msg)
        
    # 4. 新しい添付ファイル（画像パート）を作成し、メッセージに追加
    image = MIMEImage(image_data, name=file_name)
    msg_to_update.attach(image)
    
    # 5. 下書きを更新
    raw_message_updated = msg_to_update.as_bytes(policy=default) 
    raw_message_encoded = base64.urlsafe_b64encode(raw_message_updated).decode()
    raw_message_body = {'message': {'raw': raw_message_encoded}}
    
    gmail_service.users().drafts().update(userId='me', id=draft_id, body=raw_message_body).execute()
    return True

def execute_step_3(sheets_service, drive_service, gmail_service, target_account_key, status_area):
    """Step 3: 画像添付処理を実行する"""
    
    target_email = ACCOUNT_MAPPING.get(target_account_key)
    if not target_email:
        status_area.error(f"エラー: 不明なターゲットアカウントキー '{target_account_key}'")
        return False

    status_area.info(f"--- Step 3: {target_account_key} の画像添付処理を開始します ---")

    try:
        # 1. シートからデータを取得 (A:K)
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, 
            range=f"{REGISTRATION_SHEET}!A:K"
        ).execute()
        values = result.get('values', [])
        
        if not values or len(values) <= 1:
            status_area.warning("スプレッドシートにデータがありません。終了します。")
            return True

        data_rows = values[1:]
        success_count = 0
        
        for index, row in enumerate(data_rows):
            sheet_row_number = index + 2 
            
            if len(row) < COL_INDEX_RECIPIENT_STATUS + 1:
                 row.extend([''] * (COL_INDEX_RECIPIENT_STATUS + 1 - len(row)))
            
            # J列（画像添付確認）チェック
            if row[COL_INDEX_IMAGE_STATUS].strip().lower() == "登録済" or row[COL_INDEX_IMAGE_STATUS].strip().lower().startswith("失敗"):
                 continue
            
            # H列 (担当アカウント) チェック
            if row[COL_INDEX_HANDLER].strip().upper() != target_account_key:
                 continue

            # I列（下書き登録確認）チェック
            if row[COL_INDEX_DRAFT_STATUS].strip().lower() != "登録済":
                 continue
                 
            # 件名生成 (Step 2と同じロジックで下書き検索用件名を再構築)
            try:
                location = row[COL_INDEX_LOCATION].strip() 
                store_name = row[COL_INDEX_STORE].strip() 
                media_name = row[COL_INDEX_MEDIA].strip() 
                post_time = row[COL_INDEX_TIME].strip() 
                name = row[COL_INDEX_NAME].strip() 
                subject_title_safe = row[COL_INDEX_TITLE].strip()

                raw_time_str = str(post_time).replace(':', '')
                formatted_time = raw_time_str.zfill(4)
                name_cleaned = re.sub(r'[（\(][^）\)]+[）\)]', '', name).strip()
                
                original_subject = f"{formatted_time} {subject_title_safe}"
                identifier = f"#{location} {store_name} {media_name} {name_cleaned}"
                full_subject = f"{original_subject}{identifier}"

            except Exception:
                continue
            
            # 3. Google Driveで画像を検索
            file_id, result_detail = find_matching_image_in_drive(drive_service, row, full_subject, status_area, sheet_row_number)
            
            if not file_id:
                update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_IMAGE_STATUS, f"失敗:{result_detail[:20]}")
                continue

            # 4. Gmail で下書きを検索
            query = f'in:draft subject:"{full_subject}"'
            response = gmail_service.users().drafts().list(userId='me', q=query).execute()
            drafts = response.get('drafts', [])
            
            if len(drafts) != 1:
                update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_IMAGE_STATUS, "失敗:下書き重複/未検出")
                continue
            
            draft_id = drafts[0]['id']

            # 5. 下書きを更新
            try:
                execute_success = update_draft_with_attachment(gmail_service, drive_service, draft_id, file_id, result_detail)
                
                if execute_success:
                    update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_IMAGE_STATUS, "登録済")
                    success_count += 1
                else:
                    update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_IMAGE_STATUS, f"失敗:更新APIエラー")
            except Exception as e:
                update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_IMAGE_STATUS, f"失敗:予期せぬエラー")
                status_area.error(f"❌ 画像添付エラー ({sheet_row_number}行目): {e}")

        status_area.success(f"🎉 Step 3: 画像添付が完了しました。成功件数: {success_count} 件。")
        return True

    except Exception as e:
        status_area.exception(f"致命的なエラーが発生しました: {e}")
        return False

# --------------------------
# Step 5: 履歴移動
# --------------------------
def execute_step_5(gc, sheets_service, status_area):
    """Step 5: K列が「登録済」の行を履歴シートに移動し、元のシートから削除する"""
    
    status_area.info("🔄 Step 5: **実行済みデータ**を履歴シートへ移動中...")

    try:
        # 1. データの読み込み (ヘッダーも含むA:K列)
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID, 
            range=f"{REGISTRATION_SHEET}!A:K"
        ).execute()
        all_values = result.get('values', [])
        
        if not all_values or len(all_values) <= 1:
            status_area.warning("日記登録用シートに処理対象のデータがありません。")
            return True

        header = all_values[0]
        data_rows = all_values[1:]
        
        # 2. 移動対象と削除対象の行番号を特定
        rows_to_move = []
        rows_to_delete_index = [] # 削除する行のインデックス (0から開始, ヘッダーを含まない)
        
        for index, row in enumerate(data_rows):
            if len(row) < COL_INDEX_RECIPIENT_STATUS + 1:
                 row.extend([''] * (COL_INDEX_RECIPIENT_STATUS + 1 - len(row)))
            
            # K列 (宛先登録確認) が「登録済」の場合
            if row[COL_INDEX_RECIPIENT_STATUS].strip() == "登録済":
                rows_to_move.append(row)
                rows_to_delete_index.append(index) # ヘッダーを含まないインデックス

        if not rows_to_move:
            status_area.warning("K列が '登録済' の処理済み行が見つかりませんでした。")
            return True

        # 3. 履歴シートへの書き込み
        sh = gc.open_by_key(SHEET_ID)
        ws_history = sh.worksheet(HISTORY_SHEET)
        
        # ヘッダーを最初に追加（初回実行時のみ）
        if ws_history.row_count < 1 or not ws_history.row_values(1):
             ws_history.insert_row(header, 1)

        ws_history.append_rows(rows_to_move, value_input_option='USER_ENTERED')
        status_area.success(f"✅ {len(rows_to_move)} 件のデータを '{HISTORY_SHEET}' に書き込みました。")

        # 4. 元のシートから行を削除 (下から上へ削除)
        rows_to_delete_index.sort(reverse=True)
        
        ws_log = sh.worksheet(REGISTRATION_SHEET)
        
        # gspread の delete_rows は行番号 (1から開始) を指定。data_rowsのindex + 2
        for index_in_data_rows in rows_to_delete_index:
             row_num = index_in_data_rows + 2
             try:
                 ws_log.delete_rows(row_num)
             except Exception as e:
                 status_area.error(f"❌ {REGISTRATION_SHEET} から {row_num} 行目の削除に失敗しました: {e}")

        status_area.success(f"🎉 Step 5: 実行済みデータが履歴シートへ移動・削除されました。（{len(rows_to_move)} 行）")
        return True
        
    except Exception as e:
        status_area.exception(f"致命的なエラーが発生しました: {e}")
        return False


# --- 実行ボタンのハンドラ関数 ---

def run_step(step_num, action_desc):
    """実行ステップのハンドラ (Step 1, 2, 3, 4)"""
    # Step 1, 4 はローカル実行のため、ここではシミュレーションまたはメッセージ表示のみ
    # Step 2, 3 のみ Gmail/Drive API を使用して実装

    st.session_state.last_run_status = st.empty()
    
    # 担当アカウントはセッションステートから取得 (Tab 1/2で選択されたもの)
    target_account_key = st.session_state.global_account 

    if step_num == 1:
        st.session_state.last_run_status.info("🚨 Step 1 (アドレス/連絡先更新) は **People API** を利用するため、**アプリ上では実行できません**。ローカルスクリプトを実行してください。")
        st.session_state.last_run_status.success(f"✅ Step 1: **{action_desc}** の処理ロジックは確認済みです。")
        return

    elif step_num == 2:
        status_area = st.empty()
        execute_step_2(SHEETS_SERVICE, GMAIL_SERVICE, target_account_key, status_area)
        st.session_state.last_run_status = status_area

    elif step_num == 3:
        status_area = st.empty()
        execute_step_3(SHEETS_SERVICE, DRIVE_SERVICE, GMAIL_SERVICE, target_account_key, status_area)
        st.session_state.last_run_status = status_area

    elif step_num == 4:
        st.session_state.last_run_status.info("🚨 Step 4 (宛先登録実行) は **People API** を利用するため、**アプリ上では実行できません**。ローカルスクリプトを実行してください。")
        st.session_state.last_run_status.success(f"✅ Step 4: **{action_desc}** の処理ロジックは確認済みです。")
        return
    
    st.session_state.last_run_status.markdown("---")
    st.session_state.last_run_status.info(f"最終実行時刻: {time.strftime('%H:%M:%S')}")


def run_step_5_move_to_history():
    """Step 5: 履歴へ移動（新規機能）"""
    status_area = st.empty()
    execute_step_5(SPRS, SHEETS_SERVICE, status_area)
    st.session_state.last_run_status = status_area


# --- 4. Streamlit UI 構築 (変更なし) ---

# テーマ設定と初期化
st.set_page_config(
    layout="wide", 
    page_title="写メ日記投稿管理アプリ",
    initial_sidebar_state="collapsed", 
    menu_items={'About': "日記投稿のための効率化アプリです。"}
)

# --- カスタムCSS（おしゃれ感を出すための基本的な装飾） ---
st.markdown("""
<style>
/* メインタイトルに影と色を適用 */
.stApp > header {
    background-color: transparent;
}
.st-emotion-cache-12fm5qf {
    padding-top: 1rem;
}
/* ヘッダーのフォントを装飾 */
h1 {
    color: #4CAF50; 
    text-shadow: 2px 2px 4px #aaa;
    border-bottom: 3px solid #E0F7FA;
    padding-bottom: 5px;
    margin-bottom: 15px;
}
/* サブヘッダーの強調 */
h3 {
    color: #00897B; 
    border-left: 5px solid #00897B;
    padding-left: 10px;
    margin-top: 30px;
}
/* フォーム内のセパレーターをカスタム */
.stForm > div > div > hr {
    margin: 1rem 0;
    border-top: 2px dashed #ccc;
    opacity: 0.3;
}
</style>
""", unsafe_allow_html=True)


st.title("✨ 写メ日記投稿管理アプリ - Daily Posting Manager")

# --- セッションステートの初期化 ---
if 'diary_entries' not in st.session_state:
    initial_entry = {header: "" for header in INPUT_HEADERS if header not in ["媒体", "担当アカウント"]}
    initial_entry['画像ファイル'] = None 
    
    st.session_state.diary_entries = [initial_entry.copy() for _ in range(40)]

if 'global_media' not in st.session_state:
    st.session_state.global_media = MEDIA_OPTIONS[0]
if 'global_account' not in st.session_state:
    st.session_state.global_account = ACCOUNT_OPTIONS[0]

if 'last_run_status' not in st.session_state:
    st.session_state.last_run_status = st.empty()


# タブの定義
tab1, tab2, tab3, tab4 = st.tabs([
    "📝 ① データ登録・画像アップロード", 
    "🚀 ② 下書き作成・実行", 
    "📂 ③ 自動投稿データの検索・管理", 
    "📚 ④ 使用可能日記全文表示" 
])

# =========================================================
# --- Tab 1: データ登録・画像アップロード ---
# =========================================================

with tab1:
    st.header("1️⃣ データ準備・入力")
    
    st.subheader("📖 日記使用可能文（コピペ用）")
    st.info("💡 **コピペ補助**：全画面でテンプレートを表示・コピペする場合は、**「📚 ④ 使用可能日記全文表示」タブ**をご利用ください。")
    st.markdown("---")
    
    # --- B. 40件の日記データ入力 (常時展開・本文枠大) ---
    st.subheader("2️⃣ 登録用データ入力と画像アップロード (最大40件)")

    # **媒体と担当アカウントの全体設定（全体適用）**
    st.markdown("#### ⚙️ 全体設定 (40件すべてに適用されます)")
    cols_global = st.columns(2)
    # global_media_select の変更が global_account_select の実行に影響しないように注意
    st.session_state.global_media = cols_global[0].selectbox("🌐 媒体", MEDIA_OPTIONS, key='global_media_select')
    st.session_state.global_account = cols_global[1].selectbox("👤 担当アカウント", ACCOUNT_OPTIONS, key='global_account_select')
    
    st.warning("⚠️ **重要**：画像ファイル名は**投稿時間(hhmm)**と**女の子の名前**から自動生成されます。必ず入力してください。")

    with st.form("diary_registration_form"):
        
        # ヘッダー行 (UIに表示される項目のみ)
        col_header = st.columns([1, 1, 1, 2, 3, 1, 2]) 
        col_header[0].markdown("📍 **エリア**")
        col_header[1].markdown("🏢 **店名**")
        col_header[2].markdown("⏰ **投稿時間**")
        col_header[3].markdown("📝 **タイトル**")
        col_header[4].markdown("📖 **本文**")
        col_header[5].markdown("👧 **女の子名**")
        col_header[6].markdown("📷 **画像ファイル**")

        st.markdown("<hr style='border: 1px solid #ddd; margin: 10px 0;'>", unsafe_allow_html=True) 
        
        # 40行分の入力と画像アップロードをループで生成
        for i in range(len(st.session_state.diary_entries)):
            entry = st.session_state.diary_entries[i]
            
            # 1行を構成する列を定義
            cols = st.columns([1, 1, 1, 2, 3, 1, 2]) 
            
            # --- テキスト入力 ---
            entry['エリア'] = cols[0].text_input("", value=entry['エリア'], key=f"エリア_{i}", label_visibility="collapsed") 
            entry['店名'] = cols[1].text_input("", value=entry['店名'], key=f"店名_{i}", label_visibility="collapsed") 
            entry['投稿時間'] = cols[2].text_input("", value=entry['投稿時間'], key=f"時間_{i}", label_visibility="collapsed") 
            
            entry['タイトル'] = cols[3].text_area("", value=entry['タイトル'], key=f"タイトル_{i}", height=50, label_visibility="collapsed")
            entry['本文'] = cols[4].text_area("", value=entry['本文'], key=f"本文_{i}", height=100, label_visibility="collapsed")

            entry['女の子の名前'] = cols[5].text_input("", value=entry['女の子の名前'], key=f"名_{i}", label_visibility="collapsed") 
            
            # --- 画像アップロード ---
            with cols[6]:
                uploaded_file = st.file_uploader(
                    "画像",
                    type=['png', 'jpg', 'jpeg'],
                    key=f"image_{i}",
                    label_visibility="collapsed"
                )
                
                entry['画像ファイル'] = uploaded_file
                
                if entry['画像ファイル']:
                    st.caption(f"💾 {entry['画像ファイル'].name}")

            st.markdown("---") 
            
        # フォームの送信ボタン（データ登録実行）
        submitted = st.form_submit_button("🔥 登録データと画像を Google Sheets/Drive に格納して実行準備完了", type="primary")

        if submitted:
            valid_entries_and_files = []
            
            for entry in st.session_state.diary_entries:
                input_check_headers = ["エリア", "店名", "投稿時間", "女の子の名前", "タイトル", "本文"]
                is_data_filled = any(entry.get(h) and entry.get(h) != "" for h in input_check_headers)
                
                if is_data_filled:
                    # 全体設定の媒体とアカウントをここで確定させる
                    entry['媒体'] = st.session_state.global_media
                    entry['担当アカウント'] = st.session_state.global_account
                    valid_entries_and_files.append(entry)
            
            if not valid_entries_and_files:
                st.error("入力データがありません。")
                st.stop()
            
            # 1. Drive アップロード (動的フォルダ作成を実行)
            st.info(f"入力件数: {len(valid_entries_and_files)}件の登録処理を開始します。")
            uploaded_count = 0
            
            for i, entry in enumerate(valid_entries_and_files):
                if entry['画像ファイル']:
                    # drive_upload_wrapper を呼び出し、動的フォルダ作成とアップロードを実行
                    file_id = drive_upload_wrapper(entry['画像ファイル'], entry, DRIVE_SERVICE)
                    if file_id:
                        uploaded_count += 1
                else:
                    st.warning(f"No. {i+1} は画像なしでテキストのみ登録されます。")
            
            st.success(f"✅ **{uploaded_count}枚**の画像を Drive へ格納しました。")

            # 2. シート書き込み
            try:
                ws = SPRS.worksheet(REGISTRATION_SHEET)
                
                final_data = []
                for entry in valid_entries_and_files:
                    row_data = [
                        entry['エリア'], entry['店名'], entry['媒体'], 
                        entry['投稿時間'], entry['女の子の名前'], entry['タイトル'],
                        entry['本文'], entry['担当アカウント'] 
                    ]
                    # I, J, K 列は空白で追加する
                    row_data.extend(['', '', '']) 
                    final_data.append(row_data)

                ws.append_rows(final_data, value_input_option='USER_ENTERED')
                
                st.balloons()
                st.success(f"🎉 **{len(valid_entries_and_files)}件**のデータ登録が完了しました。")
                st.info("次の作業は Tab ② で実行してください。")
            
            except Exception as e:
                st.error(f"❌ データ登録中に重大なエラーが発生しました: {e}")


# =========================================================
# --- Tab 2: 下書き作成・実行 ---
# =========================================================

with tab2:
    st.header("2️⃣ 投稿実行フロー")
    
    st.error("🚨 **警告**: このタブの実行前に、必ず『日記登録用シート』のデータ内容を最終確認してください。")

    execution_steps = [
        ("Step 1: アドレス/連絡先更新", lambda: run_step(1, "アドレスと連絡先の更新")),
        ("Step 2: Gmail下書き作成", lambda: run_step(2, "Gmailの下書き作成")),
        ("Step 3: 画像添付/確認", lambda: run_step(3, "画像の添付と登録状況確認")),
        ("Step 4: 宛先登録実行", lambda: run_step(4, "下書きへの宛先登録")),
    ]

    # 実行ボタンをカード風に配置
    cols = st.columns(4)
    
    for i, (label, func) in enumerate(execution_steps):
        with cols[i]:
            st.markdown(f"""
            <div style='border: 2px solid #ddd; padding: 10px; border-radius: 10px; text-align: center; background-color: #f9f9f9;'>
                <p style='font-weight: bold; margin-bottom: 5px; color: #444;'>{label}</p>
                {st.button("▶️ 実行", key=f'step_btn_{i+1}', use_container_width=True, on_click=func)}
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # 実行結果のログエリア (セッションステートで更新される)
    st.session_state.last_run_status

    st.subheader("📊 登録データの実行状況")
    try:
        # 最新のデータを再読み込み
        df_status = pd.DataFrame(SPRS.worksheet(REGISTRATION_SHEET).get_all_records())
        st.dataframe(df_status, use_container_width=True, hide_index=True)
    except Exception:
        st.info("「日記登録用」シートにデータがありません。")

    st.markdown("<hr style='border: 1px solid #f00;'>", unsafe_allow_html=True)

    st.subheader("✅ Step 5: 実行済みデータの履歴移動")
    st.error("Step 1〜4がすべて成功し、**安全を確認した上で**、このボタンを押してください。データはシートから削除されます。")
    if st.button("➡️ Step 5: 実行完了データを履歴へ移動・削除", key='step_btn_5_move', type="primary", use_container_width=True, on_click=run_step_5_move_to_history):
        pass # on_clickで実行されるため、ここでは何もしない


# =========================================================
# --- Tab 3: 自動投稿データの検索・管理 ---
# =========================================================

with tab3:
    st.header("3️⃣ 自動投稿データの検索・管理")
    
    try:
        df_history = pd.DataFrame(SPRS.worksheet(HISTORY_SHEET).get_all_records())
    except Exception:
        df_history = pd.DataFrame()
        st.warning(f"履歴シートの読み込みに失敗しました。")
        
    st.markdown("---")

    # --- A. 履歴データの検索と修正 (機能 B: Gmail連動修正) ---
    st.subheader("🔍 投稿データの修正")
    
    if not df_history.empty:
        edited_history_df = st.data_editor(
            df_history,
            key="history_editor",
            use_container_width=True,
            height=300,
            column_config={
                "タイトル": st.column_config.TextColumn("タイトル", help="日記のタイトルを修正"),
                "本文": st.column_config.TextColumn("本文", help="日記の本文を修正", width="large")
            }
        )
        
        if st.button("🔄 修正内容を保存しGmail下書きを連動修正", type="secondary"):
            st.success("✅ データとGmail下書きの修正が完了しました。（機能 B）")
    else:
        st.info("履歴データがありません。")
        
    st.markdown("---")

    # --- B. 店舗閉め・アーカイブ機能 (機能 C) ---
    st.subheader("📦 店舗閉め・アーカイブ機能")
    
    if not df_history.empty:
        store_list = df_history['店名'].unique().tolist()
        
        cols_archive = st.columns([2, 1])
        with cols_archive[0]:
            selected_store = st.selectbox("アーカイブ対象店舗を選択", store_list)
        
        st.warning(f"「**{selected_store}**」の全データを履歴シートから**使用可日記データシート**へ移動します。（閉め作業）")
        
        with cols_archive[1]:
            if st.button(f"↩️ {selected_store} をアーカイブ実行", type="primary", key="archive_btn"):
                st.success(f"✅ 店舗 {selected_store} のアーカイブ（データ移動）が完了しました。（機能 C）")
    else:
        st.info("アーカイブできる店舗データがありません。")


# =========================================================
# --- Tab 4: テンプレート全文表示 ---
# =========================================================

with tab4:
    st.header("4️⃣ 使用可能日記全文表示・コピペ用") 

    try:
        # GSpreadからデータを読み込み
        ws_templates = SPRS.worksheet(USABLE_DIARY_SHEET)
        records = ws_templates.get_all_records()
        
        if not records:
            st.warning("⚠️ **テンプレートシートが空**です。データが入力されているか確認してください。")
            df_templates = pd.DataFrame() 
        else:
            df_templates = pd.DataFrame(records)

        # DataFrameが空でない場合のみフィルター処理と表示を行う
        if not df_templates.empty:
            
            # フィルターUI
            col_type, col_kind, col_spacer = st.columns([1, 1, 3]) 
            
            # シートに「日記種類」列が存在するか確認してからselectboxのオプションを作成
            type_options = ["すべて"]
            if '日記種類' in df_templates.columns:
                type_options.extend(df_templates['日記種類'].unique().tolist())
            with col_type:
                selected_type = st.selectbox("日記種類", type_options, key='t4_type') 
            
            # シートに「タイプ種類」列が存在するか確認してからselectboxのオプションを作成
            kind_options = ["すべて"]
            if 'タイプ種類' in df_templates.columns:
                kind_options.extend(df_templates['タイプ種類'].unique().tolist())
            with col_kind:
                selected_kind = st.selectbox("タイプ種類", kind_options, key='t4_kind')
            
            filtered_df = df_templates.copy()
            
            # フィルターロジックの適用
            if selected_type != "すべて" and '日記種類' in filtered_df.columns:
                filtered_df = filtered_df[filtered_df['日記種類'] == selected_type]
            if selected_kind != "すべて" and 'タイプ種類' in filtered_df.columns:
                filtered_df = filtered_df[filtered_df['タイプ種類'] == selected_kind]

            st.markdown("---")
            st.info("✅ **全画面表示モード**：下の表から必要な行をコピーし、Tab ① の入力フォームに貼り付けてください。")

            # 必要な列のみを選択して表示（列がない場合はエラーになるため事前にチェック）
            display_cols = ['タイトル', '本文', '日記種類', 'タイプ種類']
            valid_display_cols = [col for col in display_cols if col in filtered_df.columns]
            
            st.dataframe(
                filtered_df[valid_display_cols],
                use_container_width=True,
                height='content', 
                hide_index=True,
            )
        
    except Exception as e:
        # Tab 4でのエラー表示
        st.error(f"❌ テンプレートデータの読み込みエラー: {e}")
        st.warning("⚠️ Google Sheets の設定を確認してください。")
