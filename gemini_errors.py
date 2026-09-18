"""Translate Gemini failures without exposing exception text or metadata."""

import math
import re


def _retry_seconds(exc, text):
    details = getattr(exc, 'details', ())
    if not isinstance(details, (list, tuple)):
        details = ()
    for detail in details:
        delay = detail.get('retryDelay') if isinstance(detail, dict) else getattr(detail, 'retry_delay', None)
        if delay is None:
            continue
        try:
            if isinstance(delay, str):
                if not re.fullmatch(r'\d+(?:\.\d+)?s', delay):
                    continue
                seconds = float(delay[:-1])
            else:
                seconds = float(delay.seconds) + float(delay.nanos) / 1_000_000_000
            if math.isfinite(seconds) and seconds >= 0:
                return math.ceil(seconds)
        except (AttributeError, TypeError, ValueError, OverflowError):
            continue
    match = re.search(r'retry in (\d+(?:\.\d+)?)s\b', text)
    if match:
        seconds = float(match.group(1))
        if math.isfinite(seconds):
            return math.ceil(seconds)
    return None


def _error_kind(exc: Exception) -> str:
    """Prefer explicit non-quota failures over incidental words in messages."""
    text = str(exc).lower()
    code = getattr(exc, 'code', None)
    if callable(code):
        code = code()
    code_text = str(code).lower()
    details = getattr(exc, 'details', ())
    invalid_key = 'api_key_invalid' in text or 'api key not valid' in text
    if isinstance(details, (list, tuple)):
        invalid_key |= any(
            (detail.get('reason') if isinstance(detail, dict) else getattr(detail, 'reason', None)) == 'API_KEY_INVALID'
            for detail in details
        )
    if invalid_key:
        return 'invalid_key'
    if code in (401, 403) or any(token in code_text + text for token in ('unauthenticated', 'permission_denied', 'unauthorized', 'forbidden')):
        return 'auth'
    name = type(exc).__name__.lower()
    if isinstance(exc, TimeoutError) or code in (408, 504) or 'deadline_exceeded' in code_text or any(token in text + name for token in ('timeout', 'timed out', 'deadline')):
        return 'timeout'
    if isinstance(exc, ConnectionError) or any(token in text + name for token in ('connection', 'network', 'transporterror', 'dns')):
        return 'connection'
    if code in (404, 503) or any(token in code_text for token in ('not_found', 'unavailable')) or ('model' in text and any(token in text for token in ('not found', 'not supported', 'unavailable', 'not available'))):
        return 'model'
    if code == 429 or 'resource_exhausted' in code_text:
        return 'rate_limit'
    # A known different status must not trigger extra requests based on its text.
    if code is not None:
        return 'unknown'
    if re.search(r'\b429\b|resource_exhausted|quota|rate.?limit', text):
        return 'rate_limit'
    return 'unknown'


def is_rate_limit_error(exc: Exception) -> bool:
    """Whether this failure permits advancing to the next Gemini model."""
    return _error_kind(exc) == 'rate_limit'


def classify_gemini_error(exc: Exception) -> str:
    """Return only fixed Japanese text and an optional validated retry duration."""
    kind = _error_kind(exc)
    if kind == 'invalid_key':
        return 'APIキーが無効です。入力したAPIキーを確認してください。'
    if kind == 'auth':
        return 'AIの認証に失敗しました。APIキーと利用権限を確認してください。'
    if kind == 'rate_limit':
        message = 'AIの利用上限に達したか、リクエストが集中しています。'
        seconds = _retry_seconds(exc, str(exc).lower())
        return message + (f'約{seconds}秒後にもう一度お試しください。' if seconds is not None else 'しばらく時間をおいてもう一度お試しください。')
    if kind == 'timeout':
        return 'AIの応答に時間がかかっています。時間をおいてもう一度お試しください。'
    if kind == 'connection':
        return 'AIとの通信に失敗しました。インターネット接続を確認して、もう一度お試しください。'
    if kind == 'model':
        return '選択したAIモデルは現在利用できません。別のモデルを選ぶか、時間をおいてもう一度お試しください。'
    return 'AIによる生成に失敗しました。時間をおいてもう一度お試しください。'
