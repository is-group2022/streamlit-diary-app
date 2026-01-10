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
    # 登録アプリのTab4に直接誘導（StreamlitのURLパラメータ形式）
    URL_REUSE = f"{URL_REGIST}?tab=④+使用可能日記文（ストック）"

    # 全体の説明
    st.info("このシステムは、日々の「投稿予約」と、店舗終了時の「データ整理」を自動化するために2つのアプリに分かれています。")

    # --- ステップ1 & 2 (概要) ---
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("✨ 1. 新規登録")
        st.markdown(f"**[登録アプリ]({URL_REGIST})** を使用。時間・名前・本文を入力して一括登録します。")
    with col2:
        st.subheader("🛠 2. 修正・確認")
        st.markdown(f"**[編集アプリ]({URL_EDIT})** を使用。登録内容の変更や画像の最終確認を行います。")

    st.divider()

    # --- ステップ3 (詳細解説：落ち店移動) ---
    st.subheader("🚀 3. 店舗終了時のデータ整理（落ち店移動）")
    
    st.markdown("""
    店舗を落とした際は、**「落ち店移動」機能**を実行してください。
    手動で削除する手間を省き、大切な日記データを将来のために「倉庫」へ自動保管します。
    """)

    # メイン操作カード
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
        <div style="font-size: 0.9rem; color: #b91c1c; background: #ffffff; padding: 12px; border-radius: 8px; border: 1px solid #fecaca; margin-top: 15px;">
            ⚠️ <b>注意：</b> 処理が完了して画面が更新されるまで、ブラウザを閉じないでください。
        </div>
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
                    <td style="padding: 12px;">
                        自動で倉庫へ転記されます。<br>
                        <a href="{URL_REUSE}" target="_blank" style="color: #2563eb; font-weight: bold;">[登録アプリのTab 3]</a> 
                        からいつでも内容を確認し、他の店舗へ再利用（コピー）できます。
                    </td>
                </tr>
                <tr style="border-bottom: 1px solid #f1f5f9;">
                    <td style="padding: 12px; font-weight: bold;">🔑 ログイン情報</td>
                    <td style="padding: 12px;">システムから自動削除。<b>誤投稿の心配がなくなります。</b></td>
                </tr>
                <tr>
                    <td style="padding: 12px; font-weight: bold;">🖼 画像データ</td>
                    <td style="padding: 12px;">
                        ストレージ内の「【落ち店】フォルダ」へ移動。<br>
                        こちらも登録アプリの <b>Tab 4</b> で一覧表示・再利用が可能です。
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
    """, unsafe_allow_html=True)

# --- 3. トラブル対応 ---
with tab_trouble:
    st.header("🆘 困った時の解決ガイド")
    
    # URL設定
    URL_GCE = "https://console.cloud.google.com/compute/instances?project=project-d2e471f9-c395-4015-aea"
    ADMIN_EMAIL = "isgroup0001@gmail.com"

    with st.expander("❓ 投稿が動かない・「完了」にならない", expanded=True):
        st.markdown("""
        まずは以下の3点をチェックしてください。ほとんどの場合、これで解決します。
        
        1. **名前がサイトと合っているか？**
           - 「山田」と「山田 」（最後にスペース）は別人と判断されます。
        2. **H列（ステータス）が完全に空か？**
           - 文字が入っていると「投稿済み」と判断されます。**デリートキーで完全に消して**みてください。
        3. **画像は準備できているか？**
           - `エリア/店名/1200_名前.jpg` の形式で正しく保存されているか確認してください。
        """)

    st.divider()

    # --- 強制再起動セクション ---
    st.subheader("🛠 システムを「叩き起こす」方法（強制再起動）")
    st.error("⚠️ 注意：どうしても投稿が再開されない時だけ、以下の手順を順番に試してください。")

    st.markdown(f"""
    ### 1️⃣ Google Cloud にログインする
    **※ 非常に重要 ※**
    必ず **「アイエスグループ」** のアカウントでログインしてください。
    
    * **使用するメール**: `{ADMIN_EMAIL}`
    
    [👉 Google Cloud コンソール（管理画面）を開く]({URL_GCE})

    ### 2️⃣ SSHボタンを押す
    ログイン後、一覧にある `auto-post-server` の右側にある **「SSH」** という青い文字をクリックしてください。
    """)

    # --- 画像表示（エラー対策付き） ---
    try:
        # ファイル名が .jpg であることを確認してください
        st.image("image_980436.jpg", caption="Google Cloud 画面：この『SSH』をクリック")
    except:
        st.warning("📸 (画像ファイル image_980436.jpg が読み込めませんでした) 画面右端の『接続』列にある青い【SSH】という文字を探してください。")

    st.markdown(f"""
    ### 3️⃣ 魔法の言葉（コマンド）を貼り付ける
    黒い画面（別ウィンドウ）が立ち上がったら、1分ほど待ちます。
    文字が止まり、末尾に `$` マークなどが出てカーソルが点滅したら、下のコードを**コピーして貼り付け、Enterキー**を1回押してください。
    """)

    # 実行コマンド
    REBOOT_COMMAND = "pkill -f main.py; nohup python3 main.py > system.log 2>&1 &"
    st.code(REBOOT_COMMAND, language="bash")
    
    st.markdown("""
    <div style="background-color: #f8fafc; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; margin-top: 10px;">
        <p style="margin-bottom: 5px; font-weight: bold;">💡 何が起きるの？</p>
        <p style="font-size: 0.9rem; color: #475569; margin-bottom: 0;">
            ・フリーズしているプログラムを一度強制終了し、最新の状態で起動し直します。<br>
            ・Enterを押した後、新しい行が出れば成功です。黒い画面はそのまま閉じてOKです。
        </p>
    </div>
    
    ### 4️⃣ 動作確認
    操作後、**5〜10分**ほど待ってからスプレッドシートを確認してください。
    H列に「完了」という文字が書き込まれ始めれば、復旧完了です！
    """, unsafe_allow_html=True)

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











