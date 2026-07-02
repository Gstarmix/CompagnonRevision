"""
test_app_apply_edit.py : couverture de l'endpoint POST /api/apply_edit (Phase A.7).

L'endpoint applique une suggestion de correction sur un fichier perso de
l'arbre COURS/. On utilise un faux COURS_ROOT pointé sur un TemporaryDirectory
en monkeypatchant ``app.COURS_ROOT`` pour chaque test.

Lance avec :
    python -m unittest tests.test_app_apply_edit
"""

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

# Path setup
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


class TestApiApplyEdit(unittest.TestCase):

    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
        self._tmpobj = TemporaryDirectory()
        self.cours = Path(self._tmpobj.name).resolve()
        # Préparer un script perso éditable
        self.script = self.cours / "AN1" / "TD" / "TD5" / "scripts_oraux" / "SCRIPT.md"
        self.script.parent.mkdir(parents=True)
        self.script.write_text(
            "# Script\nf continue donc Rolle s'applique.\nAutre paragraphe.",
            encoding="utf-8",
        )
        # Patch COURS_ROOT du module app
        self._cours_patch = patch.object(self.app_module, "COURS_ROOT", self.cours)
        self._cours_patch.start()

    def tearDown(self):
        self._cours_patch.stop()
        self._tmpobj.cleanup()

    # ----------------------------------------------- happy path

    def test_applies_replaces_unique_occurrence(self):
        r = self.client.post(
            "/api/apply_edit",
            json={
                "file": "AN1/TD/TD5/scripts_oraux/SCRIPT.md",
                "before": "f continue donc Rolle s'applique.",
                "after": "f continue ET dérivable donc Rolle s'applique.",
            },
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        body = r.get_json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["delta_chars"], len("f continue ET dérivable donc Rolle s'applique.") - len("f continue donc Rolle s'applique."))
        # Fichier mis à jour
        new = self.script.read_text(encoding="utf-8")
        self.assertIn("dérivable", new)
        # Backup .bak créé avec le contenu original
        backup = self.script.with_suffix(self.script.suffix + ".bak")
        self.assertTrue(backup.exists())
        self.assertIn("Rolle s'applique.", backup.read_text(encoding="utf-8"))
        self.assertNotIn("dérivable", backup.read_text(encoding="utf-8"))

    # ----------------------------------------------- validations

    def test_rejects_traversal(self):
        r = self.client.post(
            "/api/apply_edit",
            json={
                "file": "../../../escape.md",
                "before": "X", "after": "Y",
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("traversal", r.get_json()["error"].lower())

    def test_rejects_absolute_path_unix(self):
        r = self.client.post(
            "/api/apply_edit",
            json={"file": "/etc/passwd", "before": "X", "after": "Y"},
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("absolu", r.get_json()["error"].lower())

    def test_rejects_absolute_path_windows(self):
        r = self.client.post(
            "/api/apply_edit",
            json={"file": "C:/Windows/system32.txt", "before": "X", "after": "Y"},
        )
        self.assertEqual(r.status_code, 400)

    def test_rejects_pdf_extension(self):
        # Crée un .pdf factice dans COURS_ROOT
        pdf = self.cours / "AN1" / "TD" / "TD5" / "corrections" / "correction.pdf"
        pdf.parent.mkdir(parents=True)
        pdf.write_bytes(b"%PDF-1.4 fake")
        r = self.client.post(
            "/api/apply_edit",
            json={
                "file": "AN1/TD/TD5/corrections/correction.pdf",
                "before": "fake", "after": "modifié",
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("éditable", r.get_json()["error"].lower())

    def test_rejects_missing_file(self):
        r = self.client.post(
            "/api/apply_edit",
            json={
                "file": "AN1/TD/TD5/scripts_oraux/GHOST.md",
                "before": "X", "after": "Y",
            },
        )
        self.assertEqual(r.status_code, 404)

    def test_rejects_before_not_found(self):
        r = self.client.post(
            "/api/apply_edit",
            json={
                "file": "AN1/TD/TD5/scripts_oraux/SCRIPT.md",
                "before": "ce passage n'existe pas dans le fichier",
                "after": "Y",
            },
        )
        self.assertEqual(r.status_code, 422)
        self.assertIn("introuvable", r.get_json()["error"].lower())

    def test_rejects_before_not_unique(self):
        # Réécrit le fichier avec doublon
        self.script.write_text(
            "AAA\nBBB\nAAA\n", encoding="utf-8",
        )
        r = self.client.post(
            "/api/apply_edit",
            json={
                "file": "AN1/TD/TD5/scripts_oraux/SCRIPT.md",
                "before": "AAA",
                "after": "ZZZ",
            },
        )
        self.assertEqual(r.status_code, 422)
        self.assertIn("ambigu", r.get_json()["error"].lower())
        # Fichier non modifié
        self.assertEqual(self.script.read_text(encoding="utf-8"), "AAA\nBBB\nAAA\n")

    def test_rejects_noop(self):
        r = self.client.post(
            "/api/apply_edit",
            json={
                "file": "AN1/TD/TD5/scripts_oraux/SCRIPT.md",
                "before": "Rolle", "after": "Rolle",
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("no-op", r.get_json()["error"].lower())

    def test_rejects_missing_fields(self):
        r = self.client.post("/api/apply_edit", json={"file": "x.md"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
