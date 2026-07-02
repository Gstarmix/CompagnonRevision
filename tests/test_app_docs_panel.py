"""
test_app_docs_panel.py (Phase A.8).

Vérifie l'extension du panneau Docs côté /api/corrections/init :
- slides PDF exposées (bugfix : avant Phase A.8 elles n'étaient que dans
  le panneau guidé, donc invisibles en mode colle/découverte)
- énoncé inventé du mode découverte exposé en tête de liste
- _kindLabelFr backend a un mapping cohérent pour slides + enonce_invente

Pattern d'isolation via MagicMock sur _state (cf. test_app_corrige_anchor.py).
"""

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
    """Construit un faux CompanionSession minimal pour /api/corrections/init."""
    fake = MagicMock()
    fake.session_state = MagicMock()
    ctx = MagicMock()
    ctx.matiere = "PSI"
    ctx.type = "_revision_CC2"
    ctx.num = "TP_Shannon"
    ctx.exo = "full"
    ctx.annee = None
    fake.session_state.context = ctx
    # Phase A.8 : session_state.data exposé pour invented_enonce_path
    fake.session_state.data = {}
    if invented_path:
        fake.session_state.data["invented_enonce_path"] = invented_path
    return fake


class TestCorrectionsInitDocs(unittest.TestCase):
    """Phase A.8 : slides + énoncé inventé visibles dans /api/corrections/init."""

    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()

    def test_no_active_session_returns_409(self):
        """Régression : sans session active, /api/corrections/init = 409."""
        with patch.object(self.app_module, "_state", None):
            r = self.client.get("/api/corrections/init")
        self.assertEqual(r.status_code, 409)

    # Phase A.10.13a : test_invented_enonce_path_remonte_en_tete supprimé
    # (mode invented PDF retiré).

    def test_slides_exposees_quand_dispo(self):
        """Phase A.8 : slides PDF visibles dans /api/corrections/init.

        Bugfix : avant Phase A.8, find_perso_slides_pdf n'était PAS appelé
        dans /api/corrections/init (seulement dans le panneau guidé), donc
        pour les types libres sans script_imprimable.pdf (cas TP_Shannon),
        le panneau Docs était vide alors qu'un slides_TP_Shannon.pdf existait.
        """
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
