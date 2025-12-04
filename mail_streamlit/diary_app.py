import streamlit as st
import gspread
import pandas as pd
import json
import os
import sys
import base64
import re
import time
import io
import datetime
from email.message import EmailMessage
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.parser import BytesParser
from email.policy import default

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- 設定定数 ---
# ※ このファイルを実行する際、'service_account.json' が必要です。

# メイン処理用ログシートのID
SPREADSHEET_ID_MAIN = "1sEzw59aswIlA-8_CTyUrRBLN7OnrRIJERKUZ_bELMrY"
# 全文コピペ機能用のシートID (新ID)
SPREADSHEET_ID_COPIER = "1e-iLey43A1t0bIBoijaXP55t5fjONdb0ODiTS53beqM" 

# 共通シート名
SHEET_NAME_LOG = "日記登録用"
SHEET_NAME_HISTORY = "履歴"
DRIVE_FOLDER_ID = 'YOUR_DRIVE_ROOT_FOLDER_ID' # ★要修正: あなたの「写メ日記画像用」フォルダのIDを設定してください
MAX_TIME_DIFF_MINUTES = 15 # 画像検索の許容時刻差 (±15分)

# ログシートの読み取り範囲 (A列:地域名, B:店名, C:媒体, D:時刻, E:氏名, F:タイトル, G:本文, H:担当, I:下書き処理済, J:画像処理済, K:宛先処理済)
DATA_RANGE_LOG = f"{SHEET_NAME_LOG}!A:K" # A:Kを全取得に変更 (Step 5でヘッダーも扱うため)

# 担当アカウントとメールアドレスのマッピング
ACCOUNT_MAPPING = {
    "A": "main.ekichika.a@gmail.com",
    "B": "main.ekichika.b@gmail.com",
    "SUB": "sub.media@wwwsigroupcom.com"
}

# --- カラムインデックス (0から開始) ---
COL_INDEX_LOCATION = 0     # A列: 地域名
COL_INDEX_STORE = 1        # B列: 店名
COL_INDEX_MEDIA = 2        # C列: 媒体
COL_INDEX_TIME = 3         # D列: 時刻
COL_INDEX_NAME = 4         # E列: 氏名
COL_INDEX_TITLE = 5        # F列: タイトル
COL_INDEX_BODY = 6         # G列: 本文
COL_INDEX_HANDLER = 7      # H列: 担当
COL_INDEX_DRAFT_STATUS = 8 # I列: 下書き処理済 (Step 2/draft_creator.pyが更新)
COL_INDEX_IMAGE_STATUS = 9 # J列: 画像処理済 (Step 3/image_uploader.pyが更新)
COL_INDEX_RECIPIENT_STATUS = 10 # K列: 宛先処理済 (Step 4/draft_updater.pyが更新)


# --- サービスアカウント認証とAPIサービス初期化 ---
@st.cache_resource
def get_google_services():
    """Google API (Sheets, Gmail, Drive) サービスを初期化する"""
    try:
        # Streamlit Secrets または ファイルから認証情報をロード
        if "service_account" in st.secrets:
            # Streamlit Cloud の場合
            cred_info = st.secrets["service_account"]
        else:
            # ローカル環境の場合
            with open("service_account.json", "r") as f:
                cred_info = json.load(f)

        # 必要な全スコープを設定
        creds = service_account.Credentials.from_service_account_info(
            cred_info,
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/gmail.modify',
                'https://www.googleapis.com/auth/drive', # Drive full scope to download media
            ]
        )
        
        # gspread client (シート操作用)
        gc = gspread.authorize(creds)

        # googleapiclient clients (API操作用)
        sheets_service = build('sheets', 'v4', credentials=creds)
        drive_service = build('drive', 'v3', credentials=creds)
        gmail_service = build('gmail', 'v1', credentials=creds) # Step 2, 3, 5で使用
        
        return gc, sheets_service, drive_service, gmail_service, creds
    
    except Exception as e:
        st.error(f"❌ Google APIサービスの初期化に失敗しました: {e}")
        st.info("認証情報ファイル 'service_account.json' が存在するか、Streamlit Secretsが正しく設定されているか確認してください。")
        st.stop()

# --- ユーティリティ関数 ---

def ensure_row_length(row, min_len):
    """行の長さを確認し、足りない場合は空文字列で埋める"""
    if len(row) < min_len:
         row.extend([''] * (min_len - len(row)))
    return row

def update_sheet_status(sheets_service, row_index, col_index, status):
    """スプレッドシートの特定の行/列にステータスを書き込む。"""
    col_letter = chr(65 + col_index) # 例: J列は65+9=J
    range_name = f'{SHEET_NAME_LOG}!{col_letter}{row_index}'
    value_input_option = 'USER_ENTERED'
    value = [[status]]
    body = {'values': value}
    
    try:
        sheets_service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID_MAIN, range=range_name,
            valueInputOption=value_input_option, body=body).execute()
    except HttpError as error:
        st.error(f"-> [Sheets] 書き込みエラーが発生しました: {error}")

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

# --- Step 2: 下書き作成機能のコアロジック (再掲) ---

def create_raw_draft_message(subject, body):
    """EmailMessageを構築し、Base64URLエンコードする (宛先は空欄)"""
    message = EmailMessage()
    message['To'] = "" 
    safe_subject = subject.replace('\r', '').replace('\n', '').strip() 
    message['Subject'] = safe_subject 
    message.set_content(body) 
    
    encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
    return encoded_message

def execute_draft_creation(sheets_service, gmail_service, creds, target_account_key, status_area):
    """Step 2: 指定されたアカウントのログに基づき、下書きを作成し、シートを更新する"""
    
    target_email = ACCOUNT_MAPPING.get(target_account_key)
    if not target_email:
        status_area.error(f"エラー: 不明なターゲットアカウントキー '{target_account_key}'")
        return

    try:
        status_area.info(f"--- {target_account_key} ({target_email}) の下書き作成を開始します ---")

        # 1. シートからデータを取得
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID_MAIN, 
            range=DATA_RANGE_LOG
        ).execute()
        values = result.get('values', [])
        if not values or len(values) <= 1:
            status_area.warning("スプレッドシートにデータがありません。終了します。")
            return

        header = values[0]
        data_rows = values[1:]
        total_records = len(data_rows)
        
        success_count = 0
        
        progress_bar = status_area.progress(0)
        
        # 2. ログデータの処理（1行ごと）
        for index, row in enumerate(data_rows):
            # スプレッドシートの行番号 (A2が2行目なので +2)
            sheet_row_number = index + 2 
            
            # K列までアクセスできるように行の長さを調整
            row = ensure_row_length(row, COL_INDEX_RECIPIENT_STATUS + 1)
            
            # 2.1. I列（下書き処理済）チェック
            processed_status = row[COL_INDEX_DRAFT_STATUS].strip().lower()
            if processed_status == "登録済" or processed_status == "gmailエラー":
                 progress_bar.progress((index + 1) / total_records)
                 continue
            
            # 2.2. H列 (担当アカウント) チェック
            responsible_account = row[COL_INDEX_HANDLER].strip().upper()
            if responsible_account != target_account_key:
                 progress_bar.progress((index + 1) / total_records)
                 continue
            
            # 2.3. 必須データ抽出と件名生成
            try:
                location = row[COL_INDEX_LOCATION].strip() 
                store_name = row[COL_INDEX_STORE].strip() 
                media_name = row[COL_INDEX_MEDIA].strip() 
                post_time = row[COL_INDEX_TIME].strip() 
                name = row[COL_INDEX_NAME].strip() 
                subject_title_safe = row[COL_INDEX_TITLE].strip()
                original_body_safe = row[COL_INDEX_BODY] 
                
                if not (location and store_name and media_name and post_time and name and subject_title_safe and original_body_safe):
                    progress_bar.progress((index + 1) / total_records)
                    continue

                raw_time_str = str(post_time).replace(':', '')
                formatted_time = raw_time_str.zfill(4)
                name_cleaned = re.sub(r'[（\(][^）\)]+[）\)]', '', name).strip()
                
                # --- 件名に識別子（地域名 店名 媒体 氏名）を付与 ---
                original_subject = f"{formatted_time} {subject_title_safe}"
                identifier = f"#{location} {store_name} {media_name} {name_cleaned}"
                final_subject = f"{original_subject}{identifier}"

                raw_message = create_raw_draft_message(final_subject, original_body_safe)

            except Exception as e:
                update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_DRAFT_STATUS, "データエラー")
                status_area.warning(f"⚠️ データ処理エラー ({sheet_row_number}行目): {e}")
                progress_bar.progress((index + 1) / total_records)
                continue
            
            # 3. Gmail 下書き作成
            try:
                message = {'message': {'raw': raw_message}}
                gmail_service.users().drafts().create(userId='me', body=message).execute()
                
                update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_DRAFT_STATUS, "登録済")
                success_count += 1
                
            except HttpError as e:
                update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_DRAFT_STATUS, "Gmailエラー")
                status_area.error(f"❌ Gmailエラー ({sheet_row_number}行目): {e.content.decode('utf-8') if e.content else str(e)}")
            except Exception as e:
                update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_DRAFT_STATUS, "予期せぬエラー")
                status_area.error(f"❌ 予期せぬエラー ({sheet_row_number}行目): {e}")

            progress_bar.progress((index + 1) / total_records)
            
        status_area.success(f"🎉 Step 2: 下書き作成が完了しました。成功件数: {success_count} 件。")

    except Exception as e:
        status_area.exception(f"致命的なエラーが発生しました: {e}")
        
    progress_bar.empty()
    st.session_state.last_run_2 = f"Step 2: {target_account_key} - {time.strftime('%H:%M:%S')}"

# --- Step 3: 画像添付機能のコアロジック ---

def find_matching_image_in_drive(drive_service, row, full_subject, status_area, row_index):
    """Google Drive内で条件に合う画像を、サブフォルダ階層(場所->店名)を辿って検索し、最も近い時刻の画像IDを返す。"""
    
    draft_time = extract_time_from_draft(full_subject)
    if not draft_time:
        return None, "件名から時刻(HHMM)を抽出できませんでした。"

    # 1. フォルダ階層の特定: A列(場所) -> B列(店名)
    location_name = row[COL_INDEX_LOCATION].strip() # A列
    shop_name = row[COL_INDEX_STORE].strip() # B列 (フォルダ検索にはそのまま使う)
    
    if not location_name or not shop_name:
        return None, "場所(A列)または店名(B列)が空です。"

    current_parent_id = DRIVE_FOLDER_ID # '写メ日記画像用' フォルダID
    folder_names_to_find = [location_name, shop_name]
    
    try:
        # A列(場所) -> B列(店名) のフォルダを順番に探す
        for folder_name in folder_names_to_find:
            # デリじゃのスペース揺らぎ対応を簡略化して検索（フォルダ名に媒体名は含まない前提）
            search_candidates = [folder_name]
            if folder_name.startswith("デリじゃ "):
                search_candidates.append(folder_name.replace("デリじゃ ", "デリじゃ　", 1))

            found_folder = None
            for candidate in search_candidates:
                query = (
                    f"'{current_parent_id}' in parents and "
                    f"mimeType = 'application/vnd.google-apps.folder' and "
                    f"name = '{candidate}' and trashed = false"
                )
                results = drive_service.files().list(q=query, fields="files(id)", pageSize=1).execute()
                if results.get('files'):
                    found_folder = results['files'][0]
                    break
            
            if not found_folder:
                return None, f"フォルダ階層が見つかりません: {folder_name}"
            current_parent_id = found_folder['id']

        # 2. 最終フォルダ内でファイル名のキーワードを含む画像を検索 (E列:氏名)
        person_name = row[COL_INDEX_NAME].strip() # E列
        person_name_cleaned = re.sub(r'[（\(][^）\)]+[）\)]', '', person_name).strip()
        
        file_query = (
            f"'{current_parent_id}' in parents and "
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
            file_time_match = re.search(r'(\d{4})', item['name'])
            if file_time_match:
                file_time_str = file_time_match.group(1)
                diff = calculate_time_diff(draft_time, file_time_str)
                
                if diff <= min_diff:
                    # 差分が同じ場合は、ファイル名がより厳密に一致するもの（ここでは差分が min_diff 以下のもの）を維持
                    min_diff = diff
                    best_match = item

        if best_match:
            status_area.info(f"-> [Drive] 最適な画像: {best_match['name']} (差分: {min_diff:.1f}分)")
            return best_match['id'], None
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
    
    # 3. Non-Multipart エラーの回避とメッセージの準備
    msg_to_update = original_msg
    
    if not original_msg.is_multipart():
        # Non-Multipart の場合、新しい Multipart メッセージを作成し、元のメッセージをラップ
        new_multipart_msg = MIMEMultipart()
        for header, value in original_msg.items():
             new_multipart_msg[header] = value
             
        original_payload = original_msg.get_payload()
        original_mimetype = original_msg.get_content_type()
        original_charset = original_msg.get_content_charset() or 'utf-8'
        transfer_encoding = original_msg.get('Content-Transfer-Encoding', '').lower()
        
        decoded_payload = original_payload
        if isinstance(original_payload, str) and transfer_encoding == 'base64':
             try:
                 decoded_bytes = base64.b64decode(original_payload)
                 decoded_payload = decoded_bytes.decode(original_charset, errors='replace')
             except:
                 pass # デコード失敗時は元の文字列を維持
        
        if isinstance(decoded_payload, str):
            subtype = original_mimetype.split('/')[-1]
            wrapped_part = MIMEText(decoded_payload, subtype, original_charset)
        else:
            wrapped_part = decoded_payload
            
        new_multipart_msg.attach(wrapped_part)
        msg_to_update = new_multipart_msg
        
    # 4. 新しい添付ファイル（画像パート）を作成し、メッセージに追加
    image = MIMEImage(image_data, name=file_name)
    msg_to_update.attach(image)
    
    # 5. 下書きを更新
    raw_message_updated = msg_to_update.as_bytes(policy=default) 
    raw_message_encoded = base64.urlsafe_b64encode(raw_message_updated).decode()
    raw_message_body = {'message': {'raw': raw_message_encoded}}
    
    gmail_service.users().drafts().update(userId='me', id=draft_id, body=raw_message_body).execute()
    return True, file_name

def execute_image_uploader(sheets_service, drive_service, gmail_service, target_account_key, status_area):
    """Step 3: 画像添付処理を実行する"""
    
    target_email = ACCOUNT_MAPPING.get(target_account_key)
    if not target_email:
        status_area.error(f"エラー: 不明なターゲットアカウントキー '{target_account_key}'")
        return

    try:
        status_area.info(f"--- {target_account_key} の画像添付処理を開始します ---")

        # 1. シートからデータを取得
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID_MAIN, 
            range=DATA_RANGE_LOG
        ).execute()
        values = result.get('values', [])
        if not values or len(values) <= 1:
            status_area.warning("スプレッドシートにデータがありません。終了します。")
            return

        data_rows = values[1:]
        total_records = len(data_rows)
        success_count = 0
        
        progress_bar = status_area.progress(0)
        
        # 2. ログデータの処理（1行ごと）
        for index, row in enumerate(data_rows):
            sheet_row_number = index + 2 
            row = ensure_row_length(row, COL_INDEX_RECIPIENT_STATUS + 1)
            
            # 2.1. J列（画像処理済）チェック
            image_status = row[COL_INDEX_IMAGE_STATUS].strip().lower()
            if image_status == "登録済" or image_status == "失敗":
                 progress_bar.progress((index + 1) / total_records)
                 continue
            
            # 2.2. H列 (担当アカウント) チェック
            responsible_account = row[COL_INDEX_HANDLER].strip().upper()
            if responsible_account != target_account_key:
                 progress_bar.progress((index + 1) / total_records)
                 continue

            # 2.3. I列（下書き処理済）チェック
            draft_status = row[COL_INDEX_DRAFT_STATUS].strip().lower()
            if draft_status != "登録済":
                 progress_bar.progress((index + 1) / total_records)
                 continue
                 
            # 2.4. 必須データ抽出と件名生成
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
                
                # --- 件名に識別子（地域名 店名 媒体 氏名）を付与 (Step 2と同じロジック) ---
                original_subject = f"{formatted_time} {subject_title_safe}"
                identifier = f"#{location} {store_name} {media_name} {name_cleaned}"
                full_subject = f"{original_subject}{identifier}"

            except Exception:
                progress_bar.progress((index + 1) / total_records)
                continue
            
            # 3. Google Driveで画像を検索
            file_id, reason = find_matching_image_in_drive(drive_service, row, full_subject, status_area, sheet_row_number)
            
            if not file_id:
                update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_IMAGE_STATUS, f"失敗:{reason[:20]}")
                progress_bar.progress((index + 1) / total_records)
                continue

            # 4. Gmail で下書きを検索
            query = f'in:draft subject:"{full_subject}"'
            response = gmail_service.users().drafts().list(userId='me', q=query).execute()
            drafts = response.get('drafts', [])
            
            if len(drafts) != 1:
                update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_IMAGE_STATUS, "失敗:下書き重複/未検出")
                progress_bar.progress((index + 1) / total_records)
                continue
            
            draft_id = drafts[0]['id']

            # 5. 下書きを更新
            try:
                is_success, result_detail = update_draft_with_attachment(gmail_service, drive_service, draft_id, file_id, file_id) # ファイル名は暫定でfile_id
                
                if is_success:
                    update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_IMAGE_STATUS, "登録済")
                    success_count += 1
                else:
                    update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_IMAGE_STATUS, f"失敗:更新APIエラー")
            except Exception as e:
                update_sheet_status(sheets_service, sheet_row_number, COL_INDEX_IMAGE_STATUS, f"失敗:予期せぬエラー")
                status_area.error(f"❌ 画像添付エラー ({sheet_row_number}行目): {e}")

            progress_bar.progress((index + 1) / total_records)
            
        status_area.success(f"🎉 Step 3: 画像添付が完了しました。成功件数: {success_count} 件。")

    except Exception as e:
        status_area.exception(f"致命的なエラーが発生しました: {e}")
        
    progress_bar.empty()
    st.session_state.last_run_3 = f"Step 3: {target_account_key} - {time.strftime('%H:%M:%S')}"


# --- Step 5: 履歴移動機能のコアロジック ---

def execute_draft_mover(gc, sheets_service, status_area):
    """Step 5: K列が「登録済」の行を履歴シートに移動し、元のシートから削除する"""
    
    status_area.info(f"--- Step 5: 履歴への移動処理を開始します ---")

    try:
        # 1. データの読み込み (ヘッダーも含むA:K列)
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID_MAIN, 
            range=DATA_RANGE_LOG
        ).execute()
        all_values = result.get('values', [])
        
        if not all_values or len(all_values) <= 1:
            status_area.warning("日記登録用シートに処理対象のデータがありません。")
            return

        header = all_values[0]
        data_rows = all_values[1:]
        
        # 2. 移動対象と削除対象の行番号を特定
        rows_to_move = []
        rows_to_delete_index = [] # 削除する行のインデックス (0から開始, ヘッダーを含まない)
        
        for index, row in enumerate(data_rows):
            row = ensure_row_length(row, COL_INDEX_RECIPIENT_STATUS + 1)
            
            # K列 (宛先処理済) が「登録済」の場合
            if row[COL_INDEX_RECIPIENT_STATUS].strip() == "登録済":
                rows_to_move.append(row)
                rows_to_delete_index.append(index)
                
        if not rows_to_move:
            status_area.warning("K列が '登録済' の処理済み行が見つかりませんでした。")
            return

        # 3. 履歴シートへの書き込み
        sh = gc.open_by_key(SPREADSHEET_ID_MAIN)
        ws_history = sh.worksheet(SHEET_NAME_HISTORY)
        
        # ヘッダーを最初に追加（初回実行時のみ）
        if ws_history.row_count < 1 or not ws_history.row_values(1):
             ws_history.insert_row(header, 1)

        ws_history.append_rows(rows_to_move, value_input_option='USER_ENTERED')
        status_area.success(f"✅ {len(rows_to_move)} 件のデータを '{SHEET_NAME_HISTORY}' に書き込みました。")

        # 4. 元のシートから行を削除 (重要な部分: 下から上へ削除)
        # 削除インデックスを逆順にソート (シート行番号はインデックス+2)
        rows_to_delete_index.sort(reverse=True)
        
        # gspread の delete_rows は行番号 (1から開始) を指定
        delete_row_numbers = [idx + 2 for idx in rows_to_delete_index]
        
        for row_num in delete_row_numbers:
             try:
                 ws_log = sh.worksheet(SHEET_NAME_LOG)
                 ws_log.delete_rows(row_num)
             except Exception as e:
                 status_area.error(f"❌ {SHEET_NAME_LOG} から {row_num} 行目の削除に失敗しました: {e}")

        status_area.success(f"🎉 Step 5: 履歴への移動が完了しました。{len(rows_to_move)} 行を削除しました。")
        
    except Exception as e:
        status_area.exception(f"致命的なエラーが発生しました: {e}")
        
    st.session_state.last_run_5 = f"Step 5: {time.strftime('%H:%M:%S')}"


# --- Streamlit UI ---

def display_app():
    st.set_page_config(page_title="日記投稿準備ツール", layout="wide")
    st.title("📧 日記投稿準備ツール (Streamlit App)")
    
    gc, sheets_service, drive_service, gmail_service, creds = get_google_services() # サービスの初期化
    
    st.header("1. アカウント設定")
    
    # アカウント選択
    account_keys = list(ACCOUNT_MAPPING.keys())
    col1, col2 = st.columns([1, 4])
    selected_account = col1.selectbox(
        "担当アカウントを選択してください:",
        options=account_keys,
        index=0
    )
    st.info(f"選択されたアカウント: **{selected_account}** ({ACCOUNT_MAPPING[selected_account]})")
    
    # タブの作成
    tab2, tab3, tab4, tab5, tab_copier = st.tabs([
        "Step 2: 下書き作成", 
        "Step 3: 画像添付", 
        "Step 4: 宛先登録 (ローカル実行)", 
        "Step 5: 履歴移動",
        "💡 全文コピペ用シート表示"
    ])
    
    # --- Tab 2: 下書き作成 ---
    with tab2:
        st.header("Step 2: 下書き作成 (Gmail Draft Creation)")
        st.markdown("""
        **機能**: スプレッドシート（`日記登録用`）から、担当が **'A/B/SUB'** かつ **I列が空欄/エラー** の行を読み込み、Gmailに下書きを作成します。
        - **件名 (修正済)**: `[時刻] [タイトル] #[地域名] [店名] [媒体名] [氏名]` の形式で作成されます。
        - **更新列**: 成功した場合、**I列**に **'登録済'** が書き込まれます。
        """)
        
        if st.button(f"🚀 Step 2 実行: {selected_account} の下書きを作成"):
            status_area = st.empty()
            execute_draft_creation(sheets_service, gmail_service, creds, selected_account, status_area)

        if 'last_run_2' in st.session_state:
            st.markdown(f"---")
            st.success(f"前回実行: {st.session_state.last_run_2}")
            
    # --- Tab 3: 画像添付 ---
    with tab3:
        st.header("Step 3: 画像添付 (Drive & Gmail)")
        st.markdown("""
        **機能**: **I列が '登録済'** の行を対象に、Google Driveから対応する画像を検索し、Gmailの下書きに添付します。
        - **検索ロジック**: `[地域名] / [店名] `フォルダ階層を辿り、`[氏名]`を含み、**件名時刻と $\pm 15$ 分以内** の画像ファイルを特定します。
        - **更新列**: 成功した場合、**J列**に **'登録済'** が書き込まれます。
        """)
        
        if st.button(f"📸 Step 3 実行: {selected_account} の下書きに画像を添付"):
            status_area = st.empty()
            execute_image_uploader(sheets_service, drive_service, gmail_service, selected_account, status_area)

        if 'last_run_3' in st.session_state:
            st.markdown(f"---")
            st.success(f"前回実行: {st.session_state.last_run_3}")
        
    # --- Tab 4: 宛先登録 (ローカル実行) ---
    with tab4:
        st.header("Step 4: 宛先登録 (ローカル実行)")
        st.markdown("""
        **機能**: **連絡先**を検索し、Gmailの下書きに宛先と最終件名を設定します。
        
        **【重要】People API (個人連絡先) へのアクセスは、Streamlit上ではサービスアカウントで実行できません。**
        
        このステップは、**`draft_updater.py`** をローカルPCで実行する必要があります。
        """)
        st.code(f"python draft_updater.py {selected_account}")
        st.warning("❌ アプリ上では実行できません。ローカル環境で実行してください。")

    # --- Tab 5: 履歴移動 ---
    with tab5:
        st.header("Step 5: 履歴移動 (Sheets)")
        st.markdown("""
        **機能**: **K列が '登録済'** の行を **`日記登録用`** シートから **`履歴`** シートへ移動させます。
        - **注意**: 履歴移動は、全アカウントの処理が完了してから実行してください。
        """)
        
        if st.button(f"📂 Step 5 実行: 処理済み行を履歴へ移動"):
            status_area = st.empty()
            execute_draft_mover(gc, sheets_service, status_area)

        if 'last_run_5' in st.session_state:
            st.markdown(f"---")
            st.success(f"前回実行: {st.session_state.last_run_5}")
        
    # --- Tab コピペ用シート表示 ---
    with tab_copier:
        st.header("💡 全文コピペ用シート")
        st.markdown(f"**目的**: 投稿可能な日記の全文をコピペしやすくするための表示です。")
        
        # コピペ用シートのデータ取得と表示
        try:
            sh = gc.open_by_key(SPREADSHEET_ID_COPIER)
            ws = sh.worksheet(SHEET_NAME_LOG)
            data = ws.get_all_values()
            
            if data:
                df = pd.DataFrame(data[1:], columns=data[0])
                display_cols = ['地域名', '店名', '媒体', '時刻', '氏名', 'タイトル', '本文']
                display_df = df[[c for c in display_cols if c in df.columns]]
                
                st.dataframe(display_df, height=500)
                st.success(f"✅ 外部シート: '{SHEET_NAME_LOG}' のデータを表示中。")
            else:
                st.warning("コピペ用シートにデータがありません。")
        except Exception as e:
            st.error(f"コピペ用シートの読み込みに失敗しました。IDまたはシート名を確認してください: {e}")


if __name__ == '__main__':
    display_app()
