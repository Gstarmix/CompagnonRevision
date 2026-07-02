"""
test_app_attachment_replace.py : couverture endpoint
POST /api/pending_attachments/<id>/replace (Phase v15.7.10).

Vérifie : 409 sans session, 404 si att_id inconnu, 400 si attachment
non-image (refus du crop sur PDF/Excel), 400 si fichier manquant, 200
happy path (nouveau fichier écrit, entry mise à jour, ancien fichier
préservé sur disque).
"""

import io
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
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
    """Fake CompanionSession avec une seule pending_attachment."""
    fake = MagicMock()
    fake.lock = MagicMock()
    fake.lock.__enter__ = MagicMock(return_value=None)
    fake.lock.__exit__ = MagicMock(return_value=False)
    fake.pending_attachments = [att_dict]
    return fake


class TestApiReplaceAttachment(unittest.TestCase):

    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
        # tmpdir simulant COURS_ROOT (l'ancienne photo y vit)
        self._tmpobj = TemporaryDirectory()
        self.tmp_root = Path(self._tmpobj.name)
        self.original_path = self.tmp_root / "AN1" / "TD" / "TD5" / "photos" / "table_v1.jpg"
        self.original_path.parent.mkdir(parents=True, exist_ok=True)
        self.original_path.write_bytes(b"\xff\xd8\xff" + b"oldjpg" * 100)  # ~600 octets de contenu

    def tearDown(self):
        self._tmpobj.cleanup()

    def _att(self, **overrides):
        d = {
            "id": "att_abc123",
            "rel_path": "AN1/TD/TD5/photos/table_v1.jpg",
            "filename": "table_v1.jpg",
            "original_name": "table.jpg",
            "mime": "image/jpeg",
            "size_bytes": self.original_path.stat().st_size,
            "is_image": True,
            "uploaded_at": "2026-05-10T10:00:00+02:00",
        }
        d.update(overrides)
        return d

    def test_no_active_session_returns_409(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.post(
                "/api/pending_attachments/att_abc123/replace",
                data={"file": (io.BytesIO(b"\xff\xd8\xff new"), "cropped.jpg")},
                content_type="multipart/form-data",
            )
        self.assertEqual(r.status_code, 409)

    def test_unknown_id_returns_404(self):
        fake = _make_fake_state_with_attachment(self._att())
        with patch.object(self.app_module, "_state", fake), \
             patch.object(self.app_module, "COURS_ROOT", self.tmp_root):
            r = self.client.post(
                "/api/pending_attachments/att_unknown/replace",
                data={"file": (io.BytesIO(b"\xff\xd8\xff"), "cropped.jpg")},
                content_type="multipart/form-data",
            )
        self.assertEqual(r.status_code, 404)

    def test_non_image_attachment_returns_400(self):
        att = self._att(is_image=False, mime="application/pdf",
                        rel_path="AN1/TD/TD5/attachments/notes.pdf")
        fake = _make_fake_state_with_attachment(att)
        with patch.object(self.app_module, "_state", fake), \
             patch.object(self.app_module, "COURS_ROOT", self.tmp_root):
            r = self.client.post(
                "/api/pending_attachments/att_abc123/replace",
                data={"file": (io.BytesIO(b"%PDF-1.4 fake"), "cropped.pdf")},
                content_type="multipart/form-data",
            )
        self.assertEqual(r.status_code, 400)
        self.assertIn("image", r.get_json()["error"].lower())

    def test_missing_file_returns_400(self):
        fake = _make_fake_state_with_attachment(self._att())
        with patch.object(self.app_module, "_state", fake), \
             patch.object(self.app_module, "COURS_ROOT", self.tmp_root):
            r = self.client.post(
                "/api/pending_attachments/att_abc123/replace",
                data={},
                content_type="multipart/form-data",
            )
        self.assertEqual(r.status_code, 400)

    def test_happy_path_creates_new_file_and_updates_entry(self):
        fake = _make_fake_state_with_attachment(self._att())
        new_content = b"\xff\xd8\xff" + b"newjpg" * 50  # nouveau JPEG bidon
        with patch.object(self.app_module, "_state", fake), \
             patch.object(self.app_module, "COURS_ROOT", self.tmp_root):
            r = self.client.post(
                "/api/pending_attachments/att_abc123/replace",
                data={"file": (io.BytesIO(new_content), "cropped_1234.jpg")},
                content_type="multipart/form-data",
            )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        body = r.get_json()
        self.assertTrue(body["ok"])
        self.assertTrue(body.get("cropped"))
        # Le rel_path a changé (suffixe _cropped_v1)
        self.assertNotEqual(body["rel_path"], "AN1/TD/TD5/photos/table_v1.jpg")
        self.assertIn("_cropped_v", body["rel_path"])
        # Le nouveau fichier existe
        new_path = self.tmp_root / body["rel_path"]
        self.assertTrue(new_path.exists())
        self.assertEqual(new_path.read_bytes(), new_content)
        # L'ancien fichier est préservé (pas supprimé)
        self.assertTrue(self.original_path.exists())
        # L'entry dans pending_attachments a été mutée
        self.assertEqual(fake.pending_attachments[0]["rel_path"], body["rel_path"])
        self.assertEqual(fake.pending_attachments[0]["size_bytes"], len(new_content))

    def test_recropping_avoids_cumulating_suffix(self):
        """Si on re-crop une photo déjà cropped, on ne produit pas
        `..._cropped_v1_cropped_v1.jpg` mais `..._cropped_v2.jpg`."""
        # Simule une photo déjà cropped
        cropped_path = self.tmp_root / "AN1" / "TD" / "TD5" / "photos" / "table_v1_cropped_v1.jpg"
        cropped_path.parent.mkdir(parents=True, exist_ok=True)
        cropped_path.write_bytes(b"\xff\xd8\xff already cropped")
        att = self._att(
            rel_path="AN1/TD/TD5/photos/table_v1_cropped_v1.jpg",
            filename="table_v1_cropped_v1.jpg",
        )
        fake = _make_fake_state_with_attachment(att)
        with patch.object(self.app_module, "_state", fake), \
             patch.object(self.app_module, "COURS_ROOT", self.tmp_root):
            r = self.client.post(
                "/api/pending_attachments/att_abc123/replace",
                data={"file": (io.BytesIO(b"\xff\xd8\xff again"), "cropped_again.jpg")},
                content_type="multipart/form-data",
            )
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        # Doit produire _cropped_v2, pas _cropped_v1_cropped_v1
        self.assertIn("_cropped_v2", body["filename"])
        self.assertNotIn("_cropped_v1_cropped_v1", body["filename"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
