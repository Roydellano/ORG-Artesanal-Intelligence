"""Server-side OpenRouter text client and explicit connection check."""

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import dotenv_values


ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(RuntimeError):
    """Safe error for callers; excludes credentials and provider response bodies."""


def chat(messages: list[dict[str, str]], *, max_tokens: int = 1024) -> str:
    """Load server config and make one bounded, non-streaming API request.

    Environment variables take precedence over the repository's .env file.
    No automatic retries: the future investigation controller owns retry budgets.
    """
    config = {
        **dotenv_values(Path(__file__).resolve().parent / ".env"),
        **os.environ,
    }
    api_key = (config.get("OPENROUTER_API_KEY") or "").strip()
    model = (config.get("OPENROUTER_MODEL") or "").strip()
    if not api_key or not model:
        raise OpenRouterError("Set OPENROUTER_API_KEY and OPENROUTER_MODEL in .env.")
    if not messages or max_tokens <= 0:
        raise ValueError("Provide messages and a positive max_tokens limit.")

    request = Request(
        ENDPOINT,
        data=json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": False,
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except HTTPError as error:
        status = error.code
        error.close()
        raise OpenRouterError(
            f"OpenRouter returned HTTP {status}. Check credentials, credit, model ID, or service availability."
        ) from None
    except (URLError, TimeoutError, OSError):
        raise OpenRouterError("OpenRouter connection failed or timed out.") from None
    except (ValueError, UnicodeError):
        raise OpenRouterError("OpenRouter returned invalid JSON.") from None

    try:
        choice = payload["choices"][0]
        content = choice["message"]["content"]
        if choice.get("finish_reason") != "stop":
            raise ValueError("Incomplete response")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Empty response")
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise OpenRouterError("OpenRouter returned an incomplete or invalid text response.") from None
    return content


if __name__ == "__main__":
    try:
        print(chat([{"role": "user", "content": "Reply with only: Connection successful"}]))
    except OpenRouterError as error:
        raise SystemExit(str(error)) from None
