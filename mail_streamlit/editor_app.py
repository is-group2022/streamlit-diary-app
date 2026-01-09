import streamlit as st
import pandas as pd
import gspread
import datetime
import urllib.parse
from google.oauth2.service_account import Credentials
from google.cloud import storage

# --- 1. 設定と定数 ---
try:
    SHEET_ID = st.secrets["google_resources"]["spreadsheet_id"]
    GCS_BUCKET_NAME = "auto-poster-images"
    POSTING_ACCOUNT_SHEETS = {
        "A": "投稿Aアカウント",
        "B": "投稿Bアカウント",
        "C": "投稿Cアカウント",
        "D": "投稿Dアカウント"
    }
    POSTING_ACCOUNT_OPTIONS = ["A", "B", "C", "D"]
    REGISTRATION_HEADERS = ["エリア", "店名", "媒体", "投稿時間", "女の子の名前", "タイトル", "本文"]
except KeyError:
    st.error("🚨 secrets.tomlの設定を確認してください。")
    st.stop()

# --- 2. API連携 (閲覧専用に最適化) ---
@st.cache_resource(ttl=3600)
def get_gspread_client():
    return gspread.service_account_from_dict(st.secrets["gcp_service_account"])

@st.cache_resource(ttl=3600)
def get_gcs_client():
    return storage.Client.from_service_account_info(st.secrets["gcp_service_account"])

GC = get_gspread_client()
GCS_CLIENT = get_gcs_client()
SPRS = GC.open_by_key(SHEET_ID)

def get_cached_url(blob_name):
    """公開URLを生成（API通信なし）"""
    safe_path = urllib.parse.quote(blob_name)
    return f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{safe_path}"

# --- 3. UI設定 ---
st.set_page_config(layout="wide", page_title="日記×画像 マッチング編集")

# ヘッダーを消すCSS
st.markdown("<style>header[data-testid='stHeader'] { display: none !important; }</style>", unsafe_allow_html=True)

def main():
    st.title("📝 日記×画像 マッチング編集部")
    st.caption("エリアと店舗を選択すると、日記データとGCS画像を自動で照合します。")

    # --- ステップ1: エリア・店舗選択 ---
    # API節約のため、全シートから店舗リストを生成
    all_data = []
    for s_name in POSTING_ACCOUNT_SHEETS.values():
        try:
            rows = SPRS.worksheet(s_name).get_all_values()
            if len(rows) > 1:
                df_tmp = pd.DataFrame(rows[1:], columns=rows[0])
                df_tmp['__sheet__'] = s_name
                df_tmp['__row__'] = range(2, len(rows) + 1)
                all_data.append(df_tmp)
        except: continue
    
    if not all_data:
        st.warning("データが見つかりません。")
        return

    full_df = pd.concat(all_data)
    
    c1, c2 = st.columns(2)
    areas = sorted(full_df["エリア"].unique())
    selected_area = c1.selectbox("📍 エリアを選択", ["未選択"] + areas)
    
    if selected_area != "未選択":
        stores = sorted(full_df[full_df["エリア"] == selected_area]["店名"].unique())
        selected_store = c2.selectbox("🏢 店舗を選択", ["未選択"] + stores)
        
        if selected_store != "未選択":
            # 選択された店舗の日記を抽出
            target_df = full_df[(full_df["エリア"] == selected_area) & (full_df["店名"] == selected_store)]
            
            # GCSから画像リストを取得
            bucket = GCS_CLIENT.bucket(GCS_BUCKET_NAME)
            # フォルダ名のルールに対応（デリじゃ対応）
            media_type = target_df.iloc[0]["媒体"]
            folder_name = f"デリじゃ {selected_store}" if media_type == "デリじゃ" else selected_store
            prefix = f"{selected_area}/{folder_name}/"
            
            blobs = list(bucket.list_blobs(prefix=prefix))
            image_names = [b.name for b in blobs if b.name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
            
            st.divider()
            st.subheader(f"📊 {selected_store} の照合結果 ({len(target_df)}件)")

            # --- ステップ2: 照合と表示 ---
            for idx, row in target_df.iterrows():
                # 照合キー: 投稿時間_女の子の名前 (例: 1200_ゆあ)
                match_key = f"{str(row['投稿時間']).strip()}_{str(row['女の子の名前']).strip()}"
                
                # 画像リストから部分一致するものを探す
                matched_images = [img for img in image_names if match_key in img]
                
                with st.container(border=True):
                    col_info, col_edit, col_img = st.columns([1, 2, 1])
                    
                    with col_info:
                        st.write(f"**⏰ {row['投稿時間']}**")
                        st.write(f"**👤 {row['女の子の名前']}**")
                        if matched_images:
                            st.success("✅ 画像一致")
                        else:
                            st.error("🚨 画像なし")
                            st.caption(f"検索キー: {match_key}")

                    with col_edit:
                        new_title = st.text_input("タイトル", value=row["タイトル"], key=f"ti_{idx}")
                        new_body = st.text_area("本文", value=row["本文"], key=f"bo_{idx}", height=100)
                        
                        if st.button("💾 この内容で更新", key=f"btn_{idx}"):
                            try:
                                ws = SPRS.worksheet(row['__sheet__'])
                                # 列番号 A=1, B=2, C=3, D=4, E=5, F=6, G=7
                                ws.update_cell(row['__row__'], 6, new_title) # F列: タイトル
                                ws.update_cell(row['__row__'], 7, new_body)  # G列: 本文
                                st.success("更新しました！")
                                st.cache_data.clear()
                            except Exception as e:
                                st.error(f"更新失敗: {e}")

                    with col_img:
                        if matched_images:
                            # 公開URLを使用して表示
                            img_url = get_cached_url(matched_images[0])
                            st.image(img_url, use_container_width=True)
                            st.caption(matched_images[0].split('/')[-1])
                        else:
                            st.info("画像がありません")

if __name__ == "__main__":
    main()
