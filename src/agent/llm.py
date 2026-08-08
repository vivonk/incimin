"""The agent's chat model. Anthropic only.

Multi-provider dispatch (gemini, openrouter) was removed: the golden path has to be
deterministic, and three interchangeable providers meant three different tool-calling
behaviours and three ways for a demo to drift.

Environment:
    ANTHROPIC_API_KEY   required
    ANTHROPIC_MODEL     defaults to claude-sonnet-5
    LLM_TIMEOUT         seconds per call, default 120
"""
import logging
import os
import ssl
import warnings

# Suppress unverified HTTPS request warnings
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# Disable SSL verification globally to support corporate proxies
ssl.create_default_context = ssl._create_unverified_context

from dotenv import load_dotenv
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel

load_dotenv(override=False)

log = logging.getLogger("incimin.llm")

DEFAULT_MODEL = "claude-sonnet-5"

# An agent turn (tool calls + synthesis) does not fit in the 10s this used to allow; that timeout
# fired mid-call rather than protecting against anything.
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))

_warned_about_provider = False


def _warn_if_provider_set() -> None:
    """`LLM_PROVIDER` is no longer read. Say so once rather than silently ignoring it.

    Existing `.env` files still carry `LLM_PROVIDER=openrouter` from the multi-provider era.
    Erroring on it would break those setups for a variable that no longer does anything; saying
    nothing would leave someone convinced they are talking to a provider they are not.
    """
    global _warned_about_provider
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider and provider != "anthropic" and not _warned_about_provider:
        _warned_about_provider = True
        log.warning(
            "LLM_PROVIDER=%r is ignored — this project is Anthropic-only. Remove it from .env.",
            provider,
        )


def build_llm() -> BaseChatModel:
    _warn_if_provider_set()

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise ValueError("ANTHROPIC_API_KEY is required")

    # No `temperature`: Claude 5 models reject it outright with
    # `400 invalid_request_error: "temperature is deprecated for this model"`.
    return ChatAnthropic(
        model=os.getenv("ANTHROPIC_MODEL") or DEFAULT_MODEL,
        max_retries=0,
        timeout=LLM_TIMEOUT,
    )
