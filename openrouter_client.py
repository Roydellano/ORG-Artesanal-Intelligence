"""Server-side OpenRouter text client and explicit connection check."""

import json
import os
import math
import time
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import dotenv_values


ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
PRIVACY_VERSION = "openrouter-deny-zdr-2026-09-12"


class OpenRouterError(RuntimeError):
    """Safe error for callers; excludes credentials and provider response bodies."""


class OpenRouterRateLimit(OpenRouterError):
    def __init__(self, retry_after=None):
        self.retry_after = retry_after
        wait = (f"The provider requested a wait of {retry_after} seconds." if retry_after is not None else
                "The provider did not supply a retry time; this may be a temporary throttle or a longer quota limit.")
        super().__init__("OpenRouter HTTP 429: The selected model or account is rate-limited. " + wait +
                         " Resume later or explicitly finish with offline evidence review. Repeated restarts will not reset the provider quota.")


def retry_after_seconds(value):
    """Accept only standard numeric/date Retry-After values; never echo header text."""
    if not value:
        return None
    try:
        if str(value).strip().isdigit():
            return min(int(value), 7 * 86400)
        when = parsedate_to_datetime(str(value)).timestamp()
        return max(0, min(math.ceil(when - time.time()), 7 * 86400))
    except (ValueError, TypeError, OverflowError):
        return None


def settings() -> dict:
    config = {**dotenv_values(Path(__file__).resolve().parent / ".env"), **os.environ}
    try:
        tokens = int(config.get("OPENROUTER_MAX_TOKENS") or 2048)
        timeout = int(config.get("OPENROUTER_TIMEOUT_SECONDS") or 40)
        if not 512 <= tokens <= 8192 or not 5 <= timeout <= 60:
            raise ValueError()
    except (ValueError, TypeError):
        raise OpenRouterError("OPENROUTER_MAX_TOKENS must be 512–8192 and OPENROUTER_TIMEOUT_SECONDS 5–60.") from None
    model = (config.get("OPENROUTER_MODEL") or DEFAULT_MODEL).strip()
    zdr_env = (config.get("OPENROUTER_ZDR") or "on").strip().lower()
    zdr_enabled = zdr_env not in ("off", "false", "0", "no", "disabled")
    return {"model": model, "api_key": (config.get("OPENROUTER_API_KEY") or "").strip(),
            "max_tokens": tokens, "timeout": timeout,
            "reasoning": (config.get("OPENROUTER_REASONING") or "off").lower() == "on",
            "zdr": zdr_enabled}


def public_settings() -> dict:
    try:
        config = settings()
        return {key: value for key, value in config.items() if key != "api_key"} | {
            "configured": bool(config["api_key"]),
            "synthetic_only": config["model"].endswith(":free") and config["zdr"],
            "privacy_policy": PRIVACY_VERSION if config["zdr"] else "openrouter-testing-zdr-off",
            "zdr": config["zdr"]}
    except OpenRouterError as error:
        return {"configured": False, "error": str(error)}


def chat(messages: list[dict[str, str]], *, max_tokens: int = 2048, timeout: float = 60,
         synthetic: bool = False, usage_callback=None, zdr: bool | None = None) -> str:
    """Load server config and make one bounded, non-streaming API request.

    Environment variables take precedence over the repository's .env file.
    No automatic retries: the future investigation controller owns retry budgets.
    """
    config = settings()
    api_key, model = config["api_key"], config["model"]
    use_zdr = config["zdr"] if zdr is None else bool(zdr)
    if not api_key:
        raise OpenRouterError("Set OPENROUTER_API_KEY in .env.")
    if not messages or max_tokens <= 0 or not 0 < timeout <= 60:
        raise ValueError("Provide messages and a positive max_tokens limit.")
    if model.endswith(":free") and not synthetic and use_zdr:
        raise OpenRouterError("Free endpoints are enabled only for app-generated fictional demos. For uploaded records use offline review, a model with no-collection/ZDR routing, or toggle ZDR off for testing.")

    if not use_zdr:
        provider_config = {"allow_fallbacks": True}
    elif synthetic:
        provider_config = {"allow_fallbacks": False, "require_parameters": True}
    else:
        provider_config = {"data_collection": "deny", "zdr": True, "allow_fallbacks": False,
                           "require_parameters": True}

    request = Request(
        ENDPOINT,
        data=json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "stream": False,
            "reasoning": {"enabled": config["reasoning"], "exclude": True},
            "provider": provider_config,
        }).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except HTTPError as error:
        status = error.code
        retry_after = retry_after_seconds(error.headers.get("Retry-After")) if status == 429 and error.headers else None
        error.close()
        if status == 429:
            raise OpenRouterRateLimit(retry_after) from None
        detail = {400: "Check the exact model ID and supported parameters.",
                  401: "API key is missing, invalid or expired. Check server .env.",
                  402: "The account or selected endpoint requires credit.",
                  403: "Access denied. Check model eligibility and account privacy settings.",
                  404: "No eligible endpoint. Check model ID and no-collection/ZDR support; privacy restrictions were not relaxed.",
                  502: "Provider returned an error. Try again later.",
                  503: "No provider is currently available under the configured routing policy."}.get(status, "Provider request failed. Try again later.")
        raise OpenRouterError(f"OpenRouter HTTP {status}: {detail}") from None
    except (URLError, TimeoutError, OSError) as error:
        # socket.timeout is TimeoutError on 3.10+; URLError carries it on .reason.
        if isinstance(getattr(error, "reason", error), TimeoutError):
            raise OpenRouterError(f"OpenRouter request exceeded its {timeout:g}s timeout. Raise OPENROUTER_TIMEOUT_SECONDS (maximum 60) or give the investigation a longer time budget.") from None
        raise OpenRouterError("OpenRouter connection failed. Check this machine's network access to openrouter.ai.") from None
    except (ValueError, UnicodeError):
        raise OpenRouterError("OpenRouter returned invalid JSON.") from None

    try:
        choice = payload["choices"][0]
        content = choice["message"]["content"]
        if choice.get("finish_reason") == "length":
            raise OpenRouterError("Model output hit the token limit before completing its action. Set OPENROUTER_REASONING=off or increase OPENROUTER_MAX_TOKENS (maximum 8192).")
        if choice.get("finish_reason") != "stop":
            raise ValueError("Incomplete response")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Empty response")
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        raise OpenRouterError("OpenRouter returned an incomplete or invalid text response.") from None
    if usage_callback is not None:
        usage = payload.get("usage", {})
        usage_callback({key: usage.get(key) for key in ("cost", "prompt_tokens", "completion_tokens")})
    return content


if __name__ == "__main__":
    try:
        print(chat([{"role": "user", "content": "Reply with only: Connection successful"}], synthetic=True))
    except OpenRouterError as error:
        raise SystemExit(str(error)) from None
