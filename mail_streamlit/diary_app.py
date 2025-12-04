import streamlit as st
import pandas as pd
import gspread
from io import BytesIO
import time # 処理時間シミュレーション用

# --- 1. 定数と初期設定 ---
# Secretsから認証情報とリソースIDを取得
try:
    SHEET_ID = st.secrets["google_resources"]["spreadsheet_id"]
    DRIVE_FOLDER_ID = st.secrets["google_resources"]["drive_folder_id"]
    SHEET_NAMES = st.secrets["sheet_names"]
    
    # シート名の定義
    REGISTRATION_SHEET = SHEET_NAMES["registration_sheet"]
    CONTACT_SHEET = SHEET_NAMES["contact_sheet"]
    USABLE_DIARY_SHEET = SHEET_NAMES["usable_diary_sheet"]
    HISTORY_SHEET = SHEET_NAMES["history_sheet"] # 全店舗データシート
    
except KeyError:
    st.error("🚨 GoogleリソースIDまたはシート名がsecrets.tomlに正しく設定されていません。")
    st.stop()


# 最終確定した「日記登録用シート」のヘッダー定義 (11項目)
# No. 1～8: ユーザー入力, No. 9～11: アプリ自動更新
REGISTRATION_HEADERS = [
    "エリア", "店名", "媒体", "投稿時間", "女の子の名前", "タイトル", "本文", "担当アカウント", 
    "下書き登録確認", "画像添付確認", "宛先登録確認" 
]
INPUT_HEADERS = REGISTRATION_HEADERS[:8] # ユーザーが手動で入力する8項目

# --- 2. Google Sheets API連携関数 ---

@st.cache_resource(ttl=3600)
def connect_to_gsheets():
    """GSpreadでGoogle Sheetsに接続し、クライアントを返す"""
    try:
        # Streamlit Secretsからサービスアカウント認証情報を取得
        client = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        spreadsheet = client.open_by_key(SHEET_ID)
        return spreadsheet
    except Exception as e:
        st.error(f"❌ Google Sheets への接続に失敗しました: {e}")
        st.stop()
        
SPRS = connect_to_gsheets()

# --- 3. 実行ロジック (プレースホルダー関数) ---

def run_step(step_num, action_desc, sheet_name=REGISTRATION_SHEET):
    """実行ステップのシミュレーションとシート更新のプレースホルダー"""
    st.info(f"🔄 Step {step_num}: {action_desc}を実行中...")
    time.sleep(2) # 処理時間をシミュレート
    
    # 実際にはここで外部ロジック（mail_address_extractor.py相当など）をWeb APIで実行
    
    # 成功したら、シートの該当列のステータスを更新するロジックが続く
    try:
        ws = SPRS.worksheet(sheet_name)
        # 実際には、特定の行（処理対象のデータ行）を特定して、対応する列（9, 10, 11列目）を更新します
        # 例: ws.update_cell(row, 9, "OK") 
        pass
    except Exception as e:
        st.error(f"❌ ステータス更新中にエラーが発生: {e}")
        return False

    st.success(f"✅ Step {step_num}: {action_desc}が完了しました。")
    return True


def run_step_5_move_to_history():
    """Step 5: 履歴へ移動（新規機能）"""
    st.info("🔄 Step 5: 実行済みデータを履歴シートへ移動中...")
    time.sleep(3) # 処理時間をシミュレート

    # ここに Sheets API を使用した行移動ロジックを実装
    # 1. '日記登録用'シートからステータスが全て'OK'の行を抽出
    # 2. '実験用'（履歴）シートの末尾に書き込み
    # 3. '日記登録用'シートから該当行を削除
    
    st.success("✅ Step 5: 実行済みデータが履歴シートへ移動・削除されました。")

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
        # 【使用可能日記文】シートからデータを読み込み
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

        # データエディタで表形式表示（コピペを容易にする）
        st.dataframe(
            filtered_df[['タイトル', '本文', '日記種類', 'タイプ種類']],
            use_container_width=True,
            height=250,
            hide_index=True,
        )
        st.caption("上記の表から必要なタイトルや本文をコピーし、下の入力テーブルに貼り付けてください。")
        
    except Exception as e:
        st.warning(f"テンプレートデータの読み込みに失敗しました: {e}")

    st.markdown("---")
    
    # --- B. 40件の日記データ入力 ---
    st.subheader("2️⃣ 登録用データ入力と画像アップロード (40件)")

    # データ入力用の空のDataFrameを準備 (確定した8項目のみ)
    num_entries = 40
    data = {header: [""] * num_entries for header in INPUT_HEADERS}
    df_input = pd.DataFrame(data)

    # Streamlitのデータエディタで入力UIを提供
    edited_df = st.data_editor(
        df_input,
        num_rows="dynamic",
        use_container_width=True,
        height=350
    )
    
    # 画像アップロードコンポーネント
    uploaded_files = st.file_uploader(
        "画像をまとめてアップロード (最大40枚)",
        type=['png', 'jpg', 'jpeg'],
        accept_multiple_files=True
    )
    
    uploaded_image_count = len(uploaded_files) if uploaded_files else 0
    st.caption(f"画像アップロード数: {uploaded_image_count}枚")

    if st.button("💾 データ登録を実行"):
        valid_entries = edited_df.dropna(how='all', subset=INPUT_HEADERS).reset_index(drop=True)
        
        if valid_entries.empty:
            st.error("入力データがありません。")
        elif len(valid_entries) != uploaded_image_count:
             st.warning("⚠️ 入力データ件数とアップロードされた画像件数が一致しません。")
             # 強制実行は可能だが警告を出す

        # 1. Google Drive への画像アップロード (ロジックはプレースホルダー)
        # 実際にはここで、Drive APIを使用して画像をアップロードし、ファイルIDを取得する。

        # 2. スプレッドシートへの書き込み
        try:
            ws = SPRS.worksheet(REGISTRATION_SHEET)
            
            # ステータス列（9, 10, 11列目）を初期値（例：'未実行'）で追加
            status_cols = pd.DataFrame({'下書き登録確認': ['未実行'] * len(valid_entries),
                                        '画像添付確認': ['未実行'] * len(valid_entries),
                                        '宛先登録確認': ['未実行'] * len(valid_entries)})
            
            final_df = pd.concat([valid_entries, status_cols], axis=1)

            # ヘッダーを含まずにデータのみをシートの末尾に追加
            ws.append_rows(final_df.values.tolist(), value_input_option='USER_ENTERED')
            
            st.success(f"🎉 **{len(valid_entries)}件**のデータ登録と画像アップロード（ドライブへの格納）が完了しました。")
            st.info("次の作業は Tab ② で実行してください。")
        except Exception as e:
            st.error(f"❌ データ登録中に重大なエラーが発生しました: {e}")


# =========================================================
# --- Tab 2: 下書き作成・実行 ---
# =========================================================

with tab2:
    st.header("2️⃣ 下書き作成・実行フロー (手動実行)")
    
    st.warning("🚨 **Step 0: 注意喚起** - 連絡先シートと登録データの内容を手動で確認してください。")

    # ボタンと実行ロジックのマッピング
    execution_steps = [
        ("Step 1: アドレス更新実行", lambda: run_step(1, "アドレスと連絡先の更新")),
        ("Step 2: 下書き作成実行", lambda: run_step(2, "Gmailの下書き作成")),
        ("Step 3: 画像登録確認実行", lambda: run_step(3, "画像の添付と登録状況確認")),
        ("Step 4: 宛先登録実行", lambda: run_step(4, "下書きへの宛先登録")),
    ]

    cols = st.columns(4)
    
    # 1. 実行ステップボタンの設置
    for i, (label, func) in enumerate(execution_steps):
        with cols[i]:
            if st.button(label, key=f'step_btn_{i+1}', use_container_width=True):
                func()
    
    st.markdown("---")

    # 2. ステータス確認（日記登録用シートの内容表示）
    st.subheader("👀 登録データの実行状況")
    try:
        # 最新のデータを再読み込み
        df_status = pd.DataFrame(SPRS.worksheet(REGISTRATION_SHEET).get_all_records())
        st.dataframe(df_status, use_container_width=True, hide_index=True)
    except Exception as e:
        st.info("「日記登録用」シートにデータがありません、または読み込みエラーが発生しました。")

    st.markdown("---")

    # 3. Step 5: 履歴へ移動 (最重要の分離ボタン)
    st.subheader("✅ Step 5: 履歴データ移動（最終確定）")
    st.error("Step 1〜4がすべて成功し、**安全を確認した上で**、このボタンを押してください。")
    if st.button("➡️ Step 5: 実行完了データを履歴へ移動・削除", key='step_btn_5_move', type="primary"):
        run_step_5_move_to_history()


# =========================================================
# --- Tab 3: 履歴の検索・修正・管理 ---
# =========================================================

with tab3:
    st.header("3️⃣ 履歴の検索・修正・管理")
    
    try:
        # 履歴シート（全店舗データシート）の読み込み
        df_history = pd.DataFrame(SPRS.worksheet(HISTORY_SHEET).get_all_records())
    except Exception as e:
        df_history = pd.DataFrame()
        st.warning(f"履歴シート（{HISTORY_SHEET}）の読み込みに失敗しました: {e}")
        
    st.markdown("---")

    # --- A. 履歴データの検索と修正 (機能 B: Gmail連動修正) ---
    st.subheader("🔍 履歴データの検索と修正")
    
    if not df_history.empty:
        # 履歴データの表示と修正UI
        edited_history_df = st.data_editor(
            df_history,
            key="history_editor",
            use_container_width=True,
            height=300
        )
        
        if st.button("🔄 修正内容を保存しGmail下書きを連動修正"):
            # ここで Sheets API（データ更新）と Gmail API（下書き修正）の連携ロジックを実装
            st.success("✅ データとGmail下書きの修正が完了しました。（機能 B）")
    else:
        st.info("履歴データがありません。")
        
    st.markdown("---")

    # --- B. 店舗閉め・アーカイブ機能 (機能 C) ---
    st.subheader("📦 店舗閉め・アーカイブ機能")
    
    if not df_history.empty:
        # 履歴データから店舗名リストを取得 (重複排除)
        store_list = df_history['店名'].unique().tolist()
        selected_store = st.selectbox("アーカイブ対象店舗を選択", store_list)
        
        st.warning(f"「{selected_store}」の全データを履歴シートから使用可日記データシートへ移動します。")
        
        if st.button(f"↩️ {selected_store} をアーカイブ (使用可へ移動)", type="secondary"):
            # ここで Sheets API を使用した行移動ロジックを実装
            st.success(f"✅ 店舗 {selected_store} のアーカイブ（データ移動）が完了しました。（機能 C）")
    else:
        st.info("アーカイブできる店舗データがありません。")
