import streamlit as st
import google.generativeai as genai
import datetime

# ページ設定
st.set_page_config(page_title="柔道整復師カルテAIアシスタント", layout="wide")

st.title("🦴 Yudai式：柔道整復師カルテAIアシスタント")

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

# フォーマットに合わせた入力エリア
st.subheader("📋 Risk factor & scheduleに関する指示")
immobilization = st.text_input("安静、固定部位・方法", placeholder="例：プライトン固定、三角巾にて提肘")
schedule = st.text_input("固定、または荷重スケジュール", value="2週間継続固定")

st.divider()

st.subheader("🏠 社会的背景(FIM別紙計画書内)")
social_bg = st.text_input("職業、趣味、家事活動など", placeholder="例：事務職（PC作業メイン）、週1回テニス")

st.divider()

st.subheader("🩺 当日の治療状況")
symptoms = st.text_area("○症状", placeholder="例：右手関節の腫脹、熱感、運動時痛あり。手指の感覚異常なし。")

default_treatment = """・残存機能促通による代償ADL習得訓練
・ADL指導(固定部位に負担が掛からないように)
・患部外筋力促通運動
・松葉歩行訓練(前記荷重スケジュールに準ずる)"""
treatment = st.text_area("○実施内容", value=default_treatment, height=130)

future_plan = st.text_input("○今後の治療計画", value="固定解放後のROM exへ")

st.divider()

st.subheader("⚡ 消炎鎮痛及び物理療法")
c_pt1, c_pt2 = st.columns(2)
with c_pt1:
    pt_region = st.text_input("部位", placeholder="例：右手関節周囲、右前腕")
with c_pt2:
    pt_menu = st.text_input("メニュー", placeholder="例：アイシング、低周波、超音波")

st.divider()

next_visit = st.text_input("📅 次回", placeholder="例：明日来院予定、1週間後整形外科受診後に来院")

st.divider()

# 実行ボタン
if st.button("🚀 カルテ生成開始", use_container_width=True):
    if not gemini_key:
        st.error("APIキーを入力してください")
    elif not diagnosis:
        st.warning("病名を入力してください")
    else:
        # プロンプト作成
        prompt = f"""
あなたは接骨院に勤務する優秀な柔道整復師です。
以下の入力データを元に、指定された【出力フォーマット】を一言一句違わず見出しとして使用し、新患カルテを作成してください。

【患者データ】
・疾患分類：{category}
・部位：{region}
・傷病名：{diagnosis}
・安静、固定部位・方法：{immobilization}
・固定、または荷重スケジュール：{schedule}
・職業、趣味、家事活動など：{social_bg}
・症状：{symptoms}
・実施内容：{treatment}
・今後の治療計画：{future_plan}
・物理療法部位：{pt_region}
・物理療法メニュー：{pt_menu}
・次回：{next_visit}

【出力フォーマット】（以下の形式を必ず守ってください）
◆Risk factor & scheduleに関する指示
安静、固定部位・方法:
固定、または荷重スケジュール:

◆社会的背景(FIM別紙計画書内)
職業、趣味、家事活動など:

◆当日の治療状況
○症状:
○実施内容:
○今後の治療計画:

◆消炎鎮痛及び物理療法
部位:
メニュー:

次回：

【出力条件】
・挨拶や前置きは不要です。いきなり『◆Risk factor & scheduleに関する指示』から開始してください。
・入力データが空欄（不足している）部分は、入力された傷病名や柔道整復師の一般的な処置から推測して、医学的に自然な文章で補完してください。
・箇条書きは入力データの通りに改行を維持して反映してください。
・強調したい部分には「【】」を使用してください。アスタリスク記号は絶対に使用しないでください。
"""
        with st.spinner("AIが当院フォーマットでカルテを生成中..."):
            try:
                genai.configure(api_key=gemini_key)
                model = genai.GenerativeModel(selected_model)
                response = model.generate_content(prompt)
                st.subheader("✨ 出力結果")
                st.text_area("Copy & Paste", response.text, height=550)
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
