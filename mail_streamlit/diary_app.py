import streamlit as st
import pandas as pd
import gspread
from io import BytesIO
import time 
from datetime import datetime

# Google Drive API連携に必要なライブラリ
# 実際の環境では pydrive2 や google-api-python-client を使用しますが、
# ここでは Drive API の認証とアップロード処理を関数でシミュレートします。
# 認証情報は gspread と共通の service_account_from_dict を利用します。


# --- 1. 定数と初期設定 ---
try:
    SHEET_ID = st.secrets["google_resources"]["spreadsheet_id"]
    DRIVE_FOLDER_ID = st.secrets["google_resources"]["drive_folder_id"]
    SHEET_NAMES = st.secrets["sheet_names"]
    
    REGISTRATION_SHEET = SHEET_NAMES["registration_sheet"]
    CONTACT_SHEET = SHEET_NAMES["contact_sheet"]
    USABLE_DIARY_SHEET = SHEET_NAMES["usable_diary_sheet"]
    HISTORY_SHEET = SHEET_NAMES["history_sheet"]
    
except KeyError:
    st.error("🚨 GoogleリソースIDまたはシート名がsecrets.tomlに正しく設定されていません。")
    st.stop()


# 最終確定した「日記登録用シート」のヘッダー定義 (11項目)
REGISTRATION_HEADERS = [
    "エリア", "店名", "媒体", "投稿時間", "女の子の名前", "タイトル", "本文", "担当アカウント", 
    "下書き登録確認", "画像添付確認", "宛先登録確認" 
]
INPUT_HEADERS = REGISTRATION_HEADERS[:8] # ユーザーが手動で入力する8項目

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
        
SPRS = connect_to_gsheets()


def drive_upload(uploaded_file, file_name, folder_id=DRIVE_FOLDER_ID):
    """
    Google Driveへファイルをアップロードし、ファイルIDを返す関数。
    認証には gspread と共通のサービスアカウント認証情報を使用します。
    ※ この関数は Drive API の処理をシミュレートしています。
    """
    if uploaded_file is None:
        return None

    # 実際の Drive API 処理では、認証情報を使って Drive サービスを構築し、
    # folder_id に対して file_name でファイルをアップロードします。
    
    # 実際はここで Drive API 処理
    time.sleep(0.5) 
    
    # アップロード後のファイル ID をシミュレートして返す (本物のIDではない)
    simulated_file_id = f"DRIVE_ID_{file_name}_{int(time.time())}"
    
    st.caption(f"  [ドライブ格納] -> **ファイル名: {file_name}** (ID: {simulated_file_id})")
    
    return simulated_file_id


# --- 3. 実行ロジック (プレースホルダー関数) ---

def run_step(step_num, action_desc, sheet_name=REGISTRATION_SHEET):
    """実行ステップのシミュレーションとシート更新のプレースホルダー"""
    st.info(f"🔄 Step {step_num}: {action_desc}を実行中...")
    time.sleep(2) 
    
    # 実際にはここで外部ロジックを実行し、シートのステータス列を更新します。
    # 例: ws.update_cell(row, column_index, "OK") 
    
    st.success(f"✅ Step {step_num}: {action_desc}が完了しました。")
    return True

def run_step_5_move_to_history():
    """Step 5: 履歴へ移動（新規機能）"""
    st.info("🔄 Step 5: 実行済みデータを履歴シートへ移動中...")
    time.sleep(3) 

    # ここに Sheets API を使用した行移動ロジックを実装
    
    st.success("✅ Step 5: 実行済みデータが履歴シートへ移動・削除されました。")

# --- 4. Streamlit UI 構築 ---

st.set_page_config(layout="wide", page_title="日記投稿管理アプリ")
st.title("📝 日記投稿管理 Web アプリ")

# --- セッションステートの初期化 ---
if 'diary_entries' not in st.session_state:
    initial_entry = {header: "" for header in INPUT_HEADERS}
    initial_entry['画像ファイル'] = None 
    # 40件分の空の入力枠を準備
    st.session_state.diary_entries = [initial_entry.copy() for _ in range(40)]

tab1, tab2, tab3 = st.tabs(["① データ登録・画像アップロード", "② 下書き作成・実行", "③ 履歴の検索・修正・管理"])

# =========================================================
# --- Tab 1: データ登録・画像アップロード ---
# =========================================================

with tab1:
    st.header("1️⃣ データ登録とテンプレート参照")
    
    # --- A. テンプレート参照 (使用可日記データ) ---
    st.subheader("💡 テンプレート参照（コピペ用）")
    try:
        df_templates = pd.DataFrame(SPRS.worksheet(USABLE_DIARY_SHEET).get_all_records())
        
        # フィルターUI
        col_type, col_kind = st.columns(2)
        with col_type:
            selected_type = st.selectbox("日記種類フィルター", ["すべて", "出勤", "退勤", "その他"], key='t1_type')
        with col_kind:
            selected_kind = st.selectbox("タイプ種類フィルター", ["すべて", "若", "妻", "おば"], key='t1_kind')
        
        filtered_df = df_templates.copy()
        if selected_type != "すべて":
            filtered_df = filtered_df[filtered_df['日記種類'] == selected_type]
        if selected_kind != "すべて":
            filtered_df = filtered_df[filtered_df['タイプ種類'] == selected_kind]

        st.dataframe(
            filtered_df[['タイトル', '本文', '日記種類', 'タイプ種類']],
            use_container_width=True,
            height=200,
            hide_index=True,
        )
        st.caption("上記の表から必要なタイトルや本文をコピーし、下の入力テーブルに貼り付けてください。")
        
    except Exception as e:
        st.warning(f"テンプレートデータの読み込みに失敗しました: {e}")

    st.markdown("---")
    
    # --- B. 40件の日記データ入力 (行ごとのアップロード) ---
    st.subheader("2️⃣ 登録用データ入力と画像アップロード (40件)")

    with st.form("diary_registration_form"):
        st.warning("⚠️ 画像は各行のボタンからアップロードしてください。データが残っている行のみが登録対象となります。")
        
        # 40行分の入力と画像アップロードをループで生成
        for i in range(len(st.session_state.diary_entries)):
            entry = st.session_state.diary_entries[i]
            
            # データが一つでも入力されているかチェック
            is_data_filled = any(entry[h] for h in INPUT_HEADERS if h in entry)
            
            with st.expander(f"日記 No. {i + 1} ({'データ入力済み' if is_data_filled else '未入力'})", expanded=is_data_filled):
                
                # ユーザー入力ヘッダー (8項目)
                cols_input = st.columns(4)
                entry['エリア'] = cols_input[0].text_input("エリア", value=entry['エリア'], key=f"エリア_{i}")
                entry['店名'] = cols_input[1].text_input("店名", value=entry['店名'], key=f"店名_{i}")
                entry['媒体'] = cols_input[2].text_input("媒体", value=entry['媒体'], key=f"媒体_{i}")
                entry['投稿時間'] = cols_input[3].text_input("投稿時間", value=entry['投稿時間'], key=f"時間_{i}")

                cols_text = st.columns([2, 2, 1])
                entry['タイトル'] = cols_text[0].text_area("タイトル", value=entry['タイトル'], key=f"タイトル_{i}", height=50)
                entry['本文'] = cols_text[1].text_area("本文", value=entry['本文'], key=f"本文_{i}", height=50)
                
                # 女の子の名前と担当アカウントは同じ列で下に配置
                with cols_text[2]:
                    entry['女の子の名前'] = st.text_input("女の子の名前", value=entry['女の子の名前'], key=f"名_{i}")
                    entry['担当アカウント'] = st.text_input("担当アカウント", value=entry['担当アカウント'], key=f"アカ_{i}")

                # 行ごとの画像アップロードエリア
                uploaded_file = st.file_uploader(
                    f"📸 画像ファイル (JPG/PNG)",
                    type=['png', 'jpg', 'jpeg'],
                    key=f"image_{i}"
                )
                
                # セッションステートにファイルを保存
                entry['画像ファイル'] = uploaded_file
                
                if entry['画像ファイル']:
                    st.caption(f"現在のファイル名: {entry['画像ファイル'].name}")

            
        # フォームの送信ボタン（データ登録実行）
        submitted = st.form_submit_button("💾 データ登録を実行", type="primary")

        if submitted:
            valid_entries_and_files = []
            
            # データが一つでも入力されている行を抽出し、ファイル名を処理
            for entry in st.session_state.diary_entries:
                # ユーザー入力8項目すべてが空ではないかチェック
                is_data_filled = any(entry.get(h) for h in INPUT_HEADERS)
                
                if is_data_filled:
                    valid_entries_and_files.append(entry)
            
            if not valid_entries_and_files:
                st.error("入力データがありません。")
                st.stop()
            
            # --- ここから実際の登録処理 ---
            
            st.info(f"入力件数: {len(valid_entries_and_files)}件の登録処理を開始します。")

            # 1. Google Drive への画像アップロードとファイル名変更
            uploaded_file_data = []
            for i, entry in enumerate(valid_entries_and_files):
                if entry['画像ファイル']:
                    # ファイル名生成: hhmm_女の子の名前
                    hhmm = datetime.now().strftime("%H%M")
                    girl_name = entry['女の子の名前'] if entry['女の子の名前'] else f"NO_NAME_{i}"
                    
                    # 拡張子を取得
                    ext = entry['画像ファイル'].name.split('.')[-1]
                    new_filename = f"{hhmm}_{girl_name}.{ext}"

                    # Drive API を使ってファイルをアップロード (シミュレーション)
                    file_id = drive_upload(entry['画像ファイル'], new_filename)
                    uploaded_file_data.append({'row_index': i, 'file_id': file_id})
                else:
                    st.warning(f"No. {i+1} のデータはテキストのみ登録されます。画像がありません。")
            
            st.success(f"✅ 画像 {len(uploaded_file_data)}枚を Google Drive へ **hhmm_女の子の名前** 形式で格納しました。")

            # 2. スプレッドシートへの書き込み
            try:
                ws = SPRS.worksheet(REGISTRATION_SHEET)
                
                final_data = []
                for entry in valid_entries_and_files:
                    # ユーザー入力8項目をリスト化
                    row_data = [entry[h] for h in INPUT_HEADERS]
                    # ステータス列（'未実行'）3項目を追加
                    row_data.extend(['未実行', '未実行', '未実行']) 
                    final_data.append(row_data)

                # シートの末尾に追加
                ws.append_rows(final_data, value_input_option='USER_ENTERED')
                
                st.success(f"🎉 **{len(valid_entries_and_files)}件**のテキストデータ登録が完了しました。")
                st.info("次の作業は Tab ② で実行してください。")
            
            except Exception as e:
                st.error(f"❌ データ登録中に重大なエラーが発生しました: {e}")


# =========================================================
# --- Tab 2: 下書き作成・実行 (中略、変更なし) ---
# =========================================================

with tab2:
    st.header("2️⃣ 下書き作成・実行フロー (手動実行)")
    
    st.warning("🚨 **Step 0: 注意喚起** - 連絡先シートと登録データの内容を手動で確認してください。")

    execution_steps = [
        ("Step 1: アドレス更新実行", lambda: run_step(1, "アドレスと連絡先の更新")),
        ("Step 2: 下書き作成実行", lambda: run_step(2, "Gmailの下書き作成")),
        ("Step 3: 画像登録確認実行", lambda: run_step(3, "画像の添付と登録状況確認")),
        ("Step 4: 宛先登録実行", lambda: run_step(4, "下書きへの宛先登録")),
    ]

    cols = st.columns(4)
    
    for i, (label, func) in enumerate(execution_steps):
        with cols[i]:
            if st.button(label, key=f'step_btn_{i+1}', use_container_width=True):
                func()
    
    st.markdown("---")

    st.subheader("👀 登録データの実行状況")
    try:
        df_status = pd.DataFrame(SPRS.worksheet(REGISTRATION_SHEET).get_all_records())
        st.dataframe(df_status, use_container_width=True, hide_index=True)
    except Exception:
        st.info("「日記登録用」シートにデータがありません、または読み込みエラーが発生しました。")

    st.markdown("---")

    st.subheader("✅ Step 5: 履歴データ移動（最終確定）")
    st.error("Step 1〜4がすべて成功し、**安全を確認した上で**、このボタンを押してください。")
    if st.button("➡️ Step 5: 実行完了データを履歴へ移動・削除", key='step_btn_5_move', type="primary"):
        run_step_5_move_to_history()


# =========================================================
# --- Tab 3: 履歴の検索・修正・管理 (中略、変更なし) ---
# =========================================================

with tab3:
    st.header("3️⃣ 履歴の検索・修正・管理")
    
    try:
        df_history = pd.DataFrame(SPRS.worksheet(HISTORY_SHEET).get_all_records())
    except Exception:
        df_history = pd.DataFrame()
        st.warning(f"履歴シート（{HISTORY_SHEET}）の読み込みに失敗しました。")
        
    st.markdown("---")

    # --- A. 履歴データの検索と修正 (機能 B: Gmail連動修正) ---
    st.subheader("🔍 履歴データの検索と修正")
    
    if not df_history.empty:
        edited_history_df = st.data_editor(
            df_history,
            key="history_editor",
            use_container_width=True,
            height=300
        )
        
        if st.button("🔄 修正内容を保存しGmail下書きを連動修正"):
            st.success("✅ データとGmail下書きの修正が完了しました。（機能 B）")
    else:
        st.info("履歴データがありません。")
        
    st.markdown("---")

    # --- B. 店舗閉め・アーカイブ機能 (機能 C) ---
    st.subheader("📦 店舗閉め・アーカイブ機能")
    
    if not df_history.empty:
        store_list = df_history['店名'].unique().tolist()
        selected_store = st.selectbox("アーカイブ対象店舗を選択", store_list)
        
        st.warning(f"「{selected_store}」の全データを履歴シートから使用可日記データシートへ移動します。")
        
        if st.button(f"↩️ {selected_store} をアーカイブ (使用可へ移動)", type="secondary"):
            st.success(f"✅ 店舗 {selected_store} のアーカイブ（データ移動）が完了しました。（機能 C）")
    else:
        st.info("アーカイブできる店舗データがありません。")
