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
def _make_fake_state(invented_path=None):
    fake = MagicMock()
    fake.session_state = MagicMock()
    ctx = MagicMock()
    ctx.matiere = "PSI"
    ctx.type = "_revision_CC2"
    ctx.num = "TP_Shannon"
    ctx.exo = "full"
    ctx.annee = None
    fake.session_state.context = ctx
    fake.session_state.data = {}
    if invented_path:
        fake.session_state.data["invented_enonce_path"] = invented_path
    return fake
class TestCorrectionsInitDocs(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
    def test_no_active_session_returns_409(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.get("/api/corrections/init")
        self.assertEqual(r.status_code, 409)
    def test_slides_exposees_quand_dispo(self):
        with TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            from reportlab.pdfgen.canvas import Canvas
            slides_path = tmp_path / "slides_TP_Shannon.pdf"
            c = Canvas(str(slides_path))
            c.drawString(72, 720, "Slide 1")
            c.showPage()
            c.save()
            fake = _make_fake_state()
            with patch.object(self.app_module, "_state", fake), \
                 patch.object(self.app_module, "find_enonce_pdf", return_value=None), \
                 patch.object(self.app_module, "resolve_corrections", return_value=[]), \
                 patch.object(self.app_module, "find_perso_script_imprimable", return_value=None), \
                 patch.object(self.app_module, "find_perso_slides_pdf", return_value=slides_path):
                r = self.client.get("/api/corrections/init")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        corrections = data.get("corrections", [])
        kinds = [c["kind"] for c in corrections]
        self.assertIn("slides", kinds)
if __name__ == "__main__":
    unittest.main(verbosity=2)