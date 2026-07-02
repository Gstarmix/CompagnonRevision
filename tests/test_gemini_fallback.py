"""test_gemini_fallback.py : vérifie la bascule auto Anthropic→Gemini (Phase A.7.2 v7.1).

Scénario testé : compagnon.py imprime « Impossible de demarrer : Quota 5h
a 87% », la GUI détecte le pattern dans le log et propose la bascule
Gemini. Si GEMINI_API_KEY est définie et l'utilisateur accepte, l'engine
est mis à jour dans `_secrets/engine_pref.json` et le subprocess est
relancé avec les mêmes args.

On mocke `messagebox.askyesno` (sinon ça ouvre un dialog Tk bloquant) et
`subprocess.Popen` (sinon ça lance vraiment compagnon.py). Pas besoin de
Tk root réel : on teste la logique métier de `_maybe_propose_gemini_fallback`
+ `_show_gemini_fallback_dialog` + `_relaunch_with_saved_args`.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ajout du PYTHONPATH au pattern existant des autres tests.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "_scripts"))
sys.path.insert(0, str(ROOT / "_scripts" / "dialogue"))
sys.path.insert(0, str(ROOT / "_scripts" / "audio"))
sys.path.insert(0, str(ROOT / "_scripts" / "web"))
sys.path.insert(0, str(ROOT / "_scripts" / "quota"))


class _FakeStringVar:
    """Stub léger pour tk.StringVar (get/set sans Tk)."""

    def __init__(self, value=""):
        self._v = value

    def get(self):
        return self._v

    def set(self, v):
        self._v = v


class _StubGUI:
    """Reproduit juste les attributs/méthodes nécessaires aux 3 fonctions
    testées, sans construire un vrai CompagnonGUI (qui exige Tk)."""

    def __init__(self):
        self._gemini_fallback_proposed = False
        self._last_launch_args = ["python", "-u", "compagnon.py", "PRG2", "CM", "8", "full"]
        self._proc = None
        self.engine = _FakeStringVar("cli_subscription")
        self._stop_log_thread = MagicMock()
        self.status_var = _FakeStringVar()
        self._log_local_calls = []
        self.root = MagicMock()
        # `after` doit invoquer immédiatement la callback pour que le test
        # exerce le flow complet sans event loop.
        self.root.after = lambda ms, fn=None, *a: (fn() if fn else None)

    def _log_local(self, msg):
        self._log_local_calls.append(msg)

    def _save_engine_pref(self):
        # Stub : enregistre dans un fichier temporaire pour vérif.
        self._saved_engine = self.engine.get()

    def _read_proc_stdout(self):
        pass


class TestGeminiFallback(unittest.TestCase):

    def setUp(self):
        # Import paresseux pour que les sys.path soient prêts.
        from gui import CompagnonGUI
        self.CompagnonGUI = CompagnonGUI
        self.gui = _StubGUI()
        # Bind toutes les méthodes que les fonctions testées appellent
        # entre elles via self. (Sans ça, _maybe_propose appelle
        # self._show_gemini_fallback_dialog qui n'existe pas sur le stub.)
        for name in (
            "_maybe_propose_gemini_fallback",
            "_show_gemini_fallback_dialog",
            "_relaunch_with_saved_args",
            "_read_proc_stdout",
        ):
            method = self.CompagnonGUI.__dict__[name]
            setattr(self.gui, name, method.__get__(self.gui, _StubGUI))
        # Recopie les attributs de classe consultés par les méthodes
        # (Phase A.7.2 v7.2 : _FALLBACK_PROVIDERS est sur la classe, pas
        # sur l'instance, le stub ne le voit pas via __dict__).
        self.gui._FALLBACK_PROVIDERS = self.CompagnonGUI._FALLBACK_PROVIDERS

    def _bind(self, name):
        """Renvoie la méthode déjà bound par setUp."""
        return getattr(self.gui, name)

    # -------------------------------------------------- détection du pattern

    def test_pattern_quota_5h_declenche_proposition(self):
        proposer = MagicMock()
        with patch.object(self.gui.root, "after",
                          lambda ms, fn: proposer()):
            self._bind("_maybe_propose_gemini_fallback")(
                "Impossible de demarrer : Quota 5h a 87% (seuil 85%), reset …"
            )
        self.assertTrue(self.gui._gemini_fallback_proposed)
        self.assertEqual(proposer.call_count, 1)

    def test_pattern_quota_hebdo_declenche_proposition(self):
        proposer = MagicMock()
        with patch.object(self.gui.root, "after",
                          lambda ms, fn: proposer()):
            self._bind("_maybe_propose_gemini_fallback")(
                "Impossible de demarrer : Quota hebdo a 92% …"
            )
        self.assertTrue(self.gui._gemini_fallback_proposed)
        self.assertEqual(proposer.call_count, 1)

    def test_ligne_normale_ne_declenche_pas(self):
        proposer = MagicMock()
        with patch.object(self.gui.root, "after",
                          lambda ms, fn: proposer()):
            self._bind("_maybe_propose_gemini_fallback")(
                "[INFO] Quota OK."
            )
        self.assertFalse(self.gui._gemini_fallback_proposed)
        self.assertEqual(proposer.call_count, 0)

    def test_double_propose_ignored(self):
        """Si le pattern apparaît 2 fois (ligne stderr + ligne suivante),
        on ne popup qu'une fois."""
        proposer = MagicMock()
        with patch.object(self.gui.root, "after",
                          lambda ms, fn: proposer()):
            line = "Impossible de demarrer : Quota 5h a 87%"
            self._bind("_maybe_propose_gemini_fallback")(line)
            self._bind("_maybe_propose_gemini_fallback")(line)
        self.assertEqual(proposer.call_count, 1)

    def test_engine_deja_gemini_skip(self):
        """Si on est déjà sur un provider non-Anthropic et qu'il refuse,
        on ne propose pas de re-bascule (extended Phase A.7.2 v7.2 :
        DeepSeek/Groq aussi)."""
        proposer = MagicMock()
        for already in ("gemini_api", "deepseek_api", "groq_api"):
            self.gui.engine.set(already)
            self.gui._gemini_fallback_proposed = False
            with patch.object(self.gui.root, "after",
                              lambda ms, fn: proposer()):
                self._bind("_maybe_propose_gemini_fallback")(
                    "Impossible de demarrer : Quota …"
                )
            self.assertFalse(self.gui._gemini_fallback_proposed)
        self.assertEqual(proposer.call_count, 0)

    # -------------------------------------------------- dialog + bascule

    def _clear_provider_keys(self, env: dict) -> dict:
        """Helper : retire toutes les clés de fallback de l'env testé pour
        garantir un environnement propre, indépendant de la machine du dev."""
        for k in ("GEMINI_API_KEY", "DEEPSEEK_API_KEY", "GROQ_API_KEY"):
            env.pop(k, None)
        return env

    def test_dialog_aucune_key_warning_avec_3_liens(self):
        """Sans aucune clé fallback, on warn avec les 3 liens d'inscription."""
        with patch.dict(os.environ, self._clear_provider_keys({}), clear=False):
            self._clear_provider_keys(os.environ)
            with patch("gui.messagebox.showwarning") as warn, \
                 patch("gui.messagebox.askyesno") as ask:
                self._bind("_show_gemini_fallback_dialog")()
        warn.assert_called_once()
        # Le message doit lister les 3 providers
        warn_msg = warn.call_args[0][1]
        self.assertIn("Gemini", warn_msg)
        self.assertIn("DeepSeek", warn_msg)
        self.assertIn("Groq", warn_msg)
        ask.assert_not_called()
        self.assertEqual(self.gui.engine.get(), "cli_subscription")

    def test_dialog_gemini_seul_propose_gemini(self):
        """GEMINI_API_KEY seule → Gemini est le candidat."""
        env = self._clear_provider_keys(dict(os.environ))
        env["GEMINI_API_KEY"] = "AIzaXXX"
        with patch.dict(os.environ, env, clear=True):
            with patch("gui.messagebox.askyesno", return_value=True) as ask, \
                 patch("gui.subprocess.Popen") as pop, \
                 patch("gui.threading.Thread"):
                pop.return_value.poll.return_value = None
                pop.return_value.pid = 1
                self._bind("_show_gemini_fallback_dialog")()
        self.assertEqual(self.gui.engine.get(), "gemini_api")
        self.assertIn("Gemini", ask.call_args[0][1])

    def test_dialog_deepseek_seul_propose_deepseek(self):
        """DEEPSEEK_API_KEY seule (Gemini absent) → DeepSeek est candidat."""
        env = self._clear_provider_keys(dict(os.environ))
        env["DEEPSEEK_API_KEY"] = "sk-XXX"
        with patch.dict(os.environ, env, clear=True):
            with patch("gui.messagebox.askyesno", return_value=True) as ask, \
                 patch("gui.subprocess.Popen") as pop, \
                 patch("gui.threading.Thread"):
                pop.return_value.poll.return_value = None
                pop.return_value.pid = 1
                self._bind("_show_gemini_fallback_dialog")()
        self.assertEqual(self.gui.engine.get(), "deepseek_api")
        self.assertIn("DeepSeek", ask.call_args[0][1])

    def test_dialog_groq_seul_propose_groq(self):
        """GROQ_API_KEY seule → Groq est candidat."""
        env = self._clear_provider_keys(dict(os.environ))
        env["GROQ_API_KEY"] = "gsk_XXX"
        with patch.dict(os.environ, env, clear=True):
            with patch("gui.messagebox.askyesno", return_value=True) as ask, \
                 patch("gui.subprocess.Popen") as pop, \
                 patch("gui.threading.Thread"):
                pop.return_value.poll.return_value = None
                pop.return_value.pid = 1
                self._bind("_show_gemini_fallback_dialog")()
        self.assertEqual(self.gui.engine.get(), "groq_api")
        self.assertIn("Groq", ask.call_args[0][1])

    def test_dialog_priorite_gemini_si_toutes_keys(self):
        """Toutes les 3 clés présentes → Gemini est candidat (1er dans la
        hiérarchie de pertinence)."""
        env = self._clear_provider_keys(dict(os.environ))
        env["GEMINI_API_KEY"] = "AIzaXXX"
        env["DEEPSEEK_API_KEY"] = "sk-XXX"
        env["GROQ_API_KEY"] = "gsk_XXX"
        with patch.dict(os.environ, env, clear=True):
            with patch("gui.messagebox.askyesno", return_value=True) as ask, \
                 patch("gui.subprocess.Popen") as pop, \
                 patch("gui.threading.Thread"):
                pop.return_value.poll.return_value = None
                pop.return_value.pid = 1
                self._bind("_show_gemini_fallback_dialog")()
        self.assertEqual(self.gui.engine.get(), "gemini_api")
        # Le message mentionne aussi les autres alternatives dispos
        msg = ask.call_args[0][1]
        self.assertIn("DeepSeek", msg)
        self.assertIn("Groq", msg)

    def test_dialog_user_dit_non_pas_de_bascule(self):
        """askyesno=False → engine inchangé, pas de Popen."""
        env = self._clear_provider_keys(dict(os.environ))
        env["GEMINI_API_KEY"] = "AIzaXXX"
        with patch.dict(os.environ, env, clear=True):
            with patch("gui.messagebox.askyesno", return_value=False), \
                 patch("gui.subprocess.Popen") as pop:
                self._bind("_show_gemini_fallback_dialog")()
        self.assertEqual(self.gui.engine.get(), "cli_subscription")
        pop.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
