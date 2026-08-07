import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent.llm import LLM_TIMEOUT, build_llm, get_llm_provider


class TestLLMProvider(unittest.TestCase):
    def test_anthropic_is_default_provider(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
            with patch("src.agent.llm.ChatAnthropic") as mock_anthropic:
                expected = MagicMock()
                mock_anthropic.return_value = expected

                self.assertEqual(get_llm_provider(), "anthropic")
                self.assertIs(build_llm(), expected)
                mock_anthropic.assert_called_once_with(
                    model="claude-sonnet-5",
                    max_retries=0,
                    timeout=LLM_TIMEOUT,
                )

    def test_anthropic_omits_temperature(self):
        """Claude 5 rejects `temperature` outright: 400 "temperature is deprecated for this model"."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
            with patch("src.agent.llm.ChatAnthropic") as mock_anthropic:
                build_llm()

                self.assertNotIn("temperature", mock_anthropic.call_args.kwargs)

    def test_gemini_provider(self):
        environment = {
            "LLM_PROVIDER": "GeMiNi",
            "GOOGLE_API_KEY": "test-key",
            "GEMINI_MODEL": "gemini-test-model",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch("src.agent.llm.ChatGoogleGenerativeAI") as mock_gemini:
                expected = MagicMock()
                mock_gemini.return_value = expected

                self.assertEqual(get_llm_provider(), "gemini")
                self.assertIs(build_llm(), expected)
                mock_gemini.assert_called_once_with(
                    model="gemini-test-model",
                    temperature=0,
                    max_retries=0,
                    timeout=LLM_TIMEOUT,
                )

    def test_google_model_takes_precedence_over_gemini_model(self):
        environment = {
            "LLM_PROVIDER": "gemini",
            "GOOGLE_API_KEY": "test-key",
            "GOOGLE_MODEL": "google-model",
            "GEMINI_MODEL": "legacy-model",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch("src.agent.llm.ChatGoogleGenerativeAI") as mock_gemini:
                build_llm()

                mock_gemini.assert_called_once_with(
                    model="google-model",
                    temperature=0,
                    max_retries=0,
                    timeout=LLM_TIMEOUT,
                )

    def test_openrouter_provider(self):
        environment = {
            "LLM_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "test-key",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch("src.agent.llm.ChatOpenRouter") as mock_openrouter:
                build_llm()

                mock_openrouter.assert_called_once_with(
                    model="openrouter/free",
                    temperature=0,
                    max_retries=0,
                    timeout=LLM_TIMEOUT,
                )

    def test_unsupported_provider_fails_clearly(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "openai"}, clear=True):
            with self.assertRaisesRegex(
                ValueError,
                "Unsupported LLM_PROVIDER 'openai'.*anthropic, gemini, openrouter",
            ):
                build_llm()

    def test_anthropic_requires_api_key(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "anthropic"}, clear=True):
            with self.assertRaisesRegex(ValueError, "ANTHROPIC_API_KEY"):
                build_llm()

    def test_gemini_requires_api_key(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "gemini"}, clear=True):
            with self.assertRaisesRegex(ValueError, "GOOGLE_API_KEY"):
                build_llm()


if __name__ == "__main__":
    unittest.main()
