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
def _make_fake_state(data_overrides=None):
    fake = MagicMock()
    fake.lock = MagicMock()
    fake.lock.__enter__ = MagicMock(return_value=None)
    fake.lock.__exit__ = MagicMock(return_value=False)
    data = {
        "session_id": "test_session",
        "matiere": "EN1",
        "type": "CC",
        "num": "2",
        "transcript": [
            {"role": "claude", "text": "Exercice 1. Énoncez la table de vérité.",
             "at": "2026-05-11T10:00:00+02:00"},
            {"role": "student", "text": "Heu, je bloque sur le SEL",
             "at": "2026-05-11T10:01:00+02:00"},
            {"role": "claude", "text": "Indice : SEL est l'entrée de sélection.",
             "at": "2026-05-11T10:02:00+02:00"},
        ],
        "phase": "active",
        "stats": {"total_exchanges": 0},
        "recap": None,
    }
    if data_overrides:
        data.update(data_overrides)
    def _set_meta(key, value):
        data[key] = value
    fake.session_state = MagicMock()
    fake.session_state.data = data
    fake.session_state.set_meta = MagicMock(side_effect=_set_meta)
    fake.session_state.finalize = MagicMock()
    fake.client = MagicMock()
    fake.client.append_user_message = MagicMock()
    fake.retry_pending = False
    return fake
class TestApiSessionRecap(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
    def test_no_active_session_returns_409(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.post("/api/session_recap")
        self.assertEqual(r.status_code, 409)
    def test_happy_path_generates_recap_and_basculates_to_debrief(self):
        fake = _make_fake_state()
        mocked_recap = {
            "summary": "Séance sur table de vérité MUX. Étudiant a bloqué sur SEL.",
            "concepts_covered": ["table de vérité", "multiplexeur"],
            "exercises_handled": ["CC2 ex1"],
            "suggestions": ["revoir le rôle de SEL"],
        }
        with patch.object(self.app_module, "_state", fake), \
             patch.object(self.app_module, "_generate_session_recap",
                          return_value=mocked_recap):
            r = self.client.post("/api/session_recap")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["phase"], "debrief")
        self.assertEqual(body["recap"]["summary"], mocked_recap["summary"])
        keys_set = [c.args[0] for c in fake.session_state.set_meta.call_args_list]
        self.assertIn("recap", keys_set)
        self.assertIn("phase", keys_set)
        self.assertIn("recap_at", keys_set)
        fake.client.append_user_message.assert_called_once_with(
            "[PHASE DÉBRIEF ENGAGÉE]"
        )
    def test_idempotent_when_already_debrief(self):
        fake = _make_fake_state({
            "phase": "debrief",
            "recap": {"summary": "déjà fait"},
        })
        with patch.object(self.app_module, "_state", fake), \
             patch.object(self.app_module, "_generate_session_recap") as mock_gen:
            r = self.client.post("/api/session_recap")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["cached"])
        self.assertEqual(body["phase"], "debrief")
        mock_gen.assert_not_called()
    def test_gemini_failure_returns_degraded_recap(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake), \
             patch.object(self.app_module, "_generate_session_recap",
                          side_effect=Exception("Gemini timeout")):
            r = self.client.post("/api/session_recap")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertIn("échoué", body["recap"]["summary"])
        self.assertEqual(body["phase"], "debrief")
class TestApiSessionClose(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
    def test_no_active_session_returns_409(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.post("/api/session_close")
        self.assertEqual(r.status_code, 409)
    def test_happy_path_finalizes(self):
        fake = _make_fake_state({"phase": "debrief"})
        fake.session_state.data["duration_seconds"] = 3600
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/session_close")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["session_id"], "test_session")
        keys_set = [c.args[0] for c in fake.session_state.set_meta.call_args_list]
        self.assertIn("phase", keys_set)
        self.assertIn("final_closed_at", keys_set)
        fake.session_state.finalize.assert_called_once_with(interrupted=False)
class TestApiMiniExo(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
    def test_no_active_session_returns_409(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.post("/api/mini_exo", json={"concept": "X"})
        self.assertEqual(r.status_code, 409)
    def test_concept_injects_marker(self):
        fake = _make_fake_state({"phase": "debrief"})
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/mini_exo", json={
                "concept": "MUX 2→1",
                "detail": "confusion E vs S",
                "exercise_context": "CC2 ex1",
            })
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["concept"], "MUX 2→1")
        fake.client.append_user_message.assert_called_once()
        marker = fake.client.append_user_message.call_args[0][0]
        self.assertIn("[MINI-EXO :", marker)
        self.assertIn("MUX 2→1", marker)
        self.assertIn("confusion E vs S", marker)
        self.assertIn("CC2 ex1", marker)
        self.assertTrue(fake.retry_pending)
    def test_concept_only_works_without_detail(self):
        fake = _make_fake_state({"phase": "debrief"})
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/mini_exo", json={
                "concept": "théorème de Rolle",
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["concept"], "théorème de Rolle")
    def test_missing_concept_returns_400(self):
        fake = _make_fake_state({"phase": "debrief"})
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/mini_exo", json={"detail": "X"})
        self.assertEqual(r.status_code, 400)
class TestPromptSystemRules(unittest.TestCase):
    def setUp(self):
        from config import PROMPT_SYSTEME_PATH
        self.prompt_text = PROMPT_SYSTEME_PATH.read_text(encoding="utf-8")
    def test_section_1_7_phase_debrief_present(self):
        self.assertIn("[PHASE DÉBRIEF ENGAGÉE]", self.prompt_text)
        self.assertIn("Phase débrief", self.prompt_text)
        self.assertIn("Ratio §2.1 relâché", self.prompt_text)
    def test_section_1_7bis_mini_exo_present(self):
        self.assertIn("[MINI-EXO :", self.prompt_text)
        self.assertIn("Mini-exo ciblé", self.prompt_text)
        self.assertIn("3 à 5 questions", self.prompt_text)
    def test_rule_13_no_resistance_to_debrief_switch(self):
        self.assertIn("Pas de résistance à la bascule en phase débrief",
                      self.prompt_text)
        self.assertIn("voulez-vous vraiment terminer", self.prompt_text.lower())
    def test_debrief_keeps_vocabulary_rigor(self):
        self.assertIn("Rigueur sur le vocabulaire conservée", self.prompt_text)
if __name__ == "__main__":
    unittest.main(verbosity=2)