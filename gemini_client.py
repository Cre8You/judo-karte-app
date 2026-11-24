"""Thin wrapper around the google-genai SDK (the successor of google-generativeai).

All SDK-specific code lives here so the rest of the app (and the tests) only
deal with plain text chunks.
"""

import logging
from typing import Iterator, Optional, Tuple

from google import genai
from google.genai import errors, types

from gemini_errors import describe_for_log, is_invalid_key_error

logger = logging.getLogger("judo_karte_app")

# Give up on a single request after 90 seconds instead of spinning forever.
REQUEST_TIMEOUT_MS = 90_000

# The SDK must not retry on its own: 503 / 429 follow this app's policies
# in gemini_retry.py and app.py.
NO_SDK_RETRY = types.HttpRetryOptions(attempts=1)


def make_client(api_key: str) -> genai.Client:
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS, retry_options=NO_SDK_RETRY),
    )


def thinking_config_for(model_id: str) -> Optional[types.ThinkingConfig]:
    """Keep "thinking" light: chart text needs formatting, not deep reasoning.

    Gemini 3 family (and the -latest alias, which now points to it) think at
    a medium level by default, which is the main source of slow responses.
    """
    if "lite" in model_id:
        return None  # Lite models already think minimally by default.
    if model_id.startswith("gemini-2.5"):
        return types.ThinkingConfig(thinking_budget=0)
    return types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)


def _texts(stream) -> Iterator[str]:
    for chunk in stream:
        text = getattr(chunk, "text", None)
        if text:
            yield text


def _open(client, model_id: str, prompt: str, thinking: Optional[types.ThinkingConfig]) -> Tuple[str, Iterator[str]]:
    config = types.GenerateContentConfig(thinking_config=thinking) if thinking else None
    stream = client.models.generate_content_stream(model=model_id, contents=prompt, config=config)
    texts = _texts(stream)
    # The HTTP request is sent when the first chunk is read, so connection,
    # 429 and 503 errors surface here, before anything is shown on screen.
    first = next(texts, "")
    return first, texts


def _is_thinking_rejected(exc: Exception) -> bool:
    # Any 400 while a thinking setting was sent may mean the model behind an
    # alias does not accept it; the error wording is not stable enough to match.
    return isinstance(exc, errors.APIError) and exc.code == 400 and not is_invalid_key_error(exc)


def open_stream(client, model_id: str, prompt: str) -> Tuple[str, Iterator[str]]:
    """Start streaming and return (first text, iterator over the remaining text)."""
    thinking = thinking_config_for(model_id)
    try:
        return _open(client, model_id, prompt, thinking)
    except Exception as exc:
        # If the model behind an alias does not accept this thinking setting,
        # fall back to the model's default once instead of failing.
        if thinking is None or not _is_thinking_rejected(exc):
            raise
        logger.warning("Thinking setting rejected, retrying with model default: model=%s %s", model_id, describe_for_log(exc))
        return _open(client, model_id, prompt, None)
