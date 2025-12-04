import streamlit as st
import pandas as pd
import gspread
from io import BytesIO
import time 
from datetime import datetime

# --- 1. 定数と初期設定 ---
try:
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


def drive_upload(uploaded_file, file_name, folder_id=DRIVE_FOLDER_ID):
    """
    Google Driveへファイルをアップロードし、ファイルIDを返す関数。
    ※ この関数は Drive API の処理をシミュレートしています。
    """
    if uploaded_file is None:
        return None

    # 実際の Drive API 処理はここに実装されます
    time.sleep(0.1) 
    
    # アップロード後のファイル ID をシミュレート
    simulated_file_id = f"DRIVE_ID_{file_name}_{int(time.time())}"
    
    st.caption(f"  [ドライブ格納] -> **ファイル名: {file_name}** (ID: {simulated_file_id})")
    
    return simulated_file_id


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
    page_title="日記投稿管理アプリ",
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
    color: #4CAF50; /* 少し落ち着いた緑 */
    text-shadow: 2px 2px 4px #aaa;
    border-bottom: 3px solid #E0F7FA;
    padding-bottom: 5px;
    margin-bottom: 15px;
}
/* サブヘッダーの強調 */
h3 {
    color: #00897B; /* 濃い目のティール */
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


st.title("✨ 日記投稿管理 Web アプリ - Daily Posting Manager")

# --- セッションステートの初期化 ---
if 'diary_entries' not in st.session_state:
    initial_entry = {header: "" for header in INPUT_HEADERS if header not in ["媒体", "担当アカウント"]}
    initial_entry['画像ファイル'] = None 
    
    st.session_state.diary_entries = [initial_entry.copy() for _ in range(40)]

if 'global_media' not in st.session_state:
    st.session_state.global_media = MEDIA_OPTIONS[0]
if 'global_account' not in st.session_state:
    st.session_state.global_account = ACCOUNT_OPTIONS[0]


tab1, tab2, tab3 = st.tabs(["📝 ① データ登録・画像アップロード", "🚀 ② 下書き作成・実行", "📂 ③ 履歴の検索・管理"])

# =========================================================
# --- Tab 1: データ登録・画像アップロード ---
# =========================================================

with tab1:
    st.header("1️⃣ データ準備・入力")
    
    # --- A. テンプレート参照 ---
    st.subheader("📖 日記使用可能文（コピペ用）")
    
    st.info("💡 **コピペ補助**：この表の項目を下の入力フォームにコピーしてください。ウィンドウを分けると便利です。")

    try:
        # GSpreadからデータを読み込み
        ws_templates = SPRS.worksheet(USABLE_DIARY_SHEET)
        df_templates = pd.DataFrame(ws_templates.get_all_records())
        
        # フィルターUI
        col_type, col_kind = st.columns([1, 1, 3])
        with col_type:
            selected_type = st.selectbox("日記種類", ["すべて", "出勤", "退勤", "その他"], key='t1_type')
        with col_kind:
            selected_kind = st.selectbox("タイプ種類", ["すべて", "若", "妻", "おば"], key='t1_kind')
        
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
        
    except Exception as e:
        # 実際の接続に失敗した場合のエラーメッセージ
        st.warning(f"テンプレートデータの読み込みに失敗しました: {e}")

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
            
            # --- テキスト入力（コピペしやすいように短く） ---
            entry['エリア'] = cols[0].text_input("", value=entry['エリア'], key=f"エリア_{i}", placeholder="A-Z", label_visibility="collapsed")
            entry['店名'] = cols[1].text_input("", value=entry['店名'], key=f"店名_{i}", placeholder="新宿", label_visibility="collapsed")
            entry['投稿時間'] = cols[2].text_input("", value=entry['投稿時間'], key=f"時間_{i}", placeholder="1530", label_visibility="collapsed")
            
            entry['タイトル'] = cols[3].text_area("", value=entry['タイトル'], key=f"タイトル_{i}", height=50, label_visibility="collapsed")
            entry['本文'] = cols[4].text_area("", value=entry['本文'], key=f"本文_{i}", height=100, label_visibility="collapsed") # 本文の枠を大きく

            entry['女の子の名前'] = cols[5].text_input("", value=entry['女の子の名前'], key=f"名_{i}", placeholder="さくら", label_visibility="collapsed")
            
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

            st.markdown("---") # 行間の区切りを強調
            
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
                if entry['画像ファイル']:
                    hhmm = entry['投稿時間'].strip() 
                    girl_name = entry['女の子の名前'].strip()
                    
                    if not hhmm or not girl_name:
                         st.error(f"❌ No. {i+1} のファイル名エラー
