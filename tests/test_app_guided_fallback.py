"""
test_app_guided_fallback.py (Phase v15.7.35).

Couvre :
- POST /api/browse_folder : path safety + listing + classification
- POST /api/scan_with_ai : cache mtime + appel Gemini mocké
- /api/guided/init avec overrides script_path/slides_path
- /api/guided/init renvoie guided_fallback_required quand SCRIPT introuvable
"""

import json
import os
import sys
import time
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


def _touch(path: Path, content: bytes = b"") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class TestBrowseFolder(unittest.TestCase):

    def setUp(self):
        self._tmpobj = TemporaryDirectory()
        self.cours = Path(self._tmpobj.name)
        # Structure de test
        _touch(self.cours / "PSI" / "_revision_CC2" / "aide_memoire_CC2.pdf", b"%PDF-x")
        _touch(self.cours / "PSI" / "_revision_CC2" / "annale_synthese_CC2.pdf", b"%PDF-x")
        _touch(self.cours / "PSI" / "_revision_CC2" / "scripts" / "script_oral_Bit.txt", b"texte")
        _touch(self.cours / "PSI" / "_revision_CC2" / "scripts" / "slides_Bit.pdf", b"%PDF-x")
        _touch(self.cours / "PSI" / "_revision_CC2" / "ignored.bak", b"bak")
        _touch(self.cours / "PSI" / "_revision_CC2" / ".hidden", b"hidden")

        import app
        self.app_module = app
        self.client = app.app.test_client()
        # Patch COURS_ROOT pour pointer vers notre tmp
        self._cours_root_patch = patch.object(app, "COURS_ROOT", self.cours)
        self._cours_root_patch.start()

    def tearDown(self):
        self._cours_root_patch.stop()
        self._tmpobj.cleanup()

    def test_browse_root(self):
        r = self.client.post("/api/browse_folder", json={"path": ""})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        names = [e["name"] for e in data["entries"]]
        self.assertIn("PSI", names)
        # Pas de parent_path à la racine
        self.assertIsNone(data["parent_path"])

    def test_browse_subdir(self):
        r = self.client.post("/api/browse_folder", json={"path": "PSI/_revision_CC2"})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        names = [e["name"] for e in data["entries"]]
        self.assertIn("aide_memoire_CC2.pdf", names)
        self.assertIn("annale_synthese_CC2.pdf", names)
        self.assertIn("scripts", names)
        # Skip technique
        self.assertNotIn("ignored.bak", names)
        self.assertNotIn(".hidden", names)
        # parent_path est PSI
        self.assertEqual(data["parent_path"], "PSI")

    def test_browse_classifies_kinds(self):
        r = self.client.post("/api/browse_folder", json={"path": "PSI/_revision_CC2"})
        data = r.get_json()
        by_name = {e["name"]: e for e in data["entries"]}
        self.assertEqual(by_name["aide_memoire_CC2.pdf"]["kind"], "aide_memoire")
        self.assertEqual(by_name["annale_synthese_CC2.pdf"]["kind"], "annale")

    def test_browse_path_traversal_refused(self):
        # Tente de sortir de COURS_ROOT avec `..`
        r = self.client.post("/api/browse_folder", json={"path": "../../../etc"})
        # Soit 400 (refus), soit 404 (dossier inexistant), pas un listing valide
        self.assertIn(r.status_code, (400, 404))

    def test_browse_nonexistent_returns_404(self):
        r = self.client.post("/api/browse_folder", json={"path": "PSI/NOPE"})
        self.assertEqual(r.status_code, 404)

    def test_browse_leading_slash_stripped(self):
        # Path avec slash leading doit être normalisé
        r = self.client.post("/api/browse_folder", json={"path": "/PSI"})
        # 200 OK car normalize strip le slash
        self.assertEqual(r.status_code, 200)


class TestScanWithAi(unittest.TestCase):

    def setUp(self):
        self._tmpobj = TemporaryDirectory()
        self.cours = Path(self._tmpobj.name)
        _touch(self.cours / "PSI" / "_revision_CC2" / "aide_memoire.pdf", b"%PDF-x")
        _touch(self.cours / "PSI" / "_revision_CC2" / "scripts" / "script_oral_Bit.txt", b"texte")
        _touch(self.cours / "PSI" / "_revision_CC2" / "scripts" / "slides_Bit.pdf", b"%PDF-x")

        import app
        self.app_module = app
        self.client = app.app.test_client()
        self._cours_root_patch = patch.object(app, "COURS_ROOT", self.cours)
        self._cours_root_patch.start()

    def tearDown(self):
        self._cours_root_patch.stop()
        self._tmpobj.cleanup()

    def test_scan_requires_folder_path(self):
        r = self.client.post("/api/scan_with_ai", json={})
        self.assertEqual(r.status_code, 400)

    def test_scan_path_traversal_refused(self):
        r = self.client.post("/api/scan_with_ai", json={"folder_path": "../etc"})
        self.assertIn(r.status_code, (400, 404))

    def test_scan_nonexistent_returns_404(self):
        r = self.client.post("/api/scan_with_ai", json={"folder_path": "PSI/NOPE"})
        self.assertEqual(r.status_code, 404)

    def test_scan_calls_gemini_and_persists_cache(self):
        # Mock _scan_with_ai_internal pour éviter l'appel Gemini réel
        fake_result = {
            "script_oral_path": "PSI/_revision_CC2/scripts/script_oral_Bit.txt",
            "slides_pdf_path": "PSI/_revision_CC2/scripts/slides_Bit.pdf",
            "script_imprimable_path": None,
            "confidence_0_100": 85,
            "reasoning": "script_oral_Bit.txt est le seul script ; slides_Bit.pdf seules slides",
        }
        with patch.object(self.app_module, "_scan_with_ai_internal", return_value=fake_result):
            r = self.client.post(
                "/api/scan_with_ai",
                json={"folder_path": "PSI/_revision_CC2"},
            )
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["confidence_0_100"], 85)
        self.assertFalse(data["cached"])
        self.assertIn("scanned_at", data)
        # Cache file créé
        cache_file = self.cours / "PSI" / "_revision_CC2" / "_compagnon_scan.json"
        self.assertTrue(cache_file.is_file())

    def test_scan_returns_cache_on_second_call(self):
        fake_result = {
            "script_oral_path": "PSI/_revision_CC2/scripts/script_oral_Bit.txt",
            "slides_pdf_path": "PSI/_revision_CC2/scripts/slides_Bit.pdf",
            "script_imprimable_path": None,
            "confidence_0_100": 85,
            "reasoning": "premier scan",
        }
        with patch.object(self.app_module, "_scan_with_ai_internal", return_value=fake_result) as mock_internal:
            # 1ᵉʳ appel : fresh
            self.client.post("/api/scan_with_ai", json={"folder_path": "PSI/_revision_CC2"})
            self.assertEqual(mock_internal.call_count, 1)
            # 2ᵉ appel sans force : doit hit le cache
            r = self.client.post("/api/scan_with_ai", json={"folder_path": "PSI/_revision_CC2"})
            data = r.get_json()
            self.assertTrue(data["cached"])
            # Gemini PAS rappelé
            self.assertEqual(mock_internal.call_count, 1)

    def test_scan_force_refresh_bypasses_cache(self):
        fake_result = {
            "script_oral_path": None,
            "slides_pdf_path": None,
            "script_imprimable_path": None,
            "confidence_0_100": 50,
            "reasoning": "fresh",
        }
        with patch.object(self.app_module, "_scan_with_ai_internal", return_value=fake_result) as mock_internal:
            self.client.post("/api/scan_with_ai", json={"folder_path": "PSI/_revision_CC2"})
            # force_refresh : re-call Gemini
            self.client.post(
                "/api/scan_with_ai",
                json={"folder_path": "PSI/_revision_CC2", "force_refresh": True},
            )
            self.assertEqual(mock_internal.call_count, 2)

    def test_scan_cache_invalidated_on_folder_mtime(self):
        fake_result = {
            "script_oral_path": None,
            "slides_pdf_path": None,
            "script_imprimable_path": None,
            "confidence_0_100": 50,
            "reasoning": "fresh",
        }
        with patch.object(self.app_module, "_scan_with_ai_internal", return_value=fake_result) as mock_internal:
            # 1er scan → écrit cache
            self.client.post("/api/scan_with_ai", json={"folder_path": "PSI/_revision_CC2"})
            self.assertEqual(mock_internal.call_count, 1)
            # Force le cache à avoir un mtime plus VIEUX que le dossier
            cache_file = self.cours / "PSI" / "_revision_CC2" / "_compagnon_scan.json"
            very_old = time.time() - 3600
            os.utime(cache_file, (very_old, very_old))
            # Touche un sous-dossier pour bump son mtime au moment courant
            sub = self.cours / "PSI" / "_revision_CC2" / "scripts"
            now = time.time()
            os.utime(sub, (now, now))
            # 2e call : cache obsolète → re-scan
            self.client.post("/api/scan_with_ai", json={"folder_path": "PSI/_revision_CC2"})
            self.assertEqual(mock_internal.call_count, 2)


class TestGuidedFallbackSignal(unittest.TestCase):
    """Phase v15.7.35 : /api/guided/init renvoie guided_fallback_required
    quand SCRIPT_*.md ou slides_*.pdf est absent (au lieu de juste 404).
    """

    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()

    def test_no_session_returns_409(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.get("/api/guided/init")
        self.assertEqual(r.status_code, 409)

    def test_script_missing_signals_fallback(self):
        fake = MagicMock()
        ctx = MagicMock()
        ctx.matiere = "PSI"
        ctx.type = "_revision_CC2"
        ctx.num = "full"
        ctx.annee = None
        fake.session_state = MagicMock()
        fake.session_state.context = ctx
        with patch.object(self.app_module, "_state", fake), \
             patch.object(self.app_module, "find_perso_script_md", return_value=None):
            r = self.client.get("/api/guided/init")
        self.assertEqual(r.status_code, 404)
        data = r.get_json()
        self.assertTrue(data["guided_fallback_required"])
        self.assertEqual(data["matiere"], "PSI")
        self.assertIn("folder_path", data)


class TestClaudeCodePrompt(unittest.TestCase):
    """Phase v15.7.36 : /api/claude_code_prompt génère un prompt clé-en-main
    pour une session Claude Code séparée.
    """

    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()

    def test_no_session_and_no_explicit_context_returns_409(self):
        with patch.object(self.app_module, "_state", None):
            r = self.client.post("/api/claude_code_prompt", json={"kind": "regen_script_md"})
        self.assertEqual(r.status_code, 409)

    def test_invalid_kind_returns_400(self):
        fake = MagicMock()
        fake.session_state = MagicMock()
        fake.session_state.data = {
            "matiere": "PSI", "type": "_revision_CC2", "num": "Bit_information",
            "context_files": {},
        }
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post(
                "/api/claude_code_prompt",
                json={"kind": "nonexistent_kind"},
            )
        self.assertEqual(r.status_code, 400)

    def test_regen_script_md_uses_session_context(self):
        fake = MagicMock()
        fake.session_state = MagicMock()
        fake.session_state.data = {
            "matiere": "PSI",
            "type": "_revision_CC2",
            "num": "Bit_information",
            "context_files": {
                "script_oral": "PSI/_revision_CC2/scripts/script_oral_Bit_information.txt",
                "slides_pdf": "PSI/_revision_CC2/scripts/slides_Bit_information.pdf",
                "enonce": "PSI/_revision_CC2/annale_synthese_CC2.pdf",
                "poly_cm": "PSI/_revision_CC2/aide_memoire_CC2.pdf",
            },
        }
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post(
                "/api/claude_code_prompt",
                json={"kind": "regen_script_md"},
            )
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("prompt", data)
        prompt = data["prompt"]
        # Vérifie l'alignement sur COURS/CLAUDE.md
        self.assertIn("COURS/CLAUDE.md", prompt)
        self.assertIn("SPEC_script_oral_v2.md", prompt)
        self.assertIn("run_script_oral.py", prompt)
        self.assertIn("PRESERVE.md", prompt)
        # Vérifie les paths du contexte
        self.assertIn("script_oral_Bit_information.txt", prompt)
        self.assertIn("slides_Bit_information.pdf", prompt)
        # Vérifie les conventions clés
        self.assertIn("RÈGLE", prompt)
        self.assertIn("atomic", prompt.lower())

    def test_explicit_context_bypasses_session(self):
        # Body explicite : matiere/type/num fournis → pas besoin de session
        with patch.object(self.app_module, "_state", None):
            r = self.client.post("/api/claude_code_prompt", json={
                "kind": "regen_script_md",
                "matiere": "AN1",
                "type_code": "TD",
                "num": "5",
            })
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("AN1", data["prompt"])
        self.assertEqual(data["matiere"], "AN1")

    def test_audit_matiere_cc_kind(self):
        fake = MagicMock()
        fake.session_state = MagicMock()
        fake.session_state.data = {
            "matiere": "PSI", "type": "_revision_CC2", "num": "full",
            "context_files": {},
        }
        with patch.object(self.app_module, "_state", fake):
            r = self.client.post(
                "/api/claude_code_prompt",
                json={"kind": "audit_matiere_cc"},
            )
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("Audit", data["prompt"])
        self.assertIn("orphelins", data["prompt"].lower())
        self.assertIn("PSI", data["prompt"])
        # Read-only (pas de modif)
        self.assertIn("Ne modifie aucun fichier", data["prompt"])


class TestGuidedInitValidation(unittest.TestCase):
    """Phase v15.7.36.1 : validation des extensions sur les overrides
    de /api/guided/init (évite le 500 sur parse_script appelé sur un
    .pdf). Auto-swap si user/IA a inversé.
    """

    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()

    def _mock_state(self):
        fake = MagicMock()
        ctx = MagicMock()
        ctx.matiere = "PSI"
        ctx.type = "_revision_CC2"
        ctx.num = "Bit_information"
        ctx.annee = None
        fake.session_state = MagicMock()
        fake.session_state.context = ctx
        return fake

    def test_pdf_as_script_returns_400(self):
        """User pointe vers script.pdf et slides.pdf → 400 propre, plus de 500."""
        with patch.object(self.app_module, "_state", self._mock_state()):
            r = self.client.get(
                "/api/guided/init"
                "?script_path=PSI/_revision_CC2/script.pdf"
                "&slides_path=PSI/_revision_CC2/other.pdf",
            )
        self.assertEqual(r.status_code, 400)
        data = r.get_json()
        self.assertIn("doit être un .md ou .txt", data["error"])
        self.assertTrue(data["guided_fallback_required"])

    def test_txt_as_slides_returns_400(self):
        with patch.object(self.app_module, "_state", self._mock_state()):
            r = self.client.get(
                "/api/guided/init"
                "?script_path=PSI/script.md"
                "&slides_path=PSI/script.txt",
            )
        self.assertEqual(r.status_code, 400)
        data = r.get_json()
        self.assertIn("doit être un .pdf", data["error"])

    def test_auto_flip_pdf_and_txt_inversed(self):
        """Si script=.pdf et slides=.txt → auto-swap. Pas de 400."""
        # On va plus loin que le swap : on s'assure que ça ne plante pas
        # en 500. Le test passe quel que soit le code suivant le swap,
        # tant qu'on n'a pas un 500 sur .pdf binaire.
        with patch.object(self.app_module, "_state", self._mock_state()):
            r = self.client.get(
                "/api/guided/init"
                "?script_path=PSI/slides.pdf"
                "&slides_path=PSI/script.txt",
            )
        # Le swap fait : script_path devient script.txt (valide),
        # slides_path devient slides.pdf (valide). Ensuite la résolution
        # FS dans _resolve échoue car les paths sont fictifs → renvoie 404
        # guided_fallback_required (pas 500).
        self.assertNotEqual(r.status_code, 500)

    def test_unhandled_exception_returns_json_not_html(self):
        """Wrapper try/except : toute exception inattendue renvoie du JSON,
        jamais du HTML 500 qui ferait croire au front que l'endpoint
        n'existe pas (faux message « antérieur à Phase A.7.2 v5 »).
        """
        fake = self._mock_state()
        # Force parse_script à lever (cas d'erreur inattendue)
        with patch.object(self.app_module, "_state", fake), \
             patch.object(self.app_module, "find_perso_script_md") as mock_find:
            mock_find.side_effect = RuntimeError("crash interne simulé")
            r = self.client.get("/api/guided/init")
        # Le wrapper catch → JSON 500
        self.assertEqual(r.status_code, 500)
        ct = r.headers.get("Content-Type", "")
        self.assertIn("application/json", ct)
        data = r.get_json()
        self.assertIn("crash interne simulé", data.get("detail", ""))


class TestGuidedLiteMode(unittest.TestCase):
    """Phase v15.7.36 : fallback mode guidé « lite » quand SCRIPT.md
    sans headers SLIDE N (cas script_oral_*.txt continu).
    """

    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()
        # Tmp pour script + slides factices
        self._tmpobj = TemporaryDirectory()
        self.cours = Path(self._tmpobj.name)
        # Script .txt sans headers SLIDE
        self.script = self.cours / "script_oral_test.txt"
        self.script.write_text("Texte oral continu sans headers de slide.", encoding="utf-8")
        # Slides "PDF" factice (on mockera rasterize_if_needed)
        self.slides = self.cours / "slides_test.pdf"
        self.slides.write_bytes(b"%PDF-mock")

    def tearDown(self):
        self._tmpobj.cleanup()

    def test_lite_response_when_no_slides_headers(self):
        # Mock parse_script → 0 slides + rasterize_if_needed → 3 PNGs synth
        fake_pngs = [
            Path("/tmp/slide-1.png"),
            Path("/tmp/slide-2.png"),
            Path("/tmp/slide-3.png"),
        ]
        fake_structure = MagicMock()
        fake_structure.slides = []
        fake_structure.titre_global = ""

        fake_state = MagicMock()
        ctx = MagicMock()
        ctx.matiere = "PSI"
        ctx.type = "_revision_CC2"
        ctx.num = "Bit_information"
        ctx.annee = None
        fake_state.session_state = MagicMock()
        fake_state.session_state.context = ctx

        with patch.object(self.app_module, "_state", fake_state), \
             patch.object(self.app_module, "find_perso_script_md", return_value=self.script), \
             patch.object(self.app_module, "find_perso_slides_pdf", return_value=self.slides), \
             patch.object(self.app_module, "parse_script", return_value=fake_structure), \
             patch.object(self.app_module, "rasterize_if_needed", return_value=fake_pngs), \
             patch.object(self.app_module, "COURS_ROOT", self.cours):
            r = self.client.get("/api/guided/init")

        # Phase v15.7.36 : 200 OK avec lite:true au lieu de 422
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data.get("lite"))
        self.assertEqual(data["total"], 3)
        self.assertEqual(len(data["slides"]), 3)
        # 1ʳᵉ slide a un oral_excerpt (le début du .txt)
        self.assertTrue(data["slides"][0]["oral_excerpt"])
        # Slides 2 et 3 ont oral_excerpt vide (pas de découpage)
        self.assertEqual(data["slides"][1]["oral_excerpt"], "")
        # Titres sont "Page N/3"
        self.assertEqual(data["slides"][0]["title"], "Page 1/3")
        # lite_reason expliqué
        self.assertIn("Feynman", data.get("lite_reason", ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
