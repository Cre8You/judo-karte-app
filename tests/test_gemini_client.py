import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from google.genai import errors, types

import gemini_client
from gemini_errors import classify_gemini_error, is_rate_limit_error, is_service_unavailable_error


def api_error(code, status, message='SECRET_KEY internal_metadata', details=()):
    return errors.APIError(code, {'error': {'code': code, 'status': status, 'message': message, 'details': list(details)}})


def fake_client(*streams):
    client = MagicMock()
    client.models.generate_content_stream.side_effect = streams
    return client


def chunks(*texts):
    return iter([SimpleNamespace(text=t) for t in texts])


class ThinkingConfigTest(unittest.TestCase):
    def test_gemini_3_and_latest_alias_think_low(self):
        for model in ['gemini-flash-latest', 'gemini-3.8-flash']:
            with self.subTest(model=model):
                self.assertEqual(gemini_client.thinking_config_for(model).thinking_level, types.ThinkingLevel.LOW)

    def test_gemini_2_5_flash_disables_thinking(self):
        self.assertEqual(gemini_client.thinking_config_for('gemini-2.5-flash').thinking_budget, 0)

    def test_lite_models_keep_default(self):
        for model in ['gemini-3.5-flash-lite', 'gemini-2.5-flash-lite']:
            with self.subTest(model=model):
                self.assertIsNone(gemini_client.thinking_config_for(model))


class ClientOptionsTest(unittest.TestCase):
    def test_client_has_timeout_and_no_sdk_retry(self):
        client = gemini_client.make_client('DUMMY_KEY')
        options = client._api_client._http_options
        self.assertEqual(options.timeout, gemini_client.REQUEST_TIMEOUT_MS)
        self.assertEqual(options.retry_options.attempts, 1)


class OpenStreamTest(unittest.TestCase):
    def test_returns_first_text_and_rest_skipping_empty_chunks(self):
        client = fake_client(chunks(None, '一', '', '二', '三'))
        first, rest = gemini_client.open_stream(client, 'gemini-flash-latest', 'prompt')
        self.assertEqual(first, '一')
        self.assertEqual(list(rest), ['二', '三'])
        kwargs = client.models.generate_content_stream.call_args.kwargs
        self.assertEqual(kwargs['model'], 'gemini-flash-latest')
        self.assertEqual(kwargs['contents'], 'prompt')
        self.assertEqual(kwargs['config'].thinking_config.thinking_level, types.ThinkingLevel.LOW)

    def test_lite_sends_no_config(self):
        client = fake_client(chunks('ok'))
        gemini_client.open_stream(client, 'gemini-3.5-flash-lite', 'prompt')
        self.assertIsNone(client.models.generate_content_stream.call_args.kwargs['config'])

    def test_errors_surface_before_anything_is_shown(self):
        def boom():
            raise api_error(503, 'UNAVAILABLE')
            yield  # pragma: no cover
        client = fake_client(boom())
        with self.assertRaises(errors.APIError):
            gemini_client.open_stream(client, 'gemini-flash-latest', 'prompt')

    def test_rejected_thinking_setting_retries_once_without_it(self):
        def rejected():
            raise api_error(400, 'INVALID_ARGUMENT', message='Thinking level is not supported for this model.')
            yield  # pragma: no cover
        client = fake_client(rejected(), chunks('ok'))
        first, _ = gemini_client.open_stream(client, 'gemini-flash-latest', 'prompt')
        self.assertEqual(first, 'ok')
        configs = [c.kwargs['config'] for c in client.models.generate_content_stream.call_args_list]
        self.assertIsNotNone(configs[0])
        self.assertIsNone(configs[1])

    def test_other_400_is_not_retried(self):
        def bad():
            raise api_error(400, 'INVALID_ARGUMENT', message='Request contains an invalid argument.')
            yield  # pragma: no cover
        client = fake_client(bad(), chunks('never'))
        with self.assertRaises(errors.APIError):
            gemini_client.open_stream(client, 'gemini-flash-latest', 'prompt')
        self.assertEqual(client.models.generate_content_stream.call_count, 1)


class NewSdkErrorClassificationTest(unittest.TestCase):
    def test_new_sdk_errors_are_classified(self):
        self.assertTrue(is_service_unavailable_error(api_error(503, 'UNAVAILABLE')))
        self.assertTrue(is_rate_limit_error(api_error(429, 'RESOURCE_EXHAUSTED')))
        self.assertIn('一時的', classify_gemini_error(api_error(503, 'UNAVAILABLE')))
        self.assertIn('モデル', classify_gemini_error(api_error(404, 'NOT_FOUND')))

    def test_new_sdk_retry_delay_is_read_from_response_json(self):
        error = api_error(429, 'RESOURCE_EXHAUSTED', details=[{'@type': 'type.googleapis.com/google.rpc.RetryInfo', 'retryDelay': '12.2s'}])
        message = classify_gemini_error(error)
        self.assertIn('約13秒後', message)
        self.assertNotIn('SECRET_KEY', message)

    def test_new_sdk_invalid_key_reason(self):
        error = api_error(400, 'INVALID_ARGUMENT', message='SECRET_KEY', details=[{'reason': 'API_KEY_INVALID'}])
        self.assertIn('APIキー', classify_gemini_error(error))

    def test_httpx_connect_error_is_connection(self):
        import httpx2 as httpx
        self.assertIn('通信', classify_gemini_error(httpx.ConnectError('SECRET_KEY')))
        self.assertIn('時間', classify_gemini_error(httpx.ReadTimeout('SECRET_KEY')))


if __name__ == '__main__':
    unittest.main()
