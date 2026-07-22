import datetime
import unittest

from plan_validation import validate_plan_inputs


class PlanValidationTest(unittest.TestCase):
    def setUp(self):
        self.onset_date = datetime.date(2026, 1, 10)
        self.rehab_start_date = datetime.date(2026, 1, 11)

    def test_blank_patient_id_allows_generation_and_uses_unentered_label(self):
        warning, patient_id_for_prompt = validate_plan_inputs(
            "",
            "テスト用傷病名",
            self.onset_date,
            self.rehab_start_date,
        )

        self.assertIsNone(warning)
        self.assertEqual(patient_id_for_prompt, "未入力")

    def test_entered_patient_id_is_passed_to_prompt(self):
        warning, patient_id_for_prompt = validate_plan_inputs(
            "TEST-001",
            "テスト用傷病名",
            self.onset_date,
            self.rehab_start_date,
        )

        self.assertIsNone(warning)
        self.assertEqual(patient_id_for_prompt, "TEST-001")

    def test_disease_name_remains_required(self):
        warning, _ = validate_plan_inputs(
            "",
            "",
            self.onset_date,
            self.rehab_start_date,
        )

        self.assertEqual(warning, "傷病名を入力してください")

    def test_rehab_start_date_cannot_precede_onset_date(self):
        warning, _ = validate_plan_inputs(
            "",
            "テスト用傷病名",
            self.onset_date,
            datetime.date(2026, 1, 9),
        )

        self.assertEqual(warning, "リハ開始日が発症日より前です。日付を確認してください")


if __name__ == "__main__":
    unittest.main()
