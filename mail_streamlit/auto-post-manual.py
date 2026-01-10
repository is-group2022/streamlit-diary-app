import streamlit as st

# --- ページ基本設定 ---
st.set_page_config(
    page_title="AUTO-POST 完全マニュアル",
    page_icon="🤖",
    layout="wide", # 大きく表示するためにワイドモード
    initial_sidebar_state="expanded"
)

# --- 全体共通のスタイル（文字を大きく、おしゃれに） ---
st.markdown("""
    <style>
    /* 全体の文字サイズをアップ */
    html, body, [class*="css"] {
        font-size: 1.2rem;
    }
    /* タイトルのデザイン */
    .main-title {
        font-size: 3.5rem !important;
        font-weight: 800;
        color: #1E1E1E;
        margin-bottom: 0px;
    }
    /* カード型の装飾 */
    .custom-card {
        background-color: #ffffff;
        padding: 25px;
        border-radius: 15px;
        border-left: 8px solid #FF4B4B;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        margin-bottom: 25px;
    }
    .gcs-card { border-left-color: #4285F4; }
    .gce-card { border-left-color: #34A853; }
    </style>
    """, unsafe_allow_html=True)

# --- ページ定義関数 ---

def show_home():
    st.markdown('<p class="main-title">🤖 システムの仕組み</p>', unsafe_allow_html=True)
    st.write("このシステムがどのように動いているか、全体像を詳しく解説します。")
    
    

    st.markdown("""
    <div class="custom-card gce-card">
        <h2>🚀 GCE (Google Compute Engine)</h2>
        <p><strong>「クラウド上で動く専用のパソコン」</strong>です。</p>
        <ul>
            <li>あなたの代わりに24時間365日、ブラウザを開いて投稿操作を行います。</li>
            <li>自宅のPCを閉じても、このサーバーがネットの中で動き続けます。</li>
            <li>今回提供したプログラム（main.py）はこの中で眠らずに動いています。</li>
        </ul>
    </div>
    
    <div class="custom-card gcs-card">
        <h2>☁️ GCS (Google Cloud Storage)</h2>
        <p><strong>「ネット上の画像専用フォルダ」</strong>です。</p>
        <ul>
            <li>投稿に使う写真はここに保存します。</li>
            <li><strong>重要：</strong>プログラムは「投稿時間」と「女の子の名前」をヒントに、このフォルダから自動で写真を探し出します。</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)

def show_operation():
    st.markdown('<p class="main-title">💡 日常の操作</p>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### ✅ 投稿したいとき")
        st.info("""
        1. スプレッドシートの **G列** に時間を入力（例：`1800`）
        2. **H列**（ステータス）を **空欄** にする
        3. 指定時間に画像がGCSにあるか確認
        """)
    with col2:
        st.markdown("### 🔄 再投稿したいとき")
        st.success("""
        1. すでに「完了」と書かれた **H列のセルを消す**
        2. セルが空欄になると、システムが「未投稿」と判断して再送します
        """)

    st.divider()
    st.markdown("### ⚠️ スケジュール")
    st.error("毎日 **06:00 〜 10:00** はメンテナンスのためシステムが自動停止し、H列がクリアされます。")

def show_trouble():
    st.markdown('<p class="main-title">⚠️ トラブル解決</p>', unsafe_allow_html=True)
    
    
    
    st.subheader("🚨 投稿がされない・失敗する場合")
    
    with st.expander("1. 名前が一致しているか確認", expanded=True):
        st.write("スプレッドシートの「名前」と、投稿先サイトの「登録名」が完全に一致（空白の有無など）している必要があります。")
        
    with st.expander("2. GCSのファイル名を確認"):
        st.write("画像ファイル名の先頭4桁が投稿時間（1200_...）になっており、かつ名前に女の子の名前が含まれているか確認してください。")

    with st.expander("3. H列の空欄確認"):
        st.write("H列に半角スペースなどが入っていると反応しません。一度デリートキーで完全に消してください。")

def show_admin():
    st.markdown('<p class="main-title">🛠 管理者用コマンド</p>', unsafe_allow_html=True)
    st.write("サーバー（GCE）の動作が止まった場合に、エンジニアが使用するコマンド集です。")
    
    st.subheader("再起動フロー")
    st.code("""
# 1. 実行中のプログラムを強制終了
pkill -f main.py

# 2. プログラムをバックグラウンドで再開
nohup python3 main.py > system.log 2>&1 &
    """, language="bash")
    
    st.subheader("ログの確認")
    st.code("tail -f system.log", language="bash")

# --- ルーティング（ページ切り替え） ---

# ページの名前とアイコン、実行する関数の紐付け
pages = {
    "全体図とGCE解説": show_home,
    "日常の操作方法": show_operation,
    "トラブル対応": show_trouble,
    "管理者コマンド": show_admin
}

# サイドバーでページを選択
st.sidebar.title("📖 運用ナビ")
selection = st.sidebar.radio("メニュー", list(pages.keys()))

# 選択されたページ関数を実行
pages[selection]()
