"""
test_app_upload_file.py : couverture endpoint Phase A.10.2
GET /api/upload_file?path=... qui sert depuis UPLOADS_DIR (et non
COURS_ROOT). Pendant de /api/cours_file pour les uploads de séance.

Vérifie : param manquant, traversal, chemin absolu, fichier introuvable,
extension non whitelistée, happy path inline + mime correct.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


class TestApiUploadFile(unittest.TestCase):

    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()

    def test_missing_path(self):
        r = self.client.get("/api/upload_file")
        self.assertEqual(r.status_code, 400)
        self.assertIn("manquant", r.get_json()["error"])

    def test_absolute_path_refused(self):
        # Sur Windows un chemin "C:/x" est absolu
        r = self.client.get("/api/upload_file?path=C:/etc/passwd")
        self.assertIn(r.status_code, (400, 403))

    def test_traversal_refused(self):
        r = self.client.get("/api/upload_file?path=../../etc/passwd")
        self.assertEqual(r.status_code, 400)

    def test_file_not_found(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(self.app_module, "UPLOADS_DIR", Path(td)):
                r = self.client.get("/api/upload_file?path=ghost.jpg")
            self.assertEqual(r.status_code, 404)

    def test_extension_not_servable(self):
        with tempfile.TemporaryDirectory() as td:
            uploads = Path(td)
            (uploads / "session_X").mkdir()
            f = uploads / "session_X" / "secret.exe"
            f.write_bytes(b"binary")
            with patch.object(self.app_module, "UPLOADS_DIR", uploads):
                r = self.client.get("/api/upload_file?path=session_X/secret.exe")
            self.assertEqual(r.status_code, 415)

    def test_happy_path_jpg(self):
        with tempfile.TemporaryDirectory() as td:
            uploads = Path(td)
            (uploads / "session_X" / "photos").mkdir(parents=True)
            f = uploads / "session_X" / "photos" / "p_v1.jpg"
            f.write_bytes(b"\xff\xd8\xff\xe0" + b"x" * 100)  # JPEG-ish
            with patch.object(self.app_module, "UPLOADS_DIR", uploads):
                r = self.client.get("/api/upload_file?path=session_X/photos/p_v1.jpg")
                status, mimetype = r.status_code, r.mimetype
                r.close()  # Windows : libère le handle avant rmdir
            self.assertEqual(status, 200)
            self.assertEqual(mimetype, "image/jpeg")

    def test_happy_path_png(self):
        with tempfile.TemporaryDirectory() as td:
            uploads = Path(td)
            (uploads / "session_X" / "photos").mkdir(parents=True)
            f = uploads / "session_X" / "photos" / "p.png"
            f.write_bytes(b"\x89PNG" + b"y" * 50)
            with patch.object(self.app_module, "UPLOADS_DIR", uploads):
                r = self.client.get("/api/upload_file?path=session_X/photos/p.png")
                status, mimetype = r.status_code, r.mimetype
                r.close()
            self.assertEqual(status, 200)
            self.assertEqual(mimetype, "image/png")

    def test_path_outside_uploads_dir_refused(self):
        """Path qui résout vers un parent → 403."""
        with tempfile.TemporaryDirectory() as td:
            uploads = Path(td)
            outside = uploads.parent / "outside.jpg"
            outside.write_bytes(b"x")
            try:
                with patch.object(self.app_module, "UPLOADS_DIR", uploads):
                    # `..` est attrapé en amont par "chemin invalide" 400.
                    r = self.client.get("/api/upload_file?path=../outside.jpg")
                self.assertIn(r.status_code, (400, 403))
            finally:
                if outside.exists():
                    outside.unlink()


if __name__ == "__main__":
    unittest.main(verbosity=2)
