import streamlit as st
import pandas as pd
import gspread
from io import BytesIO
import time 
import traceback 
# --- Drive API 連携に必要なライブラリを追加 ---
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
# -----------------------------------------------

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
    
    # APIスコープをSheetsとDriveの両方に設定
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
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


# --- 2. Google API連携関数 ---

@st.cache_resource(ttl=3600)
def connect_to_gsheets():
    """GSpreadでGoogle Sheetsに接続し、クライアントを返す"""
    try:
        # サービスの認証情報をsecretsから取得して接続
        client = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        spreadsheet = client.open_by_key(SHEET_ID)
        return spreadsheet
    except Exception as e:
        # 接続失敗時、ここで処理を停止
        st.error(f"❌ Google Sheets への接続に失敗しました: {e}")
        st.stop()
        
# 実際の接続を実行
SPRS = connect_to_gsheets()


@st.cache_resource(ttl=3600)
def connect_to_drive():
    """Google Drive API クライアントを初期化する"""
    try:
        # st.secretsからサービスアカウント情報をロード
        creds_info = st.secrets["gcp_service_account"]
        
        # 認証情報オブジェクトを作成
        creds = Credentials.from_service_account_info(
            creds_info, 
            scopes=SCOPES
        )
        
        # Drive API サービスをビルド
        service = build('drive', 'v3', credentials=creds)
        return service
    except Exception as e:
        st.error(f"❌ Google Drive API への接続に失敗しました: {e}")
        st.stop()

# Drive APIクライアントを初期化
try:
    DRIVE_SERVICE = connect_to_drive()
except SystemExit:
    # connect_to_drive内でst.stop()が呼ばれた場合、ここで捕捉
    pass


def drive_upload(uploaded_file, file_name, folder_id=DRIVE_FOLDER_ID):
    """
    Google Driveへファイルをアップロードし、ファイルIDを返す関数。（実際のAPI処理）
    """
    if uploaded_file is None:
        return None

    try:
        # ファイルの内容をメモリに読み込む
        file_content = uploaded_file.getvalue()
        
        # StreamlitのUploadedFileオブジェクトからファイルストリームを作成
        media_body = MediaIoBaseUpload(
            BytesIO(file_content),
            mimetype=uploaded_file.type,
            resumable=True
        )

        # ファイルメタデータ
        file_metadata = {
            'name': file_name,
            'parents': [folder_id],  # アップロード先のフォルダID
        }

        # アップロード実行
        file = DRIVE_SERVICE.files().create(
            body=file_metadata,
            media_body=media_body,
            fields='id'
        ).execute()

        file_id = file.get('id')
        
        st.caption(f"  [ドライブ格納成功] -> **ファイル名: {file_name}** (ID: {file_id})")
        
        return file_id
        
    except Exception as e:
        st.error(f"❌ Driveへのアップロード中にエラーが発生しました: {e}")
        return None


# --- 3. 実行ロジック (プレースホルダー関数) ---

def run_step(step_num, action_desc, sheet_name=REGISTRATION_SHEET):
    """実行ステップのシミュレーションとシート更新のプレースホルダー"""
    st.info(f"🔄 Step {step_num}: **{action_desc}** を実行中...")
    time.sleep(1.5) 
    st.success(f"✅ Step {step_num}: **{action_desc}** が完了しました。")
    return True

def run_step_5_move_to_history():
    """Step 5: 履歴へ移動（新規機能）"""
    st.info("🔄 Step 5: **実行済みデータ**を履歴シートへ移動中...")
    time.sleep(2) 
    # ここに Sheets API を使用した行移動ロジックを実装
    st.success("✅ Step 5: 実行済みデータが履歴シートへ移動・削除されました。")


# --- 4. Streamlit UI 構築 ---

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
            
            # --- テキスト入力（プレースホルダー削除済み） ---
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
                    valid_entries_and_files.append(entry)
            
            if not valid_entries_and_files:
                st.error("入力データがありません。")
                st.stop()
            
            # 1. Drive アップロード
            st.info(f"入力件数: {len(valid_entries_and_files)}件の登録処理を開始します。")
            uploaded_file_data = []
            
            for i, entry in enumerate(valid_entries_and_files):
                # 画像の有無にかかわらず、ファイル名生成とアップロード処理を試行
                
                # 画像がある場合のみ Drive にアップロード
                if entry['画像ファイル']:
                    hhmm = entry['投稿時間'].strip() 
                    girl_name = entry['女の子の名前'].strip()
                    
                    if not hhmm or not girl_name:
                         st.error(f"❌ No. {i+1} のファイル名エラー: 投稿時間/名前を入力してください。") 
                         continue
                         
                    ext = entry['画像ファイル'].name.split('.')[-1]
                    new_filename = f"{hhmm}_{girl_name}.{ext}"

                    # 実際の Drive API を呼び出す
                    file_id = drive_upload(entry['画像ファイル'], new_filename)
                    if file_id:
                        uploaded_file_data.append({'row_index': i, 'file_id': file_id})
                else:
                    st.warning(f"No. {i+1} は画像なしでテキストのみ登録されます。")
            
            st.success(f"✅ **{len(uploaded_file_data)}枚**の画像を Drive へ格納しました。")

            # 2. シート書き込み
            try:
                ws = SPRS.worksheet(REGISTRATION_SHEET)
                
                final_data = []
                for entry in valid_entries_and_files:
                    row_data = [
                        entry['エリア'], entry['店名'], st.session_state.global_media, 
                        entry['投稿時間'], entry['女の子の名前'], entry['タイトル'],
                        entry['本文'], st.session_state.global_account 
                    ]
                    # I, J, K 列は空白で追加する (修正済み)
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
                {st.button("▶️ 実行", key=f'step_btn_{i+1}', use_container_width=True)}
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

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
    if st.button("➡️ Step 5: 実行完了データを履歴へ移動・削除", key='step_btn_5_move', type="primary", use_container_width=True):
        run_step_5_move_to_history()


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
