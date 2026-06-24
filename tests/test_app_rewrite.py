import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "_scripts"
for _p in (
    str(ROOT),
    str(SCRIPTS),
    str(SCRIPTS / "dialogue"),
    str(SCRIPTS / "audio"),
    str(SCRIPTS / "quota"),
    str(SCRIPTS / "web"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)
class TestApiRewrite(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
    def _make_fake_client(self, response_text):
        fake = MagicMock()
        fake._history = []
        type(fake).history = property(lambda self_: list(self_._history))
        def _fake_append(text):
            fake._history.append({"role": "user", "content": text})
        def _fake_stream(on_event):
            fake._history.append({"role": "assistant", "content": response_text})
            return {"input_tokens": 100, "output_tokens": 50}
        fake.append_user_message.side_effect = _fake_append
        fake.stream_response.side_effect = _fake_stream
        return fake
    def test_empty_text_returns_400(self):
        r = self.client.post("/api/rewrite", json={"text": "", "intent": "reformulate"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.get_json()["error"], "text vide")
    def test_whitespace_only_text_returns_400(self):
        r = self.client.post("/api/rewrite", json={"text": "   \n  ", "intent": "reformulate"})
        self.assertEqual(r.status_code, 400)
    def test_invalid_intent_returns_400(self):
        r = self.client.post("/api/rewrite", json={"text": "hello world", "intent": "summarize"})
        self.assertEqual(r.status_code, 400)
        body = r.get_json()
        self.assertEqual(body["error"], "intent invalide")
        self.assertIn("reformulate", body["allowed"])
    def test_text_too_long_returns_400(self):
        big = "a" * 9000
        r = self.client.post("/api/rewrite", json={"text": big, "intent": "concise"})
        self.assertEqual(r.status_code, 400)
        body = r.get_json()
        self.assertEqual(body["error"], "text trop long")
        self.assertEqual(body["got_chars"], 9000)
    def test_successful_rewrite_returns_rewritten(self):
        fake = self._make_fake_client("Bonjour, ceci est une version reformulée.")
        with patch("app.ClaudeClient", return_value=fake), \
             patch("app._read_engine_pref", return_value="cli_subscription"):
            r = self.client.post(
                "/api/rewrite",
                json={"text": "Salut alors euh donc voilà tu vois", "intent": "reformulate"},
            )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        body = r.get_json()
        self.assertEqual(body["rewritten"], "Bonjour, ceci est une version reformulée.")
        self.assertEqual(body["intent"], "reformulate")
        self.assertEqual(body["engine"], "cli_subscription")
    def test_strips_wrapping_quotes(self):
        fake = self._make_fake_client('"Texte propre."')
        with patch("app.ClaudeClient", return_value=fake), \
             patch("app._read_engine_pref", return_value="cli_subscription"):
            r = self.client.post(
                "/api/rewrite",
                json={"text": "le brouillon initial qui doit etre nettoyé", "intent": "fix_typos"},
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["rewritten"], "Texte propre.")
    def test_strips_french_guillemets(self):
        fake = self._make_fake_client("« Texte propre. »")
        with patch("app.ClaudeClient", return_value=fake), \
             patch("app._read_engine_pref", return_value="cli_subscription"):
            r = self.client.post(
                "/api/rewrite",
                json={"text": "le brouillon initial qui doit etre nettoyé", "intent": "concise"},
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["rewritten"], "Texte propre.")
    def test_quota_exhausted_returns_429(self):
        from claude_client import ClaudeQuotaExhaustedError
        fake = MagicMock()
        fake.append_user_message = MagicMock()
        fake.stream_response.side_effect = ClaudeQuotaExhaustedError("quota épuisé")
        with patch("app.ClaudeClient", return_value=fake), \
             patch("app._read_engine_pref", return_value="cli_subscription"):
            r = self.client.post(
                "/api/rewrite",
                json={"text": "un brouillon long enough", "intent": "expand"},
            )
        self.assertEqual(r.status_code, 429)
        body = r.get_json()
        self.assertEqual(body["error"], "quota_exhausted")
        self.assertIn("quota", body["detail"])
    def test_claude_error_returns_502(self):
        from claude_client import ClaudeClientError
        fake = MagicMock()
        fake.append_user_message = MagicMock()
        fake.stream_response.side_effect = ClaudeClientError("API down")
        with patch("app.ClaudeClient", return_value=fake), \
             patch("app._read_engine_pref", return_value="cli_subscription"):
            r = self.client.post(
                "/api/rewrite",
                json={"text": "un brouillon long enough", "intent": "expand"},
            )
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.get_json()["error"], "claude_error")
    def test_empty_response_returns_502(self):
        fake = self._make_fake_client('""')
        with patch("app.ClaudeClient", return_value=fake), \
             patch("app._read_engine_pref", return_value="cli_subscription"):
            r = self.client.post(
                "/api/rewrite",
                json={"text": "un brouillon long enough", "intent": "fix_typos"},
            )
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.get_json()["error"], "reponse_vide")
    def test_all_four_intents_accepted(self):
        for intent in ("reformulate", "concise", "expand", "fix_typos"):
            fake = self._make_fake_client(f"Réponse pour {intent}.")
            with patch("app.ClaudeClient", return_value=fake), \
                 patch("app._read_engine_pref", return_value="cli_subscription"):
                r = self.client.post(
                    "/api/rewrite",
                    json={"text": "un brouillon long enough", "intent": intent},
                )
            self.assertEqual(r.status_code, 200, f"intent={intent}")
            self.assertEqual(r.get_json()["intent"], intent)
    def test_no_context_keeps_legacy_user_msg(self):
        fake = self._make_fake_client("OK.")
        captured = {}
        def _capture(text):
            captured["user_msg"] = text
            fake._history.append({"role": "user", "content": text})
        fake.append_user_message.side_effect = _capture
        with patch("app.ClaudeClient", return_value=fake), \
             patch("app._read_engine_pref", return_value="cli_subscription"):
            r = self.client.post(
                "/api/rewrite",
                json={"text": "un brouillon long enough", "intent": "fix_typos"},
            )
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("[Contexte", captured["user_msg"])
        self.assertEqual(r.get_json().get("context_chars", -1), 0)
    def test_context_tutor_injected_into_user_msg(self):
        fake = self._make_fake_client("OK.")
        captured = {}
        def _capture(text):
            captured["user_msg"] = text
            fake._history.append({"role": "user", "content": text})
        fake.append_user_message.side_effect = _capture
        ctx = "Reprenez : si SEL vaut 0, laquelle des deux entrées est recopiée sur S ?"
        with patch("app.ClaudeClient", return_value=fake), \
             patch("app._read_engine_pref", return_value="cli_subscription"):
            r = self.client.post(
                "/api/rewrite",
                json={
                    "text": "Si celle vaut 0, la sortie E1 est recopiée.",
                    "intent": "reformulate",
                    "context_tutor": ctx,
                },
            )
        self.assertEqual(r.status_code, 200)
        self.assertIn("[Contexte : dernier message du tuteur]", captured["user_msg"])
        self.assertIn(ctx, captured["user_msg"])
        self.assertIn("[/Contexte]", captured["user_msg"])
        self.assertIn("Si celle vaut 0", captured["user_msg"])
        self.assertEqual(r.get_json()["context_chars"], len(ctx))
    def test_context_tutor_truncated_keeps_tail(self):
        from app import REWRITE_MAX_CONTEXT_CHARS
        fake = self._make_fake_client("OK.")
        captured = {}
        def _capture(text):
            captured["user_msg"] = text
            fake._history.append({"role": "user", "content": text})
        fake.append_user_message.side_effect = _capture
        head = "X" * (REWRITE_MAX_CONTEXT_CHARS + 500)
        tail_marker = " QUESTION_FINALE_DU_TUTEUR ?"
        ctx = head + tail_marker
        with patch("app.ClaudeClient", return_value=fake), \
             patch("app._read_engine_pref", return_value="cli_subscription"):
            r = self.client.post(
                "/api/rewrite",
                json={
                    "text": "un brouillon long enough",
                    "intent": "concise",
                    "context_tutor": ctx,
                },
            )
        self.assertEqual(r.status_code, 200)
        self.assertIn(tail_marker, captured["user_msg"])
        self.assertEqual(r.get_json()["context_chars"], REWRITE_MAX_CONTEXT_CHARS)
    def test_fix_typos_prompt_forbids_removing_false_starts(self):
        from app import REWRITE_INTENTS
        prompt = REWRITE_INTENTS["fix_typos"].lower()
        self.assertIn("faux départ", prompt)
        self.assertIn("hésitation", prompt)
        self.assertTrue(
            "interdiction" in prompt or "interdit" in prompt,
            "Le prompt fix_typos doit utiliser un langage normatif fort",
        )
    def test_empty_context_tutor_treated_as_absent(self):
        fake = self._make_fake_client("OK.")
        captured = {}
        def _capture(text):
            captured["user_msg"] = text
            fake._history.append({"role": "user", "content": text})
        fake.append_user_message.side_effect = _capture
        with patch("app.ClaudeClient", return_value=fake), \
             patch("app._read_engine_pref", return_value="cli_subscription"):
            r = self.client.post(
                "/api/rewrite",
                json={
                    "text": "un brouillon long enough",
                    "intent": "expand",
                    "context_tutor": "   \n   ",
                },
            )
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("[Contexte", captured["user_msg"])
        self.assertEqual(r.get_json()["context_chars"], 0)
if __name__ == "__main__":
    unittest.main(verbosity=2)