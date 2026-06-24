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
def _make_fake_state(initial_photos=None):
    fake = MagicMock()
    fake.lock = MagicMock()
    fake.lock.__enter__ = MagicMock(return_value=None)
    fake.lock.__exit__ = MagicMock(return_value=False)
    fake.session_state = MagicMock()
    fake.session_state.data = {"session_photos": list(initial_photos or [])}
    def _set_meta(key, value):
        fake.session_state.data[key] = value
    fake.session_state.set_meta.side_effect = _set_meta
    return fake
class TestApiSessionPhotos(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
    def test_get_no_session(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.get("/api/session_photos")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["photos"], [])
        self.assertFalse(body["active"])
    def test_get_returns_existing(self):
        photos = [
            {
                "id": "att_aaa", "rel_path": "AN1/TD/TD5/photos/p1.jpg",
                "filename": "p1.jpg", "sent_at": "2026-05-14T10:00:00+02:00",
            },
            {
                "id": "att_bbb", "rel_path": "AN1/TD/TD5/photos/p2.jpg",
                "filename": "p2.jpg", "sent_at": "2026-05-14T10:05:00+02:00",
            },
        ]
        with patch.object(self.app_module, "_state", _make_fake_state(photos)):
            r = self.client.get("/api/session_photos")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["active"])
        self.assertEqual(len(body["photos"]), 2)
        self.assertEqual(body["photos"][0]["id"], "att_aaa")
    def test_get_empty_when_no_photos(self):
        with patch.object(self.app_module, "_state", _make_fake_state([])):
            r = self.client.get("/api/session_photos")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body["active"])
        self.assertEqual(body["photos"], [])
    def test_delete_no_session(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.delete("/api/session_photos/att_xyz")
        self.assertEqual(r.status_code, 409)
    def test_delete_unknown(self):
        photos = [{"id": "att_a", "rel_path": "x.jpg", "filename": "x.jpg"}]
        with patch.object(self.app_module, "_state", _make_fake_state(photos)):
            r = self.client.delete("/api/session_photos/att_unknown")
        self.assertEqual(r.status_code, 404)
    def test_delete_existing(self):
        photos = [
            {"id": "att_a", "rel_path": "x.jpg", "filename": "x.jpg"},
            {"id": "att_b", "rel_path": "y.jpg", "filename": "y.jpg"},
        ]
        fake = _make_fake_state(photos)
        with patch.object(self.app_module, "_state", fake):
            r = self.client.delete("/api/session_photos/att_b")
        self.assertEqual(r.status_code, 204)
        remaining = fake.session_state.data["session_photos"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["id"], "att_a")
    def test_delete_idempotent_after_success(self):
        photos = [{"id": "att_a", "rel_path": "x.jpg", "filename": "x.jpg"}]
        fake = _make_fake_state(photos)
        with patch.object(self.app_module, "_state", fake):
            r1 = self.client.delete("/api/session_photos/att_a")
            r2 = self.client.delete("/api/session_photos/att_a")
        self.assertEqual(r1.status_code, 204)
        self.assertEqual(r2.status_code, 404)
        self.assertEqual(fake.session_state.data["session_photos"], [])
import tempfile
def _make_fake_state_with_transcript(transcript, photos=None,
                                     backfilled=False):
    fake = MagicMock()
    fake.lock = MagicMock()
    fake.lock.__enter__ = MagicMock(return_value=None)
    fake.lock.__exit__ = MagicMock(return_value=False)
    fake.session_state = MagicMock()
    data = {
        "transcript": transcript,
    }
    if photos is not None:
        data["session_photos"] = photos
    if backfilled:
        data["session_photos_backfilled"] = True
    fake.session_state.data = data
    def _set_meta(key, value):
        fake.session_state.data[key] = value
    fake.session_state.set_meta.side_effect = _set_meta
    return fake
class TestBackfillSessionPhotos(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
    def test_no_backfill_when_marker_set(self):
        transcript = [
            {"role": "student", "text": "![p](AN1/TD/TD5/photos/p.jpg)",
             "at": "2026-05-10T10:00:00"},
        ]
        fake = _make_fake_state_with_transcript(transcript, backfilled=True)
        with patch.object(self.app_module, "_state", fake):
            r = self.client.get("/api/session_photos")
        self.assertEqual(r.get_json()["photos"], [])
    def test_no_backfill_when_session_photos_already_populated(self):
        photos = [{"id": "att_a", "rel_path": "x.jpg", "filename": "x.jpg"}]
        transcript = [
            {"role": "student", "text": "![y](AN1/TD/TD5/photos/y.jpg)",
             "at": "2026-05-10"},
        ]
        fake = _make_fake_state_with_transcript(transcript, photos=photos)
        with patch.object(self.app_module, "_state", fake):
            r = self.client.get("/api/session_photos")
        out = r.get_json()["photos"]
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["id"], "att_a")
        self.assertTrue(fake.session_state.data.get("session_photos_backfilled"))
    def test_backfill_from_transcript_with_real_files(self):
        with tempfile.TemporaryDirectory() as td:
            cours_root = Path(td)
            photo_dir = cours_root / "AN1" / "TD" / "TD5" / "photos"
            photo_dir.mkdir(parents=True)
            (photo_dir / "p1.jpg").write_bytes(b"fake_jpeg_data" * 100)
            (photo_dir / "p2.png").write_bytes(b"fake_png_data" * 50)
            transcript = [
                {"role": "claude", "text": "Question…", "at": "2026-05-10T10:00:00"},
                {"role": "student",
                 "text": "Voici ma photo:\n![p1.jpg](AN1/TD/TD5/photos/p1.jpg)",
                 "at": "2026-05-10T10:05:00"},
                {"role": "claude", "text": "OK", "at": "2026-05-10T10:06:00"},
                {"role": "student",
                 "text": "Et une autre ![p2.png](AN1/TD/TD5/photos/p2.png)",
                 "at": "2026-05-10T10:10:00"},
            ]
            fake = _make_fake_state_with_transcript(transcript)
            with patch.object(self.app_module, "COURS_ROOT", cours_root):
                with patch.object(self.app_module, "_state", fake):
                    r = self.client.get("/api/session_photos")
            out = r.get_json()["photos"]
            self.assertEqual(len(out), 2)
            paths = {p["rel_path"] for p in out}
            self.assertEqual(paths, {
                "AN1/TD/TD5/photos/p1.jpg",
                "AN1/TD/TD5/photos/p2.png",
            })
            for p in out:
                self.assertTrue(p.get("backfilled"))
                self.assertTrue(p["id"].startswith("photo_"))
                self.assertGreater(p["size_bytes"], 0)
            mimes = {p["filename"]: p["mime"] for p in out}
            self.assertEqual(mimes["p1.jpg"], "image/jpeg")
            self.assertEqual(mimes["p2.png"], "image/png")
            self.assertTrue(fake.session_state.data["session_photos_backfilled"])
    def test_backfill_skips_missing_files(self):
        with tempfile.TemporaryDirectory() as td:
            cours_root = Path(td)
            transcript = [
                {"role": "student",
                 "text": "![ghost](AN1/TD/TD5/photos/ghost.jpg)",
                 "at": "2026-05-10"},
            ]
            fake = _make_fake_state_with_transcript(transcript)
            with patch.object(self.app_module, "COURS_ROOT", cours_root):
                with patch.object(self.app_module, "_state", fake):
                    r = self.client.get("/api/session_photos")
            self.assertEqual(r.get_json()["photos"], [])
            self.assertTrue(fake.session_state.data["session_photos_backfilled"])
    def test_backfill_dedup_same_path(self):
        with tempfile.TemporaryDirectory() as td:
            cours_root = Path(td)
            photo_dir = cours_root / "AN1" / "TD" / "TD5" / "photos"
            photo_dir.mkdir(parents=True)
            (photo_dir / "p.jpg").write_bytes(b"x")
            transcript = [
                {"role": "student",
                 "text": "![p](AN1/TD/TD5/photos/p.jpg)",
                 "at": "2026-05-10T10:00:00"},
                {"role": "student",
                 "text": "Encore ![p](AN1/TD/TD5/photos/p.jpg)",
                 "at": "2026-05-10T10:05:00"},
            ]
            fake = _make_fake_state_with_transcript(transcript)
            with patch.object(self.app_module, "COURS_ROOT", cours_root):
                with patch.object(self.app_module, "_state", fake):
                    r = self.client.get("/api/session_photos")
            self.assertEqual(len(r.get_json()["photos"]), 1)
    def test_backfill_skips_external_urls(self):
        with tempfile.TemporaryDirectory() as td:
            cours_root = Path(td)
            transcript = [
                {"role": "student",
                 "text": "![ext](https://example.com/img.jpg)\n"
                         "![abs](/etc/passwd)\n"
                         "![api](/api/cours_file?path=x)",
                 "at": "2026-05-10"},
            ]
            fake = _make_fake_state_with_transcript(transcript)
            with patch.object(self.app_module, "COURS_ROOT", cours_root):
                with patch.object(self.app_module, "_state", fake):
                    r = self.client.get("/api/session_photos")
            self.assertEqual(r.get_json()["photos"], [])
    def test_backfill_skips_claude_bubbles(self):
        with tempfile.TemporaryDirectory() as td:
            cours_root = Path(td)
            photo_dir = cours_root / "AN1" / "TD" / "TD5" / "photos"
            photo_dir.mkdir(parents=True)
            (photo_dir / "p.jpg").write_bytes(b"x")
            transcript = [
                {"role": "claude",
                 "text": "Regardez ![hint](AN1/TD/TD5/photos/p.jpg)",
                 "at": "2026-05-10"},
            ]
            fake = _make_fake_state_with_transcript(transcript)
            with patch.object(self.app_module, "COURS_ROOT", cours_root):
                with patch.object(self.app_module, "_state", fake):
                    r = self.client.get("/api/session_photos")
            self.assertEqual(r.get_json()["photos"], [])
    def test_backfill_marker_persists_empty_result(self):
        transcript = [
            {"role": "student", "text": "Juste du texte",
             "at": "2026-05-10"},
        ]
        fake = _make_fake_state_with_transcript(transcript)
        with patch.object(self.app_module, "_state", fake):
            self.client.get("/api/session_photos")
        self.assertTrue(fake.session_state.data["session_photos_backfilled"])
        self.assertEqual(fake.session_state.data["session_photos"], [])
if __name__ == "__main__":
    unittest.main(verbosity=2)