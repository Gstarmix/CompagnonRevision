"""
test_app_cancel_stream.py : couverture endpoint POST /api/cancel_stream
(Phase v15.7.21).

Vérifie : action invalide → 400, pas de session → 409, action=resume
flag set + transcript intact, action=delete_last_user → flag set +
dernier student msg retiré du _history client ET du transcript.
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


def _make_fake_state(history=None, branch_path=None, messages=None):
    """Fake CompanionSession avec un _history client et transcript synth."""
    fake = MagicMock()
    fake.lock = MagicMock()
    fake.lock.__enter__ = MagicMock(return_value=None)
    fake.lock.__exit__ = MagicMock(return_value=False)
    fake.cancel_requested = False
    # ClaudeClient avec _history mutable
    fake.client = MagicMock()
    fake.client._history = list(history or [])
    # SessionState avec data dict + set_meta qui mute en place
    fake.session_state = MagicMock()
    fake.session_state.data = {
        "current_branch_path": list(branch_path or []),
        "messages": dict(messages or {}),
        "transcript": [],
    }
    def _set_meta(key, value):
        fake.session_state.data[key] = value
    fake.session_state.set_meta.side_effect = _set_meta
    return fake


class TestApiCancelStream(unittest.TestCase):

    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()

    def test_invalid_action_returns_400(self):
        with patch.object(self.app_module, "_state", _make_fake_state()):
            r = self.client.post("/api/cancel_stream", json={"action": "weird"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("invalide", r.get_json()["error"])

    def test_no_active_session_returns_409(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.post("/api/cancel_stream", json={"action": "resume"})
        self.assertEqual(r.status_code, 409)

    def test_resume_sets_flag_only(self):
        """action=resume : cancel_requested=True, history et transcript intacts."""
        history = [
            {"role": "user", "content": "Bonjour"},
            {"role": "assistant", "content": "Bonsoir"},
            {"role": "user", "content": "Ma table de vérité"},
        ]
        fake = _make_fake_state(history=history)
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/cancel_stream", json={"action": "resume"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["action_applied"], "resume")
        self.assertIsNone(body["deleted_msg_id"])
        # Flag set
        self.assertTrue(fake.cancel_requested)
        # Le _history du client est intact
        self.assertEqual(len(fake.client._history), 3)
        self.assertEqual(fake.client._history[-1]["content"], "Ma table de vérité")

    def test_delete_last_user_removes_from_history_and_transcript(self):
        """action=delete_last_user : retire du _history client + transcript."""
        history = [
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "R1"},
            {"role": "user", "content": "Q2 photo"},
        ]
        # Simule un transcript backend avec 3 messages, le dernier student
        # qui correspond au 3e du _history client.
        msgs = {
            "msg_a": {"id": "msg_a", "role": "claude", "text": "Bonjour", "parent_id": None},
            "msg_b": {"id": "msg_b", "role": "student", "text": "Q1", "parent_id": "msg_a"},
            "msg_c": {"id": "msg_c", "role": "claude", "text": "R1", "parent_id": "msg_b"},
            "msg_d": {"id": "msg_d", "role": "student", "text": "Q2 photo", "parent_id": "msg_c"},
        }
        branch = ["msg_a", "msg_b", "msg_c", "msg_d"]
        fake = _make_fake_state(history=history, branch_path=branch, messages=msgs)
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/cancel_stream", json={"action": "delete_last_user"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["action_applied"], "delete_last_user")
        self.assertEqual(body["deleted_msg_id"], "msg_d")
        self.assertTrue(fake.cancel_requested)
        # _history client : dernier user retiré, donc [Q1, R1] uniquement
        self.assertEqual(len(fake.client._history), 2)
        self.assertEqual(fake.client._history[-1]["content"], "R1")
        # transcript backend : msg_d retiré du path actif
        self.assertEqual(fake.session_state.data["current_branch_path"], ["msg_a", "msg_b", "msg_c"])
        # transcript dérivé reflète les 3 messages restants
        new_ts = fake.session_state.data["transcript"]
        self.assertEqual(len(new_ts), 3)
        self.assertEqual(new_ts[-1]["id"], "msg_c")

    def test_delete_when_no_user_in_path_silently_ok(self):
        """Si aucun student dans le path, action=delete_last_user ok mais
        deleted_msg_id=None (pas d'erreur)."""
        msgs = {
            "msg_a": {"id": "msg_a", "role": "claude", "text": "x", "parent_id": None},
        }
        fake = _make_fake_state(history=[], branch_path=["msg_a"], messages=msgs)
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/cancel_stream", json={"action": "delete_last_user"})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.get_json()["deleted_msg_id"])
        self.assertTrue(fake.cancel_requested)

    def test_default_action_is_resume(self):
        """Pas d'action dans le body → fallback resume."""
        fake = _make_fake_state(history=[{"role": "user", "content": "x"}])
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/cancel_stream", json={})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["action_applied"], "resume")


if __name__ == "__main__":
    unittest.main(verbosity=2)
