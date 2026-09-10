import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from test_gemini_errors import DummyError


class GeminiAppTest(unittest.TestCase):
    def test_both_modes_show_safe_errors(self):
        for mode in [0, 1]:
            for error, expected in [
                (DummyError(code=429, details=[{'retryDelay': '12.2s'}]), '約13秒後'),
                (DummyError('API_KEY_INVALID SECRET_KEY internal_metadata'), 'APIキー'),
                (ConnectionError('SECRET_KEY internal_metadata'), '通信'),
                (TimeoutError('SECRET_KEY internal_metadata'), '時間'),
                (DummyError(code=404), 'モデル'),
                (DummyError(), '生成に失敗'),
            ]:
                with self.subTest(mode=mode, expected=expected), patch('google.generativeai.configure'), patch('google.generativeai.GenerativeModel') as model:
                    model.return_value.generate_content.side_effect = error
                    at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
                    at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[mode]).run()
                    at.sidebar.text_input[0].set_value('DUMMY_API_KEY')
                    at.text_input(key='new_diagnosis' if mode == 0 else 'plan_disease_name').set_value('テスト傷病名')
                    at.button(key='new_generate' if mode == 0 else 'plan_generate').click().run()
                    self.assertEqual(len(at.exception), 0)
                    self.assertEqual(len(at.error), 1)
                    self.assertIn(expected, at.error[0].value)
                    self.assertNotIn('SECRET_KEY', at.error[0].value)
                    self.assertNotIn('internal_metadata', at.error[0].value)
                    self.assertNotIn('DUMMY_API_KEY', at.error[0].value)
                    self.assertFalse(any(item.label == 'Copy & Paste' for item in at.text_area))
