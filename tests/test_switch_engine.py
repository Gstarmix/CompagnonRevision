"""test_switch_engine.py : bascule à chaud /api/switch_engine (Phase A.7.2 v7.3).

Vérifie le scénario : pendant une session active, l'API courante lève
ClaudeQuotaExhaustedError. Le backend pousse un event SSE
``quota_midflow`` listant les fallbacks dispos. Le front POST
``/api/switch_engine`` qui :

- Valide l'engine (doit être dans SUPPORTED_ENGINES).
- Construit un nouveau ClaudeClient avec le même system_prompt, mode,
  cours_root, max_tokens.
- Transfère l'historique (`_history`) tel quel : le user message ayant
  échoué est dedans.
- Met `retry_pending=True` sur la session pour que le prochain
  /api/stream_response stream depuis l'historique sans toucher.
- Persiste le choix dans `_secrets/engine_pref.json`.

Tests sans réseau ni Tk : Flask test_client + ClaudeClient mocké.
"""

from __future__ import annotations

import json
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "_scripts"))
sys.path.insert(0, str(ROOT / "_scripts" / "dialogue"))
sys.path.insert(0, str(ROOT / "_scripts" / "audio"))
sys.path.insert(0, str(ROOT / "_scripts" / "web"))
sys.path.insert(0, str(ROOT / "_scripts" / "quota"))


def _build_fake_session(initial_engine: str = "cli_subscription"):
    """Construit un CompanionSession minimal avec un client mocké."""
    import app as app_mod
    from prompt_builder import SessionContext
    from session_state import SessionState
    from config import SESSIONS_DIR

    ctx = SessionContext(matiere="PRG2", type="CM", num="8", exo="full")
    ss = SessionState(
        session_id="test_switch", sessions_dir=SESSIONS_DIR,
        context=ctx, engine=initial_engine, model="claude",
    )

    # Client mocké : on stocke quelques attributs internes que
    # api_switch_engine consulte pour rebâtir le client.
    fake_client = MagicMock()
    fake_client.engine = initial_engine
    fake_client._system_prompt = "PROMPT TUTEUR"
    fake_client._model = "claude-opus-4-7"
    fake_client._max_tokens = 4096
    fake_client._mode = "guidé"
    fake_client._cours_root = None
    fake_client.history = [
        {"role": "user", "content": "[contexte initial]"},
        {"role": "assistant", "content": "Bonjour. Je vous écoute."},
        {"role": "user", "content": "Question qui a fait sauter le quota"},
    ]

    sess = app_mod.CompanionSession.__new__(app_mod.CompanionSession)
    sess.session_state = ss
    sess.client = fake_client
    sess.prompt_builder = MagicMock()
    sess.event_queue = __import__("queue").Queue()
    sess.streaming_thread = None
    sess.pending_user_text = None
    sess.initial_stream_pending = False
    sess.retry_pending = False
    sess.lock = threading.Lock()
    return sess, fake_client


class TestSwitchEngine(unittest.TestCase):

    def setUp(self):
        import app as app_mod
        self.app_mod = app_mod
        # Tests indépendants : reset l'état global avant chaque test.
        app_mod._state = None

    def tearDown(self):
        self.app_mod._state = None

    # -------------------------------------------------- validation engine

    def test_switch_sans_session_active_409(self):
        with self.app_mod.app.test_client() as c:
            r = c.post("/api/switch_engine", json={"engine": "gemini_api"})
        self.assertEqual(r.status_code, 409)

    def test_switch_engine_inconnu_400(self):
        sess, _ = _build_fake_session()
        self.app_mod._state = sess
        with self.app_mod.app.test_client() as c:
            r = c.post("/api/switch_engine", json={"engine": "huggingface"})
        self.assertEqual(r.status_code, 400)
        body = json.loads(r.get_data(as_text=True))
        self.assertIn("supported", body)

    # -------------------------------------------------- bascule réussie

    def test_switch_vers_gemini_remplace_client(self):
        sess, old_client = _build_fake_session(initial_engine="cli_subscription")
        self.app_mod._state = sess

        # On mock ClaudeClient pour vérifier les args de construction du
        # nouveau client sans réellement initialiser un SDK.
        with patch("claude_client.ClaudeClient") as mock_cls, \
             patch("app._persist_engine_pref") as mock_persist:
            new_client_instance = MagicMock()
            new_client_instance._history = []
            mock_cls.return_value = new_client_instance
            with self.app_mod.app.test_client() as c:
                r = c.post("/api/switch_engine", json={"engine": "gemini_api"})

        self.assertEqual(r.status_code, 200)
        body = json.loads(r.get_data(as_text=True))
        self.assertEqual(body["engine"], "gemini_api")
        self.assertEqual(body["previous_engine"], "cli_subscription")
        self.assertEqual(body["history_size"], 3)

        # Le nouveau client a été instancié avec les bons args.
        mock_cls.assert_called_once()
        kwargs = mock_cls.call_args.kwargs
        self.assertEqual(kwargs["engine"], "gemini_api")
        self.assertEqual(kwargs["system_prompt"], "PROMPT TUTEUR")
        self.assertEqual(kwargs["mode"], "guidé")

        # L'historique a été transféré (3 messages, dont le user qui a
        # fait sauter le quota, il sera retry au prochain stream).
        self.assertEqual(len(new_client_instance._history), 3)
        self.assertEqual(
            new_client_instance._history[-1]["content"],
            "Question qui a fait sauter le quota",
        )

        # st.client a été remplacé, retry_pending levé.
        self.assertIs(self.app_mod._state.client, new_client_instance)
        self.assertTrue(self.app_mod._state.retry_pending)

        # engine_pref.json persisté.
        mock_persist.assert_called_once_with("gemini_api")

    def test_switch_persiste_meme_si_save_echoue(self):
        """Si _persist_engine_pref lève OSError (disque plein, droits…),
        la bascule en mémoire DOIT quand même réussir : la session courante
        est ce qui compte, le redémarrage futur c'est secondaire."""
        sess, _ = _build_fake_session()
        self.app_mod._state = sess
        with patch("claude_client.ClaudeClient") as mock_cls, \
             patch("app._persist_engine_pref", side_effect=OSError("disque plein")):
            mock_cls.return_value = MagicMock()
            with self.app_mod.app.test_client() as c:
                r = c.post("/api/switch_engine", json={"engine": "deepseek_api"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.app_mod._state.retry_pending)

    # -------------------------------------------------- list_available_fallbacks

    def test_list_available_fallbacks_filtre_exclude(self):
        """Quand exclude=gemini_api, on ne propose pas Gemini même si la
        clé est définie."""
        import os
        keys = {"GEMINI_API_KEY": "X", "DEEPSEEK_API_KEY": "Y"}
        with patch.dict(os.environ, keys, clear=False):
            out = self.app_mod._list_available_fallbacks(exclude="gemini_api")
        engines = [d["engine"] for d in out]
        self.assertNotIn("gemini_api", engines)
        self.assertIn("deepseek_api", engines)

    def test_list_available_fallbacks_aucune_key(self):
        import os
        with patch.dict(os.environ, {}, clear=True):
            out = self.app_mod._list_available_fallbacks()
        self.assertEqual(out, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
