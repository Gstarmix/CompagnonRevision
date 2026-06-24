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
class TestApiSetCorrigeAnchor(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
    def test_no_active_session_returns_409(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.post(
                "/api/set_corrige_anchor", json={"anchor": "consultatif"},
            )
        self.assertEqual(r.status_code, 409)
        self.assertIn("pas de session", r.get_json()["error"])
    def test_invalid_anchor_returns_400(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post(
                "/api/set_corrige_anchor", json={"anchor": "weird"},
            )
        self.assertEqual(r.status_code, 400)
        self.assertIn("invalide", r.get_json()["error"])
    def test_strict_persists_and_injects_marker(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post(
                "/api/set_corrige_anchor", json={"anchor": "strict"},
            )
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["corrige_anchor"], "strict")
        self.assertTrue(body["ok"])
        fake.session_state.set_meta.assert_called_once_with("corrige_anchor", "strict")
        fake.client.append_user_message.assert_called_once_with(
            "[ANCRAGE BASCULÉ → strict]"
        )
    def test_consultatif_valid(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post(
                "/api/set_corrige_anchor", json={"anchor": "consultatif"},
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["corrige_anchor"], "consultatif")
    def test_aucun_valid(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post(
                "/api/set_corrige_anchor", json={"anchor": "aucun"},
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["corrige_anchor"], "aucun")
    def test_alias_sans_corrige_normalized_to_aucun(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post(
                "/api/set_corrige_anchor", json={"anchor": "sans_corrige"},
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["corrige_anchor"], "aucun")
        fake.session_state.set_meta.assert_called_once_with("corrige_anchor", "aucun")
    def test_case_insensitive(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post(
                "/api/set_corrige_anchor", json={"anchor": "CONSULTATIF"},
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["corrige_anchor"], "consultatif")
class TestSendMessageSlashCommandAnchor(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
    def test_slash_strict_basculates_without_sending(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/send_message", json={"text": "/strict"})
        self.assertEqual(r.status_code, 202)
        body = r.get_json()
        self.assertTrue(body["slash_command"])
        self.assertEqual(body["corrige_anchor"], "strict")
        fake.session_state.set_meta.assert_called_once_with("corrige_anchor", "strict")
        fake.client.append_user_message.assert_called_once_with(
            "[ANCRAGE BASCULÉ → strict]"
        )
    def test_slash_consultatif_with_trailing_dot_dictation(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post(
                "/api/send_message", json={"text": "/consultatif."},
            )
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.get_json()["corrige_anchor"], "consultatif")
    def test_slash_sans_corrige_normalized_to_aucun(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post(
                "/api/send_message", json={"text": "/sans_corrigé"},
            )
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.get_json()["corrige_anchor"], "aucun")
    def test_slash_aucun_case_insensitive(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/send_message", json={"text": "/AUCUN"})
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.get_json()["corrige_anchor"], "aucun")
    def test_slash_with_text_after_is_NOT_intercepted(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.post(
                "/api/send_message",
                json={"text": "/strict je veux dire vraiment"},
            )
        self.assertEqual(r.status_code, 409)
    def test_no_slash_normal_flow_unchanged(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.post(
                "/api/send_message",
                json={"text": "Le corrigé dit pourtant que..."},
            )
        self.assertEqual(r.status_code, 409)
        body = r.get_json()
        self.assertNotIn("slash_command", body)
    def test_slash_aucun_distinct_from_colle_format(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/send_message", json={"text": "/aucun"})
        self.assertEqual(r.status_code, 202)
        body = r.get_json()
        self.assertIn("corrige_anchor", body)
        self.assertNotIn("colle_format", body)
class TestPromptSystemRulesV0_6(unittest.TestCase):
    def setUp(self):
        from config import PROMPT_SYSTEME_PATH
        self.prompt_text = PROMPT_SYSTEME_PATH.read_text(encoding="utf-8")
    def test_section_1_4_three_anchor_modes_present(self):
        self.assertIn("[ANCRAGE CORRIGÉ :", self.prompt_text)
        self.assertIn("Mode `strict`", self.prompt_text)
        self.assertIn("Mode `consultatif`", self.prompt_text)
        self.assertIn("Mode `aucun`", self.prompt_text)
    def test_rule_12_no_resistance_to_anchor_switch(self):
        self.assertIn("[ANCRAGE BASCULÉ", self.prompt_text)
        self.assertIn("bascules d'ancrage", self.prompt_text)
        self.assertIn("Ne ré-invoquez pas l'autorité du corrigé", self.prompt_text)
    def test_consultatif_validates_alternative_coherent(self):
        self.assertIn("voies alternatives", self.prompt_text.lower())
        self.assertIn("cohérence interne du raisonnement étudiant", self.prompt_text)
    def test_aucun_skips_signaling_to_student(self):
        self.assertIn("Vous ne mentionnez pas l'absence de corrigé", self.prompt_text)
if __name__ == "__main__":
    unittest.main(verbosity=2)