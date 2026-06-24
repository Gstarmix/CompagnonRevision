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
def _make_fake_state(initial_selections=None):
    fake = MagicMock()
    fake.lock = MagicMock()
    fake.lock.__enter__ = MagicMock(return_value=None)
    fake.lock.__exit__ = MagicMock(return_value=False)
    fake.session_state = MagicMock()
    fake.session_state.data = {"saved_selections": list(initial_selections or [])}
    def _set_meta(key, value):
        fake.session_state.data[key] = value
    fake.session_state.set_meta.side_effect = _set_meta
    return fake
class TestApiSavedSelections(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
    def test_get_no_session(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.get("/api/saved_selections")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["selections"], [])
        self.assertFalse(body["active"])
    def test_get_returns_existing(self):
        sels = [
            {"id": "sel_x", "text": "Théorème", "role": "claude"},
            {"id": "sel_y", "text": "Note perso", "role": "student"},
        ]
        with patch.object(self.app_module, "_state", _make_fake_state(sels)):
            r = self.client.get("/api/saved_selections")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["active"])
        self.assertEqual(len(body["selections"]), 2)
    def test_post_no_session(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.post("/api/saved_selections",
                                 json={"text": "Some text"})
        self.assertEqual(r.status_code, 409)
    def test_post_text_vide(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/saved_selections", json={"text": "  "})
        self.assertEqual(r.status_code, 400)
        self.assertIn("vide", r.get_json()["error"])
    def test_post_text_trop_long(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/saved_selections",
                                 json={"text": "x" * 5001})
        self.assertEqual(r.status_code, 400)
        body = r.get_json()
        self.assertEqual(body["max_chars"], 5000)
        self.assertEqual(body["got_chars"], 5001)
    def test_post_happy_path(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/saved_selections", json={
                "text": "Une phrase importante",
                "message_id": "msg_abc123",
                "role": "claude",
            })
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        sel = r.get_json()
        self.assertTrue(sel["id"].startswith("sel_"))
        self.assertEqual(sel["text"], "Une phrase importante")
        self.assertEqual(sel["message_id"], "msg_abc123")
        self.assertEqual(sel["role"], "claude")
        self.assertIn("captured_at", sel)
        self.assertEqual(len(fake.session_state.data["saved_selections"]), 1)
    def test_post_role_default_claude(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/saved_selections",
                                 json={"text": "test"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["role"], "claude")
        with patch.object(self.app_module, "_state", _make_fake_state()):
            r = self.client.post("/api/saved_selections",
                                 json={"text": "test", "role": "weird"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["role"], "claude")
    def test_post_role_student_kept(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/saved_selections",
                                 json={"text": "test", "role": "student"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["role"], "student")
    def test_post_with_raw_text(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/saved_selections", json={
                "text": "S = E·SEL",
                "raw_text": "Théorème : $S = E \\cdot \\overline{SEL}$ avec...",
                "message_id": "msg_x",
                "role": "claude",
            })
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        sel = r.get_json()
        self.assertEqual(sel["raw_text"],
                         "Théorème : $S = E \\cdot \\overline{SEL}$ avec...")
    def test_post_without_raw_text_default_none(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/saved_selections",
                                 json={"text": "Plain text"})
        self.assertEqual(r.status_code, 200)
        sel = r.get_json()
        self.assertIsNone(sel["raw_text"])
    def test_post_raw_text_capped_at_10000(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/saved_selections", json={
                "text": "short",
                "raw_text": "y" * 12000,
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()["raw_text"]), 10000)
    def test_post_appends_not_replaces(self):
        existing = [{"id": "sel_old", "text": "Existing", "role": "claude"}]
        fake = _make_fake_state(existing)
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/saved_selections",
                                 json={"text": "Nouveau"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(fake.session_state.data["saved_selections"]), 2)
    def test_delete_no_session(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.delete("/api/saved_selections/sel_xyz")
        self.assertEqual(r.status_code, 409)
    def test_delete_unknown(self):
        fake = _make_fake_state([{"id": "sel_a", "text": "x", "role": "claude"}])
        with patch.object(self.app_module, "_state", fake):
            r = self.client.delete("/api/saved_selections/sel_unknown")
        self.assertEqual(r.status_code, 404)
    def test_delete_existing(self):
        sels = [
            {"id": "sel_a", "text": "Keep", "role": "claude"},
            {"id": "sel_b", "text": "Remove", "role": "student"},
        ]
        fake = _make_fake_state(sels)
        with patch.object(self.app_module, "_state", fake):
            r = self.client.delete("/api/saved_selections/sel_b")
        self.assertEqual(r.status_code, 204)
        remaining = fake.session_state.data["saved_selections"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["id"], "sel_a")
if __name__ == "__main__":
    unittest.main(verbosity=2)