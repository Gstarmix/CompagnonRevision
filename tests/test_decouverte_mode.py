import json
import logging
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "_scripts"
DIALOGUE_DIR = SCRIPTS / "dialogue"
for _p in (str(ROOT), str(SCRIPTS), str(DIALOGUE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from claude_client import (
    MODE_COLLE, MODE_DECOUVERTE, MODE_GUIDE, ClaudeClient,
)
from parser import (
    ParserEvent, ParserEventType, ParserState, StreamParser,
)
from prompt_builder import PromptBuilder, SessionContext
class TestModeDecouverteWiring(unittest.TestCase):
    def test_mode_decouverte_accepted(self):
        client = ClaudeClient(
            engine="cli_subscription",
            system_prompt="dummy",
            mode=MODE_DECOUVERTE,
        )
        self.assertEqual(client.mode, MODE_DECOUVERTE)
    def test_mode_invalid_rejected(self):
        with self.assertRaises(ValueError):
            ClaudeClient(
                engine="cli_subscription",
                system_prompt="dummy",
                mode="bidon",
            )
    def test_three_modes_distinct(self):
        self.assertEqual(MODE_COLLE, "colle")
        self.assertEqual(MODE_GUIDE, "guidé")
        self.assertEqual(MODE_DECOUVERTE, "découverte")
        self.assertEqual(len({MODE_COLLE, MODE_GUIDE, MODE_DECOUVERTE}), 3)
class TestPromptBuilderDecouverte(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.prompt_path = self.tmp_path / "PROMPT_DECOUVERTE.md"
        self.prompt_path.write_text(
            "# Prompt découverte\nDummy.\n", encoding="utf-8",
        )
        self.cours_root = self.tmp_path / "COURS"
        self.cours_root.mkdir(parents=True, exist_ok=True)
        self.builder = PromptBuilder(self.prompt_path, self.cours_root)
    def tearDown(self):
        self.tmp.cleanup()
    def _make_ctx(self, with_correction: bool = True) -> SessionContext:
        ctx = SessionContext(
            matiere="PSI",
            type="TP",
            num="Shannon",
            exo="full",
            enonce_path=None,
        )
        if with_correction:
            corr_md = self.cours_root / "fake_correction.md"
            corr_md.write_text("# Corrigé fake\nValeur attendue : 42.", encoding="utf-8")
            ctx.correction_paths = [corr_md]
        return ctx
    def test_corrige_always_injected_in_decouverte_even_aucun(self):
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", corrige_anchor="aucun",
        )
        self.assertIn("CORRIGÉ OFFICIEL", msg)
        self.assertIn("Valeur attendue : 42", msg)
    def test_corrige_skipped_in_colle_aucun(self):
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="colle", corrige_anchor="aucun",
        )
        self.assertNotIn("=== CORRIGÉ OFFICIEL ===", msg)
        self.assertNotIn("Valeur attendue : 42", msg)
    def test_decouverte_instructions_section_present(self):
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", corrige_anchor="strict",
        )
        self.assertIn("Mode découverte", msg)
    def test_decouverte_header_marker(self):
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", corrige_anchor="strict",
        )
        self.assertIn("[MODE : découverte]", msg)
        self.assertIn("[ANCRAGE CORRIGÉ : strict]", msg)
    def test_decouverte_no_format_colle_marker(self):
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", corrige_anchor="strict",
            colle_format="photos",
        )
        self.assertNotIn("[FORMAT COLLE", msg)
    def test_decouverte_anchor_aucun_hint_in_instructions(self):
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", corrige_anchor="aucun",
        )
        self.assertIn("[ANCRAGE CORRIGÉ : aucun]", msg)
    def test_cas_b_marker_when_enonce_present(self):
        ctx = self._make_ctx(with_correction=True)
        enonce_md = self.cours_root / "fake_enonce.md"
        enonce_md.write_text("# Énoncé fake\nFaire ceci.", encoding="utf-8")
        ctx.enonce_path = enonce_md
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", corrige_anchor="strict",
        )
        self.assertIn("[MATÉRIEL APPLIQUÉ", msg)
        self.assertIn("cas B", msg)
        self.assertIn("bottom-up", msg)
    def test_cas_a_default_when_no_material(self):
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", corrige_anchor="strict",
        )
        self.assertNotIn("[MATÉRIEL APPLIQUÉ", msg)
        self.assertIn("cas A", msg)
    def test_cas_b_marker_when_script_present(self):
        ctx = self._make_ctx(with_correction=True)
        script_md = self.cours_root / "fake_script.md"
        script_md.write_text("Script perso de l'étudiant.", encoding="utf-8")
        ctx.script_oral_path = script_md
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", corrige_anchor="strict",
        )
        self.assertIn("[MATÉRIEL APPLIQUÉ", msg)
        self.assertIn("script oral", msg)
    def test_format_pedagogique_marker_default_mixte(self):
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte",
        )
        self.assertIn("[FORMAT PÉDAGOGIQUE : mixte]", msg)
        self.assertNotIn("[FORMAT COLLE", msg)
    def test_format_pedagogique_marker_photos(self):
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", colle_format="photos",
        )
        self.assertIn("[FORMAT PÉDAGOGIQUE : photos]", msg)
    def test_format_pedagogique_marker_oral(self):
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", colle_format="oral",
        )
        self.assertIn("[FORMAT PÉDAGOGIQUE : oral]", msg)
    def test_format_pedagogique_invalid_falls_back_to_mixte(self):
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", colle_format="bidon",
        )
        self.assertIn("[FORMAT PÉDAGOGIQUE : mixte]", msg)
    def test_format_colle_marker_only_in_colle_mode(self):
        ctx = self._make_ctx(with_correction=True)
        msg_colle = self.builder.build_initial_context_message(
            ctx, mode="colle", colle_format="photos",
        )
        self.assertIn("[FORMAT COLLE : photos]", msg_colle)
        self.assertNotIn("[FORMAT PÉDAGOGIQUE", msg_colle)
    def test_no_format_marker_in_guide_mode(self):
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="guidé", colle_format="photos",
        )
        self.assertNotIn("[FORMAT COLLE", msg)
        self.assertNotIn("[FORMAT PÉDAGOGIQUE", msg)
if __name__ == "__main__":
    unittest.main(verbosity=2)