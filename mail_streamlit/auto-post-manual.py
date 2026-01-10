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
    
    # URL設定（実際のURLに書き換えてください）
    URL_REGIST = "https://app-diary-app-krfts9htfjkvrq275esxfq.streamlit.app/"
    URL_EDIT = "https://app-diary-app-vstgarmm2invbrbxhuqpra.streamlit.app/"

    st.markdown(f"""
    <div class="card">
        <h2 style="color: #2563eb; border-bottom: 2px solid #2563eb; padding-bottom: 10px;">✨ ステップ1：新規データの登録</h2>
        <p>新しい日記を投稿予約するときは<b>「登録用アプリ」</b>を使います。最大40件まで一気に仕込めます。</p>
        <div style="background-color: #f8fafc; padding: 20px; border-radius: 10px; border-left: 5px solid #2563eb; margin: 20px 0;">
            <ol style="line-height: 2;">
                <li><a href="{URL_REGIST}" target="_blank"><b>登録用アプリ</b></a> を開く。</li>
                <li>上部パネルで<b>「アカウント(A〜D)」「エリア」「店名」</b>を選択。</li>
                <li>下の一覧に<b>「時間・名前・タイトル・本文」</b>を入力し、画像をアップロード。</li>
                <li>一番下の <b>「🔥 データを一括登録する」</b> をクリック！</li>
            </ol>
        </div>
        <p style="font-size: 0.9rem; color: #64748b;">※画像はシステムが自動的に「時間_名前」の名前にリネームして保存するので、元のファイル名は何でもOKです。</p>
    </div>

    <div class="card">
        <h2 style="color: #10b981; border-bottom: 2px solid #10b981; padding-bottom: 10px;">🛠 ステップ2：内容の確認・修正</h2>
        <p>「登録した内容を直したい」「画像が合っているか見たい」ときは<b>「編集・管理用アプリ」</b>を使います。</p>
        <div style="background-color: #f0fdf4; padding: 20px; border-radius: 10px; border-left: 5px solid #10b981; margin: 20px 0;">
            <ol style="line-height: 2;">
                <li><a href="{URL_EDIT}" target="_blank"><b>編集・管理用アプリ</b></a> を開く。</li>
                <li>直したい店舗を選択すると、登録済みの日記と<b>画像がセットで表示</b>されます。</li>
                <li>本文を書き換えたら、そのすぐ下の <b>「💾 内容を保存」</b> をクリック。</li>
                <li>画像が足りない場合は「画像追加」からその場でアップロード可能です。</li>
            </ol>
        </div>
    </div>

    <div class="card">
        <h2 style="color: #f59e0b; border-bottom: 2px solid #f59e0b; padding-bottom: 10px;">🔄 ステップ3：再投稿・メンテナンス</h2>
        <p>同じ内容をもう一度投稿したい場合や、契約終了時のデータ整理について。</p>
        <div style="background-color: #fffbeb; padding: 20px; border-radius: 10px; border-left: 5px solid #f59e0b; margin: 20px 0;">
            <ul style="line-height: 2; list-style-type: none; padding-left: 0;">
                <li><b>【再投稿したい時】</b><br>スプレッドシートのH列にある「完了」という文字を消して<b>「空欄」</b>にするだけ！システムが未投稿と判断して再度実行します。</li>
                <br>
                <li><b>【店舗が終了した時】</b><br>編集アプリの「店舗アカウント状況」タブから、対象の店にチェックを入れて<b>「【落ち店】へ移動」</b>を実行。日記と画像が自動でバックアップ保管されます。</li>
            </ul>
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

