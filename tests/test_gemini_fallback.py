import unittest
from types import SimpleNamespace
from unittest.mock import call, patch

import app
import gemini_errors
import gemini_retry
from test_gemini_errors import DummyError


LATEST = 'gemini-flash-latest'
FLASH_3_5 = 'gemini-3.5-flash'
FLASH = 'gemini-2.5-flash'
LITE = 'gemini-2.5-flash-lite'


class GeminiFallbackTest(unittest.TestCase):
    def generate(self, selected, outcomes, expected_models):
        with patch.object(app.genai, 'configure'), patch.object(app.genai, 'GenerativeModel') as factory, patch.object(app, 'st') as ui:
            factory.return_value.generate_content.side_effect = outcomes
            app.generate_with_gemini('DUMMY_KEY', selected, 'same prompt', '生成中')
            self.assertEqual(factory.call_args_list, [call(model) for model in expected_models])
            self.assertEqual(factory.return_value.generate_content.call_args_list,
                             [call('same prompt', request_options={'retry': None}) for _ in expected_models])
            return ui

    def test_first_success_stops_after_one_request(self):
        ui = self.generate(LATEST, [SimpleNamespace(text='result')], [LATEST])
        ui.info.assert_not_called()
        ui.text_area.assert_called_once_with('Copy & Paste', 'result', height=700)

    def test_second_success_stops_and_names_flash(self):
        ui = self.generate(LATEST, [DummyError(code=429), SimpleNamespace(text='flash result')], [LATEST, FLASH])
        ui.info.assert_called_once_with('上位モデルの利用上限に達したため、Gemini 2.5 Flashで生成しました。')
        ui.text_area.assert_called_once_with('Copy & Paste', 'flash result', height=700)
        ui.error.assert_not_called()

    def test_third_success_stops_and_names_lite(self):
        ui = self.generate(LATEST, [DummyError(code=429), DummyError(code=429), SimpleNamespace(text='lite result')], [LATEST, FLASH, LITE])
        ui.info.assert_called_once_with('上位モデルの利用上限に達したため、Gemini 2.5 Flash Liteで生成しました。')
        ui.text_area.assert_called_once_with('Copy & Paste', 'lite result', height=700)

    def test_all_rate_limited_stop_at_three_with_last_delay(self):
        ui = self.generate(LATEST, [DummyError(code=429), DummyError(code=429), DummyError(code=429, details=[{'retryDelay': '7.2s'}])], [LATEST, FLASH, LITE])
        ui.error.assert_called_once()
        self.assertIn('約8秒後', ui.error.call_args.args[0])
        self.assertNotIn('SECRET_KEY', ui.error.call_args.args[0])
        ui.text_area.assert_not_called()
        ui.info.assert_not_called()

    def test_non_rate_errors_never_fallback_even_if_message_mentions_quota(self):
        for error in [DummyError('API_KEY_INVALID quota'), DummyError(code=401), DummyError(code=403), ConnectionError('quota'), TimeoutError('429'), DummyError('quota', code=404), DummyError('unknown'), DummyError(code=504)]:
            with self.subTest(error=error):
                ui = self.generate(LATEST, [error], [LATEST])
                ui.error.assert_called_once()
                ui.text_area.assert_not_called()

    def test_flash_only_falls_forward_to_lite(self):
        self.generate(FLASH, [DummyError(code=429), SimpleNamespace(text='ok')], [FLASH, LITE])

    def test_lite_and_explicit_other_model_do_not_fallback(self):
        for selected in [LITE, 'gemini-1.5-pro']:
            with self.subTest(selected=selected):
                self.generate(selected, [DummyError(code=429)], [selected])

    def test_duplicate_candidates_are_not_requested_twice(self):
        with patch.object(app, 'GEMINI_FALLBACK_MODELS', (LATEST, LATEST, FLASH, FLASH, LITE), create=True):
            self.generate(LATEST, [DummyError(code=429), DummyError(code=429), SimpleNamespace(text='ok')], [LATEST, FLASH, LITE])

    def test_404_on_second_candidate_stops(self):
        self.generate(LATEST, [DummyError(code=429), DummyError(code=404)], [LATEST, FLASH])

    def test_503_retries_same_model_with_exponential_backoff(self):
        with patch.object(app.genai, 'configure'), patch.object(app.genai, 'GenerativeModel') as factory, \
                patch.object(app, 'st') as ui, patch.object(gemini_retry, 'sleep') as sleep:
            factory.return_value.generate_content.side_effect = [
                DummyError(code=503),
                DummyError(code=503),
                DummyError(code=503),
                SimpleNamespace(text='recovered'),
            ]

            app.generate_with_gemini('DUMMY_KEY', LATEST, 'same prompt', '生成中')

            factory.assert_called_once_with(LATEST)
            self.assertEqual(
                factory.return_value.generate_content.call_args_list,
                [call('same prompt', request_options={'retry': None})] * 4,
            )
            self.assertEqual(sleep.call_args_list, [call(1), call(2), call(4)])
            ui.text_area.assert_called_once_with('Copy & Paste', 'recovered', height=700)
            ui.error.assert_not_called()
            ui.info.assert_not_called()

    def test_503_exhaustion_falls_back_to_3_5(self):
        with patch.object(app.genai, 'configure'), patch.object(app.genai, 'GenerativeModel') as factory, \
                patch.object(app, 'st') as ui, patch.object(gemini_retry, 'sleep') as sleep:
            factory.return_value.generate_content.side_effect = [
                DummyError(code=503),
                DummyError(code=503),
                DummyError(code=503),
                DummyError(code=503),
                SimpleNamespace(text='fallback result'),
            ]

            app.generate_with_gemini('DUMMY_KEY', LATEST, 'same prompt', '生成中')

            self.assertEqual(factory.call_args_list, [call(LATEST), call(FLASH_3_5)])
            self.assertEqual(factory.return_value.generate_content.call_count, 5)
            self.assertEqual(sleep.call_args_list, [call(1), call(2), call(4)])
            ui.text_area.assert_called_once_with('Copy & Paste', 'fallback result', height=700)
            ui.error.assert_not_called()
            ui.info.assert_not_called()

    def test_503_fallback_retries_3_5_with_exponential_backoff(self):
        with patch.object(app.genai, 'configure'), patch.object(app.genai, 'GenerativeModel') as factory, \
                patch.object(app, 'st') as ui, patch.object(gemini_retry, 'sleep') as sleep:
            factory.return_value.generate_content.side_effect = [
                DummyError(code=503),
                DummyError(code=503),
                DummyError(code=503),
                DummyError(code=503),
                DummyError(code=503),
                DummyError(code=503),
                DummyError(code=503),
                SimpleNamespace(text='recovered on fallback'),
            ]

            app.generate_with_gemini('DUMMY_KEY', LATEST, 'same prompt', '生成中')

            self.assertEqual(factory.call_args_list, [call(LATEST), call(FLASH_3_5)])
            self.assertEqual(factory.return_value.generate_content.call_count, 8)
            self.assertEqual(
                sleep.call_args_list,
                [call(1), call(2), call(4), call(1), call(2), call(4)],
            )
            ui.text_area.assert_called_once_with(
                'Copy & Paste', 'recovered on fallback', height=700
            )
            ui.error.assert_not_called()
            ui.info.assert_not_called()

    def test_503_exhaustion_on_3_5_shows_temporary_error(self):
        with patch.object(app.genai, 'configure'), patch.object(app.genai, 'GenerativeModel') as factory, \
                patch.object(app, 'st') as ui, patch.object(gemini_retry, 'sleep') as sleep:
            factory.return_value.generate_content.side_effect = [DummyError(code=503)] * 8

            app.generate_with_gemini('DUMMY_KEY', LATEST, 'same prompt', '生成中')

            self.assertEqual(factory.call_args_list, [call(LATEST), call(FLASH_3_5)])
            self.assertEqual(factory.return_value.generate_content.call_count, 8)
            self.assertEqual(
                sleep.call_args_list,
                [call(1), call(2), call(4), call(1), call(2), call(4)],
            )
            ui.error.assert_called_once()
            self.assertIn('一時的', ui.error.call_args.args[0])
            ui.text_area.assert_not_called()
            ui.info.assert_not_called()

    def test_404_on_503_fallback_stops_without_trying_rate_limit_models(self):
        with patch.object(app.genai, 'configure'), patch.object(app.genai, 'GenerativeModel') as factory, \
                patch.object(app, 'st') as ui, patch.object(gemini_retry, 'sleep') as sleep:
            factory.return_value.generate_content.side_effect = [
                DummyError(code=503),
                DummyError(code=503),
                DummyError(code=503),
                DummyError(code=503),
                DummyError(code=404),
            ]

            app.generate_with_gemini('DUMMY_KEY', LATEST, 'same prompt', '生成中')

            self.assertEqual(factory.call_args_list, [call(LATEST), call(FLASH_3_5)])
            self.assertEqual(factory.return_value.generate_content.call_count, 5)
            self.assertEqual(sleep.call_args_list, [call(1), call(2), call(4)])
            ui.error.assert_called_once()
            self.assertIn('モデル', ui.error.call_args.args[0])
            ui.text_area.assert_not_called()

    def test_429_on_503_fallback_continues_existing_rate_limit_chain(self):
        with patch.object(app.genai, 'configure'), patch.object(app.genai, 'GenerativeModel') as factory, \
                patch.object(app, 'st') as ui, patch.object(gemini_retry, 'sleep') as sleep:
            factory.return_value.generate_content.side_effect = [
                DummyError(code=503),
                DummyError(code=503),
                DummyError(code=503),
                DummyError(code=503),
                DummyError(code=429),
                SimpleNamespace(text='rate fallback result'),
            ]

            app.generate_with_gemini('DUMMY_KEY', LATEST, 'same prompt', '生成中')

            self.assertEqual(
                factory.call_args_list,
                [call(LATEST), call(FLASH_3_5), call(FLASH)],
            )
            self.assertEqual(factory.return_value.generate_content.call_count, 6)
            self.assertEqual(sleep.call_args_list, [call(1), call(2), call(4)])
            ui.info.assert_called_once_with(
                '上位モデルの利用上限に達したため、Gemini 2.5 Flashで生成しました。'
            )
            ui.text_area.assert_called_once_with(
                'Copy & Paste', 'rate fallback result', height=700
            )

    def test_pure_rate_limit_predicate(self):
        predicate = getattr(gemini_errors, 'is_rate_limit_error', None)
        self.assertTrue(callable(predicate), 'Missing rate-limit predicate')
        for error in [DummyError(code=429), DummyError('quota exceeded'), DummyError('rate limit exceeded'), DummyError(code=lambda: 'StatusCode.RESOURCE_EXHAUSTED')]:
            self.assertIs(predicate(error), True)
        for error in [DummyError('API_KEY_INVALID quota'), DummyError('quota', code=403), DummyError('quota', code=503), ConnectionError('429'), TimeoutError('quota'), DummyError()]:
            self.assertIs(predicate(error), False)
