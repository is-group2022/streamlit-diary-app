import streamlit as st
import pandas as pd
from google.cloud import bigquery
from datetime import datetime

# --- ページ設定 ---
st.set_page_config(
    page_title="AUTO-POST 管理システム",
    page_icon="🤖",
    layout="wide"
)

# --- モダンUIデザイン（CSS） ---
st.markdown("""
    <style>
    /* 全体フォント設定 */
    html, body, [class*="css"] {
        font-size: 1.15rem;
        font-family: 'Inter', 'Noto Sans JP', sans-serif;
    }
    /* ヘッダー */
    .header-box {
        background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
        padding: 50px;
        border-radius: 25px;
        color: white;
        text-align: center;
        margin-bottom: 40px;
        box-shadow: 0 15px 30px rgba(0,0,0,0.1);
    }
    /* カード */
    .info-card {
        background: white;
        padding: 35px;
        border-radius: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.06);
        border: 1px solid #f1f5f9;
        margin-bottom: 30px;
        min-height: 300px;
    }
    .info-card h2 { color: #2563eb; font-size: 2rem; margin-bottom: 20px; }
    .info-card h3 { color: #475569; font-size: 1.5rem; margin-top: 20px; }
    /* タブのデザイン変更 */
    .stTabs [data-baseweb="tab-list"] { gap: 15px; }
    .stTabs [data-baseweb="tab"] {
        height: 70px;
        padding: 0 40px;
        background-color: #f8fafc;
        border-radius: 12px 12px 0 0;
        font-size: 1.4rem !important;
        font-weight: bold;
    }
    .stTabs [aria-selected="true"] {
        background-color: #2563eb !important;
        color: white !important;
    }
    /* 料金テキスト */
    .cost-value {
        font-size: 4rem;
        font-weight: 900;
        color: #10b981;
        line-height: 1;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 料金データ取得関数 ---
def get_billing_data():
    try:
        # サービスアカウントの認証が通っている前提
        client = bigquery.Client()
        
        # ⚠️ ここを自分のプロジェクトIDとテーブル名に書き換えてください
        # テーブル名は明日の今頃にBigQueryの「billing_data」の中に生成されます
        PROJECT_ID = "あなたのプロジェクトID"
        DATASET_ID = "billing_data"
        TABLE_NAME = "gcp_billing_export_v1_XXXXX" 
        
        query = f"""
            SELECT
              service.description as service,
              SUM(cost) as cost
            FROM `{PROJECT_ID}.{DATASET_ID}.{TABLE_NAME}`
            WHERE invoice.month = FORMAT_DATE('%Y%m', CURRENT_DATE())
            GROUP BY 1
            ORDER BY cost DESC
        """
        df = client.query(query).to_dataframe()
        return df
    except Exception as e:
        # データがまだない場合のダミーデータ
        return pd.DataFrame()

# --- メインヘッダー ---
st.markdown("""
    <div class="header-box">
        <h1 style='font-size: 3.5rem; margin-bottom: 10px;'>🤖 AUTO-POST PORTAL</h1>
        <p style='font-size: 1.3rem; opacity: 0.9;'>次世代自動日記投稿システム 運用・コスト管理ダッシュボード</p>
    </div>
    """, unsafe_allow_html=True)

# --- ナビゲーションタブ ---
tab_sys, tab_op, tab_faq, tab_cost = st.tabs([
    "📂 システム解説", 
    "📝 運用マニュアル", 
    "🆘 トラブル対応", 
    "💳 リアルタイムコスト"
])

# --- 1. システム解説 ---
with tab_sys:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div class="info-card">
            <h2>🚀 GCE (Compute Engine)</h2>
            <p><strong>「クラウド上の司令塔」</strong>です。</p>
            <p>24時間365日、設定された時間にブラウザ（Chrome）を自動で立ち上げ、サイトへアクセスして日記を投稿し続けます。あなたのPCの電源を切っても、このサーバーが仕事を肩代わりします。</p>
            <h3>主な役割</h3>
            <ul>
                <li>スプレッドシートの監視</li>
                <li>画像のダウンロードとアップロード</li>
                <li>投稿完了後のステータス更新</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="info-card">
            <h2>☁️ GCS (Cloud Storage)</h2>
            <p><strong>「ネット上の画像倉庫」</strong>です。</p>
            <p>投稿に必要な画像データを安全に保管します。プログラムはここへ写真を取りに行き、使い終わった後も元データはここに残ります。</p>
            <h3>運用のコツ</h3>
            <ul>
                <li>ファイル名を「時間(4桁)_名前」にするだけ。</li>
                <li>エリアや店舗ごとにフォルダを分けることで管理が容易になります。</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

# --- 2. 運用マニュアル ---
with tab_op:
    st.markdown("""
    <div class="info-card" style="border-left: 10px solid #2563eb;">
        <h2>📝 日常の操作フロー</h2>
        <div style="font-size: 1.3rem; line-height: 2;">
            1️⃣ <b>スプレッドシートへの入力</b>：G列に投稿時間（例：1300）を入力。<br>
            2️⃣ <b>画像の準備</b>：GCSに画像をアップロード。名前と時間が合っているか確認。<br>
            3️⃣ <b>予約完了</b>：H列（ステータス）を「空欄」にする。これだけで予約完了です。<br>
            4️⃣ <b>再投稿</b>：一度「完了」になったものを再度送るなら、H列を消すだけ。
        </div>
        <br>
        <p style="color: #ef4444; font-weight: bold;">⚠️ 注意：毎日 06:00 - 10:00 はシステムメンテナンスのため自動停止します。</p>
    </div>
    """, unsafe_allow_html=True)

# --- 3. トラブル対応 ---
with tab_trouble:
    st.markdown("## 🆘 困ったときのチェックリスト")
    
    with st.expander("❓ 時間になっても投稿されない", expanded=True):
        st.write("""
        - **H列を確認**: 空白（スペース）が入っていませんか？完全に空欄にしてください。
        - **時間をチェック**: システムは指定時間の前後7分間だけ作動します。
        - **名前の一致**: サイトの登録名と一文字も違わず同じか確認してください。
        """)
        
    with st.expander("❓ サーバーを再起動したい（エンジニア向け）"):
        st.warning("この操作はシステムが完全に止まった場合のみ行ってください。")
        st.code("pkill -f main.py && nohup python3 main.py > system.log 2>&1 &", language="bash")
        st.code("tail -f system.log", language="bash")

# --- 4. リアルタイム料金 ---
with tab_cost:
    st.markdown("## 💳 クラウド利用コスト")
    
    billing_df = get_billing_data()
    
    if not billing_df.empty:
        total_usd = billing_df['cost'].sum()
        exchange_rate = 150.0 # 為替レート
        
        c1, c2 = st.columns([1, 1.5])
        with c1:
            st.markdown(f"""
            <div class="info-card" style="text-align: center;">
                <h3>今月の累積利用料</h3>
                <p class="cost-value">¥ {int(total_usd * exchange_rate):,}</p>
                <p style="color: gray;">(約 ${total_usd:.2f} USD)</p>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.write("### サービス別内訳")
            st.bar_chart(billing_df.set_index('service'))
    else:
        st.info("💡 BigQueryの請求データ反映待ちです（設定から最大24時間）。データが届くとここにグラフが表示されます。")
        st.markdown(f"""
        <div class="info-card">
            <h3>現在のクレジット状況</h3>
            <p><b>無料トライアル残高：</b> ￥44,112</p>
            <p><b>終了予定：</b> 2026年3月14日</p>
            <p style="font-size: 0.9rem; color: gray;">※アップグレード後の有効なクレジットはそのまま保持されます。</p>
        </div>
        """, unsafe_allow_html=True)
