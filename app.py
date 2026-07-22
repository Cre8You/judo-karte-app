import datetime
from typing import Dict, List

import google.generativeai as genai
import streamlit as st

from evaluation_config import JOINT_CONFIG, NRS_OPTIONS, ROM_FACTORS, SIDE_OPTIONS, SPECIAL_TEST_RESULTS
from plan_prompt import build_rehabilitation_plan_prompt
from plan_validation import validate_plan_inputs

st.set_page_config(page_title="柔道整復師カルテAIアシスタント", layout="wide")

MODEL_OPTIONS = {
    "gemini-flash-latest（1日1500回・基本）": "gemini-flash-latest",
    "gemini-3.0-flash（最新鋭！）": "gemini-3.0-flash",
    "gemini-2.5-flash（高性能！）": "gemini-2.5-flash",
    "gemini-1.5-pro（推論特化）": "gemini-1.5-pro",
}


def set_exclusive_checkbox(selected_key: str, other_key: str) -> None:
    if st.session_state.get(selected_key, False):
        st.session_state[other_key] = False


def exclusive_checkbox_pair(item_label: str, negative_label: str, positive_label: str, key_prefix: str) -> str:
    label_col, negative_col, positive_col = st.columns([2.2, 1.2, 1.2])
    negative_key = f"{key_prefix}_negative"
    positive_key = f"{key_prefix}_positive"
    with label_col:
        st.write(item_label)
    with negative_col:
        negative_checked = st.checkbox(
            negative_label,
            key=negative_key,
            on_change=set_exclusive_checkbox,
            args=(negative_key, positive_key),
        )
    with positive_col:
        positive_checked = st.checkbox(
            positive_label,
            key=positive_key,
            on_change=set_exclusive_checkbox,
            args=(positive_key, negative_key),
        )
    if positive_checked:
        return positive_label
    if negative_checked:
        return negative_label
    return "未評価"


def render_rom_assessment(joint: str, motions: List[str]) -> Dict[str, Dict[str, object]]:
    results: Dict[str, Dict[str, object]] = {}
    with st.expander("📐 ROM評価", expanded=True):
        st.caption("『制限なし』『制限あり』のどちらかを選択します。両方未選択は未評価です。")
        for index, motion in enumerate(motions):
            status = exclusive_checkbox_pair(motion, "制限なし", "制限あり", f"plan_{joint}_rom_{index}")
            factors: List[str] = []
            if status == "制限あり":
                factors = st.multiselect(
                    f"{motion}の制限因子（複数選択可）",
                    ROM_FACTORS,
                    key=f"plan_{joint}_rom_factors_{index}",
                )
            results[motion] = {"status": status, "factors": factors}
            st.divider()
    return results


def render_binary_assessment(title: str, icon: str, joint: str, items: List[str], negative_label: str, positive_label: str, key_name: str) -> Dict[str, str]:
    results: Dict[str, str] = {}
    with st.expander(f"{icon} {title}", expanded=True):
        st.caption("両方未選択の場合は未評価です。")
        for index, item in enumerate(items):
            results[item] = exclusive_checkbox_pair(
                item,
                negative_label,
                positive_label,
                f"plan_{joint}_{key_name}_{index}",
            )
            st.divider()
    return results


def render_special_tests(joint: str, tests: List[str]) -> Dict[str, Dict[str, str]]:
    results: Dict[str, Dict[str, str]] = {}
    with st.expander("🧪 スペシャルテスト", expanded=False):
        st.caption("各テストの結果を選び、陽性・判定困難の場合は所見を補足できます。")
        for index, test_name in enumerate(tests):
            result_col, note_col = st.columns([1.4, 2.6])
            with result_col:
                result = st.selectbox(
                    test_name,
                    SPECIAL_TEST_RESULTS,
                    key=f"plan_{joint}_special_result_{index}",
                )
            with note_col:
                note = ""
                if result in ["陽性", "判定困難"]:
                    note = st.text_input(
                        f"{test_name}の所見（任意）",
                        placeholder="例：疼痛誘発、不安感、弛緩性、クリックなど",
                        key=f"plan_{joint}_special_note_{index}",
                    )
            results[test_name] = {"result": result, "note": note}
            st.divider()
    return results


def format_rom_results(results: Dict[str, Dict[str, object]]) -> str:
    lines = []
    for motion, data in results.items():
        status = str(data["status"])
        factors = data.get("factors", [])
        if status == "制限あり" and factors:
            lines.append(f"・{motion}：制限あり（制限因子：{', '.join(factors)}）")
        else:
            lines.append(f"・{motion}：{status}")
    return "\n".join(lines)


def format_binary_results(results: Dict[str, str]) -> str:
    return "\n".join(f"・{item}：{status}" for item, status in results.items())


def format_special_results(results: Dict[str, Dict[str, str]]) -> str:
    lines = []
    for test_name, data in results.items():
        suffix = f"（{data['note']}）" if data["note"] else ""
        lines.append(f"・{test_name}：{data['result']}{suffix}")
    return "\n".join(lines)


def generate_with_gemini(gemini_key: str, selected_model: str, prompt: str, spinner_text: str) -> None:
    with st.spinner(spinner_text):
        try:
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel(selected_model)
            response = model.generate_content(prompt)
            st.subheader("✨ 出力結果")
            st.text_area("Copy & Paste", response.text, height=700)
        except Exception as exc:
            st.error(f"エラーが発生しました: {exc}")


def render_new_patient_mode(gemini_key: str, selected_model: str) -> None:
    with st.sidebar:
        st.divider()
        st.header("📋 分類設定")
        category = st.selectbox("【疾患分類】を選択", ["骨折", "捻挫", "脱臼", "慢性疾患"])
        region = st.selectbox("【部位】を選択", ["上肢", "下肢", "体幹"])

    st.header(f"📝 新患カルテ入力（{category} - {region}）")
    c_info1, c_info2 = st.columns(2)
    with c_info1:
        diagnosis = st.text_input("病名（傷病名）", placeholder="例：右橈骨遠位端骨折", key="new_diagnosis")
    with c_info2:
        st.date_input("発症日（受傷日）", datetime.date.today(), key="new_onset_date")

    st.divider()
    st.subheader("📋 Risk factor & scheduleに関する指示")
    st.write("◯固定部位・方法")
    selected_fix_r: List[str] = []
    selected_fix_l: List[str] = []
    selected_fix_trunk: List[str] = []
    fix_extra = ""

    if region in ["上肢", "下肢"]:
        if region == "上肢":
            fix_options = ["BE", "AE", "プライトン", "アルフェンス", "テーピング", "サポーター"]
            extra_placeholder = "例：デゾー固定、バディテーピングなど"
        else:
            fix_options = ["BE", "AE", "プライトン", "アルフェンス", "テーピング", "サポーター", "松葉杖"]
            extra_placeholder = "例：U字シーネ、厚紙副子など"
        c_fix_r, c_fix_l = st.columns(2)
        with c_fix_r:
            st.write("『右』")
            for option in fix_options:
                if st.checkbox(f"右：{option}", key=f"new_fix_r_{option}"):
                    selected_fix_r.append(option)
        with c_fix_l:
            st.write("『左』")
            for option in fix_options:
                if st.checkbox(f"左：{option}", key=f"new_fix_l_{option}"):
                    selected_fix_l.append(option)
        fix_extra = st.text_input("その他（例外・詳細）", placeholder=extra_placeholder, key="new_fix_extra")
    else:
        c_fix_t1, c_fix_t2 = st.columns(2)
        with c_fix_t1:
            for option in ["クラビクルバンド", "コルセット", "サポーター"]:
                if st.checkbox(option, key=f"new_fix_t_{option}"):
                    selected_fix_trunk.append(option)
        with c_fix_t2:
            fix_extra = st.text_input("その他（例外・詳細）", placeholder="例：鎖骨固定帯の種類など", key="new_fix_extra_trunk")

    fix_summary = ""
    if region in ["上肢", "下肢"]:
        if selected_fix_r:
            fix_summary += f"右：{', '.join(selected_fix_r)} "
        if selected_fix_l:
            fix_summary += f"左：{', '.join(selected_fix_l)} "
        if fix_extra:
            fix_summary += f"({fix_extra})"
    else:
        if selected_fix_trunk:
            fix_summary += f"{', '.join(selected_fix_trunk)} "
        if fix_extra:
            fix_summary += f"({fix_extra})"
    if not fix_summary:
        fix_summary = "特記なし"

    schedule = st.text_input("◯固定、または荷重スケジュール", value="2週間の継続固定を予定", key="new_schedule")
    st.divider()
    st.subheader("🏠 社会的背景(FIM別紙計画書内)")
    social_bg = st.text_input("職業、趣味、家事活動など", placeholder="例：事務職（PC作業メイン）", key="new_social_bg")
    st.divider()
    st.subheader("🩺 当日の治療状況")
    symptoms = st.text_area("○症状", placeholder="例：右手関節の腫脹、熱感、運動時痛あり。", key="new_symptoms")
    default_treatment = """残存機能促通による代償ADL習得訓練
ADL指導
患部外筋力促通運動
松葉歩行訓練"""
    treatment = st.text_area("○実施内容", value=default_treatment, height=120, key="new_treatment")
    future_plan = st.text_area("○今後の治療計画", placeholder="例：固定期間経過後、炎症の沈静化を確認しROM exへ移行する。", height=100, key="new_future_plan")
    reasoning = st.text_area("○臨床推論", placeholder="例：受傷機転は転倒時の手掌接地。", height=120, key="new_reasoning")
    st.divider()
    st.subheader("⚡ 消炎鎮痛及び物理療法")
    c_pt1, c_pt2 = st.columns(2)
    with c_pt1:
        pt_region = st.text_input("部位", placeholder="例：右手関節周囲", key="new_pt_region")
    with c_pt2:
        pt_menu = st.text_input("メニュー", placeholder="例：アイシング", key="new_pt_menu")
    st.divider()
    next_visit = st.text_input("📅 次回", placeholder="例：明日、固定の適合状態確認および症状経過観察のため来院予定。", key="new_next_visit")
    st.divider()

    if st.button("🚀 カルテ生成開始", use_container_width=True, key="new_generate"):
        if not gemini_key:
            st.error("APIキーを入力してください")
        elif not diagnosis:
            st.warning("病名を入力してください")
        else:
            prompt = f"""
あなたは接骨院に勤務する優秀な柔道整復師です。
以下の入力データを元に、指定された出力フォーマットに沿って新患カルテを作成してください。

【重要】
・強調記号やカッコ【】は、見出しを含め一切使用しないでください。
・各見出しの直後や文章の区切りで積極的に改行してください。
・固定方法、スケジュール、物理療法は入力内容をそのまま簡潔に出力してください。

【患者データ】
・疾患分類：{category}
・部位：{region}
・傷病名：{diagnosis}
・固定部位・方法：{fix_summary}
・固定、または荷重スケジュール：{schedule}
・職業、趣味、家事活動など：{social_bg}
・症状：{symptoms}
・実施内容：{treatment}
・今後の治療計画：{future_plan}
・臨床推論：{reasoning}
・物理療法部位：{pt_region}
・物理療法メニュー：{pt_menu}
・次回：{next_visit}

【出力フォーマット】
◆Risk factor & scheduleに関する指示
◯固定部位・方法

◯固定、または荷重スケジュール

◆社会的背景(FIM別紙計画書内)
職業、趣味、家事活動など

◆当日の治療状況
○症状:

○実施内容:

○今後の治療計画:

○臨床推論:

◆消炎鎮痛及び物理療法
部位：
メニュー：

次回：
"""
            generate_with_gemini(gemini_key, selected_model, prompt, "AIがカルテを生成中...")


def render_plan_mode(gemini_key: str, selected_model: str) -> None:
    st.header("📑 リハビリテーション計画書入力")
    st.info("柔道整復師による評価を入力し、計画書用の文章を生成します。")

    base_col1, base_col2, base_col3 = st.columns(3)
    with base_col1:
        patient_id = st.text_input("患者ID", placeholder="例：000000", key="plan_patient_id")
        joint = st.selectbox("対象関節・部位", list(JOINT_CONFIG.keys()), key="plan_joint")
    with base_col2:
        side = st.selectbox("左右", SIDE_OPTIONS, key="plan_side")
        disease_name = st.text_input(
            "傷病名",
            placeholder="例：右膝内側側副靱帯損傷",
            key="plan_disease_name",
        )
    with base_col3:
        onset_date = st.date_input("発症日（受傷日）", datetime.date.today(), key="plan_onset_date")
        rehab_start_date = st.date_input("リハ開始日", datetime.date.today(), key="plan_rehab_start_date")

    st.divider()
    st.subheader("🔥 疼痛評価")
    pain_col1, pain_col2, pain_col3 = st.columns(3)
    with pain_col1:
        rest_nrs = st.selectbox("安静時NRS", NRS_OPTIONS, key="plan_rest_nrs")
    with pain_col2:
        movement_nrs = st.selectbox("動作時NRS", NRS_OPTIONS, key="plan_movement_nrs")
    with pain_col3:
        night_nrs = st.selectbox("夜間痛NRS", NRS_OPTIONS, key="plan_night_nrs")
    pain_location = st.text_input("疼痛部位", placeholder="例：右膝関節内側、膝蓋骨周囲", key="plan_pain_location")
    pain_trigger = st.text_input("疼痛を誘発する動作", placeholder="例：階段降段、立ち上がり、歩行開始時", key="plan_pain_trigger")
    pain_quality = st.text_input("疼痛の性質", placeholder="例：鋭い痛み、鈍痛、灼熱感", key="plan_pain_quality")

    config = JOINT_CONFIG[joint]
    rom_results = render_rom_assessment(joint, config["rom"])
    mmt_results = render_binary_assessment("MMT評価", "💪", joint, config["mmt"], "筋力低下なし", "筋力低下あり", "mmt")
    sensory_results = render_binary_assessment("感覚検査", "🖐️", joint, config["sensory"], "感覚異常なし", "感覚異常あり", "sensory")
    special_results = render_special_tests(joint, config["special_tests"])

    st.divider()
    st.subheader("📝 計画書作成のための補足情報")
    context_col1, context_col2 = st.columns(2)
    with context_col1:
        participation = st.text_area("生活上の困りごと・参加制限（任意）", placeholder="例：通勤時の歩行、仕事中の立位、家事動作に支障がある", height=100, key="plan_participation")
    with context_col2:
        clinical_note = st.text_area("柔道整復師所見・補足（任意）", placeholder="例：腫脹、圧痛、歩容、固定状況、治癒経過など", height=100, key="plan_clinical_note")

    st.divider()
    if st.button("🚀 計画書生成開始", use_container_width=True, key="plan_generate"):
        validation_warning, patient_id_for_prompt = validate_plan_inputs(
            patient_id,
            disease_name,
            onset_date,
            rehab_start_date,
        )
        if not gemini_key:
            st.error("APIキーを入力してください")
        elif validation_warning:
            st.warning(validation_warning)
        else:
            prompt = build_rehabilitation_plan_prompt(
                patient_id=patient_id_for_prompt,
                joint=joint,
                side=side,
                disease_name=disease_name,
                onset_date=onset_date,
                rehab_start_date=rehab_start_date,
                rest_nrs=rest_nrs,
                movement_nrs=movement_nrs,
                night_nrs=night_nrs,
                pain_location=pain_location,
                pain_trigger=pain_trigger,
                pain_quality=pain_quality,
                rom_summary=format_rom_results(rom_results),
                mmt_summary=format_binary_results(mmt_results),
                sensory_summary=format_binary_results(sensory_results),
                special_summary=format_special_results(special_results),
                participation=participation,
                clinical_note=clinical_note,
            )
            generate_with_gemini(gemini_key, selected_model, prompt, "AIが計画書を生成中...")


def main() -> None:
    st.title("🦴 柔道整復師カルテAIアシスタント")
    with st.sidebar:
        st.header("🧭 作成モード")
        mode = st.radio("使用する機能を選択", ["① 新患カルテ作成", "② リハビリテーション計画書作成"])
        st.divider()
        st.header("🔑 AI設定")
        gemini_key = st.text_input("Gemini APIキーを入力", type="password")
        st.header("🧠 モデル設定")
        selected_label = st.selectbox("使用するAIモデル", list(MODEL_OPTIONS.keys()), index=0)
        selected_model = MODEL_OPTIONS[selected_label]

    if mode == "① 新患カルテ作成":
        render_new_patient_mode(gemini_key, selected_model)
    else:
        render_plan_mode(gemini_key, selected_model)


if __name__ == "__main__":
    main()
