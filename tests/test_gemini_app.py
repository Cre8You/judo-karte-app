import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from test_gemini_errors import DummyError

APP_PATH = str(Path(__file__).resolve().parents[1] / 'app.py')


def run_generation(mode):
    at = AppTest.from_file(APP_PATH).run()
    at.sidebar.radio[0].set_value(at.sidebar.radio[0].options[mode]).run()
    at.sidebar.text_input[0].set_value('DUMMY_API_KEY')
    at.text_input(key='new_diagnosis' if mode == 0 else 'plan_disease_name').set_value('テスト傷病名')
    at.button(key='new_generate' if mode == 0 else 'plan_generate').click().run()
    return at


class GeminiAppTest(unittest.TestCase):
    def test_both_modes_display_fallback_result_and_model_name(self):
        for mode in [0, 1]:
            with self.subTest(mode=mode), patch('gemini_client.make_client'), \
                    patch('gemini_client.open_stream') as opener:
                opener.side_effect = [DummyError(code=429), ('フォールバック', iter(['生成結果']))]
                at = run_generation(mode)
                self.assertEqual(len(at.exception), 0)
                self.assertEqual(len(at.error), 0)
                self.assertEqual([item.value for item in at.text_area if item.label == 'Copy & Paste'], ['フォールバック生成結果'])
                self.assertTrue(any('Gemini 3.8 Flashで生成しました' in item.value for item in at.info))
                self.assertEqual([c.args[1] for c in opener.call_args_list], ['gemini-flash-latest', 'gemini-3.8-flash'])
                self.assertEqual(opener.call_args_list[0].args[2], opener.call_args_list[1].args[2])

    def test_both_modes_retry_503_on_the_same_model(self):
        for mode in [0, 1]:
            with self.subTest(mode=mode), patch('gemini_client.make_client'), \
                    patch('gemini_client.open_stream') as opener, patch('gemini_retry.sleep') as sleep:
                opener.side_effect = [DummyError(code=503), ('再試行成功', iter([]))]
                at = run_generation(mode)
                self.assertEqual(len(at.exception), 0)
                self.assertEqual(len(at.error), 0)
                self.assertEqual([item.value for item in at.text_area if item.label == 'Copy & Paste'], ['再試行成功'])
                self.assertEqual([c.args[1] for c in opener.call_args_list], ['gemini-flash-latest'] * 2)
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
                with self.subTest(mode=mode, expected=expected), patch('gemini_client.make_client'), \
                        patch('gemini_client.open_stream', side_effect=error), patch('gemini_retry.sleep'):
                    at = run_generation(mode)
                    self.assertEqual(len(at.exception), 0)
                    self.assertEqual(len(at.error), 1)
                    self.assertIn(expected, at.error[0].value)
                    self.assertNotIn('SECRET_KEY', at.error[0].value)
                    self.assertNotIn('internal_metadata', at.error[0].value)
                    self.assertNotIn('DUMMY_API_KEY', at.error[0].value)
                    self.assertFalse(any(item.label == 'Copy & Paste' for item in at.text_area))

    def test_model_selector_lists_only_current_models(self):
        at = AppTest.from_file(APP_PATH).run()
        options = at.sidebar.selectbox[0].options
        self.assertEqual(len(options), 4)
        for retired in ['1.5', '3.0']:
            self.assertFalse(any(retired in option for option in options))


if __name__ == '__main__':
    unittest.main()
