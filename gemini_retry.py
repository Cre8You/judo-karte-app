"""Retry transient Gemini service failures without changing models."""

from time import sleep

from gemini_errors import is_service_unavailable_error


RETRY_DELAYS = (1, 2, 4)


def generate_content_with_retry(model, prompt: str):
    for retry_index in range(len(RETRY_DELAYS) + 1):
        try:
            return model.generate_content(prompt, request_options={"retry": None})
        except Exception as exc:
            if not is_service_unavailable_error(exc) or retry_index == len(RETRY_DELAYS):
                raise
            sleep(RETRY_DELAYS[retry_index])
