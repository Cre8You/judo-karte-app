import streamlit as st
import google.generativeai as genai
import datetime

# ページ設定
st.set_page_config(page_title="柔道整復師カルテAIアシスタント", layout="wide")

st.title("🦴 柔道整復師カルテAIアシスタント")

# --- サイドバー ---
with st.sidebar:
    st.header("🔑 AI設定")
    gemini_key = st.text_input("Gemini APIキーを入力", type="password")
    
    MODEL_OPTIONS = {
        "gemini-flash-latest（1日1500回・基本）": "gemini-flash-latest",
        "gemini-3.0-flash（最新鋭！）": "gemini-3.0-flash",
        "gemini-2.5-flash（高性能！）": "gemini-2.5-flash",
        "gemini-1.5-pro（推論特化）": "gemini-1.5-pro"
    }
    
    st.divider()
    st.header("🧠 モデル設定")
    selected_label = st.selectbox("使用するAIモデル", list(MODEL_OPTIONS.keys()), index=0)
    selected_model = MODEL_OPTIONS[selected_label]
            
    st.divider()
    st.header("📋 分類設定")
    category = st.selectbox("【疾患分類】を選択", ["骨折", "捻挫", "脱臼", "慢性疾患"])
    region = st.selectbox("【部位】を選択", ["上肢", "下肢", "体幹"])

# --- メインエリア：評価入力 ---
st.header(f"📝 新患カルテ入力（{category} - {region}）")

# 基本情報
c_info1, c_info2 = st.columns(2)
with c_info1:
    diagnosis = st.text_input("病名（傷病名）", placeholder="例：右橈骨遠位端骨折")
with c_info2:
    onset_date = st.date_input("発症日（受傷日）", datetime.date.today())

st.divider()

# --- 固定方法の入力 ---
st.subheader("📋 Risk factor & scheduleに関する指示")
st.write("安静、固定部位・方法")

selected_fix_r = []
selected_fix_l = []
selected_fix_trunk = []
fix_extra = ""

if region in ["上肢", "下肢"]:
    fix_options = ["BE", "AE", "プライトン", "アルフェンス", "テーピング", "サポーター"]
    c_fix_r, c_fix_l = st.columns(2)
    
    with c_fix_r:
        st.write("『右』")
        for opt in fix_options:
            if st.checkbox(f"右：{opt}", key=f"fix_r_{opt}"):
                selected_fix_r.append(opt)
    
    with c_fix_l:
        st.write("『左』")
        for opt in fix_options:
            if st.checkbox(f"左：{opt}", key=f"fix_l_{opt}"):
                selected_fix_l.append(opt)
else: # 体幹
    fix_options_trunk = ["クラビクルバンド", "コルセット", "サポーター"]
    c_fix_t1, c_fix_t2 = st.columns(2)
    
    with c_fix_t1:
        for opt in fix_options_trunk:
            if st.checkbox(opt, key=f"fix_t_{opt}"):
                selected_fix_trunk.append(opt)
    
    with c_fix_t2:
        fix_extra = st.text_input("その他（例外・詳細）", placeholder="例：鎖骨固定帯の種類など")

# 固定方法の文字列作成
fix_summary = ""
if region in ["上肢", "下肢"]:
    if selected_fix_r: fix_summary += f"右：{', '.join(selected_fix_r)} "
    if selected_fix_l: fix_summary += f"左：{', '.join(selected_fix_l)} "
else:
    if selected_fix_trunk: fix_summary += f"{', '.join(selected_fix_trunk)} "
    if fix_extra: fix_summary += f"({fix_extra})"

if not fix_summary:
    fix_summary = "特記なし"

# スケジュール
schedule = st.text_input("固定、または荷重スケジュール", value="2週間継続固定")

st.divider()

st.subheader("🏠 社会的背景(FIM別紙計画書内)")
social_bg = st.text_input("職業、趣味、家事活動など", placeholder="例：事務職（PC作業メイン）")

st.divider()

st.subheader("🩺 当日の治療状況")
symptoms = st.text_area("○症状", placeholder="例：右手関節の腫脹、熱感、運動時痛あり。")

default_treatment = """・残存機能促通による代償ADL習得訓練
・ADL指導(固定部位に負担が掛からないように)
・患部外筋力促通運動
・松葉歩行訓練(前記荷重スケジュールに準ずる)"""
treatment = st.text_area("○実施内容", value=default_treatment, height=130)

future_plan = st.text_input("○今後の治療計画", value="固定解放後のROM exへ")

# 臨床推論の入力位置を修正
reasoning = st.text_area("○臨床推論（症状の原因や評価など）", placeholder="例：受傷機転は転倒時の手掌接地。定型的なフォーク状変形あり。", height=120)

st.divider()

st.subheader("⚡ 消炎鎮痛及び物理療法")
c_pt1, c_pt2 = st.columns(2)
with c_pt1:
    pt_region = st.text_input("部位", placeholder="例：右手関節周囲")
with c_pt2:
    pt_menu = st.text_input("メニュー", placeholder="例：アイシング")

st.divider()

next_visit = st.text_input("📅 次回", placeholder="例：明日")

st.divider()

# 実行ボタン
if st.button("🚀 カルテ生成開始", use_container_width=True):
    if not gemini_key:
        st.error("APIキーを入力してください")
    elif not diagnosis:
        st.warning("病名を入力してください")
    else:
        # プロンプト作成（レイアウトと強調記号の制限を強化）
        prompt = f"""
あなたは接骨院に勤務する優秀な柔道整復師です。
以下の入力データを元に、指定された【出力フォーマット】に沿って新患カルテを作成してください。

【重要：レイアウト指示】
・【】やアスタリスク（**）などの強調記号は、見出しを含め一切使用しないでください。
・視覚的な見やすさを最優先し、各見出しの直後や、文章の区切りで積極的に「改行」を入れてください。
・1つの項目が長くなる場合は、適宜改行を入れて1行あたりの文字数を抑えてください。

【患者データ】
・疾患分類：{category}
・部位：{region}
・傷病名：{diagnosis}
・安静、固定部位・方法：{fix_summary}
・固定、または荷重スケジュール：{schedule}
・職業、趣味、家事活動など：{social_bg}
・症状：{symptoms}
・実施内容：{treatment}
・今後の治療計画：{future_plan}
・臨床推論：{reasoning}
・物理療法部位：{pt_region}
・物理療法メニュー：{pt_menu}
・次回：{next_visit}

【出力フォーマット】（この構成と見出しを維持し、改行を多用してください）
◆Risk factor & scheduleに関する指示
安静、固定部位・方法
（ここに内容を記載。項目名から改行して開始してください）

固定、または荷重スケジュール
（ここに内容を記載。項目名から改行して開始してください）

◆社会的背景(FIM別紙計画書内)
職業、趣味、家事活動など
（ここに内容を記載。項目名から改行して開始してください）

◆当日の治療状況
○症状:
（ここに内容を記載。項目名から改行して開始してください）

○実施内容:
（ここに箇条書きと説明を記載。説明文の前で改行してください）

○今後の治療計画:
（ここに内容を記載。項目名から改行して開始してください）

○臨床推論:
（ここに内容を記載。項目名から改行して開始してください）

◆消炎鎮痛及び物理療法
部位:
（ここに内容を記載）

メニュー:
（ここに内容を記載）

次回： （ここに内容を記載）
"""
        with st.spinner("AIが読みやすいレイアウトでカルテを生成中..."):
            try:
                genai.configure(api_key=gemini_key)
                model = genai.GenerativeModel(selected_model)
                response = model.generate_content(prompt)
                st.subheader("✨ 出力結果")
                st.text_area("Copy & Paste", response.text, height=650)
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
