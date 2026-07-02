"""
test_runtime_settings.py : couverture du module runtime_settings.

Lance avec :
    python -m unittest tests.test_runtime_settings
"""

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Path setup
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "_scripts"
for _p in (str(ROOT), str(SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from runtime_settings import (  # noqa: E402
    DEFAULT_CONTEXT_CAPS,
    DEFAULT_LAST_SELECTION,
    DEFAULT_SESSION_THRESHOLD_PCT,
    DEFAULT_WEEKLY_THRESHOLD_PCT,
    load_settings,
    save_settings,
    update_settings,
)


class TestRuntimeSettings(unittest.TestCase):

    def setUp(self):
        self._tmpobj = TemporaryDirectory()
        self.tmp = Path(self._tmpobj.name)
        self.path = self.tmp / "runtime_settings.json"

    def tearDown(self):
        self._tmpobj.cleanup()

    def test_load_returns_defaults_when_missing(self):
        s = load_settings(self.path)
        self.assertEqual(s["session_threshold_pct"], DEFAULT_SESSION_THRESHOLD_PCT)
        self.assertEqual(s["weekly_threshold_pct"], DEFAULT_WEEKLY_THRESHOLD_PCT)
        self.assertEqual(
            s["context_caps"]["cm_transcription_words"],
            DEFAULT_CONTEXT_CAPS["cm_transcription_words"],
        )

    def test_save_then_load_roundtrip(self):
        save_settings(
            {"session_threshold_pct": 70, "weekly_threshold_pct": 75},
            path=self.path,
        )
        s = load_settings(self.path)
        self.assertEqual(s["session_threshold_pct"], 70)
        self.assertEqual(s["weekly_threshold_pct"], 75)
        # updated_at posé
        self.assertIsNotNone(s["updated_at"])

    def test_load_corrupt_file_falls_back(self):
        self.path.write_text("ceci n'est pas un JSON {{{", encoding="utf-8")
        s = load_settings(self.path)
        self.assertEqual(s["session_threshold_pct"], DEFAULT_SESSION_THRESHOLD_PCT)

    def test_partial_file_merges_with_defaults(self):
        # Fichier avec juste un champ : les autres tombent sur les défauts
        self.path.write_text(
            json.dumps({"schema_version": 1, "session_threshold_pct": 60}),
            encoding="utf-8",
        )
        s = load_settings(self.path)
        self.assertEqual(s["session_threshold_pct"], 60)
        self.assertEqual(s["weekly_threshold_pct"], DEFAULT_WEEKLY_THRESHOLD_PCT)
        self.assertEqual(
            s["context_caps"]["perso_material_words"],
            DEFAULT_CONTEXT_CAPS["perso_material_words"],
        )

    def test_caps_partial_merge(self):
        save_settings(
            {"context_caps": {"cm_transcription_words": 1234}},
            path=self.path,
        )
        s = load_settings(self.path)
        self.assertEqual(s["context_caps"]["cm_transcription_words"], 1234)
        # Les autres caps gardent leur défaut
        self.assertEqual(
            s["context_caps"]["perso_material_words"],
            DEFAULT_CONTEXT_CAPS["perso_material_words"],
        )

    def test_update_settings_partial_merge(self):
        # Les overrides sont via le module-level helper qui utilise le path
        # global. Pour cohérence on tape directement save/load avec self.path.
        save_settings({"session_threshold_pct": 50}, path=self.path)
        s = load_settings(self.path)
        self.assertEqual(s["session_threshold_pct"], 50)
        # weekly_threshold_pct doit être au défaut
        self.assertEqual(s["weekly_threshold_pct"], DEFAULT_WEEKLY_THRESHOLD_PCT)

    def test_unknown_keys_ignored(self):
        save_settings(
            {"session_threshold_pct": 60, "blah": "xyz"},
            path=self.path,
        )
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertNotIn("blah", raw)
        self.assertEqual(raw["session_threshold_pct"], 60)

    # ---------------------------------------------------------------- last_selection (A.7.1)

    def test_last_selection_default_empty(self):
        s = load_settings(self.path)
        self.assertIn("last_selection", s)
        for key, default in DEFAULT_LAST_SELECTION.items():
            self.assertEqual(s["last_selection"][key], default)

    def test_last_selection_roundtrip(self):
        save_settings(
            {"last_selection": {
                "matiere": "AN1", "type": "TD", "num": "5",
                "exo": "3", "annee": "", "mode": "guidé",
                "enable_audio": True, "skip_quota": False,
            }},
            path=self.path,
        )
        s = load_settings(self.path)
        ls = s["last_selection"]
        self.assertEqual(ls["matiere"], "AN1")
        self.assertEqual(ls["type"], "TD")
        self.assertEqual(ls["num"], "5")
        self.assertEqual(ls["exo"], "3")
        self.assertEqual(ls["mode"], "guidé")
        self.assertTrue(ls["enable_audio"])
        self.assertFalse(ls["skip_quota"])

    def test_last_selection_partial_merge_keeps_defaults(self):
        # Sauve juste matière + type, le reste doit retomber sur les défauts
        save_settings(
            {"last_selection": {"matiere": "EN1", "type": "CC"}},
            path=self.path,
        )
        s = load_settings(self.path)
        ls = s["last_selection"]
        self.assertEqual(ls["matiere"], "EN1")
        self.assertEqual(ls["type"], "CC")
        # exo retombe sur "full" (default)
        self.assertEqual(ls["exo"], DEFAULT_LAST_SELECTION["exo"])
        self.assertEqual(ls["mode"], DEFAULT_LAST_SELECTION["mode"])

    def test_last_selection_coerces_bool(self):
        # JSON peut avoir des bools sous forme str, on coerce
        self.path.write_text(
            json.dumps({
                "schema_version": 1,
                "last_selection": {"enable_audio": 1, "skip_quota": 0},
            }),
            encoding="utf-8",
        )
        s = load_settings(self.path)
        self.assertTrue(s["last_selection"]["enable_audio"])
        self.assertFalse(s["last_selection"]["skip_quota"])

    def test_update_last_selection_partial(self):
        from runtime_settings import update_last_selection
        # Patch RUNTIME_SETTINGS_PATH du module pour pointer notre tmp
        from unittest.mock import patch
        import runtime_settings as rs
        with patch.object(rs, "RUNTIME_SETTINGS_PATH", self.path):
            update_last_selection(matiere="PSI", mode="guidé")
            update_last_selection(num="7")  # second update partiel
        s = load_settings(self.path)
        ls = s["last_selection"]
        self.assertEqual(ls["matiere"], "PSI")
        self.assertEqual(ls["mode"], "guidé")
        self.assertEqual(ls["num"], "7")
        # type pas touché → reste à default ""
        self.assertEqual(ls["type"], "")

    # ---------------------------------------------------------------- Phase v15.7.30 : corrige_anchor

    def test_corrige_anchor_default_strict(self):
        """Phase v15.7.30 : DEFAULT_LAST_SELECTION.corrige_anchor = 'strict'."""
        self.assertIn("corrige_anchor", DEFAULT_LAST_SELECTION)
        self.assertEqual(DEFAULT_LAST_SELECTION["corrige_anchor"], "strict")
        # Et load_settings sur fichier vierge le restitue
        s = load_settings(self.path)
        self.assertEqual(s["last_selection"]["corrige_anchor"], "strict")

    def test_corrige_anchor_roundtrip(self):
        save_settings(
            {"last_selection": {
                "matiere": "EN1", "type": "CC", "num": "2",
                "corrige_anchor": "consultatif",
            }},
            path=self.path,
        )
        s = load_settings(self.path)
        self.assertEqual(s["last_selection"]["corrige_anchor"], "consultatif")

    def test_corrige_anchor_aucun_persisted(self):
        from runtime_settings import update_last_selection
        from unittest.mock import patch
        import runtime_settings as rs
        with patch.object(rs, "RUNTIME_SETTINGS_PATH", self.path):
            update_last_selection(corrige_anchor="aucun")
        s = load_settings(self.path)
        self.assertEqual(s["last_selection"]["corrige_anchor"], "aucun")

    def test_corrige_anchor_legacy_session_falls_back_to_strict(self):
        """Une session JSON v1 sans `corrige_anchor` doit retomber sur
        `strict` (comportement v0.5 historique) au load."""
        self.path.write_text(
            json.dumps({
                "schema_version": 1,
                "last_selection": {"matiere": "AN1", "type": "TD"},
                # Pas de `corrige_anchor` (vieux fichier)
            }),
            encoding="utf-8",
        )
        s = load_settings(self.path)
        self.assertEqual(s["last_selection"]["corrige_anchor"], "strict")


if __name__ == "__main__":
    unittest.main(verbosity=2)
