import os
import pandas as pd
from datetime import datetime, time
import streamlit as st
import pandas as pd
from google.cloud import bigquery

# --- ページ設定 ---
st.set_page_config(page_title="自動日記運用マニュアル", layout="wide")

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

# --- 上部タブナビゲーションの定義 (ここで名前を確定させます) ---
tab_manual, tab_operation, tab_trouble, tab_billing = st.tabs([
    "📂 システムの仕組み (GCE/GCS)", 
    "📝 日常の操作手順", 
    "🆘 トラブル対応", 
    "📊 リアルタイム料金"
])

# --- 1. システムの仕組み (稼働状況チェック付き) ---
with tab_manual:
    st.header("📊 システム稼働状況 ＆ インフラ解説")
    
    # 現在時刻の取得
    now = datetime.now()
    current_time = now.time()
    
    # 稼働時間外（06:00 - 11:00）の判定
    is_off_hours = time(6, 0) <= current_time <= time(11, 0)

    # --- 投稿状況のリアルタイム判定 ---
    try:
        # 投稿管理シートの読み込み
        sh_status = GC.open_by_key("1sEzw59aswIlA-8_CTyUrRBLN7OnrRIJERKUZ_bELMrY")
        ws_status = sh_status.sheet1 
        data = ws_status.get_all_values()
        df = pd.DataFrame(data[1:], columns=data[0])
        
        # H列（投稿ステータス）に「完了」が含まれる行を抽出（表記のブレに対応）
        done_rows = df[df['投稿ステータス'].str.contains("完了", na=False)]

        if is_off_hours:
            # 【時間外】の表示
            st.warning(f"### ☕ 現在はシステムメンテナンス時間です (06:00〜11:00)")
            st.info("この時間は自動投稿が停止しています。11:01以降に順次再開されます。")
        
        elif not done_rows.empty:
            # 【稼働中】最新の投稿記録を取得
            last_post = done_rows.iloc[-1]
            status_val = last_post['投稿ステータス']
            shop_name = last_post.get('店名', '不明')
            
            st.success(f"### ✅ システムは正常に稼働中です")
            st.markdown(f"**最新の投稿確認:** `{status_val}` ／ **店舗:** `{shop_name}`")
            st.caption("※H列に『完了』の文字が書き込まれていることを確認しました。")
        else:
            # 【異常の可能性】完了が1件もない場合
            st.error("### ⚠️ 投稿完了が確認できません")
            st.markdown("未投稿のデータが多いか、システムが停止している可能性があります。トラブル対応タブを確認してください。")
            
    except Exception as e:
        st.error("稼働状況の取得に失敗しました。シートのIDを確認してください。")

    st.divider()

    # --- インフラ解説セクション ---
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        <div class="card">
            <h2 style="color: #2563eb;">🚀 GCE (Compute Engine)</h2>
            <p><b>「24時間動く仮想パソコン」です。</b></p>
            <ul>
                <li>スプレッドシートのH列を常に監視し、「空欄」を見つけると投稿を開始します。</li>
                <li>投稿が終わると、H列に<b>「完了: 時刻」</b>と書き込みます。</li>
                <li><b>停止時間:</b> 毎日06:00〜11:00は、システム負荷軽減のためお休みしています。</li>
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
                <li><b>注意:</b> 画像がないと、GCEは投稿をスキップし、H列も更新されません。</li>
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
    st.info("このシステムは、日々の「自動投稿予約」と、投稿の「データ編集」を自動化するために2つのアプリに分かれています。")

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
    st.subheader("🛠 システム起動方法（強制再起動）")
    st.error("⚠️ 注意：どうしても投稿が再開されない時だけ、以下の手順を順番に試してください。")

    # 手順 1
    st.markdown(f"### 1️⃣ Google Cloud にログインする")
    st.markdown(f"必ず **「アイエスグループ（{ADMIN_EMAIL}）」** のアカウントでログインしてください。")
    st.link_button("👉 Google Cloud コンソールを開く", URL_GCE)

    # 手順 2
    st.markdown("### 2️⃣ SSHボタンを押す")
    st.markdown("一覧にある `auto-post-server` の右側にある **「SSH」** という青い文字をクリックします。")
    
    # 画像表示の工夫（ファイルが見つからない場合も考慮）
    img_dir = os.path.dirname(__file__)
    def show_img(file_name, caption):
        path = os.path.join(img_dir, file_name)
        if os.path.exists(path):
            st.image(path, caption=caption)
        else:
            # フォルダ名を含めて再トライ
            alt_path = os.path.join(img_dir, "mail_streamlit", file_name)
            if os.path.exists(alt_path):
                st.image(alt_path, caption=caption)
            else:
                st.warning(f"📸 画像 {file_name} が読み込めません。ファイル名と場所を確認してください。")

    show_img("image_980436.jpg", "この『SSH』をクリックしてください")

    # 手順 3
    st.markdown("### 3️⃣ 接続を「承認」する")
    st.markdown("""
    クリック後、しばらく待つと「承認」を求める画面が出ることがあります。
    **「承認（Authorize）」** ボタンを押して進めてください。
    """)
    show_img("image_980437.jpg", "この画面が出たら『承認』または『Authorize』をクリック")

    # 手順 4
    st.markdown("### 4️⃣ コマンドを貼り付ける")
    st.markdown("""
    黒い画面が立ち上がったら、1分ほど待ちます。文字が止まり、末尾に **$** マークが出てカーソルが点滅したら準備完了です。
    
    下の枠内のコードをコピーして、黒い画面に貼り付け（**右クリック → 貼り付け**）、**Enterキー**を1回押してください。
    """)
    show_img("image_980438.jpg", "この $ マークのあとに貼り付けてEnter！")

    # 実行コマンド
    REBOOT_COMMAND = "pkill -f main.py; nohup python3 main.py > system.log 2>&1 &"
    st.code(REBOOT_COMMAND, language="bash")
    
    st.markdown("""
    <div style="background-color: #f8fafc; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; margin-top: 10px;">
        <p style="margin-bottom: 5px; font-weight: bold;">✅ 操作が終わったら</p>
        <p style="font-size: 0.9rem; color: #475569; margin-bottom: 0;">
            ・Enterを押して新しい行が出れば成功です。黒い画面はバツボタンで閉じてOK。<br>
            ・<b>5〜10分後</b>にスプレッドシートのH列に「完了」が出始めるか確認してください。
        </p>
    </div>
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




















