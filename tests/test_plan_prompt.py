import datetime
import unittest

from plan_prompt import build_rehabilitation_plan_prompt


PLAN_HEADINGS = [
    "【疼痛について】",
    "【筋力について】",
    "【感覚異常について】",
    "【可動域について】",
    "【短期目標】",
    "【長期目標】",
    "【治療方針】",
    "【治療内容】",
    "【参加制限に対する具体的な対応方針】",
    "【機能障害に対する具体的な対応方針】",
]


class PlanPromptTest(unittest.TestCase):
    def build_prompt(self, patient_id="TEST-001"):
        return build_rehabilitation_plan_prompt(
            patient_id=patient_id,
            joint="膝関節",
            side="右",
            disease_name="テスト用傷病名",
            onset_date=datetime.date(2026, 1, 10),
            rehab_start_date=datetime.date(2026, 1, 11),
            rest_nrs=1,
            movement_nrs=4,
            night_nrs="未評価",
            pain_location="テスト用疼痛部位",
            pain_trigger="テスト用誘発動作",
            pain_quality="テスト用疼痛性質",
            rom_summary="・屈曲：制限あり（制限因子：疼痛）",
            mmt_summary="・膝関節伸展：筋力低下あり",
            sensory_summary="・膝前面：感覚異常なし",
            special_summary="・Lachman test：未実施",
            participation="テスト用参加制限",
            clinical_note="テスト用柔道整復師所見",
        )

    def test_excludes_non_plan_output_instructions(self):
        prompt = self.build_prompt()

        for forbidden_text in [
            "【電子カルテ用】",
            "電子カルテ向け評価結果",
            "優先的問題点",
            "標準算定期限",
            "リハビリ期限",
        ]:
            self.assertNotIn(forbidden_text, prompt)

    def test_contains_exactly_ten_plan_headings_in_order(self):
        prompt = self.build_prompt()
        heading_positions = [prompt.index(heading) for heading in PLAN_HEADINGS]

        self.assertEqual(heading_positions, sorted(heading_positions))
        self.assertEqual(prompt.count("【"), len(PLAN_HEADINGS))
        for heading in PLAN_HEADINGS:
            self.assertEqual(prompt.count(heading), 1)

    def test_contains_every_length_and_line_limit(self):
        prompt = self.build_prompt()

        expected_limits = {
            "【疼痛について】": "20文字以内",
            "【筋力について】": "20文字以内",
            "【感覚異常について】": "20文字以内",
            "【可動域について】": "20文字以内",
            "【短期目標】": "100文字以内",
            "【長期目標】": "50文字以内",
            "【治療方針】": "120文字以内",
            "【治療内容】": "最大6行",
            "【参加制限に対する具体的な対応方針】": "200文字以内",
            "【機能障害に対する具体的な対応方針】": "200文字以内",
        }
        for index, heading in enumerate(PLAN_HEADINGS):
            section_end = prompt.find("【", prompt.index(heading) + 1)
            if section_end == -1:
                section_end = len(prompt)
            section = prompt[prompt.index(heading):section_end]
            self.assertIn(expected_limits[heading], section)

    def test_distinguishes_unassessed_from_normal_results(self):
        prompt = self.build_prompt()

        self.assertIn("未評価、未実施、未入力と、異常なし、陰性を明確に区別", prompt)
        self.assertIn("評価情報が不足している項目を異常なしと判断しない", prompt)

    def test_forbids_inventing_treatment_content(self):
        prompt = self.build_prompt()

        self.assertIn("①評価結果に基づき治療内容を検討", prompt)
        self.assertIn("入力されていない具体的な運動名、物理療法、治療手技、回数、負荷量を勝手に追加しない", prompt)

    def test_blank_patient_id_is_written_as_unentered(self):
        prompt = self.build_prompt(patient_id="")

        self.assertIn("・患者ID：未入力", prompt)

    def test_entered_patient_id_is_written_unchanged(self):
        prompt = self.build_prompt(patient_id="TEST-001")

        self.assertIn("・患者ID：TEST-001", prompt)

    def test_includes_all_supplied_assessment_data(self):
        prompt = self.build_prompt()

        for input_value in [
            "膝関節",
            "右",
            "テスト用傷病名",
            "2026年01月10日",
            "2026年01月11日",
            "・安静時NRS：1",
            "・動作時NRS：4",
            "・夜間痛NRS：未評価",
            "テスト用疼痛部位",
            "テスト用誘発動作",
            "テスト用疼痛性質",
            "・屈曲：制限あり（制限因子：疼痛）",
            "・膝関節伸展：筋力低下あり",
            "・膝前面：感覚異常なし",
            "・Lachman test：未実施",
            "テスト用参加制限",
            "テスト用柔道整復師所見",
        ]:
            self.assertIn(input_value, prompt)

    def test_uses_experienced_judo_therapist_role(self):
        prompt = self.build_prompt()

        self.assertIn("あなたは臨床経験豊富な柔道整復師です", prompt)
        self.assertNotIn("理学療法士", prompt)


if __name__ == "__main__":
    unittest.main()
