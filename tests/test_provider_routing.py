from __future__ import annotations
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "_scripts"))
sys.path.insert(0, str(ROOT / "_scripts" / "dialogue"))
class TestProviderRouting(unittest.TestCase):
    def test_supported_engines_contient_les_5(self):
        from claude_client import (
            SUPPORTED_ENGINES, ENGINE_CLI, ENGINE_API, ENGINE_GEMINI,
            ENGINE_DEEPSEEK, ENGINE_GROQ,
        )
        self.assertIn(ENGINE_CLI, SUPPORTED_ENGINES)
        self.assertIn(ENGINE_API, SUPPORTED_ENGINES)
        self.assertIn(ENGINE_GEMINI, SUPPORTED_ENGINES)
        self.assertIn(ENGINE_DEEPSEEK, SUPPORTED_ENGINES)
        self.assertIn(ENGINE_GROQ, SUPPORTED_ENGINES)
        self.assertEqual(len(SUPPORTED_ENGINES), 5)
    def test_openai_compatible_providers_format(self):
        from claude_client import _OPENAI_COMPATIBLE_PROVIDERS
        required = {"base_url", "api_key_env", "default_model",
                    "model_env", "provider_name", "signup_url",
                    "model_prefix"}
        for engine_id, cfg in _OPENAI_COMPATIBLE_PROVIDERS.items():
            self.assertEqual(
                required, set(cfg.keys()),
                f"Provider {engine_id} a des clés inattendues : {cfg.keys()}"
            )
            self.assertTrue(cfg["base_url"].startswith("https://"))
            self.assertTrue(cfg["api_key_env"].isupper())
            self.assertIn("_", cfg["api_key_env"])
    def test_engine_inconnu_leve(self):
        from claude_client import ClaudeClient
        with self.assertRaises(ValueError) as cm:
            ClaudeClient(engine="hf_inference", system_prompt="x")
        self.assertIn("Engine inconnu", str(cm.exception))
    def test_dispatch_deepseek_appelle_openai_compatible(self):
        from claude_client import (
            ClaudeClient, ENGINE_DEEPSEEK, _OPENAI_COMPATIBLE_PROVIDERS,
        )
        client = ClaudeClient(engine=ENGINE_DEEPSEEK, system_prompt="x")
        client.append_user_message("test")
        with patch.object(
            ClaudeClient, "_stream_via_openai_compatible",
            return_value={"input_tokens": 10, "output_tokens": 5},
        ) as mock_method:
            stats = client.stream_response(on_event=lambda e: None)
        mock_method.assert_called_once()
        cfg_arg = mock_method.call_args[0][1]
        self.assertEqual(cfg_arg, _OPENAI_COMPATIBLE_PROVIDERS[ENGINE_DEEPSEEK])
        self.assertEqual(stats, {"input_tokens": 10, "output_tokens": 5})
    def test_dispatch_groq_appelle_openai_compatible(self):
        from claude_client import (
            ClaudeClient, ENGINE_GROQ, _OPENAI_COMPATIBLE_PROVIDERS,
        )
        client = ClaudeClient(engine=ENGINE_GROQ, system_prompt="x")
        client.append_user_message("test")
        with patch.object(
            ClaudeClient, "_stream_via_openai_compatible",
            return_value={"input_tokens": None, "output_tokens": None},
        ) as mock_method:
            client.stream_response(on_event=lambda e: None)
        mock_method.assert_called_once()
        cfg_arg = mock_method.call_args[0][1]
        self.assertEqual(cfg_arg, _OPENAI_COMPATIBLE_PROVIDERS[ENGINE_GROQ])
    def test_dispatch_gemini_appelle_stream_via_gemini(self):
        from claude_client import ClaudeClient, ENGINE_GEMINI
        client = ClaudeClient(engine=ENGINE_GEMINI, system_prompt="x")
        client.append_user_message("test")
        with patch.object(
            ClaudeClient, "_stream_via_gemini",
            return_value={"input_tokens": 1, "output_tokens": 2},
        ) as mock_method:
            client.stream_response(on_event=lambda e: None)
        mock_method.assert_called_once()
    def test_dispatch_api_anthropic_appelle_stream_via_api(self):
        from claude_client import ClaudeClient, ENGINE_API
        client = ClaudeClient(engine=ENGINE_API, system_prompt="x")
        client.append_user_message("test")
        with patch.object(
            ClaudeClient, "_stream_via_api",
            return_value={"input_tokens": 1, "output_tokens": 2},
        ) as mock_method:
            client.stream_response(on_event=lambda e: None)
        mock_method.assert_called_once()
    def test_deepseek_sans_key_leve_clear_message(self):
        import os
        from claude_client import (
            ClaudeClient, ENGINE_DEEPSEEK, ClaudeClientError,
        )
        env_backup = os.environ.pop("DEEPSEEK_API_KEY", None)
        try:
            client = ClaudeClient(engine=ENGINE_DEEPSEEK, system_prompt="x")
            client.append_user_message("test")
            fake_openai = MagicMock()
            with patch.dict(sys.modules, {"openai": fake_openai}):
                with self.assertRaises(ClaudeClientError) as cm:
                    client.stream_response(on_event=lambda e: None)
            msg = str(cm.exception)
            self.assertIn("DEEPSEEK_API_KEY", msg)
            self.assertIn("platform.deepseek.com", msg)
        finally:
            if env_backup is not None:
                os.environ["DEEPSEEK_API_KEY"] = env_backup
    def test_groq_sans_key_leve_clear_message(self):
        import os
        from claude_client import (
            ClaudeClient, ENGINE_GROQ, ClaudeClientError,
        )
        env_backup = os.environ.pop("GROQ_API_KEY", None)
        try:
            client = ClaudeClient(engine=ENGINE_GROQ, system_prompt="x")
            client.append_user_message("test")
            fake_openai = MagicMock()
            with patch.dict(sys.modules, {"openai": fake_openai}):
                with self.assertRaises(ClaudeClientError) as cm:
                    client.stream_response(on_event=lambda e: None)
            msg = str(cm.exception)
            self.assertIn("GROQ_API_KEY", msg)
            self.assertIn("console.groq.com", msg)
        finally:
            if env_backup is not None:
                os.environ["GROQ_API_KEY"] = env_backup
if __name__ == "__main__":
    unittest.main(verbosity=2)