"""Тесты для фабрики LLM."""
import pytest
from unittest.mock import patch, MagicMock


class TestGetLlm:
    def test_unknown_provider_raises(self):
        mock_settings = MagicMock()
        mock_settings.llm_provider = "unknown_provider"

        with patch("llm.provider.settings", mock_settings):
            # Сбрасываем кэш lru_cache перед тестом
            from llm.provider import get_llm
            get_llm.cache_clear()

            with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
                get_llm()

            get_llm.cache_clear()

    def test_ollama_provider_creates_chat_ollama(self):
        mock_settings = MagicMock()
        mock_settings.llm_provider = "ollama"
        mock_settings.ollama_base_url = "http://localhost:11434"
        mock_settings.ollama_model = "qwen2.5:7b"

        mock_ollama_class = MagicMock()

        with patch("llm.provider.settings", mock_settings):
            with patch.dict("sys.modules", {"langchain_ollama": MagicMock(ChatOllama=mock_ollama_class)}):
                from llm.provider import get_llm
                get_llm.cache_clear()
                get_llm()
                mock_ollama_class.assert_called_once_with(
                    base_url="http://localhost:11434",
                    model="qwen2.5:7b",
                )
                get_llm.cache_clear()

    def test_gemini_provider_creates_chat_google(self):
        mock_settings = MagicMock()
        mock_settings.llm_provider = "gemini"
        mock_settings.gemini_model = "gemini-2.0-flash"
        mock_settings.gemini_api_key = "test-key"

        mock_gemini_class = MagicMock()

        with patch("llm.provider.settings", mock_settings):
            with patch.dict("sys.modules", {
                "langchain_google_genai": MagicMock(ChatGoogleGenerativeAI=mock_gemini_class)
            }):
                from llm.provider import get_llm
                get_llm.cache_clear()
                get_llm()
                mock_gemini_class.assert_called_once_with(
                    model="gemini-2.0-flash",
                    google_api_key="test-key",
                )
                get_llm.cache_clear()
