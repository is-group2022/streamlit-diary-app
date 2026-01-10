import streamlit as st
import pandas as pd
from google.cloud import bigquery

# --- ページ設定 ---
st.set_page_config(page_title="AUTO-POST 運用管理", layout="wide")

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
st.title("🤖 自動投稿システム 総合管理ポータル")
st.write("PC閲覧専用：システムの稼働状況とマニュアルを統合管理しています。")

# --- 上部タブナビゲーションの定義 (ここで名前を確定させます) ---
tab_manual, tab_operation, tab_trouble, tab_billing = st.tabs([
    "📂 システムの仕組み (GCE/GCS)", 
    "📝 日常の操作手順", 
    "🆘 トラブル対応", 
    "📊 リアルタイム料金"
])

# --- 1. システムの仕組み (GCE/GCSを詳しく解説) ---
with tab_manual:
    st.header("1. クラウドインフラの解説")
    
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div class="card">
            <h2 style="color: #2563eb;">🚀 GCE (Compute Engine)</h2>
            <p><b>「24時間動く仮想パソコン」です。</b></p>
            <ul>
                <li>Googleのデータセンター内で、あなたのプログラムを実行し続けます。</li>
                <li><b>役割:</b> スプレッドシートを監視し、時間になったらブラウザを自動操作して投稿します。</li>
                <li><b>メリット:</b> 自宅のPCを閉じても、ネット上で作業が完結します。</li>
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
                <li><b>役割:</b> サーバー(GCE)が投稿時にここへ写真を取りに来ます。</li>
                <li><b>ルール:</b> ファイル名の先頭を「時間_名前」にすることで、システムが正しく写真を識別します。</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

# --- 2. 日常の操作 ---
with tab_operation:
    st.header("📝 日々の運用ルール")
    st.markdown("""
    <div class="card">
        <h3>✅ 投稿予約の3ステップ</h3>
        <ol>
            <li><b>スプレッドシート更新</b>: G列に時間(1200等)、F列に名前を入力。</li>
            <li><b>ステータス解除</b>: H列を「空欄」にする（ここが埋まっていると動きません）。</li>
            <li><b>画像確認</b>: GCSに指定のファイル名で画像があるかチェック。</li>
        </ol>
        <hr>
        <h3>🔄 再投稿したい場合</h3>
        <p>H列に「完了」と出ていても、その文字を消して<b>空欄にするだけ</b>で、次の巡回時に再度投稿が始まります。</p>
    </div>
    """, unsafe_allow_html=True)

# --- 3. トラブル対応 (エラーが出ていた箇所) ---
with tab_trouble:
    st.header("🆘 トラブル解決ガイド")
    
    with st.expander("特定の投稿が「失敗」になる、または反応しない", expanded=True):
        st.markdown("""
        - **名前の完全一致**: サイト上の名前とシートの名前が1文字でも違う（空白や全角など）と失敗します。
        - **H列の状態**: 半角スペースなどが入っていませんか？一度デリートキーで完全に消してください。
        - **画像不足**: GCSに、その時間に合わせた画像が入っているか確認してください。
        """)

    with st.expander("🛠 管理者用：プログラムの強制再起動"):
        st.warning("システムが完全に停止した時のみ実行してください。")
        st.code("pkill -f main.py && nohup python3 main.py > system.log 2>&1 &", language="bash")

# --- 4. リアルタイム料金 ---
with tab_billing:
    st.header("📊 利用料金のモニタリング")
    
    # 実際はBigQueryから取得しますが、設定反映待機用の表示
    current_cost_usd = 0.00  # データが届くとここが更新されます
    
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
