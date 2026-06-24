import json
import sys
import tempfile
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
def _make_fake_state(initial_stickies=None):
    fake = MagicMock()
    fake.lock = MagicMock()
    fake.lock.__enter__ = MagicMock(return_value=None)
    fake.lock.__exit__ = MagicMock(return_value=False)
    fake.session_state = MagicMock()
    fake.session_state.data = {"stickies": list(initial_stickies or [])}
    def _set_meta(key, value):
        fake.session_state.data[key] = value
    fake.session_state.set_meta.side_effect = _set_meta
    return fake
class TestApiStickies(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
    def test_get_no_session(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.get("/api/stickies")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["stickies"], [])
        self.assertFalse(body["active"])
    def test_get_returns_existing(self):
        stickies = [
            {"id": "sticky_a", "kind": "user", "text": "Pense aux signatures",
             "enabled": True, "created_at": "2026-05-14T10:00:00+02:00",
             "edited_at": None, "source_message_id": None},
            {"id": "sticky_b", "kind": "tutor", "text": "Compute en O(n)",
             "enabled": True, "created_at": "2026-05-14T10:05:00+02:00",
             "edited_at": None, "source_message_id": None},
        ]
        with patch.object(self.app_module, "_state", _make_fake_state(stickies)):
            r = self.client.get("/api/stickies")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["active"])
        self.assertEqual(len(body["stickies"]), 2)
    def test_post_no_session(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.post("/api/stickies", json={"text": "x"})
        self.assertEqual(r.status_code, 409)
    def test_post_text_vide(self):
        with patch.object(self.app_module, "_state", _make_fake_state()):
            r = self.client.post("/api/stickies", json={"text": "  "})
        self.assertEqual(r.status_code, 400)
    def test_post_text_trop_long(self):
        with patch.object(self.app_module, "_state", _make_fake_state()):
            r = self.client.post("/api/stickies", json={"text": "x" * 201})
        self.assertEqual(r.status_code, 400)
        body = r.get_json()
        self.assertEqual(body["max_chars"], 200)
    def test_post_happy_path_default_user(self):
        fake = _make_fake_state()
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/stickies", json={"text": "Signatures STP"})
        self.assertEqual(r.status_code, 200)
        sticky = r.get_json()
        self.assertTrue(sticky["id"].startswith("sticky_"))
        self.assertEqual(sticky["text"], "Signatures STP")
        self.assertEqual(sticky["kind"], "user")
        self.assertTrue(sticky["enabled"])
        self.assertEqual(len(fake.session_state.data["stickies"]), 1)
    def test_post_kind_tutor(self):
        with patch.object(self.app_module, "_state", _make_fake_state()):
            r = self.client.post("/api/stickies", json={
                "text": "Toujours signature", "kind": "tutor",
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["kind"], "tutor")
    def test_post_kind_invalid_falls_back_to_user(self):
        with patch.object(self.app_module, "_state", _make_fake_state()):
            r = self.client.post("/api/stickies", json={
                "text": "X", "kind": "weird",
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["kind"], "user")
    def test_post_normalizes_whitespace(self):
        with patch.object(self.app_module, "_state", _make_fake_state()):
            r = self.client.post("/api/stickies", json={
                "text": "  foo   bar\n\nbaz  ",
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["text"], "foo bar baz")
    def test_post_with_source_message_id(self):
        with patch.object(self.app_module, "_state", _make_fake_state()):
            r = self.client.post("/api/stickies", json={
                "text": "Test", "source_message_id": "msg_xyz",
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["source_message_id"], "msg_xyz")
    def test_patch_no_session(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.patch("/api/stickies/sticky_a", json={"text": "x"})
        self.assertEqual(r.status_code, 409)
    def test_patch_empty_body(self):
        with patch.object(self.app_module, "_state", _make_fake_state()):
            r = self.client.patch("/api/stickies/sticky_a", json={})
        self.assertEqual(r.status_code, 400)
    def test_patch_unknown_id(self):
        existing = [{"id": "sticky_a", "kind": "user", "text": "x",
                     "enabled": True, "created_at": "t", "edited_at": None,
                     "source_message_id": None}]
        with patch.object(self.app_module, "_state", _make_fake_state(existing)):
            r = self.client.patch("/api/stickies/sticky_zzz", json={"text": "new"})
        self.assertEqual(r.status_code, 404)
    def test_patch_text_only(self):
        existing = [{"id": "sticky_a", "kind": "user", "text": "old",
                     "enabled": True, "created_at": "t", "edited_at": None,
                     "source_message_id": None}]
        fake = _make_fake_state(existing)
        with patch.object(self.app_module, "_state", fake):
            r = self.client.patch("/api/stickies/sticky_a", json={"text": "new"})
        self.assertEqual(r.status_code, 200)
        updated = r.get_json()
        self.assertEqual(updated["text"], "new")
        self.assertIsNotNone(updated["edited_at"])
        self.assertTrue(updated["enabled"])
    def test_patch_enabled_only(self):
        existing = [{"id": "sticky_a", "kind": "user", "text": "x",
                     "enabled": True, "created_at": "t", "edited_at": None,
                     "source_message_id": None}]
        with patch.object(self.app_module, "_state", _make_fake_state(existing)):
            r = self.client.patch("/api/stickies/sticky_a", json={"enabled": False})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["enabled"])
    def test_patch_text_trop_long(self):
        existing = [{"id": "sticky_a", "kind": "user", "text": "x",
                     "enabled": True, "created_at": "t", "edited_at": None,
                     "source_message_id": None}]
        with patch.object(self.app_module, "_state", _make_fake_state(existing)):
            r = self.client.patch("/api/stickies/sticky_a", json={"text": "y" * 201})
        self.assertEqual(r.status_code, 400)
    def test_delete_no_session(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.delete("/api/stickies/sticky_xyz")
        self.assertEqual(r.status_code, 409)
    def test_delete_unknown(self):
        existing = [{"id": "sticky_a", "kind": "user", "text": "x",
                     "enabled": True, "created_at": "t", "edited_at": None,
                     "source_message_id": None}]
        with patch.object(self.app_module, "_state", _make_fake_state(existing)):
            r = self.client.delete("/api/stickies/sticky_zzz")
        self.assertEqual(r.status_code, 404)
    def test_delete_existing(self):
        existing = [
            {"id": "sticky_a", "kind": "user", "text": "keep",
             "enabled": True, "created_at": "t", "edited_at": None,
             "source_message_id": None},
            {"id": "sticky_b", "kind": "tutor", "text": "remove",
             "enabled": True, "created_at": "t", "edited_at": None,
             "source_message_id": None},
        ]
        fake = _make_fake_state(existing)
        with patch.object(self.app_module, "_state", fake):
            r = self.client.delete("/api/stickies/sticky_b")
        self.assertEqual(r.status_code, 204)
        remaining = fake.session_state.data["stickies"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["id"], "sticky_a")
    def test_import_from_no_session(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.post("/api/stickies/import_from/some_session", json={})
        self.assertIn(r.status_code, (404, 409))
    def test_import_from_invalid_session_id(self):
        with patch.object(self.app_module, "_state", _make_fake_state()):
            r = self.client.post(
                "/api/stickies/import_from/..%2Fevil", json={},
            )
        self.assertIn(r.status_code, (400, 404))
    def test_import_from_real_source(self):
        import app as app_module
        with tempfile.TemporaryDirectory() as td:
            tmp_sessions_dir = Path(td)
            source_id = "2026-05-13_TEST_TD1_ex1_colle_mixte_strict_1"
            source_data = {
                "session_id": source_id,
                "stickies": [
                    {"id": "sticky_old1", "kind": "user", "text": "Signatures",
                     "enabled": True, "created_at": "t", "edited_at": None,
                     "source_message_id": None},
                    {"id": "sticky_old2", "kind": "tutor", "text": "Complexité",
                     "enabled": True, "created_at": "t", "edited_at": None,
                     "source_message_id": None},
                    {"id": "sticky_old3", "kind": "user", "text": "Disabled",
                     "enabled": False, "created_at": "t", "edited_at": None,
                     "source_message_id": None},
                ],
            }
            (tmp_sessions_dir / f"{source_id}.json").write_text(
                json.dumps(source_data), encoding="utf-8",
            )
            fake = _make_fake_state()
            with patch.object(app_module, "SESSIONS_DIR", tmp_sessions_dir):
                with patch.object(app_module, "_state", fake):
                    r = self.client.post(
                        f"/api/stickies/import_from/{source_id}", json={},
                    )
            self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
            body = r.get_json()
            self.assertEqual(body["imported_count"], 2)
            imported_ids = {s["id"] for s in body["imported"]}
            self.assertNotIn("sticky_old1", imported_ids)
            self.assertNotIn("sticky_old2", imported_ids)
            kinds = {s["kind"] for s in body["imported"]}
            self.assertEqual(kinds, {"user", "tutor"})
            for s in body["imported"]:
                self.assertEqual(s["imported_from"], source_id)
            self.assertEqual(len(fake.session_state.data["stickies"]), 2)
class TestFormatStickiesBlockForLlm(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self._fn = app._format_stickies_block_for_llm
    def test_empty_when_no_stickies(self):
        fake = _make_fake_state([])
        out = self._fn(fake)
        self.assertEqual(out, "")
    def test_empty_when_all_disabled(self):
        stickies = [
            {"id": "s1", "kind": "user", "text": "X", "enabled": False},
            {"id": "s2", "kind": "tutor", "text": "Y", "enabled": False},
        ]
        fake = _make_fake_state(stickies)
        out = self._fn(fake)
        self.assertEqual(out, "")
    def test_emits_block_with_enabled_only(self):
        stickies = [
            {"id": "s1", "kind": "user", "text": "Signatures", "enabled": True},
            {"id": "s2", "kind": "tutor", "text": "O(n)", "enabled": True},
            {"id": "s3", "kind": "user", "text": "Disabled", "enabled": False},
        ]
        fake = _make_fake_state(stickies)
        out = self._fn(fake)
        self.assertIn("[CONSIGNES ÉPINGLÉES PAR L'ÉTUDIANT", out)
        self.assertIn("[/CONSIGNES ÉPINGLÉES]", out)
        self.assertIn("📌 Signatures", out)
        self.assertIn("🤖 O(n)", out)
        self.assertNotIn("Disabled", out)
        self.assertTrue(out.endswith("\n"))
    def test_handles_missing_enabled_field_as_true(self):
        stickies = [{"id": "s1", "kind": "user", "text": "Legacy"}]
        fake = _make_fake_state(stickies)
        out = self._fn(fake)
        self.assertIn("📌 Legacy", out)
    def test_skip_empty_text(self):
        stickies = [{"id": "s1", "kind": "user", "text": "  ", "enabled": True}]
        fake = _make_fake_state(stickies)
        out = self._fn(fake)
        self.assertEqual(out, "")
    def test_robust_to_missing_data_dict(self):
        fake = MagicMock()
        fake.session_state.data = None
        out = self._fn(fake)
        self.assertEqual(out, "")
if __name__ == "__main__":
    unittest.main(verbosity=2)