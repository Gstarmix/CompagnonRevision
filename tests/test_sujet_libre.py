import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "_scripts"
for _p in (
    str(ROOT), str(SCRIPTS),
    str(SCRIPTS / "dialogue"),
    str(SCRIPTS / "audio"),
    str(SCRIPTS / "quota"),
    str(SCRIPTS / "web"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from prompt_builder import (
    PromptBuilder, SessionContext, slugify_topic,
)
class TestSlugifyTopic(unittest.TestCase):
    def test_simple_python(self):
        self.assertIn("python", slugify_topic("apprendre python"))
    def test_strip_stop_words(self):
        slug = slugify_topic("je veux apprendre python")
        self.assertIn("python", slug)
        self.assertNotIn("je", slug.split("-"))
    def test_accents_stripped(self):
        slug = slugify_topic("Le théorème de Bayes en probabilité")
        self.assertIn("theoreme", slug)
        self.assertIn("bayes", slug)
        self.assertNotIn("é", slug)
        self.assertNotIn("ô", slug)
    def test_special_chars_replaced(self):
        slug = slugify_topic("Math/Stats : inférentielles !")
        self.assertNotIn("/", slug)
        self.assertNotIn(":", slug)
        self.assertNotIn("!", slug)
        self.assertIn("math", slug)
        self.assertIn("stats", slug)
    def test_empty_falls_back(self):
        self.assertEqual(slugify_topic(""), "libre")
        self.assertEqual(slugify_topic("   "), "libre")
    def test_length_capped(self):
        long = "j'aimerais devenir un expert en intelligence artificielle générative et raisonnement causal pour applications médicales"
        slug = slugify_topic(long, max_len=30)
        self.assertLessEqual(len(slug), 30)
        self.assertTrue(slug)
class TestPromptBuilderSujetLibre(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        tmp_path = Path(self.tmp.name)
        self.prompt_path = tmp_path / "PROMPT_DECOUVERTE.md"
        self.prompt_path.write_text("dummy", encoding="utf-8")
        self.cours_root = tmp_path / "COURS"
        self.cours_root.mkdir()
        self.builder = PromptBuilder(self.prompt_path, self.cours_root)
    def tearDown(self):
        self.tmp.cleanup()
    def _make_libre_ctx(self, sujet="je veux apprendre python"):
        return SessionContext(
            matiere="LIBRE", type="SUJET", num="python", exo="full",
            sujet_libre=sujet,
        )
    def test_marker_sujet_libre_injecte(self):
        ctx = self._make_libre_ctx()
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte",
        )
        self.assertIn("[SUJET LIBRE]", msg)
        self.assertIn("=== SUJET LIBRE", msg)
        self.assertIn("apprendre python", msg)
    def test_no_materiel_cours_message(self):
        ctx = self._make_libre_ctx()
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte",
        )
        self.assertIn("Aucun matériel COURS", msg)
        self.assertIn("connaissances LLM", msg)
    def test_no_corrige_section_when_libre(self):
        ctx = self._make_libre_ctx()
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte",
        )
        self.assertNotIn("=== CORRIGÉ OFFICIEL ===", msg)
    def test_decouverte_instructions_cadrage_1er_tour(self):
        ctx = self._make_libre_ctx()
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte",
        )
        self.assertIn("cadrage", msg.lower())
        self.assertIn("Niveau actuel", msg)
        self.assertIn("Objectif", msg)
    def test_colle_libre_instructions(self):
        ctx = self._make_libre_ctx()
        msg = self.builder.build_initial_context_message(
            ctx, mode="colle", corrige_anchor="aucun",
        )
        self.assertIn("SUJET LIBRE", msg)
        self.assertIn("posture colle", msg)
        self.assertNotIn("[MODE : découverte]", msg)
class TestApiStartSessionSujetLibre(unittest.TestCase):
    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
    def test_mode_guide_refuse_en_libre(self):
        body = {
            "sujet_libre": "apprendre Python",
            "mode": "guidé",
        }
        with patch.object(self.app_module, "_state", None):
            r = self.client.post("/api/start_session", json=body)
        self.assertEqual(r.status_code, 400)
        self.assertIn("guidé", r.get_json()["error"])
        self.assertIn("sujet libre", r.get_json()["error"])
    def test_session_id_libre_format(self):
        from app import _build_session_id
        ctx = SessionContext(
            matiere="LIBRE", type="SUJET", num="python", exo="full",
            sujet_libre="apprendre Python",
        )
        sid = _build_session_id(ctx)
        self.assertIn("_LIBRE_python_full", sid)
    def test_session_id_classique_inchange(self):
        from app import _build_session_id
        ctx = SessionContext(
            matiere="AN1", type="TD", num="5", exo="3",
        )
        sid = _build_session_id(ctx)
        self.assertIn("_AN1_TD5_ex3", sid)
    def test_build_context_libre_sentinelles(self):
        from app import _build_session_context
        ctx = _build_session_context({
            "sujet_libre": "je veux apprendre python",
        })
        self.assertEqual(ctx.matiere, "LIBRE")
        self.assertEqual(ctx.type, "SUJET")
        self.assertIn("python", ctx.num)
        self.assertEqual(ctx.exo, "full")
        self.assertEqual(ctx.sujet_libre, "je veux apprendre python")
        self.assertIsNone(ctx.enonce_path)
        self.assertEqual(ctx.correction_paths, [])
        self.assertIsNone(ctx.script_oral_path)
if __name__ == "__main__":
    unittest.main(verbosity=2)