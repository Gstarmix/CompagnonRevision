"""
compagnon.py : entry point CLI du compagnon de révision.

Usage::

    python compagnon.py AN1 TD 5 3
    python compagnon.py AN1 TD 5 3 --enonce-path AN1/TD/AN1_TD5_enonce.pdf
    python compagnon.py AN1 TD 5 3 --resume
    python compagnon.py AN1 TD 5 3 --enable-audio

Pose le ``sys.path`` vers les sous-modules (``_scripts/dialogue``, ``audio``,
``quota``, ``web``) puis :

1. Vérifie le quota Pro Max via ``can_start_session()``.
2. Si ``--resume``, liste les sessions reprenables.
3. Lance Flask en thread daemon sur ``127.0.0.1:5680``.
4. Optionnel : démarre le listener push-to-talk + transcripteur Whisper.
5. Ouvre le navigateur sur l'UI avec les query params pré-remplis.
6. Bloque jusqu'à ``Ctrl+C`` ou jusqu'à la mort du thread Flask.

Cf. ARCHITECTURE.md §10.
"""

import argparse
import logging
import sys
import threading
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlencode

# Path bootstrap : pose les chemins avant les imports internes (config.py
# est à la racine, les modules sont dans _scripts/{dialogue,audio,quota,web}/).
ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "_scripts"
for _sub in ("dialogue", "audio", "quota", "web"):
    sys.path.insert(0, str(SCRIPTS / _sub))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(ROOT))

from app import app, DEFAULT_PORT  # noqa: E402
from config import SESSIONS_DIR  # noqa: E402
from quota_check import can_start_session  # noqa: E402
from session_state import SessionState  # noqa: E402

logger = logging.getLogger(__name__)


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.skip_quota_check:
        logger.warning("--skip-quota-check actif : quota Claude non verifie.")
    else:
        # Le quota_check vise les fenêtres 5h / hebdo Anthropic. Si l'engine
        # actif est non-Anthropic (Gemini/DeepSeek/Groq), ce check est sans
        # objet (chacun a son propre rate limiting côté API). On skip.
        from app import _read_engine_pref
        from claude_client import ENGINE_CLI, ENGINE_API
        active_engine = _read_engine_pref()
        if active_engine not in (ENGINE_CLI, ENGINE_API):
            logger.info(
                "Engine %s : quota Anthropic non applicable, skip.",
                active_engine,
            )
        else:
            ok, reason = can_start_session()
            if not ok:
                print(f"Impossible de demarrer : {reason}", file=sys.stderr)
                return 1
            logger.info("Quota OK.")

    if args.resume:
        _print_resumable()

    url = _build_url(args)

    # host="0.0.0.0" pour que Flask soit accessible depuis l'IP Tailscale
    # du PC, nécessaire pour que la page /mobile depuis le téléphone
    # puisse uploader des photos. Sécurité : Tailscale chiffre tout et le
    # firewall ACL Tailscale limite l'accès aux machines de ton tailnet.
    # Le PC reste en local-only sur le LAN normal (Windows Defender bloque
    # les connexions LAN par défaut sauf si tu as autorisé Python).
    flask_thread = threading.Thread(
        target=lambda: app.run(
            host="0.0.0.0", port=DEFAULT_PORT,
            debug=False, threaded=True, use_reloader=False,
        ),
        daemon=True,
        name="flask-app",
    )
    flask_thread.start()
    time.sleep(1)  # laisse Flask binder le port avant browser/listener

    listener = None
    if args.enable_audio:
        listener = _start_audio_listener()

    logger.info("Ouverture du navigateur : %s", url)
    _open_ui(url)

    try:
        while flask_thread.is_alive():
            flask_thread.join(timeout=1)
    except KeyboardInterrupt:
        logger.info("Interruption clavier, arret en cours.")
    finally:
        if listener is not None:
            listener.stop()
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compagnon de révision (Phase A)")
    p.add_argument("matiere", help="AN1, EN1, PSI, ...")
    p.add_argument("type", help="TD, TP, CC, CM, Examen, Quiz")
    p.add_argument("num", help="Numéro du TD/TP/CC")
    p.add_argument("exo", help="Numéro de l'exercice ou 'full'")
    p.add_argument("--source", choices=("cours", "droit"), default="cours",
                   help="Phase S4 (Cartable) : source du contenu. cours (défaut) = "
                        "arbo COURS L1 Info (PDF). droit = arbo DROIT produite par "
                        "Cartable (markdown : transcription + fiche). En droit, les "
                        "positionnels valent matiere=<slug>, type=CM|TD, num=<n>, "
                        "exo=full ; le front bascule sur les combos droit et envoie "
                        "source=droit à /api/start_session.")
    p.add_argument("--annee", help="Millésime CC (ex: 2025-26), requis pour les CC multi-millésimes")
    p.add_argument("--mode", choices=("colle", "guidé", "découverte"), default="colle",
                   help="colle (défaut) = interrogation pure ; "
                        "guidé = tuteur slide-par-slide + accès FS Read/Grep/Glob "
                        "+ suggestions de correction (absorbe l'ex-mode lecture, supprimé Phase Z.8) ; "
                        "découverte (Phase A.8) = tuteur explicateur, zéro prérequis, "
                        "exposition courte + question + validation. Idéal pour démarrer "
                        "un sujet jamais (ou peu) suivi en CM. Génère un PDF d'énoncé "
                        "d'entraînement en début de séance.")
    p.add_argument("--colle-format", choices=("oral", "photos", "mixte"), default="mixte",
                   help="Phase v15.7.4 : format d'interaction en mode colle (ignoré en guidé) : "
                        "oral = pas de photo (le tuteur ne la mentionne jamais) ; "
                        "photos = le tuteur attend la photo sur les questions structurées "
                        "(table de vérité, schéma, équation posée) ; "
                        "mixte (défaut) = décision au cas par cas. "
                        "Bascule possible en cours de séance via /oral, /photos, /mixte ou les chips UI.")
    p.add_argument("--corrige-anchor", choices=("strict", "consultatif", "aucun"), default="strict",
                   help="Phase v15.7.30 : mode d'ancrage corrigé en mode colle (ignoré en guidé) : "
                        "strict (défaut) = corrigé fait foi (règle inviolable du prompt v0.5) ; "
                        "consultatif = corrigé visible mais cité comme point de vue parmi d'autres, "
                        "voies alternatives validées sans exiger de reproduire le prof ; "
                        "aucun = corrigé pas injecté dans le contexte (révision sans biais conformité). "
                        "Bascule possible en cours de séance via /strict, /consultatif, /sans_corrigé ou les chips UI.")
    p.add_argument("--enonce-path", help="Override PDF d'énoncé (sinon auto-résolu via cours_resolver)")
    p.add_argument("--resume", action="store_true",
                   help="Lister les sessions reprenables avant de démarrer")
    p.add_argument("--enable-audio", action="store_true",
                   help="Hooker ESPACE et activer Whisper push-to-talk")
    p.add_argument("--skip-quota-check", action="store_true",
                   help="Bypass le quota_check au boot (tests d'infra qui ne hit pas Claude)")
    p.add_argument("--ignore-enonce", action="store_true",
                   help="Phase v15.7.36.5 : le tuteur invente ses propres questions/exos "
                        "au lieu de suivre un énoncé existant. Utile pour la révision "
                        "globale d'un thème (cas PSI _revision_CC2/) où l'annale + poly "
                        "fournissent assez de matière sans énoncé pré-défini. "
                        "Si pas d'énoncé est trouvé sur disque, ce mode est implicite.")
    p.add_argument("--sujet-libre",
                   help="Phase A.8.3 : texte libre du sujet à apprendre (hors COURS/). "
                        "Ex: --sujet-libre \"je veux apprendre Python pour scrapper le web\". "
                        "Quand ce flag est fourni, matière/type/num/exo positionnels sont "
                        "remplacés par des sentinelles côté backend (matiere=LIBRE, "
                        "type=SUJET, num=<slug>, exo=full). Mode guidé refusé en libre.")
    p.add_argument("--workspace-root",
                   help="Phase A.9 : chemin absolu d'un dossier hors COURS/ à "
                        "utiliser comme matériel de séance (codebase, docs, CV, "
                        "etc.). Quand fourni : matiere/type/num/exo positionnels "
                        "deviennent sentinelles (WORKSPACE/DIR/<slug>/full), mode "
                        "forcé `workspace`, prompt PROMPT_SYSTEME_WORKSPACE.md, "
                        "tools Read/Grep/Glob scopés via cwd subprocess.")
    p.add_argument("--workspace-focus",
                   help="Phase A.9 : sous-dossier (relatif au workspace_root) "
                        "à mettre en avant dans le résumé auto. Ex: "
                        "--workspace-focus _scripts/dialogue.")
    p.add_argument("--workspace-exclude", action="append", default=[],
                   help="Phase A.9 : pattern d'exclusion supplémentaire (basename "
                        "ou *.ext, additif aux défauts hard-codés). Cumulatif : "
                        "--workspace-exclude _archives --workspace-exclude *.log.")
    p.add_argument("--autostart", action="store_true",
                   help="Phase v15.7.36.2 : déclenche automatiquement le start_session "
                        "côté navigateur (sans clic Lancer dans le form). Utilisé par la "
                        "GUI Tk qui pré-remplit tous les paramètres : l'user clique Lancer "
                        "dans la GUI, l'URL inclut `autostart=1`, le front auto-submit. "
                        "Si l'user ouvre l'UI via le bouton « Ouvrir l'UI navigateur » de "
                        "la GUI, ce flag n'est pas set et le comportement normal est conservé.")
    return p.parse_args()


def _print_resumable() -> None:
    resumable = SessionState.find_resumable(SESSIONS_DIR)
    if not resumable:
        print("Aucune session reprenable.")
        return
    print("Sessions reprenables :")
    for p in resumable:
        print(f"  - {p.name}")
    print(
        "Phase A : pas de reprise auto. Relance avec les memes arguments "
        "pour reprendre la session du jour, ou choisis-en une ci-dessus."
    )


def _build_url(args: argparse.Namespace) -> str:
    params = {
        "matiere": args.matiere,
        "type": args.type,
        "num": args.num,
        "exo": args.exo,
    }
    # Phase S4 (Cartable) : propage la source droit ; le front lit ce param,
    # bascule sur les combos droit et route matiere/type/num en sélection droit.
    if getattr(args, "source", "cours") == "droit":
        params["source"] = "droit"
    if args.annee:
        params["annee"] = args.annee
    if args.mode and args.mode != "colle":
        params["mode"] = args.mode
    # Phase v15.7.4 : `colle_format` propagé à l'URL (le front l'envoie
    # ensuite à /api/start_session). Omis si default "mixte" pour garder
    # l'URL courte.
    if getattr(args, "colle_format", "mixte") != "mixte":
        params["colle_format"] = args.colle_format
    # Phase v15.7.30 : `corrige_anchor` propagé à l'URL. Omis si default
    # "strict" (cas écrasant, garde l'URL courte).
    if getattr(args, "corrige_anchor", "strict") != "strict":
        params["corrige_anchor"] = args.corrige_anchor
    # Phase v15.7.36.5 : ignore_enonce, le tuteur invente ses questions
    if getattr(args, "ignore_enonce", False):
        params["ignore_enonce"] = "1"
    # Phase A.8.3 : sujet libre propagé via URL. Le front voit ce param,
    # bascule en mode sujet libre, cache les combos COURS, et envoie
    # sujet_libre au backend.
    if getattr(args, "sujet_libre", None):
        params["sujet_libre"] = args.sujet_libre
    # Phase A.9 : workspace propagé via URL. Le front voit ces params,
    # bascule en mode workspace, cache les combos COURS, et envoie
    # workspace_root/focus/excludes au backend.
    if getattr(args, "workspace_root", None):
        params["workspace_root"] = args.workspace_root
        if getattr(args, "workspace_focus", None):
            params["workspace_focus_subdir"] = args.workspace_focus
        if getattr(args, "workspace_exclude", None):
            params["workspace_excludes"] = ",".join(args.workspace_exclude)
    # Phase v15.7.36.2 : autostart pour bypass le clic Lancer côté front
    if getattr(args, "autostart", False):
        params["autostart"] = "1"
    if args.enonce_path:
        params["enonce_path"] = args.enonce_path
    return f"http://127.0.0.1:{DEFAULT_PORT}/?{urlencode(params)}"


def _open_ui(url: str) -> None:
    """Ouvre l'UI dans une fenêtre applicative Edge (``--app=``, sans barre de
    navigateur), comme l'application Cartable, pour que les deux logiciels
    offrent la même expérience « fenêtre dédiée ». Repli : navigateur par
    défaut si Edge est introuvable (comportement historique)."""
    import os
    import subprocess

    candidats = [
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Microsoft/Edge/Application/msedge.exe",
    ]
    for edge in candidats:
        if edge.is_file():
            subprocess.Popen([str(edge), f"--app={url}"])
            return
    webbrowser.open(url)


def _start_audio_listener():
    """Instancie WhisperTranscriber + PushToTalkListener.

    Le callback ``on_recording_complete`` transcrit le WAV puis POST le texte
    sur ``/api/send_message`` côté Flask local ; le streaming ultérieur est
    géré par l'UI navigateur classique.
    """
    import requests
    from listener import PushToTalkListener
    from transcribe_stream import WhisperTranscriber

    logger.info("Chargement Whisper large-v3 (peut prendre quelques secondes)...")
    transcriber = WhisperTranscriber()

    def on_wav(wav_path: Path) -> None:
        try:
            text, dur = transcriber.transcribe(wav_path)
            logger.info("Transcription (%.2fs audio) : %s", dur, text[:120])
            r = requests.post(
                f"http://127.0.0.1:{DEFAULT_PORT}/api/send_message",
                json={"text": text}, timeout=5,
            )
            if r.status_code not in (200, 202):
                logger.warning(
                    "send_message HTTP %d : %s", r.status_code, r.text[:200],
                )
        except Exception:
            logger.exception("Echec dans on_wav (callback push-to-talk)")

    listener = PushToTalkListener(on_recording_complete=on_wav)
    listener.start()
    logger.info("Push-to-talk arme sur ESPACE. Maintenir pour parler, relacher pour envoyer.")
    return listener


if __name__ == "__main__":
    raise SystemExit(main())
