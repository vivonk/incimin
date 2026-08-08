import logging
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.agent import llm as llm_module
from src.agent.llm import DEFAULT_MODEL, LLM_TIMEOUT, build_llm


class TestLLM(unittest.TestCase):
    def setUp(self):
        # The "provider is ignored" warning fires once per process; reset so each test sees it.
        llm_module._warned_about_provider = False

    def test_builds_an_anthropic_model(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
            with patch("src.agent.llm.ChatAnthropic") as mock_anthropic:
                expected = MagicMock()
                mock_anthropic.return_value = expected

                self.assertIs(build_llm(), expected)
                mock_anthropic.assert_called_once_with(
                    model=DEFAULT_MODEL,
                    max_retries=0,
                    timeout=LLM_TIMEOUT,
                )

    def test_model_is_overridable(self):
        environment = {"ANTHROPIC_API_KEY": "test-key", "ANTHROPIC_MODEL": "claude-opus-5"}
        with patch.dict(os.environ, environment, clear=True):
            with patch("src.agent.llm.ChatAnthropic") as mock_anthropic:
                build_llm()

                self.assertEqual(mock_anthropic.call_args.kwargs["model"], "claude-opus-5")

    def test_blank_model_falls_back_to_the_default(self):
        """An empty `ANTHROPIC_MODEL=` line in .env must not become the model name."""
        environment = {"ANTHROPIC_API_KEY": "test-key", "ANTHROPIC_MODEL": ""}
        with patch.dict(os.environ, environment, clear=True):
            with patch("src.agent.llm.ChatAnthropic") as mock_anthropic:
                build_llm()

                self.assertEqual(mock_anthropic.call_args.kwargs["model"], DEFAULT_MODEL)

    def test_omits_temperature(self):
        """Claude 5 rejects `temperature` outright: 400 "temperature is deprecated for this model"."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True):
            with patch("src.agent.llm.ChatAnthropic") as mock_anthropic:
                build_llm()

                self.assertNotIn("temperature", mock_anthropic.call_args.kwargs)

    def test_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "ANTHROPIC_API_KEY"):
                build_llm()

    def test_stale_provider_setting_warns_but_still_builds(self):
        """Existing .env files carry LLM_PROVIDER=openrouter; it is ignored, not fatal."""
        environment = {"ANTHROPIC_API_KEY": "test-key", "LLM_PROVIDER": "openrouter"}
        with patch.dict(os.environ, environment, clear=True):
            with patch("src.agent.llm.ChatAnthropic"):
                with self.assertLogs("incimin.llm", level=logging.WARNING) as captured:
                    build_llm()

        self.assertIn("openrouter", captured.output[0])
        self.assertIn("Anthropic-only", captured.output[0])

    def test_anthropic_provider_setting_is_not_warned_about(self):
        environment = {"ANTHROPIC_API_KEY": "test-key", "LLM_PROVIDER": "anthropic"}
        with patch.dict(os.environ, environment, clear=True):
            with patch("src.agent.llm.ChatAnthropic"):
                with patch.object(llm_module.log, "warning") as mock_warning:
                    build_llm()

                    mock_warning.assert_not_called()

    def test_provider_warning_fires_only_once(self):
        environment = {"ANTHROPIC_API_KEY": "test-key", "LLM_PROVIDER": "gemini"}
        with patch.dict(os.environ, environment, clear=True):
            with patch("src.agent.llm.ChatAnthropic"):
                with patch.object(llm_module.log, "warning") as mock_warning:
                    build_llm()
                    build_llm()

                    self.assertEqual(mock_warning.call_count, 1)


if __name__ == "__main__":
    unittest.main()
