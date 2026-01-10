import streamlit as st
import pandas as pd

# --- ページ設定 ---
st.set_page_config(page_title="AUTO-POST DASHBOARD", layout="wide")

# --- カスタムCSS（PC向け・高精細デザイン） ---
st.markdown("""
    <style>
    /* 全体のフォントサイズ */
    html, body, [class*="css"] {
        font-size: 1.15rem;
        font-family: 'Inter', sans-serif;
    }
    /* ヘッダーデザイン */
    .header-box {
        background: linear-gradient(90deg, #1E1E2F 0%, #4E4E6A 100%);
        padding: 40px;
        border-radius: 20px;
        color: white;
        text-align: center;
        margin-bottom: 30px;
        box-shadow: 0 10px 20px rgba(0,0,0,0.2);
    }
    /* カードデザイン */
    .card {
        background-color: white;
        padding: 30px;
        border-radius: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        border: 1px solid #E5E7EB;
        margin-bottom: 25px;
    }
    .card h2 { color: #2563EB; border-bottom: 2px solid #F3F4F6; padding-bottom: 10px; }
    .price-card {
        background-color: #F8FAFC;
        border-left: 10px solid #10B981;
    }
    /* タブの文字を大きく */
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 1.5rem;
        font-weight: bold;
        padding: 10px 20px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- タイトルセクション ---
st.markdown("""
    <div class="header-box">
        <h1>🤖 自動日記投稿システム 管理・運用ポータル</h1>
        <p>GCEサーバー稼働状況・運用マニュアル・料金管理</p>
    </div>
    """, unsafe_allow_html=True)

# --- 上部ナビゲーション（タブ） ---
tab_main, tab_op, tab_error, tab_cost = st.tabs([
    "📂 システムの仕組み", 
    "📝 日常の操作", 
    "🆘 トラブル対応", 
    "💰 料金・サーバー管理"
])

# --- 1. システムの仕組み ---
with tab_main:
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div class="card">
            <h2>🚀 GCE (Compute Engine)</h2>
            <p><strong>「24時間動く仮想パソコン」</strong>です。</p>
            <ul>
                <li>Googleのデータセンター内で、あなたのプログラムを実行し続けます。</li>
                <li>ブラウザ(Chrome)を自動起動し、日記サイトへアクセスします。</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown("""
        <div class="card">
            <h2>☁️ GCS (Cloud Storage)</h2>
            <p><strong>「画像のオンライン倉庫」</strong>です。</p>
            <ul>
                <li>スプレッドシートの指示に従い、この倉庫から写真を取り出します。</li>
                <li>ファイル名が間違っていると、写真は投稿されません。</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

# --- 2. 日常の操作 ---
with tab_op:
    st.markdown("""
    <div class="card">
        <h2>✅ 運用フロー</h2>
        <ol>
            <li><strong>スプレッドシートの編集</strong>: G列に時間(1200)、F列に名前を入力。</li>
            <li><strong>ステータス解除</strong>: 再投稿時はH列を空欄にする。</li>
            <li><strong>朝の自動処理</strong>: 06:00-10:00は全自動メンテナンス時間です。</li>
        </ol>
    </div>
    """, unsafe_allow_html=True)

# --- 3. トラブル対応 ---
with tab_error:
    st.error("🚨 異常を感じた場合は以下の項目を確認してください")
    exp1 = st.expander("投稿がスキップされる", expanded=True)
    exp1.write("H列に何か文字（完了や失敗、スペース）が入っていませんか？システムは「完全に空」のセルしか処理しません。")
    
    exp2 = st.expander("画像がアップロードされない")
    exp2.write("GCSのバケット内に、[エリア/店舗名/時間_名前.jpg] の形式で画像があるか確認してください。")

# --- 4. 料金・サーバー管理 ---
with tab_cost:
    st.markdown("## 💰 運用コストの見積り")
    
    # 料金シミュレーター（手入力やAPI連携の代わりに）
    c1, c2, c3 = st.columns(3)
    with c1:
        gce_cost = st.number_input("GCE 月額料金 (USD)", value=25.0)
    with c2:
        gcs_cost = st.number_input("GCS ストレージ料金 (USD)", value=5.0)
    with c3:
        exchange_rate = st.number_input("為替レート (JPY/USD)", value=150.0)
    
    total_jpy = (gce_cost + gcs_cost) * exchange_rate
    
    st.markdown(f"""
    <div class="card price-card">
        <h3>📊 今月の概算コスト</h3>
        <h1 style='color: #10B981;'>¥ {total_jpy:,.0f} <small style='font-size: 1rem; color: gray;'>/ 月</small></h1>
        <p>内訳: GCE(${gce_cost}) + GCS(${gcs_cost}) = Total(${gce_cost + gcs_cost})</p>
    </div>
    """, unsafe_allow_html=True)

    st.divider()
    st.subheader("🛠 エンジニア用復旧コマンド")
    st.code("pkill -f main.py && nohup python3 main.py > system.log 2>&1 &", language="bash")
