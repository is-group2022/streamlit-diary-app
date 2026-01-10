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
    URL_STOCK_SHEET = "https://docs.google.com/spreadsheets/d/1e-iLey43A1t0bIBoijaXP55t5fjONdb0ODiTS53beqM"

    # 全体の説明
    st.info("このシステムは、日々の「投稿予約」と、店舗終了時の「データ整理」を自動化するために2つのアプリに分かれています。")

    # --- ステップ1 & 2 (概要) ---
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("✨ 1. 新規登録")
        st.markdown(f"**[登録アプリ]({URL_REGIST})** を使用。時間・名前・本文を入力して一括登録します。")
    with col2:
        st.subheader("🛠 2. 修正・確認")
        st.markdown(f"**[編集アプリ]({URL_EDIT})** を使用。登録した内容の変更や、画像の見え方を確認します。")

    st.divider()

    # --- ステップ3 (詳細解説：落ち店移動) ---
    st.subheader("🚀 3. 店舗終了時のデータ整理（落ち店移動）")
    
    # 機能のメリット説明
    st.markdown("""
    店舗の契約が終了した際、手動でデータを消すと「再開時にまた打ち直す」手間が発生します。
    **「落ち店移動」機能**を使うと、データを「捨てる」のではなく「倉庫に預ける」処理を自動で行います。
    """)

    # 見栄えを整えたHTMLカード
    st.markdown(f"""
    <div style="background-color: #fff1f2; padding: 20px; border-radius: 10px; border-left: 5px solid #e11d48; margin-bottom: 20px;">
        <h4 style="color: #e11d48; margin-top: 0;">🛠 移動の具体的なやり方</h4>
        <ol style="line-height: 1.8;">
            <li><a href="{URL_EDIT}" target="_blank" style="color: #e11d48; font-weight: bold;">編集・管理用アプリ</a> を開く。</li>
            <li>タブ <b>「📊 ② 店舗アカウント状況」</b> を選択。</li>
            <li>一覧から終了する店舗に<b>チェック</b>を入れる。</li>
            <li>画面下の <b>「🚀 選択した店舗を【落ち店】へ移動する」</b> ボタンを押す。</li>
            <li>赤い確認メッセージが出るので <b>「⭕ はい、実行します」</b> をクリック。</li>
        </ol>
        <p style="font-size: 0.9rem; color: #b91c1c; background: #fee2e2; padding: 10px; border-radius: 5px;">
            ⚠️ <b>完了まで待機：</b> 処理中は裏でシートの書き換えと画像の移動を行っています。数秒〜数十秒かかるので、画面が切り替わるまで閉じないでください。
        </p>
    </div>

    <div style="background-color: #f8fafc; padding: 20px; border-radius: 10px; border: 1px solid #e2e8f0; margin-bottom: 20px;">
        <h4 style="margin-top: 0; color: #334155;">❓ 移動するとどうなる？（メリット）</h4>
        <table style="width: 100%; border-collapse: collapse; font-size: 0.9rem;">
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <th style="text-align: left; padding: 8px; color: #64748b;">対象</th>
                <th style="text-align: left; padding: 8px; color: #64748b;">処理内容</th>
            </tr>
            <tr>
                <td style="padding: 8px; font-weight: bold;">日記データ</td>
                <td style="padding: 8px;"><a href="{URL_STOCK_SHEET}" target="_blank">ストック用シート</a>へ自動移動。他の店舗で再利用できます。</td>
            </tr>
            <tr>
                <td style="padding: 8px; font-weight: bold;">投稿システム</td>
                <td style="padding: 8px;">ログイン情報が削除されるため、<b>間違えて投稿される事故</b>を100%防ぎます。</td>
            </tr>
            <tr>
                <td style="padding: 8px; font-weight: bold;">画像ファイル</td>
                <td style="padding: 8px;">「【落ち店】フォルダ」へ自動移動。サーバーを綺麗に保てます。</td>
            </tr>
        </table>
    </div>

    <div style="background-color: #fffbeb; padding: 15px; border-radius: 10px; border-left: 5px solid #f59e0b;">
        <p style="margin-bottom: 0;"><b>🔁 おまけ：同じ日記を再投稿したい時</b><br>
        スプレッドシートのH列（ステータス）にある「完了」の文字を消して<b>「空欄」</b>にするだけで、次回の巡回時に再度投稿が予約されます。</p>
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




