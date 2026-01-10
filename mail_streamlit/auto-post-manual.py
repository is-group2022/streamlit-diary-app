import os
import re
import pandas as pd
from datetime import datetime, time
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from google.cloud import bigquery
from datetime import datetime, time, timedelta, timezone

# --- ページ設定 ---
st.set_page_config(page_title="自動日記運用マニュアル", layout="wide")

# --- 0. Googleスプレッドシートへの接続設定 (追加箇所) ---
try:
    scope = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scope
    )
    GC = gspread.authorize(credentials)
except Exception as e:
    st.error("Googleスプレッドシートの認証設定（Secrets）が見つかりません。")
    st.stop()

# --- モダンUIデザイン（文字を大きく、PCで見やすく） ---
st.markdown("""
    <style>
    html, body, [class*="css"] { font-size: 1.15rem; }
    .stTabs [data-baseweb="tab-list"] { gap: 15px; }
    .stTabs [data-baseweb="tab"] {
        height: 60px;
        background-color: #f1f5f9;
        border-radius: 10px 10px 0 0;
        padding: 10px 40px;
        font-weight: bold;
        font-size: 1.3rem !important;
    }
    .stTabs [aria-selected="true"] { background-color: #2563eb !important; color: white !important; }
    .card {
        background: white;
        padding: 2.5rem;
        border-radius: 1.5rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.08);
        border: 1px solid #e2e8f0;
        margin-bottom: 30px;
    }
    .cost-text { font-size: 4rem; font-weight: 900; color: #10B981; }
    </style>
    """, unsafe_allow_html=True)

# --- タイトル ---
st.title("🤖 自動日記運用マニュアル")
st.write("システムの稼働状況とマニュアルを統合管理しています。")

# --- 上部タブナビゲーションの定義 ---
tab_manual, tab_operation, tab_trouble, tab_billing = st.tabs([
    "📂 システムの仕組み (GCE/GCS)", 
    "📝 日常の操作手順", 
    "🆘 トラブル対応", 
    "📊 リアルタイム料金"
])

# --- 1. システムの仕組み (時刻比較・最新特定版) ---
with tab_manual:
    st.header("📊 システム稼働状況 ＆ インフラ解説")
    
    JST = timezone(timedelta(hours=+9), 'JST')
    
    st.markdown("#### 🔄 リアルタイム投稿確認")
    if st.button("最新の投稿状況をチェックする"):
        spreadsheet_id = "1sEzw59aswIlA-8_CTyUrRBLN7OnrRIJERKUZ_bELMrY"
        target_sheets = ["投稿Aアカウント", "投稿Bアカウント", "投稿Cアカウント", "投稿Dアカウント"]
        
        status_summary = []

        with st.spinner('全行から最新時刻のログを探索中...'):
            try:
                sh_status = GC.open_by_key(spreadsheet_id)
                
                for name in target_sheets:
                    try:
                        ws = sh_status.worksheet(name)
                        # 💡 範囲を広めに取得（H列を含むJ列まで）
                        raw_data = ws.get('A1:J2000') 
                        
                        latest_entry = None
                        latest_time_obj = None

                        if raw_data:
                            # 💡 全行をループして「時間」を比較する
                            for i, row in enumerate(raw_data):
                                if len(row) >= 8:
                                    status_cell = str(row[7]).strip()
                                    # 「完了: 12:34:56」のような形式から時刻を抽出
                                    match = re.search(r'(\d{1,2}:\d{2}:\d{2})', status_cell)
                                    if "完了" in status_cell and match:
                                        time_str = match.group(1)
                                        try:
                                            # 時刻文字列を比較可能なオブジェクトに変換
                                            current_time_obj = datetime.strptime(time_str, '%H:%M:%S')
                                            
                                            # 💡 暫定的に「今日」の出来事として比較
                                            if latest_time_obj is None or current_time_obj > latest_time_obj:
                                                latest_time_obj = current_time_obj
                                                latest_entry = {
                                                    "シート": name,
                                                    "状況": status_cell,
                                                    "店舗": row[1] if len(row) > 1 else "不明",
                                                    "行": i + 1
                                                }
                                        except:
                                            continue
                            
                        if latest_entry:
                            status_summary.append(latest_entry)
                        else:
                            status_summary.append({"シート": name, "状況": "💤 待機中", "店舗": "-", "行": "-"})
                        
                    except Exception as e:
                        status_summary.append({"シート": name, "状況": "⚠️ 読込エラー", "店舗": "-", "行": "-"})

                st.success(f"✅ 全行スキャン完了（確認時刻: {datetime.now(JST).strftime('%H:%M:%S')}）")
                st.table(pd.DataFrame(status_summary))

            except Exception as e:
                st.error(f"接続エラー: {e}")
    
    # --- インフラ解説セクション ---
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div class="card">
            <h2 style="color: #2563eb;">🚀 GCE (Compute Engine)</h2>
            <p><b>「24時間動く仮想パソコン」です。</b></p>
            <ul>
                <li>投稿A〜Dの各シートを順番に巡回して監視しています。</li>
                <li>空欄を見つけると投稿し、終わると<b>「完了:時刻」</b>を書き込みます。</li>
                <li><b>停止時間:</b> 毎日06:00〜11:00はお休みです。</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="card">
            <h2 style="color: #4285f4;">☁️ GCS (Cloud Storage)</h2>
            <p><b>「画像専用のオンライン倉庫」です。</b></p>
            <ul>
                <li>投稿に使用する写真は、すべてここに保存されます。</li>
                <li>画像がないと、GCEは投稿をスキップして次のアカウント（シート）へ移ります。</li>
                <li>その場合、H列は更新されないため「止まっている」ように見えます。</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

# --- 2. 日常の操作 ---
with tab_operation:
    st.header("📝 運用マニュアル：2つのアプリの使い分け")
    
    # URL設定
    URL_REGIST = "https://app-diary-app-krfts9htfjkvrq275esxfq.streamlit.app/"
    URL_EDIT = "https://app-diary-app-vstgarmm2invbrbxhuqpra.streamlit.app/"
    URL_REUSE = f"{URL_REGIST}?tab=④+使用可能日記文（ストック）"

    st.info("このシステムは、日々の「自動投稿予約」と、投稿の「データ編集」を自動化するために2つのアプリに分かれています。")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("✨ 1. 新規登録")
        st.markdown(f"**[登録アプリ]({URL_REGIST})** を使用。時間・名前・本文を入力して一括登録します。")
    with col2:
        st.subheader("🛠 2. 修正・確認")
        st.markdown(f"**[編集アプリ]({URL_EDIT})** を使用。登録内容の変更や画像の最終確認を行います。")

    st.divider()
    st.subheader("🚀 3. 店舗終了時のデータ整理（落ち店移動）")
    st.markdown("""
    店舗を落とした際は、**「落ち店移動」機能**を実行してください。
    手動で削除する手間を省き、大切な日記データを将来のために「倉庫」へ自動保管します。
    """)

    st.markdown(f"""
    <div style="background-color: #fff1f2; padding: 25px; border-radius: 12px; border-left: 6px solid #e11d48; margin-bottom: 25px;">
        <h4 style="color: #e11d48; margin-top: 0; display: flex; align-items: center;">
            <span style="font-size: 1.5rem; margin-right: 10px;">🛠</span> 移動の具体的なやり方
        </h4>
        <ol style="line-height: 2; font-weight: 500;">
            <li><a href="{URL_EDIT}" target="_blank" style="color: #e11d48; text-decoration: underline;">編集・管理用アプリ</a> を開く。</li>
            <li>タブ <b>「📊 ② 店舗アカウント状況」</b> を選択。</li>
            <li>一覧から終了する店舗に<b>チェック</b>を入れる。</li>
            <li>画面下の <b>「🚀 選択した店舗を【落ち店】へ移動する」</b> をクリック。</li>
            <li>赤い確認画面で <b>「⭕ はい、実行します」</b> を選択。</li>
        </ol>
    </div>

    <div style="background-color: #f8fafc; padding: 20px; border-radius: 12px; border: 1px solid #e2e8f0;">
        <h4 style="margin-top: 0; color: #334155;">❓ 移動するとデータはどうなる？</h4>
        <table style="width: 100%; border-collapse: collapse; font-size: 0.95rem;">
            <thead>
                <tr style="border-bottom: 2px solid #e2e8f0;">
                    <th style="text-align: left; padding: 10px; color: #64748b; width: 30%;">データ種別</th>
                    <th style="text-align: left; padding: 10px; color: #64748b;">移動後の状態</th>
                </tr>
            </thead>
            <tbody>
                <tr style="border-bottom: 1px solid #f1f5f9;">
                    <td style="padding: 12px; font-weight: bold;">📝 日記本文</td>
                    <td style="padding: 12px;">自動で倉庫へ転記されます。<br><a href="{URL_REUSE}" target="_blank" style="color: #2563eb; font-weight: bold;">[登録アプリのTab 3]</a> から再利用できます。</td>
                </tr>
                <tr style="border-bottom: 1px solid #f1f5f9;">
                    <td style="padding: 12px; font-weight: bold;">🔑 ログイン情報</td>
                    <td style="padding: 12px;">システムから自動削除。</td>
                </tr>
                <tr>
                    <td style="padding: 12px; font-weight: bold;">🖼 画像データ</td>
                    <td style="padding: 12px;">「【落ち店】フォルダ」へ移動。Tab 4で管理可能です。</td>
                </tr>
            </tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)

# --- 3. トラブル対応 ---
with tab_trouble:
    st.header("🆘 困った時の解決ガイド")
    URL_GCE = "https://console.cloud.google.com/compute/instances?project=project-d2e471f9-c395-4015-aea"
    ADMIN_EMAIL = "isgroup0001@gmail.com"

    with st.expander("❓ 投稿が動かない・「完了」にならない", expanded=True):
        st.markdown("""
        1. **名前がサイトと合っているか？**
        2. **H列（ステータス）が完全に空か？**
        3. **画像は準備できているか？**
        """)

    st.divider()
    st.subheader("🛠 システム起動方法（強制再起動）")
    st.error("⚠️ 注意：どうしても投稿が再開されない時だけ、以下の手順を順番に試してください。")

    st.markdown(f"### 1️⃣ Google Cloud にログインする")
    st.markdown(f"必ず **「アイエスグループ（{ADMIN_EMAIL}）」** のアカウントでログインしてください。")
    st.link_button("👉 Google Cloud コンソールを開く", URL_GCE)

    st.markdown("### 2️⃣ SSHボタンを押す")
    st.markdown("一覧にある `auto-post-server` の右側にある **「SSH」** をクリックします。")
    
    img_dir = os.path.dirname(__file__)
    def show_img(file_name, caption):
        path = os.path.join(img_dir, file_name)
        if not os.path.exists(path):
            path = os.path.join(img_dir, "mail_streamlit", file_name)
        if os.path.exists(path):
            st.image(path, caption=caption)
        else:
            st.warning(f"📸 画像 {file_name} が読み込めません。")

    show_img("image_980436.jpg", "この『SSH』をクリックしてください")

    st.markdown("### 3️⃣ 接続を「承認」する")
    st.markdown("「承認（Authorize）」ボタンを押して進めてください。")
    show_img("image_980437.jpg", "この画面が出たら『承認』または『Authorize』をクリック")

    st.markdown("### 4️⃣ コマンドを貼り付ける")
    st.markdown("文字が止まり、末尾に **$** マークが出たら下のコードを貼り付けてEnterキーを押してください。")
    show_img("image_980438.jpg", "この $ マークのあとに貼り付けてEnter！")

    REBOOT_COMMAND = "pkill -f main.py; nohup python3 main.py > system.log 2>&1 &"
    st.code(REBOOT_COMMAND, language="bash")
    
    st.markdown("""
    <div style="background-color: #f8fafc; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; margin-top: 10px;">
        <p style="margin-bottom: 5px; font-weight: bold;">✅ 操作が終わったら</p>
        <p style="font-size: 0.9rem; color: #475569; margin-bottom: 0;">
            ・Enterを押して新しい行が出れば成功。5〜10分後にH列を確認してください。
        </p>
    </div>
    """, unsafe_allow_html=True)

# --- 4. リアルタイム料金 ---
with tab_billing:
    st.header("📊 利用料金のモニタリング")
    current_cost_usd = 0.00
    st.markdown(f"""
    <div class="card">
        <h3>今月の概算利用料</h3>
        <span class="cost-text">¥ {int(current_cost_usd * 150):,}</span>
        <p style="color: gray;">※設定後、BigQueryにデータが届くまで最大24時間かかります。</p>
        <hr>
        <p><b>無料トライアル残高：</b> ￥44,112</p>
        <p><b>終了予定：</b> 2026年3月14日</p>
    </div>
    """, unsafe_allow_html=True)













