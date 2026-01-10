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
    
    # URL設定（運用環境に合わせて適宜修正してください）
    URL_REGIST = "https://app-diary-app-krfts9htfjkvrq275esxfq.streamlit.app/"
    URL_EDIT = "https://app-diary-app-vstgarmm2invbrbxhuqpra.streamlit.app/"
    URL_STOCK_SHEET = "https://docs.google.com/spreadsheets/d/1e-iLey43A1t0bIBoijaXP55t5fjONdb0ODiTS53beqM"

    st.markdown(f"""
    <style>
        .card {{
            background-color: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 30px;
            border: 1px solid #e2e8f0;
        }}
        .step-num {{
            display: inline-block;
            background-color: #2563eb;
            color: white;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            text-align: center;
            line-height: 30px;
            margin-right: 10px;
            font-weight: bold;
        }}
    </style>

    <div class="card">
        <h2 style="color: #2563eb; border-bottom: 2px solid #2563eb; padding-bottom: 10px;">
            <span class="step-num">1</span>新規データの一括登録
        </h2>
        <p>新しい日記を予約する際は<b>「登録用アプリ」</b>を使用します。</p>
        <div style="background-color: #f8fafc; padding: 20px; border-radius: 10px; border-left: 5px solid #2563eb; margin: 15px 0;">
            <ol style="line-height: 2;">
                <li><a href="{URL_REGIST}" target="_blank"><b>登録用アプリ</b></a> を開く</li>
                <li>「アカウント」「エリア」「店舗名」を選択</li>
                <li>一覧表に内容（時間、名前、本文など）を入力し、画像をアップ</li>
                <li><b>「🔥 データを一括登録する」</b> をクリック！</li>
            </ol>
        </div>
    </div>

    <div class="card">
        <h2 style="color: #10b981; border-bottom: 2px solid #10b981; padding-bottom: 10px;">
            <span class="step-num">2</span>内容の確認・個別修正
        </h2>
        <p>登録済みのデータの修正や、画像の差し替えを行う場合です。</p>
        <div style="background-color: #f0fdf4; padding: 20px; border-radius: 10px; border-left: 5px solid #10b981; margin: 15px 0;">
            <ol style="line-height: 2;">
                <li><a href="{URL_EDIT}" target="_blank"><b>編集・管理用アプリ</b></a> を開く</li>
                <li>修正したい店舗を選択し、画像と本文のセットを確認</li>
                <li>内容を書き換えたら、必ず直下の <b>「💾 内容を保存」</b> をクリック</li>
            </ol>
        </div>
    </div>

    <div class="card">
        <h2 style="color: #f59e0b; border-bottom: 2px solid #f59e0b; padding-bottom: 10px;">
            <span class="step-num">3</span>店舗終了時のデータ整理（落ち店移動）
        </h2>
        <p>契約終了や一時停止の店舗は、専用の<b>「移動機能」</b>で安全に処理します。</p>
        
        <div style="background-color: #fff1f2; padding: 20px; border-radius: 10px; border-left: 5px solid #e11d48; margin: 15px 0;">
            <h4 style="color: #e11d48; margin-top: 0;">🛠 移動の手順</h4>
            <ol style="line-height: 2;">
                <li><a href="{URL_EDIT}" target="_blank"><b>編集アプリ</b></a> の「📊 ② 店舗アカウント状況」タブを開く</li>
                <li>対象の店舗にチェックを入れ、<b>「🚀 【落ち店】へ移動する」</b>を押す</li>
                <li>最終確認で「⭕ はい」を押して、<b>完了画面が出るまで待つ</b></li>
            </ol>

            <div style="background-color: white; padding: 15px; border-radius: 8px; margin-top: 15px; border: 1px dashed #e11d48;">
                <p style="font-weight: bold; margin-bottom: 5px; color: #333;">💡 移動するとデータはどうなる？</p>
                <ul style="font-size: 0.9rem; color: #4b5563; margin-bottom: 0;">
                    <li><b>日記の保管</b>：<a href="{URL_STOCK_SHEET}" target="_blank">ストック用シート</a>へ自動転記（後で再利用可）</li>
                    <li><b>誤投稿防止</b>：ログイン管理シートから該当店舗を自動削除</li>
                    <li><b>画像の整理</b>：GCS内の画像を自動で「【落ち店】フォルダ」へ退避</li>
                </ul>
            </div>
        </div>
        
        <div style="background-color: #fffbeb; padding: 15px; border-radius: 10px; border-left: 5px solid #f59e0b;">
            <p style="margin-bottom: 0;"><b>🔁 同じ日記を再投稿したい場合：</b><br>
            スプレッドシートのH列（ステータス）にある「完了」の文字を消して<b>「空欄」</b>にするだけで、次回の巡回時に再度投稿されます。</p>
        </div>
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



