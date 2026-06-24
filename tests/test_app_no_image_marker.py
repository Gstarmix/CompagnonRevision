import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
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
class TestHasImageMarkdownRegex(unittest.TestCase):
    def test_image_markdown_matches(self):
        from app import _HAS_IMAGE_MARKDOWN_RE
        self.assertTrue(_HAS_IMAGE_MARKDOWN_RE.search(
            "Voilà ma photo ![cahier.jpg](path/to/cahier.jpg)"
        ))
        self.assertTrue(_HAS_IMAGE_MARKDOWN_RE.search(
            "![photo](AN1/TD/photo.png)"
        ))
    def test_no_image_returns_no_match(self):
        from app import _HAS_IMAGE_MARKDOWN_RE
        self.assertIsNone(_HAS_IMAGE_MARKDOWN_RE.search(
            "Juste du texte sans image"
        ))
        self.assertIsNone(_HAS_IMAGE_MARKDOWN_RE.search(
            "On parle d'images en général mais sans markdown"
        ))
        self.assertIsNone(_HAS_IMAGE_MARKDOWN_RE.search(
            "[lien](https://example.com)"
        ))
    def test_multiline_with_image(self):
        from app import _HAS_IMAGE_MARKDOWN_RE
        text = (
            "Voilà ma dictée :\n"
            "Je note ceci, je note cela.\n"
            "![cahier.jpg](pending/cahier_v1.jpg)"
        )
        self.assertTrue(_HAS_IMAGE_MARKDOWN_RE.search(text))
class TestStreamResponseNoImageMarker(unittest.TestCase):
    def test_companion_session_has_last_user_had_image_attr(self):
        from app import CompanionSession
        fake_state = MagicMock()
        fake_client = MagicMock()
        fake_builder = MagicMock()
        cs = CompanionSession(fake_state, fake_client, fake_builder)
        self.assertFalse(cs.last_user_had_image)
    def test_apply_all_filters_propagates_user_had_image(self):
        from output_filters import apply_all_filters
        text = (
            "📸 Ce que je lis dans votre photo :\n"
            "> Une fonction qui renvoie un résultat `return`\n"
            "\n"
            "Vérification : c'est correct.\n"
            "\n"
            "Continuons sur l'étape suivante."
        )
        out, stats = apply_all_filters(text, user_had_image=False)
        self.assertEqual(stats["hallucinated_ocr_block_removed"], 1)
        self.assertNotIn("📸", out)
        self.assertNotIn("Vérification", out)
        self.assertIn("Continuons", out)
class TestPromptDoctrineNoImage(unittest.TestCase):
    def setUp(self):
        from config import PROMPT_SYSTEME_PATH
        self.prompt_text = PROMPT_SYSTEME_PATH.read_text(encoding="utf-8")
    def test_marker_aucune_image_mentioned(self):
        self.assertIn("[AUCUNE IMAGE DANS CE MESSAGE]", self.prompt_text)
    def test_regle_absolue_pas_de_photo_pas_de_bloc(self):
        self.assertIn("interdit absolu", self.prompt_text.lower())
        self.assertIn("photo manquante", self.prompt_text.lower())
if __name__ == "__main__":
    unittest.main(verbosity=2)