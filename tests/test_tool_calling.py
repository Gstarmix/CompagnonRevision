from __future__ import annotations
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
ROOT = Path(__file__).resolve().parent.parent
DIALOGUE_DIR = ROOT / "_scripts" / "dialogue"
for _p in (str(ROOT), str(DIALOGUE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from tool_schemas import (
    ANTHROPIC_TOOLS,
    TOOL_NAME_TO_EVENT_TYPE,
    engine_supports_native_tools,
    get_gemini_function_declarations,
    get_openai_compat_tools,
    tool_call_to_payload,
    tune_prompt_for_engine,
)
class TestToolSchemas(unittest.TestCase):
    def test_anthropic_tools_have_required_fields(self):
        for tool in ANTHROPIC_TOOLS:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("input_schema", tool)
            self.assertEqual(tool["input_schema"]["type"], "object")
    def test_anthropic_has_3_tools(self):
        names = {t["name"] for t in ANTHROPIC_TOOLS}
        self.assertEqual(names, {
            "next_slide", "goto_slide", "suggest_edit",
        })
    def test_gemini_function_declarations_format(self):
        decls = get_gemini_function_declarations()
        self.assertEqual(len(decls), 3)
        for d in decls:
            self.assertIn("name", d)
            self.assertIn("description", d)
            self.assertIn("parameters", d)
            self.assertNotIn("input_schema", d)
    def test_openai_compat_tools_format(self):
        tools = get_openai_compat_tools()
        self.assertEqual(len(tools), 3)
        for t in tools:
            self.assertEqual(t["type"], "function")
            self.assertIn("function", t)
            f = t["function"]
            self.assertIn("name", f)
            self.assertIn("description", f)
            self.assertIn("parameters", f)
class TestEngineSupport(unittest.TestCase):
    def test_cli_subscription_does_not_support_native_tools(self):
        self.assertFalse(engine_supports_native_tools("cli_subscription"))
    def test_api_engines_support_native_tools(self):
        for engine in ("api_anthropic", "gemini_api", "deepseek_api", "groq_api"):
            self.assertTrue(
                engine_supports_native_tools(engine),
                f"Engine {engine} devrait supporter les tools natifs",
            )
    def test_unknown_engine_does_not_support(self):
        self.assertFalse(engine_supports_native_tools("totally_made_up_engine"))
class TestToolCallToPayload(unittest.TestCase):
    def test_next_slide_returns_empty_string(self):
        payload = tool_call_to_payload("next_slide", {})
        self.assertEqual(payload, "")
    def test_goto_slide_returns_n_int(self):
        payload = tool_call_to_payload("goto_slide", {"n": 5})
        self.assertEqual(payload, {"n": 5})
    def test_goto_slide_coerces_string_to_int(self):
        payload = tool_call_to_payload("goto_slide", {"n": "7"})
        self.assertEqual(payload, {"n": 7})
    def test_suggest_edit_with_reason(self):
        payload = tool_call_to_payload("suggest_edit", {
            "file": "AN1/TD/TD5/perso/SCRIPT.md",
            "before": "ancien texte",
            "after": "nouveau texte",
            "reason": "Le corrigé prof attend X.",
        })
        self.assertEqual(payload["file"], "AN1/TD/TD5/perso/SCRIPT.md")
        self.assertEqual(payload["reason"], "Le corrigé prof attend X.")
    def test_suggest_edit_optional_reason(self):
        payload = tool_call_to_payload("suggest_edit", {
            "file": "X.md", "before": "a", "after": "b",
        })
        self.assertNotIn("reason", payload)
    def test_unknown_tool_raises(self):
        with self.assertRaises(ValueError):
            tool_call_to_payload("ce_tool_existe_pas", {})
class TestToolNameMapping(unittest.TestCase):
    def test_all_tool_names_have_event_type(self):
        anthropic_names = {t["name"] for t in ANTHROPIC_TOOLS}
        mapped_names = set(TOOL_NAME_TO_EVENT_TYPE.keys())
        self.assertEqual(anthropic_names, mapped_names)
class TestTunePromptForEngine(unittest.TestCase):
    def test_cli_subscription_passthrough(self):
        out = tune_prompt_for_engine("Vous êtes un colleur.", "cli_subscription")
        self.assertEqual(out, "Vous êtes un colleur.")
    def test_api_anthropic_passthrough(self):
        out = tune_prompt_for_engine("X", "api_anthropic")
        self.assertEqual(out, "X")
    def test_gemini_prelude_added(self):
        out = tune_prompt_for_engine("Original.", "gemini_api")
        self.assertIn("[Note pour le moteur]", out)
        self.assertIn("Gemini", out)
        self.assertTrue(out.endswith("Original."))
    def test_deepseek_prelude_added(self):
        out = tune_prompt_for_engine("Original.", "deepseek_api")
        self.assertIn("[Note pour le moteur]", out)
        self.assertTrue(out.endswith("Original."))
    def test_groq_prelude_added(self):
        out = tune_prompt_for_engine("Original.", "groq_api")
        self.assertIn("[Note pour le moteur]", out)
class TestEmitToolEvents(unittest.TestCase):
    def setUp(self):
        from claude_client import ClaudeClient
        self.client = ClaudeClient(
            engine="api_anthropic",
            system_prompt="test",
            mode="guidé",
        )
    def _make_final(self, blocks):
        mock = MagicMock()
        mock.content = blocks
        return mock
    def _make_tool_block(self, name, input_dict):
        block = MagicMock()
        block.type = "tool_use"
        block.name = name
        block.input = input_dict
        return block
    def _make_text_block(self, text):
        block = MagicMock()
        block.type = "text"
        block.text = text
        return block
    def test_no_tool_blocks_emits_nothing(self):
        final = self._make_final([self._make_text_block("réponse simple")])
        events = []
        self.client._emit_tool_events_from_final(
            final, lambda ev: events.append(ev),
        )
        self.assertEqual(len(events), 0)
    def test_next_slide_tool_emits_event(self):
        final = self._make_final([
            self._make_text_block("OK on passe."),
            self._make_tool_block("next_slide", {}),
        ])
        events = []
        self.client._emit_tool_events_from_final(
            final, lambda ev: events.append(ev),
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type.value, "next_slide")
    def test_goto_slide_tool_emits_event_with_n(self):
        final = self._make_final([
            self._make_tool_block("goto_slide", {"n": 3}),
        ])
        events = []
        self.client._emit_tool_events_from_final(
            final, lambda ev: events.append(ev),
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].type.value, "goto_slide")
        self.assertEqual(events[0].payload, {"n": 3})
    def test_unknown_tool_skipped_silently(self):
        final = self._make_final([
            self._make_tool_block("inexistant", {}),
        ])
        events = []
        self.client._emit_tool_events_from_final(
            final, lambda ev: events.append(ev),
        )
        self.assertEqual(len(events), 0)
if __name__ == "__main__":
    unittest.main()