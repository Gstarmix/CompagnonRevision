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
def _make_fake_state():
    fake = MagicMock()
    fake.lock = MagicMock()
    fake.lock.__enter__ = MagicMock(return_value=None)
    fake.lock.__exit__ = MagicMock(return_value=False)
    fake.session_state = MagicMock()
    fake.session_state.set_meta = MagicMock()
    fake.client = MagicMock()
    fake.client.append_user_message = MagicMock()
    return fake
class TestApiSetColleFormat(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
    def test_no_active_session_returns_409(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.post("/api/set_colle_format",
                                 json={"format": "photos"})
        self.assertEqual(r.status_code, 409)
        self.assertIn("pas de session", r.get_json()["error"])
    def test_invalid_format_returns_400(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/set_colle_format",
                                 json={"format": "weird"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("invalide", r.get_json()["error"])
    def test_valid_format_persists_and_injects_marker(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/set_colle_format",
                                 json={"format": "photos"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["colle_format"], "photos")
        self.assertTrue(body["ok"])
        fake.session_state.set_meta.assert_called_once_with("colle_format", "photos")
        fake.client.append_user_message.assert_called_once_with(
            "[FORMAT BASCULÉ → photos]"
        )
    def test_singular_photo_normalized_to_photos(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/set_colle_format",
                                 json={"format": "photo"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["colle_format"], "photos")
        fake.session_state.set_meta.assert_called_once_with("colle_format", "photos")
    def test_case_insensitive(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/set_colle_format",
                                 json={"format": "ORAL"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["colle_format"], "oral")
class TestSendMessageSlashCommand(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
    def test_slash_oral_basculates_without_sending(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/send_message", json={"text": "/oral"})
        self.assertEqual(r.status_code, 202)
        body = r.get_json()
        self.assertTrue(body["slash_command"])
        self.assertEqual(body["colle_format"], "oral")
        fake.session_state.set_meta.assert_called_once_with("colle_format", "oral")
        fake.client.append_user_message.assert_called_once_with(
            "[FORMAT BASCULÉ → oral]"
        )
    def test_slash_photos_with_trailing_dot_dictation(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/send_message", json={"text": "/photos."})
        self.assertEqual(r.status_code, 202)
        body = r.get_json()
        self.assertTrue(body["slash_command"])
        self.assertEqual(body["colle_format"], "photos")
    def test_slash_mixte_case_insensitive(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/send_message", json={"text": "/MIXTE"})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.get_json()["colle_format"], "mixte")
    def test_slash_with_text_after_is_NOT_intercepted(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", None):
            r = self.client.post(
                "/api/send_message",
                json={"text": "/photos je veux dire vraiment"},
            )
        self.assertEqual(r.status_code, 409)
    def test_no_slash_normal_flow_unchanged(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.post("/api/send_message",
                                 json={"text": "Bonjour, je commence l'exo 3."})
        self.assertEqual(r.status_code, 409)
        body = r.get_json()
        self.assertNotIn("slash_command", body)
class TestPromptSystemRulesV0_3(unittest.TestCase):
    def setUp(self):
        from config import PROMPT_SYSTEME_PATH
        self.prompt_text = PROMPT_SYSTEME_PATH.read_text(encoding="utf-8")
    def test_section_1_6_format_colle_present(self):
        self.assertIn("[FORMAT COLLE :", self.prompt_text)
        self.assertIn("Format `oral`", self.prompt_text)
        self.assertIn("Format `photos`", self.prompt_text)
        self.assertIn("Format `mixte`", self.prompt_text)
    def test_rule_11_no_resistance_to_format_switch(self):
        self.assertIn("[FORMAT BASCULÉ", self.prompt_text)
        self.assertIn("résistance", self.prompt_text.lower())
        self.assertIn("êtes-vous sûr", self.prompt_text.lower())
    def test_garde_fou_jamais_sauter_question_silencieusement(self):
        self.assertIn("Ne sautez jamais silencieusement", self.prompt_text)
    def test_neutralite_canal_upload_v15_7_5(self):
        self.assertIn("neutralité sur le canal d'upload", self.prompt_text)
        self.assertIn("N'imposez aucun canal précis", self.prompt_text)
    def test_protocole_ocr_photo_v15_7_19(self):
        self.assertIn("📸 Ce que je lis dans votre photo", self.prompt_text)
        self.assertIn("N'INFÉREZ JAMAIS", self.prompt_text)
        self.assertIn("(vide)", self.prompt_text)
        self.assertIn("30 %", self.prompt_text)
class TestDecouvertePromptFormat(unittest.TestCase):
    def setUp(self):
        from config import PROMPT_SYSTEME_DECOUVERTE_PATH
        self.prompt_text = PROMPT_SYSTEME_DECOUVERTE_PATH.read_text(encoding="utf-8")
    def test_section_1_6ter_present(self):
        self.assertIn("1.6ter", self.prompt_text)
        self.assertIn("[FORMAT PÉDAGOGIQUE :", self.prompt_text)
        self.assertIn("Format `oral`", self.prompt_text)
        self.assertIn("Format `photos`", self.prompt_text)
        self.assertIn("Format `mixte`", self.prompt_text)
    def test_rule_11_no_resistance_to_format_switch_decouverte(self):
        self.assertIn("[FORMAT PÉDAGOGIQUE BASCULÉ", self.prompt_text)
        self.assertIn("résistance", self.prompt_text.lower())
        self.assertIn("êtes-vous sûr", self.prompt_text.lower())
    def test_ocr_protocol_present_in_decouverte(self):
        self.assertIn("📸 Ce que je lis dans votre photo", self.prompt_text)
class TestApiSlashFormatDecouverte(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
    def test_apply_format_change_uses_pedagogique_marker_in_decouverte(self):
        from app import _apply_colle_format_change, MODE_DECOUVERTE
        fake = _make_fake_state()
        fake.session_state.data = {"mode": MODE_DECOUVERTE}
        _apply_colle_format_change(fake, "photos")
        injected = fake.client.append_user_message.call_args[0][0]
        self.assertIn("[FORMAT PÉDAGOGIQUE BASCULÉ", injected)
        self.assertIn("photos", injected)
        self.assertNotIn("[FORMAT BASCULÉ", injected)
    def test_apply_format_change_uses_classic_marker_in_colle(self):
        from app import _apply_colle_format_change, MODE_COLLE
        fake = _make_fake_state()
        fake.session_state.data = {"mode": MODE_COLLE}
        _apply_colle_format_change(fake, "oral")
        injected = fake.client.append_user_message.call_args[0][0]
        self.assertIn("[FORMAT BASCULÉ", injected)
        self.assertIn("oral", injected)
        self.assertNotIn("PÉDAGOGIQUE", injected)
if __name__ == "__main__":
    unittest.main(verbosity=2)