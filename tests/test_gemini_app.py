import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest
from test_gemini_errors import DummyError


class GeminiAppTest(unittest.TestCase):
    def test_both_modes_display_fallback_result_and_model_name(self):
        for mode in [0, 1]:
            with self.subTest(mode=mode), patch('google.generativeai.configure'), patch('google.generativeai.GenerativeModel') as model:
                model.return_value.generate_content.side_effect = [
                    DummyError(code=429), SimpleNamespace(text='フォールバック生成結果')]
                at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
                at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[mode]).run()
                at.sidebar.text_input[0].set_value('DUMMY_API_KEY')
                at.text_input(key='new_diagnosis' if mode == 0 else 'plan_disease_name').set_value('テスト傷病名')
                at.button(key='new_generate' if mode == 0 else 'plan_generate').click().run()
                self.assertEqual(len(at.exception), 0)
                self.assertEqual(len(at.error), 0)
                self.assertEqual([item.value for item in at.text_area if item.label == 'Copy & Paste'], ['フォールバック生成結果'])
                self.assertTrue(any('Gemini 2.5 Flashで生成しました' in item.value for item in at.info))
                self.assertEqual([item.args[0] for item in model.call_args_list], ['gemini-flash-latest', 'gemini-2.5-flash'])
                requests = model.return_value.generate_content.call_args_list
                self.assertEqual(len(requests), 2)
                self.assertEqual(requests[0], requests[1])

    def test_both_modes_retry_503_on_the_same_model(self):
        for mode in [0, 1]:
            with self.subTest(mode=mode), patch('google.generativeai.configure'), \
                    patch('google.generativeai.GenerativeModel') as model, patch('gemini_retry.sleep') as sleep:
                model.return_value.generate_content.side_effect = [
                    DummyError(code=503), SimpleNamespace(text='再試行成功')]
                at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
                at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[mode]).run()
                at.sidebar.text_input[0].set_value('DUMMY_API_KEY')
                at.text_input(key='new_diagnosis' if mode == 0 else 'plan_disease_name').set_value('テスト傷病名')
                at.button(key='new_generate' if mode == 0 else 'plan_generate').click().run()
                self.assertEqual(len(at.exception), 0)
                self.assertEqual(len(at.error), 0)
                self.assertEqual(
                    [item.value for item in at.text_area if item.label == 'Copy & Paste'],
                    ['再試行成功'],
                )
                self.assertEqual([item.args[0] for item in model.call_args_list], ['gemini-flash-latest'])
                self.assertEqual(model.return_value.generate_content.call_count, 2)
                sleep.assert_called_once_with(1)

    def test_both_modes_show_safe_errors(self):
        for mode in [0, 1]:
            for error, expected in [
                (DummyError(code=429, details=[{'retryDelay': '12.2s'}]), '約13秒後'),
                (DummyError('API_KEY_INVALID SECRET_KEY internal_metadata'), 'APIキー'),
                (ConnectionError('SECRET_KEY internal_metadata'), '通信'),
                (TimeoutError('SECRET_KEY internal_metadata'), '時間'),
                (DummyError(code=404), 'モデル'),
                (DummyError(code=503), '一時的'),
                (DummyError(), '生成に失敗'),
            ]:
                with self.subTest(mode=mode, expected=expected), patch('google.generativeai.configure'), \
                        patch('google.generativeai.GenerativeModel') as model, patch('gemini_retry.sleep'):
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
