"""
test_decouverte_mode.py (Phase A.8).

Vérifie le câblage du mode Découverte :
- claude_client.MODE_DECOUVERTE accepté
- prompt_builder injecte le corrigé même en ancrage `aucun` (pour le PDF)
- prompt_builder injecte la section MODE/INSTRUCTIONS spécifique découverte
- parser reconnaît la balise <<<SAVE_INVENTED_PDF>>>
"""

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

from claude_client import (  # noqa: E402
    MODE_COLLE, MODE_DECOUVERTE, MODE_GUIDE, ClaudeClient,
)
from parser import (  # noqa: E402
    ParserEvent, ParserEventType, ParserState, StreamParser,
)
from prompt_builder import PromptBuilder, SessionContext  # noqa: E402


class TestModeDecouverteWiring(unittest.TestCase):
    """Phase A.8 : câblage du mode Découverte côté ClaudeClient."""

    def test_mode_decouverte_accepted(self):
        """MODE_DECOUVERTE est accepté par ClaudeClient (pas de ValueError)."""
        client = ClaudeClient(
            engine="cli_subscription",
            system_prompt="dummy",
            mode=MODE_DECOUVERTE,
        )
        self.assertEqual(client.mode, MODE_DECOUVERTE)

    def test_mode_invalid_rejected(self):
        """Un mode inconnu est toujours rejeté."""
        with self.assertRaises(ValueError):
            ClaudeClient(
                engine="cli_subscription",
                system_prompt="dummy",
                mode="bidon",
            )

    def test_three_modes_distinct(self):
        """Les 3 modes ont des constantes distinctes (pas de typo)."""
        self.assertEqual(MODE_COLLE, "colle")
        self.assertEqual(MODE_GUIDE, "guidé")
        self.assertEqual(MODE_DECOUVERTE, "découverte")
        self.assertEqual(len({MODE_COLLE, MODE_GUIDE, MODE_DECOUVERTE}), 3)


class TestPromptBuilderDecouverte(unittest.TestCase):
    """Phase A.8 : prompt_builder.build_initial_context_message en mode découverte."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        # Faux prompt système découverte
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
            # On crée un faux PDF avec extension .md (le _extract_pdf_text
            # supporte .md directement, pas besoin de vrai PDF).
            corr_md = self.cours_root / "fake_correction.md"
            corr_md.write_text("# Corrigé fake\nValeur attendue : 42.", encoding="utf-8")
            ctx.correction_paths = [corr_md]
        return ctx

    def test_corrige_always_injected_in_decouverte_even_aucun(self):
        """Mode découverte : corrigé injecté même quand ancrage = 'aucun'.

        Justification : le tuteur découverte a besoin du corrigé pour
        pondre l'énoncé inventé avec un niveau calibré. Le mode `aucun`
        cache normalement le corrigé en mode colle, mais en découverte
        c'est levé (cf. §1.4 du prompt DECOUVERTE).
        """
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", corrige_anchor="aucun",
        )
        # Le bloc CORRIGÉ OFFICIEL DOIT être présent
        self.assertIn("CORRIGÉ OFFICIEL", msg)
        self.assertIn("Valeur attendue : 42", msg)

    def test_corrige_skipped_in_colle_aucun(self):
        """Sanity check : en mode colle + aucun, le BLOC corrigé est skip (régression).

        On vérifie l'absence du header de section ``=== CORRIGÉ OFFICIEL ===``,
        pas juste la chaîne 'CORRIGÉ OFFICIEL' qui peut apparaître par ailleurs
        (instructions « Mode révision sans énoncé » la liste comme ressource).
        """
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="colle", corrige_anchor="aucun",
        )
        self.assertNotIn("=== CORRIGÉ OFFICIEL ===", msg)
        # Et le contenu du corrigé n'est pas non plus extrait
        self.assertNotIn("Valeur attendue : 42", msg)

    def test_decouverte_instructions_section_present(self):
        """Mode découverte : la section INSTRUCTIONS annonce le mode."""
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", corrige_anchor="strict",
        )
        # Phase A.10.13a : la balise SAVE_INVENTED_PDF n'est plus utilisée.
        # Le mode découverte fonctionne sans PDF inventé (le tuteur improvise
        # les questions en conversation, plus efficace).
        self.assertIn("Mode découverte", msg)

    def test_decouverte_header_marker(self):
        """Mode découverte : le header inclut [MODE : découverte]."""
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", corrige_anchor="strict",
        )
        self.assertIn("[MODE : découverte]", msg)
        self.assertIn("[ANCRAGE CORRIGÉ : strict]", msg)

    def test_decouverte_no_format_colle_marker(self):
        """Mode découverte : pas de [FORMAT COLLE : ...] (réservé au mode colle)."""
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", corrige_anchor="strict",
            colle_format="photos",
        )
        self.assertNotIn("[FORMAT COLLE", msg)

    def test_decouverte_anchor_aucun_hint_in_instructions(self):
        """En ancrage 'aucun', les instructions le rappellent au tuteur.

        Phase A.10.13a : le hint « sans corrigé » est désormais
        injecté seulement quand le contexte le justifie (via header
        ou message anchor). Test assoupli : pas de regression.
        """
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", corrige_anchor="aucun",
        )
        self.assertIn("[ANCRAGE CORRIGÉ : aucun]", msg)

    # Phase A.8.1 : cas A (PDF inventé) vs cas B (matériel existant)

    def test_cas_b_marker_when_enonce_present(self):
        """Si enonce_path est set, [MATÉRIEL APPLIQUÉ : ...] est injecté
        et la section INSTRUCTIONS bascule en cas B (posture bottom-up).
        """
        ctx = self._make_ctx(with_correction=True)
        # Simule un énoncé présent
        enonce_md = self.cours_root / "fake_enonce.md"
        enonce_md.write_text("# Énoncé fake\nFaire ceci.", encoding="utf-8")
        ctx.enonce_path = enonce_md
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", corrige_anchor="strict",
        )
        self.assertIn("[MATÉRIEL APPLIQUÉ", msg)
        self.assertIn("cas B", msg)
        # Posture bottom-up mentionnée
        self.assertIn("bottom-up", msg)

    def test_cas_a_default_when_no_material(self):
        """Sans énoncé/script/slides, pas de marker MATÉRIEL APPLIQUÉ :
        cas A actif (le tuteur invente les questions en conversation).
        """
        ctx = self._make_ctx(with_correction=True)
        # ctx par défaut n'a pas d'énoncé/script/slides
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", corrige_anchor="strict",
        )
        self.assertNotIn("[MATÉRIEL APPLIQUÉ", msg)
        self.assertIn("cas A", msg)
        # Phase A.10.13a : plus de SAVE_INVENTED_PDF. Le tuteur invente
        # ses questions au fil de la conversation, pas en PDF figé.

    def test_cas_b_marker_when_script_present(self):
        """Si script_oral_path est set (sans énoncé), cas B aussi."""
        ctx = self._make_ctx(with_correction=True)
        script_md = self.cours_root / "fake_script.md"
        script_md.write_text("Script perso de l'étudiant.", encoding="utf-8")
        ctx.script_oral_path = script_md
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", corrige_anchor="strict",
        )
        self.assertIn("[MATÉRIEL APPLIQUÉ", msg)
        self.assertIn("script oral", msg)

    # Phase A.8.2 : [FORMAT PÉDAGOGIQUE : ...] en mode découverte

    def test_format_pedagogique_marker_default_mixte(self):
        """Mode découverte injecte [FORMAT PÉDAGOGIQUE : mixte] par défaut.

        Distinct du [FORMAT COLLE : ...] du mode colle (postures
        différentes : ancrage mnémonique vs gestion objets structurés).
        """
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte",
        )
        self.assertIn("[FORMAT PÉDAGOGIQUE : mixte]", msg)
        # Ne doit PAS contenir [FORMAT COLLE : ...] (réservé au mode colle)
        self.assertNotIn("[FORMAT COLLE", msg)

    def test_format_pedagogique_marker_photos(self):
        """colle_format='photos' → [FORMAT PÉDAGOGIQUE : photos]."""
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", colle_format="photos",
        )
        self.assertIn("[FORMAT PÉDAGOGIQUE : photos]", msg)

    def test_format_pedagogique_marker_oral(self):
        """colle_format='oral' → [FORMAT PÉDAGOGIQUE : oral]."""
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", colle_format="oral",
        )
        self.assertIn("[FORMAT PÉDAGOGIQUE : oral]", msg)

    def test_format_pedagogique_invalid_falls_back_to_mixte(self):
        """colle_format invalide → fallback mixte (cf. _normalize_colle_format)."""
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="découverte", colle_format="bidon",
        )
        self.assertIn("[FORMAT PÉDAGOGIQUE : mixte]", msg)

    def test_format_colle_marker_only_in_colle_mode(self):
        """Le marker [FORMAT COLLE : ...] reste réservé au mode colle.

        Régression : on s'assure qu'on ne casse pas l'existant.
        """
        ctx = self._make_ctx(with_correction=True)
        msg_colle = self.builder.build_initial_context_message(
            ctx, mode="colle", colle_format="photos",
        )
        self.assertIn("[FORMAT COLLE : photos]", msg_colle)
        self.assertNotIn("[FORMAT PÉDAGOGIQUE", msg_colle)

    def test_no_format_marker_in_guide_mode(self):
        """Mode guidé : ni [FORMAT COLLE] ni [FORMAT PÉDAGOGIQUE] injecté."""
        ctx = self._make_ctx(with_correction=True)
        msg = self.builder.build_initial_context_message(
            ctx, mode="guidé", colle_format="photos",
        )
        self.assertNotIn("[FORMAT COLLE", msg)
        self.assertNotIn("[FORMAT PÉDAGOGIQUE", msg)


# Phase A.10.13a (2026-05-14) : TestParserSaveInventedPdf supprimée.
# Le mode invented PDF a été retiré (cf. CHANGELOG A.10.13a). User :
# « le mode qui créé des énoncés ça sert à rien car vaut mieux que
# compagnon créé en fonction de la personne ».


if __name__ == "__main__":
    unittest.main(verbosity=2)
