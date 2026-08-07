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
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openrouter import ChatOpenRouter

load_dotenv(override=False)

SUPPORTED_PROVIDERS = ("anthropic", "gemini", "openrouter")

# An agent turn (tool calls + synthesis) does not fit in the 10s this used to allow; that timeout
# fired mid-call rather than protecting against anything.
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))


def get_llm_provider() -> str:
    return os.getenv("LLM_PROVIDER", "anthropic").strip().lower() or "anthropic"


def _require_api_key(provider: str, variable_name: str) -> None:
    if not os.getenv(variable_name):
        raise ValueError(
            f"{variable_name} is required when LLM_PROVIDER={provider}"
        )


def build_llm() -> BaseChatModel:
    provider = get_llm_provider()

    if provider == "anthropic":
        _require_api_key(provider, "ANTHROPIC_API_KEY")
        # No `temperature`: Claude 5 models reject it outright with
        # `400 invalid_request_error: "temperature is deprecated for this model"`.
        return ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5"),
            max_retries=0,
            timeout=LLM_TIMEOUT,
        )

    if provider == "gemini":
        _require_api_key(provider, "GOOGLE_API_KEY")
        return ChatGoogleGenerativeAI(
            model=(
                os.getenv("GOOGLE_MODEL")
                or os.getenv("GEMINI_MODEL")
                or "gemini-3.6-flash"
            ),
            temperature=0,
            max_retries=0,
            timeout=LLM_TIMEOUT,
        )

    if provider == "openrouter":
        _require_api_key(provider, "OPENROUTER_API_KEY")
        return ChatOpenRouter(
            model=os.getenv("OPENROUTER_MODEL", "openrouter/free"),
            temperature=0,
            max_retries=0,
            timeout=LLM_TIMEOUT,
        )

    supported = ", ".join(SUPPORTED_PROVIDERS)
    raise ValueError(
        f"Unsupported LLM_PROVIDER '{provider}'. Supported providers: {supported}"
    )
