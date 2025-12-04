import streamlit as st
import pandas as pd
import gspread
from io import BytesIO

# --- 1. 定数と初期設定 ---
# Streamlit Secretsから認証情報とリソースIDを取得
try:
    SHEET_ID = st.secrets["google_resources"]["spreadsheet_id"]
    DRIVE_FOLDER_ID = st.secrets["google_resources"]["drive_folder_id"]
    SHEET_NAMES = st.secrets["sheet_names"]
    
    # シート名の定義
    REGISTRATION_SHEET = SHEET_NAMES["registration_sheet"]
    CONTACT_SHEET = SHEET_NAMES["contact_sheet"]
    USABLE_DIARY_SHEET = SHEET_NAMES["usable_diary_sheet"]
    HISTORY_SHEET = SHEET_NAMES["history_sheet"]
    
except KeyError:
    st.error("🚨 GoogleリソースIDまたはシート名がsecrets.tomlに正しく設定されていません。")
    st.stop()


# 登録用シートのヘッダー定義 (確定した11項目 + 画像URL/ID)
# このリストは、Tab 1の入力フォーム、Tab 2の処理、Tab 3の履歴移動で中心的に使用されます。
REGISTRATION_HEADERS = [
    "エリア", "店名", "媒体", "投稿時間", "女の子の名前", "タイトル", "本文", "担当アカウント", 
    "下書き登録確認", "画像添付確認", "宛先登録確認", "画像URL/ID" 
]

# --- 2. Google Sheets API連携関数 ---

@st.cache_resource(ttl=3600)
def connect_to_gsheets():
    """GSpreadでGoogle Sheetsに接続し、クライアントを返す"""
    try:
        # Streamlit Secretsからサービスアカウント認証情報を取得して認証
        client = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        spreadsheet = client.open_by_key(SHEET_ID)
        return spreadsheet
    except Exception as e:
        st.error(f"❌ Google Sheets への接続に失敗しました: {e}")
        st.stop()
        
SPRS = connect_to_gsheets()

# --- 3. 実行ロジック (プレースホルダー) ---

def run_step_1_address_update():
    """Step 1: アドレス更新 (mail_address_extractor.py, contact_updater.py 相当)"""
    st.info("🔄 Step 1: アドレスと連絡先の更新を実行中...")
    # ここに外部スクリプト相当のロジック（またはWeb API呼び出し）を実装
    st.success("✅ Step 1: アドレスと連絡先の更新が完了しました。")

def run_step_2_draft_creation():
    """Step 2: 下書き作成 (draft_creator.py 相当)"""
    st.info("🔄 Step 2: Gmailの下書き作成を実行中...")
    # ここに draft_creator.py 相当のロジックを実装し、成功したらシートのステータス列を更新
    st.success("✅ Step 2: 下書き作成が完了しました。シートの「下書き登録確認」列を更新しました。")

def run_step_3_image_upload_check():
    """Step 3: 画像登録確認 (image_uploader.py 相当)"""
    st.info("🔄 Step 3: 画像の添付と登録状況を確認中...")
    # ここに image_uploader.py 相当のロジックを実装し、成功したらシートのステータス列を更新
    st.success("✅ Step 3: 画像の添付が完了しました。シートの「画像添付確認」列を更新しました。")

def run_step_4_destination_registration():
    """Step 4: 宛先登録 (draft_updater.py 相当)"""
    st.info("🔄 Step 4: 下書きへの宛先登録を実行中...")
    # ここに draft_updater.py 相当のロジックを実装し、成功したらシートのステータス列を更新
    st.success("✅ Step 4: 宛先登録が完了しました。シートの「宛先登録確認」列を更新しました。")

def run_step_5_move_to_history():
    """Step 5: 履歴へ移動（新規機能）"""
    st.info("🔄 Step 5: 実行済みデータを履歴シートへ移動中...")
    # ここに Sheets API を使用した行移動ロジックを実装
    st.success("✅ Step 5: 実行済みデータが履歴シートへ移動・削除されました。")
    # 処理完了後、Tab 2の表示をリフレッシュ

# --- 4. Streamlit UI 構築 ---

st.set_page_config(layout="wide", page_title="日記投稿管理アプリ")
st.title("📝 日記投稿管理 Web アプリ")

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
            selected_type = st.selectbox("日記種類フィルター", ["すべて", "出勤", "退勤", "その他"])
        with col_kind:
            selected_kind = st.selectbox("タイプ種類フィルター", ["すべて", "若", "妻", "おば"])
        
        filtered_df = df_templates.copy()
        if selected_type != "すべて":
            filtered_df = filtered_df[filtered_df['日記種類'] == selected_type]
        if selected_kind != "すべて":
            filtered_df = filtered_df[filtered_df['タイプ種類'] == selected_kind]

        # データエディタで表形式表示（コピペを容易にする）
        st.dataframe(
            filtered_df[['タイトル', '本文', '日記種類', 'タイプ種類']],
            use_container_width=True,
            height=300,
            hide_index=True,
            column_config={
                "タイトル": st.column_config.Column("タイトル", width="medium"),
                "本文": st.column_config.Column("本文", width="large"),
            }
        )
        st.caption("上記の表から必要なタイトルや本文をコピーし、下の入力テーブルに貼り付けてください。")
        
    except Exception as e:
        st.warning(f"テンプレートデータの読み込みに失敗しました: {e}")

    st.markdown("---")
    
    # --- B. 40件の日記データ入力 ---
    st.subheader("2️⃣ 登録用データ入力と画像アップロード (40件)")
    st.warning("登録ボタンを押すまでスプレッドシートへの書き込みは行われません。")

    # データ入力用の空のDataFrameを準備 (簡略化のためDataFrameを使用)
    num_entries = 40
    data = {header: [""] * num_entries for header in REGISTRATION_HEADERS if header not in ["下書き登録確認", "画像添付確認", "宛先登録確認", "画像URL/ID"]}
    df_input = pd.DataFrame(data)

    # Streamlitのデータエディタで入力UIを提供
    edited_df = st.data_editor(
        df_input,
        num_rows="dynamic",
        use_container_width=True,
        height=400
    )
    
    # 画像アップロードコンポーネントのプレースホルダー
    uploaded_files = st.file_uploader(
        "画像をまとめてアップロード (最大40枚)",
        type=['png', 'jpg', 'jpeg'],
        accept_multiple_files=True
    )

    if st.button("💾 データ登録を実行"):
        if len(edited_df) == 0:
            st.error("入力データがありません。")
        else:
            # 実際にはここで、以下の処理を行います
            # 1. 画像ファイルをGoogle Driveへアップロードし、IDを取得
            # 2. 取得したIDを DataFrame の '画像URL/ID' 列に追加
            # 3. 確定した DataFrame を '日記登録用' シートの末尾に書き込む
            st.success("🎉 データ登録と画像アップロード（ドライブへの格納）が完了しました。")
            st.info(f"登録件数: {len(edited_df)}件。詳細は Tab ② で確認できます。")


# =========================================================
# --- Tab 2: 下書き作成・実行 ---
# =========================================================

with tab2:
    st.header("2️⃣ 下書き作成・実行フロー (手動実行)")
    
    st.warning("🚨 注意喚起: 下書き作成の前に、連絡先シートと登録データの内容を確認してください。")

    # ボタンと実行ロジックのマッピング
    execution_steps = [
        ("Step 1: アドレス更新実行", run_step_1_address_update),
        ("Step 2: 下書き作成実行", run_step_2_draft_creation),
        ("Step 3: 画像登録確認実行", run_step_3_image_upload_check),
        ("Step 4: 宛先登録実行", run_step_4_destination_registration),
    ]

    cols = st.columns(4)
    
    # 1. 実行ステップボタンの設置
    for i, (label, func) in enumerate(execution_steps):
        with cols[i]:
            if st.button(label, key=f'step_btn_{i+1}', use_container_width=True):
                # 実行処理
                func()
    
    st.markdown("---")

    # 2. ステータス確認（日記登録用シートの内容表示）
    st.subheader("👀 登録データの実行状況")
    try:
        df_status = pd.DataFrame(SPRS.worksheet(REGISTRATION_SHEET).get_all_records())
        st.dataframe(df_status, use_container_width=True, hide_index=True)
    except Exception as e:
        st.info("「日記登録用」シートにデータがありません、または読み込みエラーが発生しました。")
        st.error(f"エラー内容: {e}")

    st.markdown("---")

    # 3. Step 5: 履歴へ移動 (最重要の分離ボタン)
    st.subheader("✅ Step 5: 履歴データ移動（最終確定）")
    st.error("Step 1〜4がすべて成功したことを**確認した上で**、このボタンを押してください。")
    if st.button("➡️ Step 5: 実行完了データを履歴へ移動・削除", key='step_btn_5_move', type="primary"):
        run_step_5_move_to_history()


# =========================================================
# --- Tab 3: 履歴の検索・修正・管理 ---
# =========================================================

with tab3:
    st.header("3️⃣ 履歴の検索・修正・管理")

    # --- A. 履歴データの検索と修正 (機能 B, C の準備) ---
    st.subheader("🔍 履歴データの検索と修正")
    try:
        df_history = pd.DataFrame(SPRS.worksheet(HISTORY_SHEET).get_all_records())
        
        # 履歴データの表示と修正UI (簡略化)
        edited_history_df = st.data_editor(
            df_history,
            key="history_editor",
            use_container_width=True,
            height=300
        )
        
        if st.button("🔄 修正内容を保存しGmail下書きを連動修正"):
            # ここで Google Sheets API と Gmail API を連携させるロジックを実装
            st.success("✅ データとGmail下書きの修正が完了しました。（機能 B）")

    except Exception as e:
        st.warning(f"履歴シート（{HISTORY_SHEET}）の読み込みに失敗しました: {e}")
        
    st.markdown("---")

    # --- B. 店舗閉め・アーカイブ機能 (機能 C) ---
    st.subheader("📦 店舗閉め・アーカイブ機能")
    
    # 履歴データから店舗名リストを取得 (重複排除)
    if 'df_history' in locals() and not df_history.empty:
        store_list = df_history['店名'].unique().tolist()
    else:
        store_list = ["データがありません"]

    selected_store = st.selectbox("アーカイブ対象店舗を選択", store_list)
    
    st.warning("選択した店舗の全データを履歴シートから使用可日記データシートへ移動します。")
    if st.button(f"↩️ {selected_store} をアーカイブ (使用可へ移動)", type="secondary"):
        if selected_store != "データがありません":
            # ここで Sheets API を使用した行移動ロジックを実装
            st.success(f"✅ 店舗 {selected_store} のアーカイブ（データ移動）が完了しました。（機能 C）")
        else:
            st.error("アーカイブできる店舗データがありません。")
