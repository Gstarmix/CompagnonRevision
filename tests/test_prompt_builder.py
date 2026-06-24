import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "_scripts"
DIALOGUE = SCRIPTS / "dialogue"
for _p in (str(ROOT), str(SCRIPTS), str(DIALOGUE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from prompt_builder import (
    CM_TRANSCRIPTION_WORD_CAP,
    PromptBuilder,
    SessionContext,
)
def make_blank_pdf(path: Path) -> None:
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    with path.open("wb") as f:
        w.write(f)
class TestPromptBuilder(unittest.TestCase):
    def setUp(self):
        self._tmpobj = TemporaryDirectory()
        self.tmp = Path(self._tmpobj.name)
        self.system_prompt = self.tmp / "PROMPT_SYSTEME.md"
        self.system_prompt.write_text(
            "# Prompt système (test fixture)\nTu es prof particulier exigeant.",
            encoding="utf-8",
        )
        self.cours_root = self.tmp / "COURS"
        self.cours_root.mkdir()
        self.builder = PromptBuilder(self.system_prompt, self.cours_root)
        self.enonce = self.tmp / "AN1_TD5_enonce.pdf"
        make_blank_pdf(self.enonce)
    def tearDown(self):
        self._tmpobj.cleanup()
    def _ctx(self, **overrides) -> SessionContext:
        defaults = dict(
            matiere="AN1",
            type="TD",
            num="5",
            exo="3",
            enonce_path=self.enonce,
        )
        defaults.update(overrides)
        return SessionContext(**defaults)
    def test_system_prompt_property_loads_file(self):
        self.assertIn("prof particulier", self.builder.system_prompt)
        with self.assertRaises(AttributeError):
            self.builder.system_prompt = "autre chose"
    def test_minimal_message_only_enonce(self):
        msg = self.builder.build_initial_context_message(self._ctx())
        self.assertIn("=== CONTEXTE DE LA SÉANCE ===", msg)
        self.assertIn("Matière : AN1", msg)
        self.assertIn("Type : TD 5", msg)
        self.assertIn("Exercice ciblé : exercice 3", msg)
        self.assertIn("=== ÉNONCÉ DE L'EXERCICE ===", msg)
        self.assertIn("PDF probablement scanné", msg)
        self.assertNotIn("=== TRANSCRIPTION CM PERTINENTE ===", msg)
        self.assertNotIn("=== POLY DU PROF", msg)
        self.assertNotIn("POINTS FAIBLES HISTORIQUES", msg)
        self.assertIn("=== INSTRUCTIONS ===", msg)
        self.assertIn("Démarre la séance", msg)
        self.assertNotIn("[RESUME_SESSION]", msg)
    def test_exo_full_label(self):
        msg = self.builder.build_initial_context_message(self._ctx(exo="full"))
        self.assertIn("Exercice ciblé : tout le TD/TP", msg)
        self.assertNotIn("exercice full", msg)
    def test_resume_message(self):
        msg = self.builder.build_initial_context_message(
            self._ctx(), is_resume=True
        )
        self.assertTrue(msg.startswith("[RESUME_SESSION]"))
        self.assertIn("Reprends la séance interrompue", msg)
        self.assertNotIn("Démarre la séance", msg)
    def test_cm_transcription_under_cap(self):
        cm = self.tmp / "cm.txt"
        cm.write_text("alpha bêta gamma delta", encoding="utf-8")
        msg = self.builder.build_initial_context_message(
            self._ctx(cm_transcription_path=cm)
        )
        self.assertIn("=== TRANSCRIPTION CM PERTINENTE ===", msg)
        self.assertIn("alpha bêta gamma delta", msg)
        self.assertNotIn("tronqué", msg)
    def test_cm_transcription_over_cap_is_truncated(self):
        cm = self.tmp / "cm_long.txt"
        cm.write_text(" ".join(f"mot{i}" for i in range(CM_TRANSCRIPTION_WORD_CAP + 50)),
                      encoding="utf-8")
        msg = self.builder.build_initial_context_message(
            self._ctx(cm_transcription_path=cm)
        )
        self.assertIn(f"tronqué à {CM_TRANSCRIPTION_WORD_CAP} mots", msg)
        self.assertIn(f"mot{CM_TRANSCRIPTION_WORD_CAP - 1}", msg)
        self.assertNotIn(
            f" mot{CM_TRANSCRIPTION_WORD_CAP + 10} ", msg + " "
        )
    def test_pdf_missing_file_graceful(self):
        ctx = self._ctx(enonce_path=self.tmp / "ghost.pdf")
        msg = self.builder.build_initial_context_message(ctx)
        self.assertIn("PDF introuvable", msg)
    def test_pdf_corrupt_file_graceful(self):
        bogus = self.tmp / "bogus.pdf"
        bogus.write_text("ceci n'est pas un PDF", encoding="utf-8")
        ctx = self._ctx(enonce_path=bogus)
        msg = self.builder.build_initial_context_message(ctx)
        self.assertIn("Extraction PDF échouée", msg)
    def test_session_context_reexport_from_session_state(self):
        from session_state import SessionContext as ContextFromState
        self.assertIs(ContextFromState, SessionContext)
    def test_corrigé_section_inserted_when_correction_paths(self):
        corr = self.tmp / "correction_TD5_ex3_AN1.pdf"
        make_blank_pdf(corr)
        msg = self.builder.build_initial_context_message(
            self._ctx(correction_paths=[corr])
        )
        self.assertIn("=== CORRIGÉ OFFICIEL ===", msg)
        self.assertIn("--- correction_TD5_ex3_AN1.pdf ---", msg)
    def test_corrigé_section_absent_when_no_correction_paths(self):
        msg = self.builder.build_initial_context_message(self._ctx())
        self.assertNotIn("CORRIGÉ OFFICIEL", msg)
    def test_corrigé_section_multi_files(self):
        a = self.tmp / "correction_TD5_ex3_AN1.pdf"
        b = self.tmp / "correction_TD5_ex4_AN1.pdf"
        make_blank_pdf(a)
        make_blank_pdf(b)
        msg = self.builder.build_initial_context_message(
            self._ctx(correction_paths=[a, b])
        )
        self.assertIn("--- correction_TD5_ex3_AN1.pdf ---", msg)
        self.assertIn("--- correction_TD5_ex4_AN1.pdf ---", msg)
    def test_tache_section_inserted(self):
        tache = self.tmp / "TACHE_AN1_TD5_ex3.md"
        tache.write_text("# Ma TACHE\nQuelques notes.", encoding="utf-8")
        msg = self.builder.build_initial_context_message(
            self._ctx(tache_path=tache)
        )
        self.assertIn("=== TACHE PERSO", msg)
        self.assertIn("Quelques notes", msg)
    def test_script_oral_section_inserted(self):
        script = self.tmp / "script_oral.txt"
        script.write_text("Bonjour, je commence par énoncer le théorème...",
                          encoding="utf-8")
        msg = self.builder.build_initial_context_message(
            self._ctx(script_oral_path=script)
        )
        self.assertIn("=== SCRIPT ORAL PERSO (TTS-ready) ===", msg)
        self.assertIn("énoncer le théorème", msg)
    def test_slides_pdf_mention_only(self):
        slides = self.tmp / "slides_AN1_TD5.pdf"
        make_blank_pdf(slides)
        msg = self.builder.build_initial_context_message(
            self._ctx(slides_pdf_path=slides)
        )
        self.assertIn("=== SLIDES PERSO (mention) ===", msg)
        self.assertIn(str(slides), msg)
        self.assertIn("Contenu non extrait", msg)
    def test_perso_text_file_word_cap(self):
        from prompt_builder import PERSO_MATERIAL_WORD_CAP
        big = self.tmp / "big_tache.md"
        big.write_text(
            " ".join(f"mot{i}" for i in range(PERSO_MATERIAL_WORD_CAP + 50)),
            encoding="utf-8",
        )
        msg = self.builder.build_initial_context_message(
            self._ctx(tache_path=big)
        )
        self.assertIn(f"tronqué à {PERSO_MATERIAL_WORD_CAP} mots", msg)
    def test_corrigé_total_char_cap_truncation(self):
        from prompt_builder import CORRECTION_TOTAL_CHAR_CAP
        import prompt_builder as pb
        original_cap = pb.CORRECTION_TOTAL_CHAR_CAP
        try:
            pb.CORRECTION_TOTAL_CHAR_CAP = 100
            corr_a = self.tmp / "correction_a.pdf"
            corr_b = self.tmp / "correction_b.pdf"
            make_blank_pdf(corr_a)
            make_blank_pdf(corr_b)
            msg = self.builder.build_initial_context_message(
                self._ctx(correction_paths=[corr_a, corr_b])
            )
            self.assertIn("corrigés non inclus faute de place", msg)
            self.assertIn("correction_b.pdf", msg)
        finally:
            pb.CORRECTION_TOTAL_CHAR_CAP = original_cap
    def test_annee_field_optional_default_none(self):
        ctx = self._ctx()
        self.assertIsNone(ctx.annee)
        ctx_cc = self._ctx(annee="2025-26", type="CC", num="1", exo="full")
        self.assertEqual(ctx_cc.annee, "2025-26")
    def test_format_colle_default_mixte_when_mode_colle(self):
        msg = self.builder.build_initial_context_message(self._ctx())
        self.assertIn("[FORMAT COLLE : mixte]", msg)
    def test_format_colle_oral_explicit(self):
        msg = self.builder.build_initial_context_message(
            self._ctx(), mode="colle", colle_format="oral",
        )
        self.assertIn("[FORMAT COLLE : oral]", msg)
        self.assertNotIn("[FORMAT COLLE : mixte]", msg)
    def test_format_colle_photos_explicit(self):
        msg = self.builder.build_initial_context_message(
            self._ctx(), mode="colle", colle_format="photos",
        )
        self.assertIn("[FORMAT COLLE : photos]", msg)
    def test_format_colle_invalid_falls_back_to_mixte(self):
        msg = self.builder.build_initial_context_message(
            self._ctx(), mode="colle", colle_format="bidule",
        )
        self.assertIn("[FORMAT COLLE : mixte]", msg)
        self.assertNotIn("[FORMAT COLLE : bidule]", msg)
    def test_format_colle_absent_in_guide_mode(self):
        msg = self.builder.build_initial_context_message(
            self._ctx(), mode="guidé", colle_format="photos",
        )
        self.assertNotIn("[FORMAT COLLE", msg)
    def test_format_colle_normalize_helper(self):
        self.assertEqual(PromptBuilder._normalize_colle_format("ORAL"), "oral")
        self.assertEqual(PromptBuilder._normalize_colle_format("Photos"), "photos")
        self.assertEqual(PromptBuilder._normalize_colle_format("MIXTE"), "mixte")
        self.assertEqual(PromptBuilder._normalize_colle_format(""), "mixte")
        self.assertEqual(PromptBuilder._normalize_colle_format("nimporte"), "mixte")
        self.assertEqual(PromptBuilder._normalize_colle_format(None), "mixte")
    def _make_dummy_correction(self) -> Path:
        path = self.tmp / "correction_TD5_ex3_AN1.pdf"
        make_blank_pdf(path)
        return path
    def test_corrige_anchor_default_strict_when_mode_colle(self):
        msg = self.builder.build_initial_context_message(self._ctx())
        self.assertIn("[ANCRAGE CORRIGÉ : strict]", msg)
    def test_corrige_anchor_consultatif_explicit(self):
        corr = self._make_dummy_correction()
        msg = self.builder.build_initial_context_message(
            self._ctx(correction_paths=[corr]),
            mode="colle", corrige_anchor="consultatif",
        )
        self.assertIn("[ANCRAGE CORRIGÉ : consultatif]", msg)
        self.assertIn("=== CORRIGÉ OFFICIEL ===", msg)
    def test_corrige_anchor_aucun_skips_corrige_block(self):
        corr = self._make_dummy_correction()
        msg = self.builder.build_initial_context_message(
            self._ctx(correction_paths=[corr]),
            mode="colle", corrige_anchor="aucun",
        )
        self.assertIn("[ANCRAGE CORRIGÉ : aucun]", msg)
        self.assertNotIn("=== CORRIGÉ OFFICIEL ===", msg)
        self.assertIn("=== ÉNONCÉ DE L'EXERCICE ===", msg)
    def test_corrige_anchor_invalid_falls_back_to_strict(self):
        msg = self.builder.build_initial_context_message(
            self._ctx(), mode="colle", corrige_anchor="weird",
        )
        self.assertIn("[ANCRAGE CORRIGÉ : strict]", msg)
        self.assertNotIn("[ANCRAGE CORRIGÉ : weird]", msg)
    def test_corrige_anchor_absent_in_guide_mode(self):
        msg = self.builder.build_initial_context_message(
            self._ctx(), mode="guidé", corrige_anchor="consultatif",
        )
        self.assertNotIn("[ANCRAGE CORRIGÉ", msg)
    def test_corrige_anchor_normalize_helper(self):
        self.assertEqual(PromptBuilder._normalize_corrige_anchor("STRICT"), "strict")
        self.assertEqual(PromptBuilder._normalize_corrige_anchor("Consultatif"), "consultatif")
        self.assertEqual(PromptBuilder._normalize_corrige_anchor("AUCUN"), "aucun")
        self.assertEqual(PromptBuilder._normalize_corrige_anchor("sans_corrigé"), "aucun")
        self.assertEqual(PromptBuilder._normalize_corrige_anchor("sans_corrige"), "aucun")
        self.assertEqual(PromptBuilder._normalize_corrige_anchor("sans corrigé"), "aucun")
        self.assertEqual(PromptBuilder._normalize_corrige_anchor(""), "strict")
        self.assertEqual(PromptBuilder._normalize_corrige_anchor("nimporte"), "strict")
        self.assertEqual(PromptBuilder._normalize_corrige_anchor(None), "strict")
    def test_corrige_anchor_strict_keeps_corrige_block(self):
        corr = self._make_dummy_correction()
        msg = self.builder.build_initial_context_message(
            self._ctx(correction_paths=[corr]),
            mode="colle", corrige_anchor="strict",
        )
        self.assertIn("=== CORRIGÉ OFFICIEL ===", msg)
        self.assertIn("[ANCRAGE CORRIGÉ : strict]", msg)
class TestDroitContext(unittest.TestCase):
    def setUp(self):
        self._tmpobj = TemporaryDirectory()
        self.tmp = Path(self._tmpobj.name)
        self.system_prompt = self.tmp / "PROMPT_SYSTEME.md"
        self.system_prompt.write_text("# Prompt test\nColleur exigeant.", encoding="utf-8")
        self.builder = PromptBuilder(self.system_prompt, self.tmp)
        self.transcription = self.tmp / "CM3_droit-personnes_1509.txt"
        self.transcription.write_text(
            "La personnalité juridique commence à la naissance.", encoding="utf-8"
        )
        self.fiche = self.tmp / "fiche_CM3_droit-personnes_1509.md"
        self.fiche.write_text(
            "# Fiche CM3\n- La personne physique acquiert la personnalité à la "
            "naissance vivante et viable.", encoding="utf-8"
        )
    def tearDown(self):
        self._tmpobj.cleanup()
    def _ctx(self, **overrides) -> SessionContext:
        defaults = dict(
            matiere="droit-personnes",
            type="CM",
            num="3",
            exo="full",
            droit_source="droit-personnes",
            droit_transcription_path=self.transcription,
            droit_fiche_path=self.fiche,
        )
        defaults.update(overrides)
        return SessionContext(**defaults)
    def test_droit_injects_transcription_and_fiche(self):
        msg = self.builder.build_initial_context_message(self._ctx())
        self.assertIn("=== TRANSCRIPTION DU COURS ===", msg)
        self.assertIn("personnalité juridique commence", msg)
        self.assertIn("=== FICHE DE RÉVISION ===", msg)
        self.assertIn("naissance vivante et viable", msg)
    def test_droit_has_no_enonce_no_corrige(self):
        msg = self.builder.build_initial_context_message(self._ctx())
        self.assertNotIn("=== ÉNONCÉ DE L'EXERCICE ===", msg)
        self.assertNotIn("=== CORRIGÉ OFFICIEL ===", msg)
        self.assertNotIn("[ANCRAGE CORRIGÉ", msg)
        self.assertIn("[SOURCE : droit]", msg)
        self.assertIn("PAS de corrigé officiel", msg)
    def test_droit_references_listed(self):
        methodo = self.tmp / "methodo_dissertation.md"
        methodo.write_text("# Méthodo dissertation", encoding="utf-8")
        arret = self.tmp / "arret_perruche.md"
        arret.write_text("# Arrêt Perruche", encoding="utf-8")
        msg = self.builder.build_initial_context_message(
            self._ctx(droit_methodo_paths=[methodo], droit_arrets_paths=[arret])
        )
        self.assertIn("=== RÉFÉRENCES DISPONIBLES (méthodo & arrêts) ===", msg)
        self.assertIn("Méthodo : methodo_dissertation.md", msg)
        self.assertIn("Fiche d'arrêt : arret_perruche.md", msg)
    def test_droit_instructions_mode_aware(self):
        colle = self.builder.build_initial_context_message(self._ctx(), mode="colle")
        self.assertIn("Mode colle (droit)", colle)
        deco = self.builder.build_initial_context_message(self._ctx(), mode="découverte")
        self.assertIn("Mode découverte (droit)", deco)
        guide = self.builder.build_initial_context_message(self._ctx(), mode="guidé")
        self.assertIn("Mode guidé (droit)", guide)
    def test_droit_transcription_capped(self):
        long_txt = " ".join(["mot"] * (CM_TRANSCRIPTION_WORD_CAP + 500))
        self.transcription.write_text(long_txt, encoding="utf-8")
        msg = self.builder.build_initial_context_message(self._ctx())
        self.assertIn("[...tronqué", msg)
if __name__ == "__main__":
    unittest.main(verbosity=2)