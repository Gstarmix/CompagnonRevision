"""
test_claude_client_multimodal.py : couverture des helpers multimodaux
Phase v15.7.18 (extraction images Markdown + transformation par moteur).

On teste UNIQUEMENT les 4 helpers module-level (pas l'intégration SDK
qui demande de mocker anthropic / google.genai / openai = trop fragile
pour le ratio bénéfice/coût). Les tests d'intégration multimodaux se
font en runtime via des photos réelles.
"""

import base64
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


def _write_jpeg(path: Path, payload: bytes = b"fake jpeg content") -> None:
    """Crée un fichier JPEG minimal (magic bytes + payload arbitraire)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xd8\xff" + payload)


class TestExtractInlineImages(unittest.TestCase):

    def setUp(self):
        from claude_client import _extract_inline_images
        self.fn = _extract_inline_images
        self._tmpobj = TemporaryDirectory()
        self.cours_root = Path(self._tmpobj.name)
        self.photo_path = self.cours_root / "EN1" / "CC" / "photos" / "test.jpg"
        _write_jpeg(self.photo_path, b"x" * 500)

    def tearDown(self):
        self._tmpobj.cleanup()

    def test_no_image_returns_unchanged(self):
        text = "Voici ma réponse, sans photo."
        new_text, images = self.fn(text, self.cours_root)
        self.assertEqual(new_text, text)
        self.assertEqual(images, [])

    def test_extracts_single_image(self):
        text = "Ma table : ![photo](EN1/CC/photos/test.jpg)"
        new_text, images = self.fn(text, self.cours_root)
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0]["alt"], "photo")
        self.assertEqual(images[0]["media_type"], "image/jpeg")
        # Placeholder dans le texte
        self.assertIn("[image: photo]", new_text)
        self.assertNotIn("![photo]", new_text)
        # Bytes correctement encodés
        decoded = base64.b64decode(images[0]["data_b64"])
        self.assertEqual(decoded, self.photo_path.read_bytes())

    def test_missing_file_silently_skipped(self):
        text = "Ma réponse : ![photo](EN1/CC/photos/inexistante.jpg)"
        new_text, images = self.fn(text, self.cours_root)
        self.assertEqual(images, [])
        self.assertIn("[image introuvable: photo]", new_text)

    def test_unsupported_extension_skipped(self):
        # .raw n'est pas dans _IMAGE_MEDIA_TYPES
        weird = self.cours_root / "test.raw"
        weird.write_bytes(b"raw")
        text = "Voir : ![data](test.raw)"
        new_text, images = self.fn(text, self.cours_root)
        self.assertEqual(images, [])
        self.assertIn("[image non incluse: data]", new_text)

    def test_oversized_image_skipped_with_warning(self):
        # 6 MB > _MAX_IMAGE_BYTES (5 MB)
        big = self.cours_root / "big.jpg"
        _write_jpeg(big, b"y" * (6 * 1024 * 1024))
        text = "Voir : ![big](big.jpg)"
        new_text, images = self.fn(text, self.cours_root)
        self.assertEqual(images, [])
        self.assertIn("[image trop grande: big]", new_text)

    def test_multiple_images_in_one_text(self):
        photo2 = self.cours_root / "EN1" / "CC" / "photos" / "test2.png"
        _write_jpeg(photo2)  # même magic bytes mais on l'appelle .png
        text = ("Texte avant ![p1](EN1/CC/photos/test.jpg) "
                "milieu ![p2](EN1/CC/photos/test2.png) après")
        new_text, images = self.fn(text, self.cours_root)
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0]["alt"], "p1")
        self.assertEqual(images[0]["media_type"], "image/jpeg")
        self.assertEqual(images[1]["alt"], "p2")
        self.assertEqual(images[1]["media_type"], "image/png")
        # Placeholders à la bonne position
        self.assertIn("[image: p1]", new_text)
        self.assertIn("[image: p2]", new_text)

    def test_absolute_path_resolved(self):
        text = f"Voir : ![p](abs)".replace("abs", str(self.photo_path).replace("\\", "/"))
        new_text, images = self.fn(text, None)  # cours_root None ok pour absolus
        self.assertEqual(len(images), 1)


class TestMessagesToAnthropicMultimodal(unittest.TestCase):
    """Phase v15.7.18 : transformation user messages → blocs Anthropic."""

    def setUp(self):
        from claude_client import _messages_to_anthropic_multimodal
        self.fn = _messages_to_anthropic_multimodal
        self._tmpobj = TemporaryDirectory()
        self.cours_root = Path(self._tmpobj.name)
        self.photo = self.cours_root / "photo.jpg"
        _write_jpeg(self.photo, b"z" * 100)

    def tearDown(self):
        self._tmpobj.cleanup()

    def test_text_only_messages_unchanged(self):
        history = [
            {"role": "user", "content": "Bonjour"},
            {"role": "assistant", "content": "Bonsoir"},
        ]
        out = self.fn(history, self.cours_root)
        self.assertEqual(out, history)

    def test_user_message_with_image_becomes_blocks(self):
        history = [
            {"role": "user", "content": "Ma photo : ![p](photo.jpg)"},
        ]
        out = self.fn(history, self.cours_root)
        self.assertEqual(len(out), 1)
        msg = out[0]
        self.assertEqual(msg["role"], "user")
        self.assertIsInstance(msg["content"], list)
        self.assertEqual(msg["content"][0]["type"], "text")
        self.assertEqual(msg["content"][1]["type"], "image")
        self.assertEqual(msg["content"][1]["source"]["type"], "base64")
        self.assertEqual(msg["content"][1]["source"]["media_type"], "image/jpeg")
        self.assertTrue(msg["content"][1]["source"]["data"])

    def test_assistant_message_not_transformed(self):
        # Même si l'assistant cite un markdown image, on ne le transforme pas
        # (Anthropic n'accepte les images que côté user).
        history = [
            {"role": "assistant", "content": "Voir ![tableau](photo.jpg)"},
        ]
        out = self.fn(history, self.cours_root)
        self.assertEqual(out[0]["content"], "Voir ![tableau](photo.jpg)")


class TestMessagesToOpenAIMultimodal(unittest.TestCase):
    """Phase v15.7.18 : transformation user messages → blocs OpenAI-compat."""

    def setUp(self):
        from claude_client import _messages_to_openai_multimodal
        self.fn = _messages_to_openai_multimodal
        self._tmpobj = TemporaryDirectory()
        self.cours_root = Path(self._tmpobj.name)
        self.photo = self.cours_root / "p.jpg"
        _write_jpeg(self.photo, b"q" * 80)

    def tearDown(self):
        self._tmpobj.cleanup()

    def test_image_url_data_uri_format(self):
        history = [
            {"role": "user", "content": "Photo : ![x](p.jpg)"},
        ]
        out = self.fn(history, self.cours_root)
        msg = out[0]
        self.assertIsInstance(msg["content"], list)
        img_block = msg["content"][1]
        self.assertEqual(img_block["type"], "image_url")
        url = img_block["image_url"]["url"]
        self.assertTrue(url.startswith("data:image/jpeg;base64,"))


class TestMessagesToGeminiParts(unittest.TestCase):
    """Phase v15.7.18 : transformation user messages → Gemini parts."""

    def setUp(self):
        from claude_client import _messages_to_gemini_parts
        self.fn = _messages_to_gemini_parts
        self._tmpobj = TemporaryDirectory()
        self.cours_root = Path(self._tmpobj.name)
        self.photo = self.cours_root / "g.jpg"
        _write_jpeg(self.photo, b"w" * 60)

    def tearDown(self):
        self._tmpobj.cleanup()

    def test_assistant_role_translated_to_model(self):
        """Gemini utilise 'model' au lieu de 'assistant'."""
        history = [
            {"role": "user", "content": "Q"},
            {"role": "assistant", "content": "R"},
        ]
        out = self.fn(history, self.cours_root)
        self.assertEqual(out[0]["role"], "user")
        self.assertEqual(out[1]["role"], "model")

    def test_inline_data_for_image(self):
        history = [
            {"role": "user", "content": "Photo : ![g](g.jpg)"},
        ]
        out = self.fn(history, self.cours_root)
        msg = out[0]
        parts = msg["parts"]
        self.assertEqual(parts[0]["text"][:6], "Photo ")  # texte préservé
        self.assertIn("inline_data", parts[1])
        self.assertEqual(parts[1]["inline_data"]["mime_type"], "image/jpeg")
        # Gemini attend les bytes bruts (pas base64), on a décodé
        self.assertIsInstance(parts[1]["inline_data"]["data"], bytes)
        self.assertEqual(parts[1]["inline_data"]["data"], self.photo.read_bytes())


class TestAutocloseTruncatedTags(unittest.TestCase):
    """Phase A.11.1 : rattrapage des balises laissées ouvertes quand un
    moteur tronque le stream (limite de tokens)."""

    def setUp(self):
        from claude_client import _autoclose_truncated_tags
        self.fn = _autoclose_truncated_tags

    def test_balanced_returns_empty(self):
        self.assertEqual(self.fn("<<<CAHIER>>>abc<<<END>>>"), "")
        self.assertEqual(self.fn("texte normal sans balise"), "")

    def test_unclosed_cahier(self):
        self.assertEqual(self.fn("<<<CAHIER>>>contenu coupé"), "<<<END>>>")

    def test_unclosed_cahier_with_titre_attr(self):
        self.assertEqual(
            self.fn('<<<CAHIER titre="Récap">>>contenu coupé'), "<<<END>>>",
        )

    def test_unclosed_tts(self):
        self.assertEqual(self.fn("<<<TTS>>>passage clé"), "<<<END>>>")

    def test_multiple_unclosed(self):
        # Un CAHIER fermé + un TTS ouvert → un seul <<<END>>> manquant.
        txt = "<<<CAHIER>>>x<<<END>>><<<TTS>>>y"
        self.assertEqual(self.fn(txt), "<<<END>>>")

    def test_extra_close_is_not_negative(self):
        # Plus de close que d'open : on ne renvoie jamais de suffixe négatif.
        self.assertEqual(self.fn("texte<<<END>>>"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
