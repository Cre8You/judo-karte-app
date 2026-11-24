import unittest
from unittest.mock import call, patch, sentinel

import app
import gemini_client
import gemini_errors
import gemini_retry
from test_gemini_errors import DummyError


LATEST = 'gemini-flash-latest'
FLASH_3_8 = 'gemini-3.8-flash'
LITE_3_5 = 'gemini-3.5-flash-lite'
FLASH_2_5 = 'gemini-2.5-flash'


def ok(first, *rest):
    return (first, iter(rest))


def failing_rest(first_chunks, error):
    def gen():
        yield from first_chunks
        raise error
    return gen()


class GeminiFallbackTest(unittest.TestCase):
    def generate(self, selected, outcomes, expected_models):
        with patch.object(gemini_client, 'make_client', return_value=sentinel.client) as make_client, \
                patch.object(gemini_client, 'open_stream', side_effect=outcomes) as opener, \
                patch.object(gemini_retry, 'sleep') as sleep, \
                patch.object(app, 'st') as ui:
            app.generate_with_gemini('DUMMY_KEY', selected, 'same prompt', '生成中')
            make_client.assert_called_once_with('DUMMY_KEY')
            self.assertEqual(opener.call_args_list,
                             [call(sentinel.client, model, 'same prompt') for model in expected_models])
            self.sleep = sleep
            return ui

    def final_text(self, ui):
        output = ui.empty.return_value
        output.text_area.assert_called_once()
        self.assertEqual(output.text_area.call_args.args[0], 'Copy & Paste')
        return output.text_area.call_args.args[1]

    def test_first_success_streams_and_stops_after_one_request(self):
        ui = self.generate(LATEST, [ok('前半', '中盤', '後半')], [LATEST])
        ui.info.assert_not_called()
        ui.error.assert_not_called()
        self.assertEqual(self.final_text(ui), '前半中盤後半')
        # Text is redrawn as each chunk arrives.
        self.assertEqual(ui.empty.return_value.text.call_args_list,
                         [call('前半'), call('前半中盤'), call('前半中盤後半')])

    def test_rate_limit_falls_forward_and_names_model(self):
        ui = self.generate(LATEST, [DummyError(code=429), ok('flash result')], [LATEST, FLASH_3_8])
        ui.info.assert_called_once_with('上位モデルの利用上限に達したため、Gemini 3.8 Flashで生成しました。')
        self.assertEqual(self.final_text(ui), 'flash result')

    def test_rate_limit_chain_reaches_lite(self):
        ui = self.generate(LATEST, [DummyError(code=429), DummyError(code=429), ok('lite result')], [LATEST, FLASH_3_8, LITE_3_5])
        ui.info.assert_called_once_with('上位モデルの利用上限に達したため、Gemini 3.5 Flash-Liteで生成しました。')
        self.assertEqual(self.final_text(ui), 'lite result')

    def test_all_rate_limited_stop_with_last_delay(self):
        ui = self.generate(LATEST, [DummyError(code=429), DummyError(code=429), DummyError(code=429, details=[{'retryDelay': '7.2s'}])], [LATEST, FLASH_3_8, LITE_3_5])
        ui.error.assert_called_once()
        self.assertIn('約8秒後', ui.error.call_args.args[0])
        self.assertNotIn('SECRET_KEY', ui.error.call_args.args[0])
        ui.empty.return_value.text_area.assert_not_called()
        ui.info.assert_not_called()

    def test_non_retryable_errors_never_fallback(self):
        for error in [DummyError('API_KEY_INVALID quota'), DummyError(code=401), DummyError(code=403), ConnectionError('quota'),
                      TimeoutError('429'), DummyError('unknown'), DummyError(code=504), DummyError(code=400)]:
            with self.subTest(error=error):
                ui = self.generate(LATEST, [error], [LATEST])
                ui.error.assert_called_once()
                ui.empty.return_value.text_area.assert_not_called()

    def test_models_outside_chain_do_not_fallback(self):
        for selected in [LITE_3_5, FLASH_2_5]:
            with self.subTest(selected=selected):
                self.generate(selected, [DummyError(code=429)], [selected])

    def test_fixed_flash_falls_forward_to_lite(self):
        self.generate(FLASH_3_8, [DummyError(code=429), ok('ok')], [FLASH_3_8, LITE_3_5])

    def test_duplicate_candidates_are_not_requested_twice(self):
        with patch.object(app, 'GEMINI_FALLBACK_MODELS', (LATEST, LATEST, FLASH_3_8, FLASH_3_8, LITE_3_5)):
            self.generate(LATEST, [DummyError(code=429), DummyError(code=429), ok('ok')], [LATEST, FLASH_3_8, LITE_3_5])

    def test_unavailable_latest_alias_falls_forward_and_tells_user(self):
        ui = self.generate(LATEST, [DummyError('model not found', code=404), ok('3.8 result')], [LATEST, FLASH_3_8])
        ui.info.assert_called_once_with('選択したモデルが現在利用できなかったため、Gemini 3.8 Flashで生成しました。')
        ui.error.assert_not_called()
        self.assertEqual(self.final_text(ui), '3.8 result')

    def test_404_on_last_candidate_stops_with_model_error(self):
        ui = self.generate(LATEST, [DummyError(code=404)] * 3, [LATEST, FLASH_3_8, LITE_3_5])
        ui.error.assert_called_once()
        self.assertIn('モデル', ui.error.call_args.args[0])
        ui.empty.return_value.text_area.assert_not_called()

    def test_404_on_model_outside_chain_does_not_fallback(self):
        ui = self.generate(FLASH_2_5, [DummyError(code=404)], [FLASH_2_5])
        self.assertIn('モデル', ui.error.call_args.args[0])

    def test_failures_are_logged_without_reaching_the_ui(self):
        with self.assertLogs('judo_karte_app', level='WARNING') as logs:
            ui = self.generate(LATEST, [DummyError('This model models/x is no longer available', code=404), ok('ok')], [LATEST, FLASH_3_8])
        self.assertIn('model=gemini-flash-latest', logs.output[0])
        self.assertIn('code=404', logs.output[0])
        self.assertIn('no longer available', logs.output[0])
        for args in ui.info.call_args_list + ui.error.call_args_list:
            self.assertNotIn('no longer available', args.args[0])

    def test_503_retries_same_model_with_short_backoff(self):
        ui = self.generate(LATEST, [DummyError(code=503), DummyError(code=503), ok('recovered')], [LATEST] * 3)
        self.assertEqual(self.sleep.call_args_list, [call(1), call(2)])
        self.assertEqual(self.final_text(ui), 'recovered')
        ui.info.assert_not_called()

    def test_503_exhaustion_falls_forward_and_tells_user(self):
        ui = self.generate(LATEST, [DummyError(code=503)] * 3 + [ok('fallback result')], [LATEST] * 3 + [FLASH_3_8])
        self.assertEqual(self.sleep.call_args_list, [call(1), call(2)])
        ui.info.assert_called_once_with('上位モデルが混雑していたため、Gemini 3.8 Flashで生成しました。')
        self.assertEqual(self.final_text(ui), 'fallback result')

    def test_503_everywhere_has_bounded_wait_then_temporary_error(self):
        ui = self.generate(LATEST, [DummyError(code=503)] * 9, [LATEST] * 3 + [FLASH_3_8] * 3 + [LITE_3_5] * 3)
        # Worst case is 9 seconds of sleeping (previously 14 s + up to 8 requests).
        self.assertEqual(sum(c.args[0] for c in self.sleep.call_args_list), 9)
        ui.error.assert_called_once()
        self.assertIn('一時的', ui.error.call_args.args[0])
        ui.empty.return_value.text_area.assert_not_called()

    def test_503_then_429_keeps_first_reason(self):
        ui = self.generate(LATEST, [DummyError(code=503)] * 3 + [DummyError(code=429), ok('lite')], [LATEST] * 3 + [FLASH_3_8, LITE_3_5])
        ui.info.assert_called_once_with('上位モデルが混雑していたため、Gemini 3.5 Flash-Liteで生成しました。')

    def test_error_mid_stream_keeps_partial_text(self):
        ui = self.generate(LATEST, [('前半', failing_rest(['中盤'], TimeoutError('SECRET_KEY')))], [LATEST])
        ui.error.assert_called_once()
        self.assertIn('時間', ui.error.call_args.args[0])
        ui.warning.assert_called_once()
        self.assertEqual(self.final_text(ui), '前半中盤')

    def test_empty_response_shows_error(self):
        ui = self.generate(LATEST, [ok('')], [LATEST])
        ui.error.assert_called_once()
        self.assertIn('返ってきませんでした', ui.error.call_args.args[0])
        ui.empty.return_value.text_area.assert_not_called()

    def test_pure_rate_limit_predicate(self):
        predicate = getattr(gemini_errors, 'is_rate_limit_error', None)
        self.assertTrue(callable(predicate), 'Missing rate-limit predicate')
        for error in [DummyError(code=429), DummyError('quota exceeded'), DummyError('rate limit exceeded'), DummyError(code=lambda: 'StatusCode.RESOURCE_EXHAUSTED')]:
            self.assertIs(predicate(error), True)
        for error in [DummyError('API_KEY_INVALID quota'), DummyError('quota', code=403), DummyError('quota', code=503), ConnectionError('429'), TimeoutError('quota'), DummyError()]:
            self.assertIs(predicate(error), False)


if __name__ == '__main__':
    unittest.main()
