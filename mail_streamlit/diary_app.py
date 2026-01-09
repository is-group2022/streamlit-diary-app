import streamlit as st
import pandas as pd
import gspread
import zipfile
import re
from io import BytesIO
from google.oauth2.service_account import Credentials
from google.cloud import storage 
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# --- 1. 定数と初期設定 ---
try:
    SHEET_ID = st.secrets["google_resources"]["spreadsheet_id"] 
    ACCOUNT_STATUS_SHEET_ID = "1_GmWjpypap4rrPGNFYWkwcQE1SoK3QOMJlozEhkBwVM"
    USABLE_DIARY_SHEET_ID = "1e-iLey43A1t0bIBoijaXP55t5fjONdb0ODiTS53beqM"
    
    GCS_BUCKET_NAME = "auto-poster-images"

    SHEET_NAMES = st.secrets["sheet_names"]
    POSTING_ACCOUNT_SHEETS = {
        "A": "投稿Aアカウント",
        "B": "投稿Bアカウント",
        "C": "投稿Cアカウント",
        "D": "投稿Dアカウント"
    }
    
    USABLE_DIARY_SHEET = "【使用可能日記文】"
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

def gcs_upload_wrapper(uploaded_file, entry, area, store):
    try:
        bucket = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
        folder_name = f"デリじゃ {store}" if st.session_state.global_media == "デリじゃ" else store
        ext = uploaded_file.name.split('.')[-1]
        blob_path = f"{area}/{folder_name}/{entry['投稿時間'].strip()}_{entry['女の子の名前'].strip()}.{ext}"
        blob = bucket.blob(blob_path)
        blob.upload_from_string(uploaded_file.getvalue(), content_type=uploaded_file.type)
        return True
    except Exception as e:
        st.error(f"❌ GCSアップロード失敗: {e}")
        return False

@st.cache_data(ttl=600)
def get_cached_url(blob_name):
    bucket = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(blob_name)
    return blob.generate_signed_url(version="v4", expiration=600, method="GET")

# --- 3. UI 構築 ---
st.set_page_config(layout="wide", page_title="写メ日記投稿管理")

st.markdown("""
    <style>
    .block-container { padding-top: 0rem !important; padding-bottom: 0rem !important; }
    header[data-testid="stHeader"] { display: none !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; height: 80px; }
    button[data-baseweb="tab"] {
        font-size: 32px !important; font-weight: 800 !important; height: 70px !important;
        padding: 0px 30px !important; background-color: #f0f2f6 !important;
        border-radius: 10px 10px 0px 0px !important; margin-right: 5px !important;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: white !important; background-color: #FF4B4B !important;
    }
    .sticky-header-row {
        position: -webkit-sticky;
        position: sticky;
        top: 0px;
        z-index: 1000;
        background-color: white !important;
        padding: 10px 0px;
        margin-bottom: 5px;
    }
    </style>
""", unsafe_allow_html=True)

if 'diary_entries' not in st.session_state:
    st.session_state.diary_entries = [{h: "" for h in INPUT_HEADERS} for _ in range(40)]

# タブ構成の更新
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📝 ① データ登録", 
    "📊 ② 店舗アカウント状況", 
    "📂 ③ 投稿日記文管理", 
    "📸 ④ 投稿画像管理",
    "📚 ⑤ 使用可能日記文",
    "🖼 ⑥ 使用可能画像"
])

combined_data = []
acc_summary = {}; acc_counts = {}
try:
    all_ws = SPRS.worksheets()
    ws_dict = {ws.title: ws for ws in all_ws}
    for code, s_name in POSTING_ACCOUNT_SHEETS.items():
        if s_name in ws_dict:
            rows = ws_dict[s_name].get_all_values()
            if len(rows) > 1:
                for i, r in enumerate(rows[1:]):
                    if any(str(c).strip() for c in r[:7]):
                        combined_data.append([code, i+2] + [r[j] if j<len(r) else "" for j in range(7)])
                        a, s, m = str(r[0]).strip(), str(r[1]).strip(), str(r[2]).strip()
                        acc_counts[code] = acc_counts.get(code, 0) + 1
                        if code not in acc_summary: acc_summary[code] = {}
                        if a not in acc_summary[code]: acc_summary[code][a] = set()
                        acc_summary[code][a].add(f"{m} : {s}")
except: pass

# --- Tab 1 ---
with tab1:
    st.header("1️⃣ 新規データ登録")
    
    # 基本情報
    c1, c2, c3, c4 = st.columns(4)
    target_acc = c1.selectbox("👤 投稿アカウント", POSTING_ACCOUNT_OPTIONS, key="sel_acc_1")
    st.session_state.global_media = c2.selectbox("🌐 媒体", MEDIA_OPTIONS, key="sel_media_1")
    global_area = c3.text_input("📍 エリア", key="in_area_1")
    global_store = c4.text_input("🏢 店名", key="in_store_1")
    
    st.subheader("🔑 ログイン情報")
    c5, c6 = st.columns(2)
    login_id = c5.text_input("ID", key="login_id")
    login_pw = c6.text_input("パスワード", key="login_pw")
    
    st.markdown("---")
    st.subheader("📸 投稿内容入力")

    # ヘッダー固定表示（HTML）
    st.markdown("""
        <div style="display: flex; flex-direction: row; border-bottom: 2px solid #444; background-color: #f0f2f6; padding: 10px; border-radius: 5px 5px 0 0;">
            <div style="flex: 1; font-weight: bold;">時間</div>
            <div style="flex: 1; font-weight: bold;">名前</div>
            <div style="flex: 2; font-weight: bold;">タイトル</div>
            <div style="flex: 3; font-weight: bold;">本文</div>
            <div style="flex: 2; font-weight: bold;">画像</div>
        </div>
    """, unsafe_allow_html=True)

    # 入力フォームの生成（40行）
    # 大量入力時の負荷を下げるため、key管理を徹底
    for i in range(40):
        cols = st.columns([1, 1, 2, 3, 2])
        st.session_state.diary_entries[i]['投稿時間'] = cols[0].text_input(f"t{i}", key=f"t_{i}", label_visibility="collapsed")
        st.session_state.diary_entries[i]['女の子の名前'] = cols[1].text_input(f"n{i}", key=f"n_{i}", label_visibility="collapsed")
        st.session_state.diary_entries[i]['タイトル'] = cols[2].text_area(f"ti{i}", key=f"ti_{i}", height=68, label_visibility="collapsed")
        st.session_state.diary_entries[i]['本文'] = cols[3].text_area(f"b{i}", key=f"b_{i}", height=68, label_visibility="collapsed")
        st.session_state.diary_entries[i]['img'] = cols[4].file_uploader(f"g{i}", key=f"img_{i}", label_visibility="collapsed")

    if st.button("🔥 データを登録する", type="primary", use_container_width=True):
        # 入力チェック
        valid_data = [e for e in st.session_state.diary_entries if e['投稿時間'] and e['女の子の名前']]
        if not valid_data:
            st.error("投稿時間と名前を入力してください")
            st.stop()
        
        if not global_area or not global_store:
            st.error("エリアと店名を入力してください")
            st.stop()

        progress_text = st.empty()
        try:
            # 1. 画像アップロード
            progress_text.info("📸 画像をアップロード中...")
            for e in valid_data:
                if e['img']:
                    gcs_upload_wrapper(e['img'], e, global_area, global_store)
            
            # 2. スプレッドシート（日記文）一括登録
            progress_text.info("📝 日記文を登録中...")
            sheet_name = POSTING_ACCOUNT_SHEETS[target_acc]
            
            # APIエラー回避のためシート取得を慎重に行う
            try:
                ws_main = SPRS.worksheet(sheet_name)
            except Exception as e:
                st.error(f"シート '{sheet_name}' が見つかりません。スプレッドシートのタブ名を確認してください。")
                st.stop()
                
            rows_main = [[global_area, global_store, st.session_state.global_media, e['投稿時間'], e['女の子の名前'], e['タイトル'], e['本文']] for e in valid_data]
            ws_main.append_rows(rows_main, value_input_option='USER_ENTERED')
            
            # 3. スプレッドシート（ステータス/ログイン情報）登録
            progress_text.info("🔐 ログイン情報を登録中...")
            ws_status = STATUS_SPRS.worksheet(sheet_name)
            ws_status.append_row([global_area, global_store, st.session_state.global_media, login_id, login_pw], value_input_option='USER_ENTERED')
            
            progress_text.empty()
            st.success(f"✅ {len(valid_data)}件のデータを正常に登録しました！")
            
            # 登録後、入力をクリアするためにリロード（任意）
            # st.rerun()

        except Exception as e:
            st.error(f"APIエラーが発生しました。時間を置いて再度試してください。詳細: {e}")
            
# =========================================================
# --- Tab 2: 📊 全アカウント店舗アカウント状況 (落ち店移動機能・決定版) ---
# =========================================================
with tab2:
    st.markdown("## 📊 全アカウント店舗アカウント状況")
    st.caption("店舗を選択して「落ち店移動」を実行すると、日記文のバックアップ、アカウント紐付け解除、画像移動を自動で行います。")

    if combined_data:
        # 1. 移動対象を選択するためのチェックボックス管理
        if 'move_to_ochimise' not in st.session_state:
            st.session_state.move_to_ochimise = {}

        # 2. 各アカウントの状況表示
        for acc_code in POSTING_ACCOUNT_OPTIONS:
            count = acc_counts.get(acc_code, 0)
            st.markdown(f"### 👤 投稿{acc_code}アカウント　`{count} 件`")
            
            if acc_code in acc_summary:
                areas = acc_summary[acc_code]
                area_cols = st.columns(len(areas) if len(areas) > 0 else 1)
                
                for idx, (area_name, shops) in enumerate(areas.items()):
                    with area_cols[idx]:
                        st.info(f"📍 **{area_name}**")
                        for shop in sorted(shops):
                            cb_key = f"move_{acc_code}_{area_name}_{shop}"
                            st.checkbox(f"{shop}", key=cb_key)
            else:
                st.caption("稼働データなし")
            st.markdown("---")

        # 3. 落ち店移動の実行エリア
        selected_shops = []
        for key, value in st.session_state.items():
            if key.startswith("move_") and value:
                parts = key.split('_')
                if len(parts) >= 4:
                    selected_shops.append({
                        "acc": parts[1], "area": parts[2], "shop": parts[3], "key": key
                    })

        if selected_shops:
            st.warning(f"⚠️ 現在 {len(selected_shops)} 店舗が選択されています。")
            if st.button("🚀 選択した店舗を【落ち店】へ移動する", type="primary", use_container_width=True):
                st.session_state.confirm_move = True

            if st.session_state.get("confirm_move"):
                st.error("❗ 本当に実行しますか？ (日記文の移動、設定の削除、画像の移動が実行されます)")
                col_yes, col_no = st.columns(2)
                
                if col_yes.button("⭕ はい、実行します", type="primary", use_container_width=True):
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    try:
                        # --- 修正ポイント：gspreadクライアントの確実な取得 ---
                        # SPRSから、open_by_keyメソッドを持つ認証済みクライアントを特定
                        # もしSPRSが大元のクライアントならそのまま使い、スプレッドシートならそのクライアントを使う
                        if hasattr(SPRS, 'open_by_key'):
                            auth_gc = SPRS
                        elif hasattr(SPRS, 'spreadsheet') and hasattr(SPRS.spreadsheet, 'client') and hasattr(SPRS.spreadsheet.client, 'open_by_key'):
                            auth_gc = SPRS.spreadsheet.client
                        else:
                            # 万が一上記がダメな場合、STATUS_SPRSなど他の定義済みオブジェクトから試行
                            auth_gc = STATUS_SPRS.spreadsheet.client if hasattr(STATUS_SPRS, 'spreadsheet') else STATUS_SPRS
                        
                        # スプレッドシートIDの定義
                        SS_STOCK_ID = "1e-iLey43A1t0bIBoijaXP55t5fjONdb0ODiTS53beqM" # 日記ストック
                        SS_LINK_ID = "1_GmWjpypap4rrPGNFYWkwcQE1SoK3QOMJlozEhkBwVM" # 紐付け
                        
                        # 新しいクライアント経由でスプレッドシートを開く
                        sh_stock = auth_gc.open_by_key(SS_STOCK_ID)
                        ws_stock = sh_stock.sheet1
                        sh_link = auth_gc.open_by_key(SS_LINK_ID)
                        
                        for i, item in enumerate(selected_shops):
                            status_text.info(f"処理中 ({i+1}/{len(selected_shops)}): {item['shop']}")
                            
                            # --- ① 日記文の移動 ---
                            ws_main = SPRS.worksheet(POSTING_ACCOUNT_SHEETS[item['acc']])
                            main_data = ws_main.get_all_values()
                            # 逆順ループで行削除のズレを防止
                            for row_idx in range(len(main_data), 0, -1):
                                row = main_data[row_idx-1]
                                if len(row) >= 2 and row[0] == item['area'] and row[1] == item['shop']:
                                    title = row[5] if len(row) >= 6 else ""
                                    body = row[6] if len(row) >= 7 else ""
                                    ws_stock.append_row(["落ち店", "一括移動", title, body])
                                    time.sleep(1.0) # API制限回避
                                    ws_main.delete_rows(row_idx)
                                    break

                            # --- ② アカウント紐付けの削除 ---
                            ws_link = sh_link.worksheet(POSTING_ACCOUNT_SHEETS[item['acc']])
                            link_data = ws_link.get_all_values()
                            for row_idx in range(len(link_data), 0, -1):
                                row = link_data[row_idx-1]
                                if len(row) >= 2 and row[0] == item['area'] and row[1] == item['shop']:
                                    ws_link.delete_rows(row_idx)
                                    break

                            # --- ③ GCS画像の移動 ---
                            bucket = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
                            possible_prefixes = [
                                f"{item['area']}/{item['shop']}/",
                                f"{item['area']}/デリじゃ {item['shop']}/",
                                f"{item['area']}/デリじゃ　{item['shop']}/"
                            ]
                            
                            for prefix in possible_prefixes:
                                blobs = list(bucket.list_blobs(prefix=prefix))
                                if blobs:
                                    for b in blobs:
                                        new_name = b.name.replace(prefix, f"【落ち店】/{item['shop']}/")
                                        bucket.copy_blob(b, bucket, new_name)
                                        b.delete()
                                    break
                            
                            time.sleep(1.0) 
                            progress_bar.progress((i + 1) / len(selected_shops))
                        
                        st.success("🎉 全ての移動処理が完了しました！")
                        st.session_state.confirm_move = False
                        for s_item in selected_shops: st.session_state[s_item['key']] = False
                        st.cache_data.clear()
                        st.rerun()

                    except Exception as e:
                        st.error(f"エラーが発生しました: {e}")
                        st.session_state.confirm_move = False

                if col_no.button("❌ キャンセル", use_container_width=True):
                    st.session_state.confirm_move = False
                    st.rerun()
    else:
        st.info("現在稼働中のデータはありません。")
        
# =========================================================
# --- Tab 3: 📂 投稿日記文管理 (変更検知・自動ソート版) ---
# =========================================================
with tab3:
    st.markdown("### 📂 投稿日記文管理 (一括編集)")
    st.caption("※内容を変更すると自動的に最上部へ移動し、赤く強調されます。")

    if combined_data:
        # 1. 元データの作成
        df_orig = pd.DataFrame(combined_data, columns=["アカウント", "行番号"] + REGISTRATION_HEADERS)
        
        # 2. 検索・フィルタ機能
        c_search1, c_search2 = st.columns([1, 2])
        filter_acc = c_search1.multiselect("👤 アカウントで絞り込み", POSTING_ACCOUNT_OPTIONS, key="filter_acc_3")
        filter_text = c_search2.text_input("🔍 キーワード検索 (店名・名前など)", key="filter_text_3")

        # 3. 編集用データのセッション管理
        if 'edited_df_3' not in st.session_state:
            st.session_state.edited_df_3 = df_orig.copy()

        working_df = st.session_state.edited_df_3.copy()

        # 4. 変更をチェックしてフラグを立てる
        # 元のデータと比較して1箇所でも違えば True
        diff_mask = (working_df != df_orig).any(axis=1)
        working_df.insert(0, "状態", diff_mask.map({True: "🔴 変更あり", False: "ー"}))

        # 5. ソート（変更ありを一番上、次にアカウント順）
        working_df = working_df.sort_values(by=["状態", "アカウント"], ascending=[False, True])

        # 6. フィルタリング実行
        if filter_acc:
            working_df = working_df[working_df["アカウント"].isin(filter_acc)]
        if filter_text:
            working_df = working_df[working_df.astype(str).apply(lambda x: filter_text.lower() in x.str.lower().any(), axis=1)]

        # 7. 表示スタイリング（変更箇所の行を赤くする）
        def highlight_changes(row):
            if row["状態"] == "🔴 変更あり":
                return ['background-color: #ffebee; color: #b71c1c; font-weight: bold'] * len(row)
            return [''] * len(row)

        styled_df = working_df.style.apply(highlight_changes, axis=1)

        # 8. データエディタ
        new_edited_df = st.data_editor(
            styled_df,
            key="main_editor_3",
            use_container_width=True,
            hide_index=True,
            disabled=["状態", "アカウント", "行番号"],
            height=600
        )

        # セッション状態の更新（再描画時に変更を維持するため）
        # ※ st.data_editor の戻り値から「状態」列を除いて保存
        st.session_state.edited_df_3 = new_edited_df.drop(columns=["状態"])

        # 9. 保存処理
        c_save1, c_save2 = st.columns([4, 1])
        if c_save2.button("🔥 一括保存", type="primary", use_container_width=True):
            changed_rows = new_edited_df[new_edited_df["状態"] == "🔴 変更あり"]
            
            if changed_rows.empty:
                st.warning("変更された箇所がありません。")
            else:
                with st.spinner("スプレッドシートを更新中..."):
                    try:
                        for acc_code in POSTING_ACCOUNT_OPTIONS:
                            acc_changes = changed_rows[changed_rows["アカウント"] == acc_code]
                            if acc_changes.empty: continue
                            
                            ws = SPRS.worksheet(POSTING_ACCOUNT_SHEETS[acc_code])
                            for _, row in acc_changes.iterrows():
                                row_idx = int(row["行番号"])
                                # 保存時は元のヘッダー順に並べ替え
                                update_values = [str(row[h]) for h in REGISTRATION_HEADERS]
                                ws.update(f"A{row_idx}:G{row_idx}", [update_values], value_input_option='USER_ENTERED')
                        
                        st.success(f"🎉 {len(changed_rows)}件の変更を保存しました！")
                        # 保存後はキャッシュとセッションをクリアして最新化
                        if 'edited_df_3' in st.session_state: del st.session_state.edited_df_3
                        st.rerun()
                    except Exception as e:
                        st.error(f"保存エラー: {e}")

        if c_save1.button("🔄 編集をリセット", use_container_width=False):
            if 'edited_df_3' in st.session_state: del st.session_state.edited_df_3
            st.rerun()

    else:
        st.info("編集可能なデータはありません。")
# =========================================================
# --- Tab 4: 📸 ④ 投稿画像管理 (ハイブリッド・ダウンロード版) ---
# =========================================================
with tab4:
    st.header("📸 投稿画像管理")
    
    # --- 1. キャッシュ関数 ---
    @st.cache_data(ttl=600)
    def get_gcs_hierarchy_v7():
        try:
            b = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
            blobs = GCS_CLIENT.list_blobs(GCS_BUCKET_NAME, prefix="", delimiter='/')
            list(blobs)
            areas = [p.replace("/", "") for p in blobs.prefixes if "【落ち店】" not in p and p != "/"]
            hierarchy = {}
            for area in areas:
                area_blobs = GCS_CLIENT.list_blobs(GCS_BUCKET_NAME, prefix=f"{area}/", delimiter='/')
                list(area_blobs)
                hierarchy[area] = [p for p in area_blobs.prefixes]
            return hierarchy
        except: return {}

    @st.cache_data(ttl=300)
    def get_image_list_cached_v7(path):
        b = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
        blobs = list(b.list_blobs(prefix=path))
        return [bl.name for bl in blobs if bl.name != path and bl.name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]

    hierarchy = get_gcs_hierarchy_v7()

    if hierarchy:
        c_sel1, c_sel2 = st.columns(2)
        selected_area = c_sel1.selectbox("📍 エリア", ["選択してください"] + list(hierarchy.keys()), key="sel_area_4")
        
        if selected_area != "選択してください":
            store_paths = hierarchy[selected_area]
            store_options = {p.split('/')[-2]: p for p in store_paths}
            selected_store_name = c_sel2.selectbox("🏢 店舗", ["選択してください"] + list(store_options.keys()), key="sel_store_4")

            if selected_store_name != "選択してください":
                target_path = store_options[selected_store_name]
                active_bucket = GCS_CLIENT.bucket(GCS_BUCKET_NAME)

                # --- アップロード ---
                with st.expander("➕ 画像をこの店舗に追加", expanded=False):
                    up_files = st.file_uploader("画像をドロップ", accept_multiple_files=True, type=["jpg","jpeg","png","webp"], key="up4_v7")
                    if st.button("🚀 アップロード開始", use_container_width=True):
                        if up_files:
                            for f in up_files:
                                active_bucket.blob(f"{target_path}{f.name}").upload_from_string(f.getvalue(), content_type=f.type)
                            st.cache_data.clear(); st.rerun()

                st.markdown("---")

                # --- 検索と操作 ---
                img_names = get_image_list_cached_v7(target_path)
                
                if img_names:
                    search_query = st.text_input("🔍 名前で検索", key="search_4_v7")
                    display_names = [n for n in img_names if search_query.lower() in n.split('/')[-1].lower()]

                    btn_c1, btn_c2, btn_c3, btn_c4 = st.columns([1, 1, 2, 2])
                    if btn_c1.button("✅ 全選択", use_container_width=True):
                        for n in display_names: st.session_state[f"del_4_{n}"] = True
                        st.rerun()
                    if btn_c2.button("⬜️ 解除", use_container_width=True):
                        for n in display_names: st.session_state[f"del_4_{n}"] = False
                        st.rerun()

                    selected_items = [n for n in display_names if st.session_state.get(f"del_4_{n}")]

                    # --- ハイブリッド・ダウンロード ---
                    if selected_items:
                        if len(selected_items) == 1:
                            # 1枚なら「生」で保存
                            path = selected_items[0]
                            file_name = path.split('/')[-1]
                            btn_c3.download_button(
                                label="💾 1枚を保存",
                                data=active_bucket.blob(path).download_as_bytes(),
                                file_name=file_name,
                                use_container_width=True,
                                type="primary"
                            )
                        else:
                            # 複数なら「ZIP」で保存
                            zip_buf = BytesIO()
                            with zipfile.ZipFile(zip_buf, "w") as zf:
                                for path in selected_items:
                                    zf.writestr(f"{selected_store_name}/{path.split('/')[-1]}", active_bucket.blob(path).download_as_bytes())
                            btn_c3.download_button(
                                label=f"⬇️ {len(selected_items)}枚をZIP保存",
                                data=zip_buf.getvalue(),
                                file_name=f"{selected_store_name}.zip",
                                use_container_width=True,
                                type="primary"
                            )

                        # --- 削除確認 ---
                        if btn_c4.button(f"🗑 {len(selected_items)}枚を削除", use_container_width=True, type="secondary"):
                            st.session_state.confirm_del_4 = True

                        if st.session_state.get("confirm_del_4"):
                            st.error(f"⚠️ 選択した {len(selected_items)} 枚を本当に削除しますか？")
                            conf_c1, conf_c2 = st.columns(2)
                            if conf_c1.button("⭕ 削除実行", type="primary", use_container_width=True):
                                for n in selected_items: active_bucket.blob(n).delete()
                                st.session_state.confirm_del_4 = False
                                st.cache_data.clear(); st.rerun()
                            if conf_c2.button("❌ キャンセル", use_container_width=True):
                                st.session_state.confirm_del_4 = False
                                st.rerun()

                    st.markdown(f"**表示中: {len(display_names)} 枚**")
                    
                    # --- 画像グリッド表示 ---
                    cols = st.columns(8)
                    for idx, b_name in enumerate(display_names):
                        with cols[idx % 8]:
                            short_name = b_name.split('/')[-1]
                            st.image(get_cached_url(b_name), use_container_width=True)
                            # 画像名を表示（見やすく改行対応）
                            st.caption(short_name)
                            st.checkbox("選", key=f"del_4_{b_name}", label_visibility="collapsed")
                else:
                    st.info("画像がありません。")

# --- Tab 5 ---
with tab5:
    st.header("5️⃣ 使用可能日記文")
    try:
        tmp_sprs = connect_to_gsheets(USABLE_DIARY_SHEET_ID)
        tmp_ws = tmp_sprs.worksheet("【使用可能日記文】")
        tmp_data = tmp_ws.get_all_values()
        if len(tmp_data) > 1:
            st.dataframe(pd.DataFrame(tmp_data[1:], columns=tmp_data[0]), use_container_width=True, height=600)
    except Exception as e: st.error(f"読み込みエラー: {e}")

# =========================================================
# --- Tab 6: 🖼 ⑥ 使用可能画像（落ち店） 高速版 ---
# =========================================================
with tab6:
    st.header("🖼 使用可能画像ブラウザ（落ち店）")
    
    ROOT_PATH = "【落ち店】/"
    
    # 落ち店専用の画像リスト取得キャッシュ
    @st.cache_data(ttl=300)
    def get_ochimise_images_cached(prefix, recursive=False):
        b = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
        # recursive=Trueの場合はdelimiterを指定せず全取得、Falseの場合は指定
        if recursive:
            blobs = list(b.list_blobs(prefix=prefix))
        else:
            blobs = list(b.list_blobs(prefix=prefix, delimiter='/'))
        return [bl.name for bl in blobs if bl.name != prefix and bl.name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]

    # 1. モード選択とフォルダ取得
    try:
        bucket = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
        blobs_init = GCS_CLIENT.list_blobs(GCS_BUCKET_NAME, prefix=ROOT_PATH, delimiter='/')
        list(blobs_init)
        folders = blobs_init.prefixes
    except: folders = []

    show_all = st.checkbox("📂 全画像表示（全ての店舗をまとめて表示）", key="show_all_ochimise")

    target_images = []
    current_label = "落ち店"

    if show_all:
        # 全表示モード
        target_images = get_ochimise_images_cached(ROOT_PATH, recursive=True)
        current_label = "全店舗一括"
    elif folders:
        # 店舗選択モード
        folder_opts = {f.replace(ROOT_PATH, "").replace("/", ""): f for f in folders}
        selected_key = st.selectbox("📁 店舗フォルダを選択", ["選択してください"] + list(folder_opts.keys()), key="sel_ochimise_folder")
        if selected_key != "選択してください":
            target_path = folder_opts[selected_key]
            target_images = get_ochimise_images_cached(target_path, recursive=False)
            current_label = selected_key

    # 2. アクションエリア
    if target_images:
        st.markdown("---")
        
        # 検索バー
        search_q = st.text_input("🔍 名前で検索 (落ち店内)", key="search_6")
        display_imgs = [n for n in target_images if search_q.lower() in n.split('/')[-1].lower()]

        # 操作ボタン
        c1, c2, c3, c4 = st.columns([1, 1, 2, 2])
        if c1.button("✅ 全選択", key="all_6", use_container_width=True):
            for n in display_imgs: st.session_state[f"sel_6_{n}"] = True
            st.rerun()
        if c2.button("⬜️ 解除", key="none_6", use_container_width=True):
            for n in display_imgs: st.session_state[f"sel_6_{n}"] = False
            st.rerun()

        selected_items = [n for n in display_imgs if st.session_state.get(f"sel_6_{n}")]

        if selected_items:
            # ハイブリッドダウンロード
            if len(selected_items) == 1:
                path = selected_items[0]
                c3.download_button("💾 1枚保存し削除", data=bucket.blob(path).download_as_bytes(), file_name=path.split('/')[-1], use_container_width=True, type="primary")
            else:
                zip_buf = BytesIO()
                with zipfile.ZipFile(zip_buf, "w") as zf:
                    for path in selected_items:
                        zf.writestr(f"落ち店_{current_label}/{path.split('/')[-1]}", bucket.blob(path).download_as_bytes())
                c3.download_button(f"⬇️ {len(selected_items)}枚ZIP保存し削除", data=zip_buf.getvalue(), file_name=f"落ち店_{current_label}.zip", use_container_width=True, type="primary")
            
            # 削除（保存せずに削除したい場合用）
            if c4.button(f"🗑 {len(selected_items)}枚を完全削除", use_container_width=True, type="secondary"):
                for n in selected_items: bucket.blob(n).delete()
                st.cache_data.clear(); st.rerun()

        st.write(f"**表示数: {len(display_imgs)}枚**")

        # 3. 画像グリッド（8列）
        cols = st.columns(8)
        for idx, b_name in enumerate(display_imgs):
            with cols[idx % 8]:
                st.image(get_cached_url(b_name), use_container_width=True)
                st.caption(b_name.split('/')[-1])
                st.checkbox("選", key=f"sel_6_{b_name}", label_visibility="collapsed")
    else:
        if not show_all: st.info("表示するフォルダを選択してください。")
        else: st.info("画像が見つかりませんでした。")









