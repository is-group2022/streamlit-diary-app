import streamlit as st
import pandas as pd
import gspread
from io import BytesIO
from google.oauth2.service_account import Credentials
from google.cloud import storage  # 追加
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- 1. 定数と初期設定 ---
try:
    SHEET_ID = st.secrets["google_resources"]["spreadsheet_id"] 
    # ACCOUNT_STATUS_SHEET_ID はログイン情報用
    ACCOUNT_STATUS_SHEET_ID = "1_GmWjpypap4rrPGNFYWkwcQE1SoK3QOMJlozEhkBwVM"
    USABLE_DIARY_SHEET_ID = "1e-iLey43A1t0bIBoijaXP55t5fjONdb0ODiTS53beqM" # 修正済みID
    
    # GCSの設定
    GCS_BUCKET_NAME = "auto-poster-images"

    SHEET_NAMES = st.secrets["sheet_names"]
    POSTING_ACCOUNT_SHEETS = {
        "A": "投稿Aアカウント",
        "B": "投稿Bアカウント",
        "C": "投稿Cアカウント",
        "D": "投稿Dアカウント"
    }
    
    USABLE_DIARY_SHEET = "【使用可能日記文】" # 教えていただいたシート名
    MEDIA_OPTIONS = ["駅ちか", "デリじゃ"]
    POSTING_ACCOUNT_OPTIONS = ["A", "B", "C", "D"] 
    
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/cloud-platform']
except KeyError:
    st.error("🚨 secrets.tomlの設定を確認してください。")
    st.stop()

REGISTRATION_HEADERS = ["エリア", "店名", "媒体", "投稿時間", "女の子の名前", "タイトル", "本文"]
INPUT_HEADERS = ["投稿時間", "女の子の名前", "タイトル", "本文"]

# --- 2. 各種API連携 ---

@st.cache_resource(ttl=3600)
def connect_to_gsheets(sheet_id):
    client = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    return client.open_by_key(sheet_id)

@st.cache_resource(ttl=3600)
def get_gcs_client():
    return storage.Client.from_service_account_info(st.secrets["gcp_service_account"])

try:
    SPRS = connect_to_gsheets(SHEET_ID)
    STATUS_SPRS = connect_to_gsheets(ACCOUNT_STATUS_SHEET_ID) 
    GCS_CLIENT = get_gcs_client()
except Exception as e:
    st.error(f"❌ API接続失敗: {e}"); st.stop()

# --- GCS 補助関数 (ドライブ関数から差し替え) ---
def gcs_upload_wrapper(uploaded_file, entry, area, store):
    try:
        bucket = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
        # フォルダ階層の作成
        folder_name = f"デリじゃ {store}" if st.session_state.global_media == "デリじゃ" else store
        ext = uploaded_file.name.split('.')[-1]
        # パス: エリア/店名/時間_名前.拡張子
        blob_path = f"{area}/{folder_name}/{entry['投稿時間'].strip()}_{entry['女の子の名前'].strip()}.{ext}"
        
        blob = bucket.blob(blob_path)
        blob.upload_from_string(uploaded_file.getvalue(), content_type=uploaded_file.type)
        return True
    except Exception as e:
        st.error(f"❌ GCSアップロード失敗: {e}")
        return False

# --- 3. UI 構築 ---
st.set_page_config(layout="wide", page_title="写メ日記投稿管理")

# --- タブの文字を最大級にするカスタムCSS ---
st.markdown("""
    <style>
    /* タブのコンテナ自体の高さを確保 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        height: 80px;
    }

    /* 各タブのスタイル */
    button[data-baseweb="tab"] {
        font-size: 32px !important; /* さらに大きく */
        font-weight: 800 !important; /* 極太 */
        height: 70px !important;
        padding: 0px 30px !important;
        background-color: #f0f2f6 !important; /* 未選択時の背景色 */
        border-radius: 10px 10px 0px 0px !important; /* 角を丸く */
        margin-right: 5px !important;
    }

    /* 選択されているタブのスタイル */
    button[data-baseweb="tab"][aria-selected="true"] {
        color: white !important;
        background-color: #FF4B4B !important; /* 選択時は赤背景 */
        border-bottom: 5px solid #b33232 !important;
    }

    /* マウスを乗せた時（ホバー）の動き */
    button[data-baseweb="tab"]:hover {
        background-color: #e0e2e6 !important;
        color: #FF4B4B !important;
    }
    </style>
""", unsafe_allow_html=True)

if 'diary_entries' not in st.session_state:
    st.session_state.diary_entries = [{h: "" for h in INPUT_HEADERS} for _ in range(40)]

tab1, tab2, tab3 = st.tabs(["📝 ① データ登録", "📂 ② 投稿データ管理", "📚 ③  使用可能日記文表示"])

# =========================================================
# --- Tab 1: データ登録 ---
# =========================================================
with tab1:
    st.header("1️⃣ 新規データ登録")
    
    c1, c2, c3, c4 = st.columns(4)
    target_acc = c1.selectbox("👤 投稿アカウント", POSTING_ACCOUNT_OPTIONS)
    st.session_state.global_media = c2.selectbox("🌐 媒体", MEDIA_OPTIONS)
    global_area = c3.text_input("📍 エリア")
    global_store = c4.text_input("🏢 店名")

    st.markdown("---")
    st.subheader("🔑 ログイン情報（アカウント登録用）")
    c5, c6 = st.columns(2)
    login_id = c5.text_input("ID", key="login_id")
    login_pw = c6.text_input("パスワード", key="login_pw")

    st.markdown("---")
    st.subheader("📸 投稿内容入力")
    
    with st.form("reg_form"):
        h_cols = st.columns([1, 1, 2, 3, 2])
        h_cols[0].write("**投稿時間**")
        h_cols[1].write("**女の子の名前**")
        h_cols[2].write("**タイトル**")
        h_cols[3].write("**本文**")
        h_cols[4].write("**画像**")

        for i in range(40):
            cols = st.columns([1, 1, 2, 3, 2])
            st.session_state.diary_entries[i]['投稿時間'] = cols[0].text_input(f"時間{i}", key=f"t_{i}", label_visibility="collapsed")
            st.session_state.diary_entries[i]['女の子の名前'] = cols[1].text_input(f"名{i}", key=f"n_{i}", label_visibility="collapsed")
            st.session_state.diary_entries[i]['タイトル'] = cols[2].text_area(f"題{i}", key=f"ti_{i}", height=68, label_visibility="collapsed")
            st.session_state.diary_entries[i]['本文'] = cols[3].text_area(f"本{i}", key=f"b_{i}", height=68, label_visibility="collapsed")
            st.session_state.diary_entries[i]['img'] = cols[4].file_uploader(f"画{i}", key=f"img_{i}", label_visibility="collapsed")
        
        if st.form_submit_button("🔥 データを登録する", type="primary"):
            valid_data = [e for e in st.session_state.diary_entries if e['投稿時間'] and e['女の子の名前']]
            if not valid_data: st.error("投稿内容を入力してください"); st.stop()
            
            # A. GCSアップロード
            for e in valid_data:
                if e['img']: gcs_upload_wrapper(e['img'], e, global_area, global_store)
            
            # B. メインシート書き込み
            ws_main = SPRS.worksheet(POSTING_ACCOUNT_SHEETS[target_acc])
            rows_main = [[global_area, global_store, st.session_state.global_media, e['投稿時間'], e['女の子の名前'], e['タイトル'], e['本文']] for e in valid_data]
            ws_main.append_rows(rows_main, value_input_option='USER_ENTERED')
            
            # C. ステータス管理シート書き込み
            ws_status = STATUS_SPRS.worksheet(POSTING_ACCOUNT_SHEETS[target_acc])
            status_row = [global_area, global_store, st.session_state.global_media, login_id, login_pw]
            ws_status.append_row(status_row, value_input_option='USER_ENTERED')
            
            st.success(f"✅ 投稿データ {len(rows_main)} 件とログイン情報を GCS およびシートへ登録しました！")
# =========================================================
# --- Tab 2: 投稿データ管理 (診断ログ付き) ---
# =========================================================
with tab2:
    st.header("2️⃣ 投稿データ管理 (全アカウント統合編集)")
    
    combined_data = []
    debug_logs = [] # どこで止まっているか確認するためのログ

    for acc_code, sheet_name in POSTING_ACCOUNT_SHEETS.items():
        try:
            # 1. ワークシートの取得を試行
            ws = SPRS.worksheet(sheet_name)
            # 2. 全データの取得
            raw_data = ws.get_all_values()
            
            if len(raw_data) > 1:
                added_count = 0
                for i, row in enumerate(raw_data[1:]):
                    # 少なくとも最初の7列のどこかにデータがあるか
                    if any(str(cell).strip() for cell in row[:7]):
                        # 列数が足りない場合に備えて長さを調整
                        row_full = [row[j] if j < len(row) else "" for j in range(7)]
                        combined_data.append([acc_code, i + 2] + row_full)
                        added_count += 1
                debug_logs.append(f"✅ {acc_code}({sheet_name}): {added_count}件取得")
            else:
                debug_logs.append(f"⚠️ {acc_code}({sheet_name}): データが空（見出しのみ）")
                
        except Exception as e:
            # エラーを無視せずログに残す
            debug_logs.append(f"❌ {acc_code}({sheet_name}): エラー -> {str(e)}")

    # 画面上部に読み込み状況を表示（正常なら消してもOK）
    with st.expander("📊 読み込み状況の詳細を確認"):
        for log in debug_logs:
            st.write(log)

    if combined_data:
        df = pd.DataFrame(combined_data, columns=["アカウント", "行番号"] + REGISTRATION_HEADERS)
        
        # 編集画面
        edited_df = st.data_editor(
            df, 
            key="main_editor", 
            use_container_width=True, 
            hide_index=True, 
            disabled=["アカウント", "行番号"], 
            height=600
        )

        if st.button("💾 変更内容をスプレッドシートに反映する", type="primary"):
            with st.spinner("更新中..."):
                try:
                    # 変更があったアカウントを特定して更新
                    for acc_code in POSTING_ACCOUNT_OPTIONS:
                        target_rows = edited_df[edited_df["アカウント"] == acc_code]
                        if target_rows.empty: continue
                        
                        ws = SPRS.worksheet(POSTING_ACCOUNT_SHEETS[acc_code])
                        for _, row in target_rows.iterrows():
                            row_idx = int(row["行番号"])
                            new_values = [str(row[h]) for h in REGISTRATION_HEADERS]
                            # アップデート範囲を明示
                            ws.update(f"A{row_idx}:G{row_idx}", [new_values], value_input_option='USER_ENTERED')
                    st.success("🎉 スプレッドシートを更新しました！")
                    st.rerun() # 更新後に画面をリフレッシュ
                except Exception as e:
                    st.error(f"❌ 更新エラー: {e}")
    else:
        st.info("登録されているデータはありません。")
# =========================================================
# --- Tab 3: テンプレート全文表示 (確定版) ---
# =========================================================
with tab3:
    st.header("3️⃣ 使用可能日記文")
    try:
        # スプレッドシートに接続
        tmp_sprs = connect_to_gsheets(USABLE_DIARY_SHEET_ID)
        
        # 直接シート名を指定して読み込み
        target_name = "【使用可能日記文】"
        tmp_ws = tmp_sprs.worksheet(target_name)
        
        # データの取得
        tmp_data = tmp_ws.get_all_values()
        
        if len(tmp_data) > 1:
            # 1行目をヘッダーとしてデータフレームを作成
            df_tmp = pd.DataFrame(tmp_data[1:], columns=tmp_data[0])
            
            # 画面いっぱいに表示
            st.dataframe(df_tmp, use_container_width=True, height=600)
        else:
            st.info(f"シート「{target_name}」にデータが見つかりませんでした。")
            
    except Exception as e:
        st.error(f"🚨 読み込みエラー: {e}")
        st.info("スプレッドシートの右上の「共有」ボタンから、サービスアカウントのメールアドレスが追加されているか再度確認してください。")






