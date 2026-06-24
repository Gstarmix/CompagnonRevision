import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
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
def _make_droit_arbo(root: Path) -> None:
    cm = root / "droit-personnes" / "CM"
    (cm / "transcriptions").mkdir(parents=True)
    (cm / "fiches").mkdir(parents=True)
    (cm / "transcriptions" / "CM3_droit-personnes_1509.txt").write_text(
        "La personnalité juridique commence à la naissance.", encoding="utf-8"
    )
    (cm / "fiches" / "fiche_CM3_droit-personnes_1509.md").write_text(
        "# Fiche CM3\n- Naissance vivante et viable.", encoding="utf-8"
    )
    methodo = root / "_methodo"
    methodo.mkdir(parents=True)
    (methodo / "methodo_dissertation.md").write_text(
        "# Méthodo dissertation", encoding="utf-8"
    )
class TestDroitOptionsEndpoint(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
        self._tmpobj = TemporaryDirectory()
        self.droit_root = Path(self._tmpobj.name)
        _make_droit_arbo(self.droit_root)
    def tearDown(self):
        self._tmpobj.cleanup()
    def test_lists_matieres(self):
        with patch.object(self.app_module, "CARTABLE_ROOT", self.droit_root):
            r = self.client.get("/api/droit_options")
        self.assertEqual(r.status_code, 200)
        out = r.get_json()
        self.assertIn("droit-personnes", out["matieres"])
        self.assertEqual(out["types"], [])
        self.assertEqual(out["nums"], [])
    def test_cascade_types_then_nums(self):
        with patch.object(self.app_module, "CARTABLE_ROOT", self.droit_root):
            r = self.client.get("/api/droit_options?matiere=droit-personnes")
            self.assertEqual(r.get_json()["types"], ["CM"])
            r2 = self.client.get(
                "/api/droit_options?matiere=droit-personnes&type=CM"
            )
        self.assertEqual(r2.get_json()["nums"], ["3"])
class TestBuildSessionContextDroit(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self._tmpobj = TemporaryDirectory()
        self.droit_root = Path(self._tmpobj.name)
        _make_droit_arbo(self.droit_root)
    def tearDown(self):
        self._tmpobj.cleanup()
    def test_droit_context_resolves_transcription_and_fiche(self):
        body = {
            "source": "droit",
            "matiere": "droit-personnes",
            "type": "CM",
            "num": "3",
        }
        with patch.object(self.app_module, "CARTABLE_ROOT", self.droit_root):
            ctx = self.app_module._build_session_context(body)
        self.assertEqual(ctx.droit_source, "droit-personnes")
        self.assertEqual(ctx.matiere, "droit-personnes")
        self.assertEqual(ctx.type, "CM")
        self.assertEqual(ctx.num, "3")
        self.assertEqual(ctx.exo, "full")
        self.assertIsNotNone(ctx.droit_transcription_path)
        self.assertIsNotNone(ctx.droit_fiche_path)
        self.assertTrue(any(
            p.name == "methodo_dissertation.md" for p in ctx.droit_methodo_paths
        ))
        self.assertIsNone(ctx.enonce_path)
        self.assertEqual(ctx.correction_paths, [])
class TestBuildSessionIdDroit(unittest.TestCase):
    def test_droit_session_id_format(self):
        import app
        from prompt_builder import SessionContext
        ctx = SessionContext(
            matiere="droit-personnes", type="CM", num="3", exo="full",
            droit_source="droit-personnes",
        )
        sid = app._build_session_id(
            ctx, mode="colle", colle_format="mixte", corrige_anchor="aucun"
        )
        self.assertTrue(
            sid.endswith("_DROIT_droit-personnes_CM3_full_colle_mixte_aucun"),
            sid,
        )
if __name__ == "__main__":
    unittest.main(verbosity=2)