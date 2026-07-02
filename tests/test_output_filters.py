"""
test_output_filters.py : couvre les 3 filtres anti-dérive du tuteur
(Phase A.7.2 v15).

Lance :
    python -m unittest tests.test_output_filters
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIALOGUE_DIR = ROOT / "_scripts" / "dialogue"
for _p in (str(ROOT), str(DIALOGUE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from output_filters import (  # noqa: E402
    apply_all_filters,
    has_pending_question,
    strip_hallucinated_ocr_block,
    strip_misplaced_next_slide,
    strip_next_slide_if_pending_question,
    strip_recited_rules,
    strip_role_hijacking,
)


# ============================================================ strip_role_hijacking

class TestStripRoleHijacking(unittest.TestCase):

    def test_no_hijack_returns_text_unchanged(self):
        text = "Bon résumé. Vous avez bien intégré la table de vérité."
        out, n = strip_role_hijacking(text)
        self.assertEqual(out, text)
        self.assertEqual(n, 0)

    def test_word_user_in_normal_sentence_is_kept(self):
        # « user » dans une phrase normale ne doit PAS être détecté
        text = "Le user pose une question importante sur l'API."
        out, n = strip_role_hijacking(text)
        self.assertEqual(out, text)
        self.assertEqual(n, 0)

    def test_user_prefix_removes_line(self):
        text = "Bon résumé.\nUSER: OK je continue\nLa suite normale."
        out, n = strip_role_hijacking(text)
        self.assertEqual(n, 1)
        self.assertNotIn("USER:", out)
        self.assertIn("Bon résumé", out)
        self.assertIn("La suite normale", out)

    def test_assistant_prefix_removes_line(self):
        text = "Réponse normale.\nASSISTANT: voilà ce que je dis"
        out, n = strip_role_hijacking(text)
        self.assertEqual(n, 1)
        self.assertNotIn("ASSISTANT:", out)

    def test_full_dialog_simulation_removed(self):
        text = (
            "Allez-y, lisez la slide.\n"
            "USER: OK on attaque la slide 2.\n"
            "ASSISTANT: Allez-y, je vous écoute.\n"
            "USER: voici ma réponse\n"
            "Suite légitime."
        )
        out, n = strip_role_hijacking(text)
        self.assertEqual(n, 3)
        self.assertNotIn("USER:", out)
        self.assertNotIn("ASSISTANT:", out)
        self.assertIn("Allez-y, lisez la slide", out)
        self.assertIn("Suite légitime", out)

    def test_french_role_prefixes_removed(self):
        text = "Réponse.\nÉTUDIANT: ma question\nTUTEUR: ma réponse"
        out, n = strip_role_hijacking(text)
        self.assertEqual(n, 2)

    def test_case_insensitive(self):
        text = "Bonjour.\nuser: minuscule\nAssistant: mixed"
        out, n = strip_role_hijacking(text)
        self.assertEqual(n, 2)

    def test_empty_string(self):
        out, n = strip_role_hijacking("")
        self.assertEqual(out, "")
        self.assertEqual(n, 0)

    def test_inline_with_markdown_bold_caught(self):
        # Cas réel observé en session : tuteur écrit
        # « ... allez voir slide 2. **USER: Slide 2. ASSISTANT: ...** »
        text = (
            "Bon démarrage. Allez voir la slide 2. "
            "**USER: Slide 2. ASSISTANT: blablah**"
        )
        out, n = strip_role_hijacking(text)
        self.assertGreater(n, 0)
        self.assertNotIn("USER:", out)
        self.assertNotIn("ASSISTANT:", out)
        self.assertIn("Bon démarrage", out)
        self.assertNotIn("**", out)  # le ** orphelin retiré aussi

    def test_inline_no_markdown_caught(self):
        # Inline sans markdown bold mais avec ponctuation devant
        text = "Allez-y, lisez. USER: ma question ASSISTANT: ma réponse"
        out, n = strip_role_hijacking(text)
        self.assertGreater(n, 0)
        self.assertNotIn("USER:", out)
        self.assertIn("Allez-y, lisez", out)

    def test_word_boundary_protects_legit_words(self):
        # « POSEUR: », « DOSSIER: » ne doivent pas matcher (lettres avant)
        # même si elles contiennent un préfixe rôle en suffixe.
        text = "Voici le DOSSIER: complet. Le POSEUR: a fini."
        out, n = strip_role_hijacking(text)
        self.assertEqual(n, 0)
        self.assertEqual(out, text)


# ============================================================ strip_recited_rules

class TestStripRecitedRules(unittest.TestCase):

    def test_no_recitation_returns_unchanged(self):
        text = "Bon résumé. La slide est claire."
        out, n = strip_recited_rules(text)
        self.assertEqual(out, text)
        self.assertEqual(n, 0)

    def test_regle_inviolable_paragraph_removed(self):
        text = (
            "Bon résumé de votre lecture.\n\n"
            "RÈGLE INVIOLABLE : texte vs balise.\n\n"
            "Continuez."
        )
        out, n = strip_recited_rules(text)
        self.assertEqual(n, 1)
        self.assertNotIn("RÈGLE INVIOLABLE", out)
        self.assertIn("Bon résumé", out)
        self.assertIn("Continuez", out)

    def test_note_systeme_paragraph_removed(self):
        text = "Réponse normale.\n\n[Note système : ce message a été édité]"
        out, n = strip_recited_rules(text)
        self.assertEqual(n, 1)
        self.assertNotIn("[Note système", out)

    def test_case_insensitive_match(self):
        text = "Réponse.\n\nrègle inviolable est super importante."
        out, n = strip_recited_rules(text)
        self.assertEqual(n, 1)

    def test_word_inside_legit_paragraph_removes_full_paragraph(self):
        # Effet de bord assumé : si la phrase-signature apparaît au milieu
        # d'un paragraphe légitime, tout le paragraphe est retiré. C'est
        # conservateur mais sûr.
        text = (
            "Premier paragraphe propre.\n\n"
            "Et là je dis « RÈGLE INVIOLABLE » au milieu de ma phrase.\n\n"
            "Troisième paragraphe propre."
        )
        out, n = strip_recited_rules(text)
        self.assertEqual(n, 1)
        self.assertIn("Premier paragraphe propre", out)
        self.assertIn("Troisième paragraphe propre", out)

    def test_empty_string(self):
        out, n = strip_recited_rules("")
        self.assertEqual(out, "")
        self.assertEqual(n, 0)


# ============================================================ strip_misplaced_next_slide

class TestStripMisplacedNextSlide(unittest.TestCase):

    def test_no_balise_unchanged(self):
        text = "Pas de balise dans cette réponse."
        out, n = strip_misplaced_next_slide(text)
        self.assertEqual(out, text)
        self.assertEqual(n, 0)

    def test_balise_at_end_kept(self):
        text = "Bon résumé, on passe à la suivante. <<<NEXT_SLIDE>>>"
        out, n = strip_misplaced_next_slide(text)
        self.assertEqual(out, text)
        self.assertEqual(n, 0)

    def test_balise_at_end_with_trailing_newline_kept(self):
        text = "Réponse.\n<<<NEXT_SLIDE>>>\n"
        out, n = strip_misplaced_next_slide(text)
        self.assertEqual(out, text)  # le whitespace de queue est OK
        self.assertEqual(n, 0)

    def test_single_balise_in_middle_removed(self):
        text = "Je vais émettre <<<NEXT_SLIDE>>> pour passer à la suite."
        out, n = strip_misplaced_next_slide(text)
        self.assertEqual(n, 1)
        self.assertNotIn("<<<NEXT_SLIDE>>>", out)

    def test_multiple_balises_keep_last_if_at_end(self):
        text = (
            "OK <<<NEXT_SLIDE>>> milieu de phrase, "
            "puis je dis <<<NEXT_SLIDE>>> encore. "
            "Vraie fin <<<NEXT_SLIDE>>>"
        )
        out, n = strip_misplaced_next_slide(text)
        self.assertEqual(n, 2)
        self.assertEqual(out.count("<<<NEXT_SLIDE>>>"), 1)
        self.assertTrue(out.rstrip().endswith("<<<NEXT_SLIDE>>>"))

    def test_multiple_balises_none_at_end_all_removed(self):
        text = "OK <<<NEXT_SLIDE>>> milieu, encore <<<NEXT_SLIDE>>> et fin."
        out, n = strip_misplaced_next_slide(text)
        self.assertEqual(n, 2)
        self.assertNotIn("<<<NEXT_SLIDE>>>", out)


# ============================================================ apply_all_filters

class TestApplyAllFilters(unittest.TestCase):

    def test_clean_text_passes_through(self):
        text = "Réponse propre du tuteur."
        out, stats = apply_all_filters(text)
        self.assertEqual(out, text)
        self.assertFalse(stats["any_filtered"])

    def test_capitalize_first_letter_after_filter(self):
        # Si le filtre a coupé un préfixe USER: et laisse une suite avec
        # une minuscule en début, on doit capitaliser cosmétiquement.
        from output_filters import apply_all_filters
        text = "USER: ma question\nnouvelle slide à l'écran. Allez-y."
        out, stats = apply_all_filters(text)
        self.assertTrue(stats["any_filtered"])
        # Le résultat ne doit pas commencer par minuscule
        first_alpha = next((c for c in out if c.isalpha()), "")
        if first_alpha:
            self.assertTrue(
                first_alpha.isupper(),
                f"Première lettre devrait être majuscule, got {first_alpha!r}",
            )

    def test_no_capitalize_if_no_filter(self):
        # Si pas de filtrage, on ne touche pas au texte (le tuteur peut
        # légitimement commencer par une minuscule, ex: équation « f(x) = »).
        from output_filters import apply_all_filters
        text = "f(x) = 2x + 1 dans cette slide."
        out, stats = apply_all_filters(text)
        self.assertFalse(stats["any_filtered"])
        self.assertEqual(out, text)

    def test_cumulated_dérives(self):
        # Utilise des paragraphes (\n\n) bien séparés pour que les 3
        # filtres puissent agir indépendamment sans s'entremanger.
        text = (
            "Bon résumé sur la slide.\n"
            "USER: OK on continue.\n"
            "ASSISTANT: bien noté.\n"
            "\n"
            "Paragraphe propre du tuteur.\n"
            "\n"
            "Je vais émettre <<<NEXT_SLIDE>>> ici dans le texte.\n"
            "\n"
            "Réponse finale. <<<NEXT_SLIDE>>>"
        )
        out, stats = apply_all_filters(text)
        self.assertTrue(stats["any_filtered"])
        self.assertGreaterEqual(stats["role_hijacking_lines_removed"], 2)
        self.assertGreaterEqual(stats["misplaced_next_slide_removed"], 1)
        self.assertNotIn("USER:", out)
        self.assertNotIn("ASSISTANT:", out)
        self.assertIn("Bon résumé", out)
        self.assertIn("Paragraphe propre", out)
        self.assertTrue(out.rstrip().endswith("<<<NEXT_SLIDE>>>"))
        # 1 seule balise NEXT_SLIDE en queue (les autres retirées)
        self.assertEqual(out.count("<<<NEXT_SLIDE>>>"), 1)


# ============================================================ has_pending_question + strip_next_slide_if_pending_question

class TestPendingQuestion(unittest.TestCase):

    def test_text_without_question_returns_false(self):
        self.assertFalse(has_pending_question("Bon résumé. Vous avez tout."))

    def test_text_ending_with_question_returns_true(self):
        self.assertTrue(has_pending_question("Vous me les énumérez ?"))

    def test_question_before_next_slide_tag_still_detected(self):
        # Le tuteur écrit une question PUIS la balise NEXT_SLIDE → la
        # question est en queue avant la balise → flagged.
        text = "Vous me les énumérez ? <<<NEXT_SLIDE>>>"
        self.assertTrue(has_pending_question(text))

    def test_empty_text(self):
        self.assertFalse(has_pending_question(""))

    def test_strip_next_slide_when_question_present(self):
        text = "Bon résumé. Vous me les énumérez ? <<<NEXT_SLIDE>>>"
        out, n = strip_next_slide_if_pending_question(text)
        self.assertEqual(n, 1)
        self.assertNotIn("<<<NEXT_SLIDE>>>", out)
        self.assertTrue(out.endswith("?"))

    def test_strip_next_slide_no_question_no_op(self):
        text = "Bon résumé. <<<NEXT_SLIDE>>>"
        out, n = strip_next_slide_if_pending_question(text)
        self.assertEqual(n, 0)
        self.assertEqual(out, text)

    def test_strip_next_slide_no_tag_no_op(self):
        text = "Vous me les énumérez ?"
        out, n = strip_next_slide_if_pending_question(text)
        self.assertEqual(n, 0)
        self.assertEqual(out, text)


# ============================================================ Phase A.8.4 : strip_hallucinated_ocr_block

class TestStripHallucinatedOcrBlock(unittest.TestCase):
    """Phase A.8.4 : retire le bloc `📸 Ce que je lis dans votre photo :`
    quand user_had_image=False (anti-hallucination)."""

    def test_no_image_in_message_block_removed(self):
        """Sans image attachée, le bloc OCR halluciné est retiré."""
        text = (
            "📸 Ce que je lis dans votre photo :\n\n"
            "> 9. Une fonction qui renvoie un résultat `return`\n"
            "> Une fonction peut calculer un résultat...\n\n"
            "Vérification : C'est correct.\n\n"
            "Continuons. Quelle est la prochaine étape ?"
        )
        out, n = strip_hallucinated_ocr_block(text, user_had_image=False)
        self.assertEqual(n, 1)
        self.assertNotIn("📸", out)
        self.assertNotIn("Vérification", out)
        # La suite légitime est préservée
        self.assertIn("Continuons", out)

    def test_with_image_block_kept(self):
        """Avec image attachée, le bloc OCR est légitime → préservé."""
        text = (
            "📸 Ce que je lis dans votre photo :\n\n"
            "> Mon cahier dit X = 42\n\n"
            "Vérification : OK."
        )
        out, n = strip_hallucinated_ocr_block(text, user_had_image=True)
        self.assertEqual(n, 0)
        self.assertEqual(out, text)

    def test_no_ocr_block_in_text_no_op(self):
        """Pas de bloc OCR du tout → no-op même si user_had_image=False."""
        text = "Bien. Continuons sur la fonction suivante."
        out, n = strip_hallucinated_ocr_block(text, user_had_image=False)
        self.assertEqual(n, 0)
        self.assertEqual(out, text)

    def test_ocr_block_at_start_only(self):
        """Le bloc en début, suivi d'une autre réponse : la réponse est gardée."""
        text = (
            "📸 Ce que je lis dans votre photo :\n"
            "> contenu inventé\n\n"
            "Maintenant ma vraie question."
        )
        out, n = strip_hallucinated_ocr_block(text, user_had_image=False)
        self.assertEqual(n, 1)
        self.assertIn("Maintenant ma vraie question", out)

    def test_apply_all_filters_with_user_had_image_default_true(self):
        """Régression : apply_all_filters sans arg explicite garde le bloc."""
        text = (
            "📸 Ce que je lis dans votre photo :\n"
            "> photo réelle\n\n"
            "Vérification : OK."
        )
        out, stats = apply_all_filters(text)  # default user_had_image=True
        self.assertEqual(stats["hallucinated_ocr_block_removed"], 0)
        self.assertIn("📸", out)

    def test_apply_all_filters_with_user_had_image_false(self):
        """apply_all_filters(text, user_had_image=False) retire le bloc."""
        text = (
            "📸 Ce que je lis dans votre photo :\n"
            "> contenu fabriqué\n\n"
            "Vérification : valide.\n\n"
            "La suite légitime."
        )
        out, stats = apply_all_filters(text, user_had_image=False)
        self.assertEqual(stats["hallucinated_ocr_block_removed"], 1)
        self.assertNotIn("📸", out)
        self.assertIn("La suite légitime", out)


if __name__ == "__main__":
    unittest.main()
