"""Retry transient Gemini service failures (503) on the same model."""

from time import sleep

import gemini_client
from gemini_errors import is_service_unavailable_error

# Shorter than before (1, 2, 4): after 2 retries the app moves on to the next
# model instead of keeping the user waiting.
RETRY_DELAYS = (1, 2)


def open_stream_with_retry(client, model_id: str, prompt: str):
    for retry_index in range(len(RETRY_DELAYS) + 1):
        try:
            return gemini_client.open_stream(client, model_id, prompt)
        except Exception as exc:
            if not is_service_unavailable_error(exc) or retry_index == len(RETRY_DELAYS):
                raise
            sleep(RETRY_DELAYS[retry_index])
