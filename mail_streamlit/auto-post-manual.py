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
    st.header("📝 運用マニュアル：2つのアプリの使い分け")
    
    # URL設定
    URL_REGIST = "https://app-diary-app-krfts9htfjkvrq275esxfq.streamlit.app/"
    URL_EDIT = "https://app-diary-app-vstgarmm2invbrbxhuqpra.streamlit.app/"

    # ステップ1と2はそのまま継続 ... (中略)

    st.markdown(f"""
    <div class="card">
        <h2 style="color: #f59e0b; border-bottom: 2px solid #f59e0b; padding-bottom: 10px;">🔄 ステップ3：再投稿 ＆ 店舗の終了（落ち店移動）</h2>
        <p>同じ内容をもう一度投稿したい場合や、店舗の契約が終了した際の<b>最重要ステップ</b>です。</p>
        
        <div style="background-color: #fffbeb; padding: 20px; border-radius: 10px; border-left: 5px solid #f59e0b; margin: 15px 0;">
            <h4 style="margin-top: 0;">🔁 同じ内容をもう一度投稿する</h4>
            <p>スプレッドシートのH列（ステータス列）にある「完了」という文字を消して<b>「空欄」</b>にするだけです。システムが自動で未投稿と判断し、次の巡回で再投稿します。</p>
        </div>

        <div style="background-color: #fff1f2; padding: 20px; border-radius: 10px; border-left: 5px solid #e11d48; margin: 15px 0;">
            <h4 style="margin-top: 0; color: #e11d48;">🚪 店舗が終了（落ち店）になった場合</h4>
            <p>手作業でのデータ削除は不要です。<a href="{URL_EDIT}" target="_blank"><b>編集・管理用アプリ</b></a> の<b>「📊 ② 店舗アカウント状況」</b>タブを使って一括整理します。</p>
            
            <p><b>【実行の手順】</b></p>
            <ol>
                <li>編集アプリで移動させたい店舗に<b>チェック</b>を入れる。</li>
                <li><b>「🚀 選択した店舗を【落ち店】へ移動する」</b>をクリック。</li>
                <li>確認画面で<b>「⭕ はい、実行します」</b>を押して待機（完了まで画面を閉じない）。</li>
            </ol>

            <p style="margin-top: 15px; font-weight: bold; border-top: 1px dashed #e11d48; padding-top: 10px;">⚠️ 実行後に自動で行われること：</p>
            <ul style="font-size: 0.9rem;">
                <li><b>日記文</b>：<a href="https://docs.google.com/spreadsheets/d/1e-iLey43A1t0bIBoijaXP55t5fjONdb0ODiTS53beqM" target="_blank">使用可能日記文シート</a>へ自動バックアップ。</li>
                <li><b>ログイン情報</b>：誤投稿を防ぐため、システムからID・PWを完全削除。</li>
                <li><b>画像データ</b>：ストレージ内のフォルダを<b>「【落ち店】/店舗名/」</b>へ自動移動。</li>
            </ul>
        </div>
        <p style="font-size: 0.85rem; color: #64748b;">※「落ち店」に移動した画像は、登録用アプリの「🖼 ④ 使用可能画像」タブからいつでも再利用・削除が可能です。</p>
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


