import unittest

from evaluation_config import JOINT_CONFIG, ROM_FACTORS


class EvaluationConfigTest(unittest.TestCase):
    def test_every_joint_has_required_sections(self):
        required = {"diseases", "rom", "mmt", "sensory", "special_tests"}
        for joint, config in JOINT_CONFIG.items():
            self.assertTrue(required.issubset(config), joint)
            for key in required:
                self.assertGreater(len(config[key]), 0, f"{joint}: {key}")

    def test_every_joint_supports_custom_disease(self):
        for joint, config in JOINT_CONFIG.items():
            self.assertIn("その他", config["diseases"], joint)

    def test_rom_factors_match_initial_spec(self):
        self.assertEqual(ROM_FACTORS, ["疼痛", "筋性", "軟部組織性", "骨性"])


if __name__ == "__main__":
    unittest.main()
