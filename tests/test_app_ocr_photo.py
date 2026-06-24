import shutil
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
def _make_fake_state_with_attachment(att_dict):
    fake = MagicMock()
    fake.lock = MagicMock()
    fake.lock.__enter__ = MagicMock(return_value=None)
    fake.lock.__exit__ = MagicMock(return_value=False)
    fake.pending_attachments = [att_dict]
    return fake
def _fake_client_returning(response_text):
    fake = MagicMock()
    fake._history = []
    type(fake).history = property(lambda self_: list(self_._history))
    def _append(text):
        fake._history.append({"role": "user", "content": text})
    def _stream(on_event):
        fake._history.append({"role": "assistant", "content": response_text})
    fake.append_user_message.side_effect = _append
    fake.stream_response.side_effect = _stream
    return fake
class TestApiOcrPhoto(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
        self._tmpdir = Path(tempfile.mkdtemp(prefix="ocr_test_"))
        self._uploads_patcher = patch.object(app, "UPLOADS_DIR", self._tmpdir)
        self._uploads_patcher.start()
        target = self._tmpdir / "EN1/CC/photos/test.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\xff\xd8\xff fake jpg bytes")
    def tearDown(self):
        self._uploads_patcher.stop()
        shutil.rmtree(self._tmpdir, ignore_errors=True)
    def _att(self, **overrides):
        d = {
            "id": "att_xyz999",
            "rel_path": "EN1/CC/photos/test.jpg",
            "filename": "test.jpg",
            "original_name": "table.jpg",
            "mime": "image/jpeg",
            "size_bytes": 12345,
            "is_image": True,
            "storage": "uploads",
        }
        d.update(overrides)
        return d
    def test_missing_attachment_id_returns_400(self):
        with patch.object(self.app_module, "_state", _make_fake_state_with_attachment(self._att())):
            r = self.client.post("/api/ocr_photo", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("attachment_id", r.get_json()["error"])
    def test_no_active_session_returns_409(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.post("/api/ocr_photo", json={"attachment_id": "x"})
        self.assertEqual(r.status_code, 409)
    def test_unknown_attachment_returns_404(self):
        fake = _make_fake_state_with_attachment(self._att())
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/ocr_photo", json={"attachment_id": "att_unknown"})
        self.assertEqual(r.status_code, 404)
    def test_non_image_attachment_returns_400(self):
        att = self._att(is_image=False)
        fake = _make_fake_state_with_attachment(att)
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post("/api/ocr_photo", json={"attachment_id": "att_xyz999"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("image", r.get_json()["error"].lower())
    def test_happy_path_returns_ocr_markdown(self):
        att = self._att()
        fake = _make_fake_state_with_attachment(att)
        response = (
            '<<<OCR>>>{"ocr_markdown": "| SEL | S |\\n|---|---|\\n| 0 | (vide) |",'
            ' "kind_detected": "table_de_verite", "completeness_pct": 50,'
            ' "warnings": ["colonne S vide"]}<<<END>>>'
        )
        with patch.object(self.app_module, "_state", fake), \
             patch("app.ClaudeClient", return_value=_fake_client_returning(response)):
            r = self.client.post("/api/ocr_photo", json={
                "attachment_id": "att_xyz999",
                "hint": "table de vérité MUX21",
            })
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        body = r.get_json()
        self.assertIn("| SEL | S |", body["ocr_markdown"])
        self.assertIn("(vide)", body["ocr_markdown"])
        self.assertEqual(body["kind_detected"], "table_de_verite")
        self.assertEqual(body["completeness_pct"], 50)
        self.assertEqual(body["warnings"], ["colonne S vide"])
        self.assertEqual(body["model"], "gemini-2.5-flash")
        self.assertEqual(body["attachment_id"], "att_xyz999")
    def test_forces_gemini_flash_regardless_of_engine_pref(self):
        att = self._att()
        fake_state = _make_fake_state_with_attachment(att)
        response = '<<<OCR>>>{"ocr_markdown": "x", "kind_detected": "autre", "completeness_pct": 100, "warnings": []}<<<END>>>'
        with patch.object(self.app_module, "_state", fake_state), \
             patch("app.ClaudeClient", return_value=_fake_client_returning(response)) as MockClient, \
             patch("app._read_engine_pref", return_value="cli_subscription"):
            r = self.client.post("/api/ocr_photo", json={"attachment_id": "att_xyz999"})
        self.assertEqual(r.status_code, 200)
        kwargs = MockClient.call_args.kwargs
        self.assertEqual(kwargs.get("engine"), "gemini_api")
        self.assertEqual(kwargs.get("model"), "gemini-2.5-flash")
    def test_empty_ocr_markdown_returns_502(self):
        att = self._att()
        fake = _make_fake_state_with_attachment(att)
        response = '<<<OCR>>>{"ocr_markdown": "", "kind_detected": "autre"}<<<END>>>'
        with patch.object(self.app_module, "_state", fake), \
             patch("app.ClaudeClient", return_value=_fake_client_returning(response)):
            r = self.client.post("/api/ocr_photo", json={"attachment_id": "att_xyz999"})
        self.assertEqual(r.status_code, 502)
        self.assertEqual(r.get_json()["error"], "reponse_vide")
    def test_warnings_capped_at_10(self):
        att = self._att()
        fake = _make_fake_state_with_attachment(att)
        warnings = [f"warning {i}" for i in range(20)]
        import json as _json
        warnings_json = _json.dumps(warnings)
        response = (
            '<<<OCR>>>{"ocr_markdown": "x", "kind_detected": "autre",'
            ' "completeness_pct": 80, "warnings": '
            + warnings_json + '}<<<END>>>'
        )
        with patch.object(self.app_module, "_state", fake), \
             patch("app.ClaudeClient", return_value=_fake_client_returning(response)):
            r = self.client.post("/api/ocr_photo", json={"attachment_id": "att_xyz999"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()["warnings"]), 10)
if __name__ == "__main__":
    unittest.main(verbosity=2)