import unittest
from types import SimpleNamespace

from gemini_errors import classify_gemini_error


class DummyError(Exception):
    def __init__(self, message='SECRET_KEY internal_metadata', code=None, details=()):
        super().__init__(message)
        self.code = code
        self.details = details


class GeminiErrorsTest(unittest.TestCase):
    def test_categories_are_safe(self):
        cases = [
            (DummyError(code=429), '利用上限'),
            (DummyError('quota exceeded SECRET_KEY'), '利用上限'),
            (DummyError('rate limit exceeded SECRET_KEY'), '利用上限'),
            (DummyError('API_KEY_INVALID SECRET_KEY'), 'APIキー'),
            (DummyError(details=[{'reason': 'API_KEY_INVALID'}]), 'APIキー'),
            (ConnectionError('SECRET_KEY'), '通信'),
            (TimeoutError('SECRET_KEY'), '時間'),
            (DummyError(code=504), '時間'),
            (DummyError(code=404), 'モデル'),
            (DummyError(code=503), 'モデル'),
            (DummyError('model is not supported SECRET_KEY'), 'モデル'),
            (DummyError(), '生成に失敗'),
        ]
        for error, expected in cases:
            with self.subTest(error=type(error), expected=expected):
                result = classify_gemini_error(error)
                self.assertIn(expected, result)
                self.assertNotIn('SECRET_KEY', result)
                self.assertNotIn('internal_metadata', result)

    def test_retry_delay_formats_round_up(self):
        cases = [
            DummyError(code=429, details=[{'retryDelay': '12.2s'}]),
            DummyError(code=429, details=[SimpleNamespace(retry_delay=SimpleNamespace(seconds=12, nanos=200000000))]),
            DummyError('429 Please retry in 12.2s. SECRET_KEY'),
        ]
        for error in cases:
            with self.subTest(error=error):
                self.assertIn('約13秒後にもう一度お試しください', classify_gemini_error(error))

    def test_invalid_or_missing_delay_is_not_displayed(self):
        for delay in [None, 'SECRET_KEY', '-1s', 'NaNs', 'infs']:
            with self.subTest(delay=delay):
                result = classify_gemini_error(DummyError(code=429, details=[{'retryDelay': delay}]))
                self.assertNotIn('約', result)
                self.assertNotIn('SECRET_KEY', result)


if __name__ == '__main__':
    unittest.main()
