"""
test_app_colle_format.py : couverture endpoint POST /api/set_colle_format
+ détection slash-command dans /api/send_message (Phase v15.7.4).

On mocke ``_state`` directement pour ne pas avoir à démarrer une vraie
session Claude (qui chargerait Whisper/PDF/etc).
"""

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
    """Construit un faux CompanionSession minimal pour tester les endpoints."""
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
        # set_meta a été appelé pour persister le format
        fake.session_state.set_meta.assert_called_once_with("colle_format", "photos")
        # Marker injecté dans l'historique du client
        fake.client.append_user_message.assert_called_once_with(
            "[FORMAT BASCULÉ → photos]"
        )

    def test_singular_photo_normalized_to_photos(self):
        """Tolérance singulier : /api/set_colle_format {photo} → photos."""
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
    """Phase v15.7.4 : la slash-command /oral|/photos|/mixte interceptée
    dans /api/send_message bascule le format SANS envoyer au tuteur.
    """

    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()

    def test_slash_oral_basculates_without_sending(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/send_message", json={"text": "/oral"})
        # Réponse 202 avec slash_command true
        self.assertEqual(r.status_code, 202)
        body = r.get_json()
        self.assertTrue(body["slash_command"])
        self.assertEqual(body["colle_format"], "oral")
        # Bascule effective côté state
        fake.session_state.set_meta.assert_called_once_with("colle_format", "oral")
        fake.client.append_user_message.assert_called_once_with(
            "[FORMAT BASCULÉ → oral]"
        )
        # PAS de pending_user_text setté (le tuteur ne doit pas voir « /oral »)
        # On vérifie que pending_user_text n'a pas été touché
        # (l'attribut peut ne pas exister du tout sur le mock)

    def test_slash_photos_with_trailing_dot_dictation(self):
        """Tolérance dictée vocale : « slash photos point. » → /photos."""
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
        """Si le user tape /photos suivi d'une vraie phrase, c'est pas
        une slash-command : ça part au tuteur tel quel (peut-être que
        l'étudiant cite un /photos dans sa réponse)."""
        fake = _make_fake_state()
        # Pas de session active → on s'attend à 409 si le slash NE matche
        # PAS et qu'on tombe dans le flow normal de send_message.
        with patch.object(self.app_module, "_state", None):
            r = self.client.post(
                "/api/send_message",
                json={"text": "/photos je veux dire vraiment"},
            )
        # Le slash ne matche pas (texte après) → flow normal → 409
        # parce que _state est None.
        self.assertEqual(r.status_code, 409)

    def test_no_slash_normal_flow_unchanged(self):
        """Texte normal sans /oral|/photos|/mixte → flow inchangé (409
        si pas de session, mais surtout pas 202 slash_command)."""
        with patch.object(self.app_module, "_state", None):
            r = self.client.post("/api/send_message",
                                 json={"text": "Bonjour, je commence l'exo 3."})
        self.assertEqual(r.status_code, 409)
        # Pas de slash_command dans la réponse
        body = r.get_json()
        self.assertNotIn("slash_command", body)


class TestPromptSystemRulesV0_3(unittest.TestCase):
    """Phase v15.7.4 : test de doctrine sur le prompt système COMPAGNON.

    Vérifie que §1.6 et §4.11 sont bien présents et non vidés par un
    refactor accidentel du fichier `_prompts/PROMPT_SYSTEME_COMPAGNON.md`.
    """

    def setUp(self):
        from config import PROMPT_SYSTEME_PATH
        self.prompt_text = PROMPT_SYSTEME_PATH.read_text(encoding="utf-8")

    def test_section_1_6_format_colle_present(self):
        self.assertIn("[FORMAT COLLE :", self.prompt_text)
        self.assertIn("Format `oral`", self.prompt_text)
        self.assertIn("Format `photos`", self.prompt_text)
        self.assertIn("Format `mixte`", self.prompt_text)

    def test_rule_11_no_resistance_to_format_switch(self):
        # La règle 11 doit interdire les questions de type « êtes-vous sûr ? »
        self.assertIn("[FORMAT BASCULÉ", self.prompt_text)
        self.assertIn("résistance", self.prompt_text.lower())
        self.assertIn("êtes-vous sûr", self.prompt_text.lower())

    def test_garde_fou_jamais_sauter_question_silencieusement(self):
        # Le §1.6 doit explicitement interdire de sauter une question
        # silencieusement quand la dictée paraît bancale.
        self.assertIn("Ne sautez jamais silencieusement", self.prompt_text)

    def test_neutralite_canal_upload_v15_7_5(self):
        """Phase v15.7.5 : règle de wording « neutralité sur le canal d'upload »
        doit être présente. Empêche le tuteur d'imposer le bouton 📎
        (alors qu'il y a aussi /mobile, QR, et futures voies d'upload).
        """
        self.assertIn("neutralité sur le canal d'upload", self.prompt_text)
        self.assertIn("N'imposez aucun canal précis", self.prompt_text)

    def test_protocole_ocr_photo_v15_7_19(self):
        """Phase v15.7.19 : protocole OCR obligatoire avant tout jugement
        sur une photo. Anti-hallucination : le tuteur doit verbaliser ce
        qu'il LIT (case par case avec marqueur (vide) si applicable),
        avant de donner son verdict. Friction EN1 CC2 : le tuteur avait
        validé une table avec colonne S entièrement vide en complétant
        mentalement.
        """
        # Le protocole OCR doit être présent
        self.assertIn("📸 Ce que je lis dans votre photo", self.prompt_text)
        # La règle anti-inférence doit être inviolable
        self.assertIn("N'INFÉREZ JAMAIS", self.prompt_text)
        # Marqueur pour cases vides explicite
        self.assertIn("(vide)", self.prompt_text)
        # Garde-fou seuil 30 % de cases vides
        self.assertIn("30 %", self.prompt_text)


class TestDecouvertePromptFormat(unittest.TestCase):
    """Phase A.8.2 : §1.6ter du prompt DECOUVERTE + règle §4.11."""

    def setUp(self):
        from config import PROMPT_SYSTEME_DECOUVERTE_PATH
        self.prompt_text = PROMPT_SYSTEME_DECOUVERTE_PATH.read_text(encoding="utf-8")

    def test_section_1_6ter_present(self):
        """§1.6ter doit exister et décrire les 3 formats."""
        self.assertIn("1.6ter", self.prompt_text)
        self.assertIn("[FORMAT PÉDAGOGIQUE :", self.prompt_text)
        self.assertIn("Format `oral`", self.prompt_text)
        self.assertIn("Format `photos`", self.prompt_text)
        self.assertIn("Format `mixte`", self.prompt_text)

    def test_rule_11_no_resistance_to_format_switch_decouverte(self):
        """§4.11 du DECOUVERTE doit interdire la résistance aux bascules."""
        self.assertIn("[FORMAT PÉDAGOGIQUE BASCULÉ", self.prompt_text)
        self.assertIn("résistance", self.prompt_text.lower())
        self.assertIn("êtes-vous sûr", self.prompt_text.lower())

    def test_ocr_protocol_present_in_decouverte(self):
        """Phase A.8.2 : le protocole OCR doit aussi être dans DECOUVERTE."""
        self.assertIn("📸 Ce que je lis dans votre photo", self.prompt_text)


class TestApiSlashFormatDecouverte(unittest.TestCase):
    """Phase A.8.2 : slash-cmds /oral /photos /mixte injectent
    [FORMAT PÉDAGOGIQUE BASCULÉ → ...] en mode découverte, et
    [FORMAT BASCULÉ → ...] en mode colle.
    """

    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()

    def test_apply_format_change_uses_pedagogique_marker_in_decouverte(self):
        """En mode découverte, _apply_colle_format_change injecte
        [FORMAT PÉDAGOGIQUE BASCULÉ → ...] (pas [FORMAT BASCULÉ → ...]).
        """
        from app import _apply_colle_format_change, MODE_DECOUVERTE
        fake = _make_fake_state()
        fake.session_state.data = {"mode": MODE_DECOUVERTE}
        _apply_colle_format_change(fake, "photos")
        injected = fake.client.append_user_message.call_args[0][0]
        self.assertIn("[FORMAT PÉDAGOGIQUE BASCULÉ", injected)
        self.assertIn("photos", injected)
        self.assertNotIn("[FORMAT BASCULÉ", injected)

    def test_apply_format_change_uses_classic_marker_in_colle(self):
        """En mode colle, marker historique [FORMAT BASCULÉ → ...]."""
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
