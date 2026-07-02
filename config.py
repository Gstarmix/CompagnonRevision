"""
config.py : constantes et chemins du projet Compagnon_Revision.

Source de vérité unique pour les chemins et les versions de schéma. Tout
le reste du code importe depuis ici, jamais de chemin absolu en dur.

Cf. CLAUDE.md §3.1.
"""

from pathlib import Path
from zoneinfo import ZoneInfo

# ============================================================ Racines

PROJECT_ROOT = Path(__file__).resolve().parent
COURS_ROOT = Path(r"C:\Users\Gstar\OneDrive\Documents\COURS")
ARSENAL_PATH = PROJECT_ROOT.parent / "ArsenalArguments"
# Racine du contenu Droit produit par le projet Cartable (transcriptions, fiches,
# méthodo, arrêts). Additif : coexiste avec COURS_ROOT (archive L1 Info), ne le
# remplace pas. Navigué par `_scripts/dialogue/droit_resolver.py`. Le câblage
# GUI/app/prompt_builder reste à faire en session supervisée : cf. le handoff
# d'intégration côté Cartable (`Cartable/_handoff/04_INTEGRATION_COMPAGNON.md`).
CARTABLE_ROOT = PROJECT_ROOT.parent / "Cartable" / "DROIT"

# ============================================================ Sous-dossiers projet

SCRIPTS_DIR = PROJECT_ROOT / "_scripts"
PROMPTS_DIR = PROJECT_ROOT / "_prompts"
SESSIONS_DIR = PROJECT_ROOT / "_sessions"
PHOTOS_INBOX_DIR = PROJECT_ROOT / "_photos_inbox"
CACHE_DIR = PROJECT_ROOT / "_cache"
TTS_CACHE_DIR = CACHE_DIR / "tts"
SECRETS_DIR = PROJECT_ROOT / "_secrets"
LOGS_DIR = PROJECT_ROOT / "_logs"
AUDIO_LOGS_DIR = LOGS_DIR / "audio"
# Phase A.10.2 (2026-05-14) : les uploads de pièces jointes en séance
# (photos / PDF / Excel envoyés au tuteur) vivent désormais ici plutôt
# que sous COURS_ROOT. Friction d'origine : « c'est débile que les
# photos soit dans COURS/ car tout ne concerne pas les cours »
# (sessions Sujet libre, Workspace, etc.). Arborescence :
#   _uploads/{session_id}/photos/<file_vN.ext>
#   _uploads/{session_id}/attachments/<file_vN.ext>
# Les sessions antérieures gardent leurs photos sous COURS/ ; le
# backfill A.10.1 les détecte via le markdown du transcript.
UPLOADS_DIR = PROJECT_ROOT / "_uploads"

# ============================================================ Fichiers spéciaux

ENGINE_PREF_PATH = SECRETS_DIR / "engine_pref.json"
RUNTIME_SETTINGS_PATH = SECRETS_DIR / "runtime_settings.json"
REMOTE_ACCESS_PATH = SECRETS_DIR / "remote_access.json"
PROMPT_SYSTEME_PATH = PROMPTS_DIR / "PROMPT_SYSTEME_COMPAGNON.md"
# Phase Z.8 (2026-05-09) : ex-PROMPT_SYSTEME_LECTURE renommé.
# Le mode `lecture` a été supprimé, absorbé entièrement par `guidé`.
# Le prompt tuteur (posture tuteur + accès FS Read/Grep + SUGGESTED_EDIT)
# reste utilisé tel quel par le mode guidé, juste renommé pour cohérence.
PROMPT_SYSTEME_GUIDE_PATH = PROMPTS_DIR / "PROMPT_SYSTEME_GUIDE.md"
# Phase A.8 (2026-05-12) : nouveau prompt pour le mode `découverte`.
# Tuteur explicateur zéro prérequis, génère un PDF d'énoncé d'entraînement
# en début de séance via la balise <<<SAVE_INVENTED_PDF>>>.
PROMPT_SYSTEME_DECOUVERTE_PATH = PROMPTS_DIR / "PROMPT_SYSTEME_DECOUVERTE.md"
# Phase A.9 (2026-05-13) : prompt pour le mode `workspace` (tutorat sur un
# dossier arbitraire hors COURS/, avec accès Read/Grep/Glob scopé via cwd).
# Activé via la checkbox `📁 Workspace` + folder picker dans la GUI Tk.
PROMPT_SYSTEME_WORKSPACE_PATH = PROMPTS_DIR / "PROMPT_SYSTEME_WORKSPACE.md"

# Phase A.10.13a (2026-05-14) : `GENERATED_DIR` (dossier `_generated/` qui
# stockait les PDFs d'énoncés inventés par le tuteur Découverte) retiré.
# Le mode invented PDF a été supprimé : le tuteur invente ses questions
# au fil de la conversation, plus pertinent pédagogiquement qu'un PDF
# figé en début de séance. User : « le mode qui créé des énoncés ça sert
# à rien car vaut mieux que compagnon créé en fonction de la personne ».

# Phase A.10.11 (2026-05-14) : `ARCHIVES_DIR` (le dossier `_archives/` qui
# stockait l'archive .md miroir des sessions) a été retiré. Feature jugée
# redondante avec le JSON de session par l'user : le live-archive .md à
# chaque tour ajoutait de l'I/O disque pour zéro usage réel (l'UI permet
# déjà de relire toutes les sessions). Le dossier disque peut subsister
# en local, il est ignoré par le code.

# ============================================================ Timezone

TIMEZONE = ZoneInfo("Europe/Paris")

# ============================================================ Versions de schéma

SCHEMA_VERSION_SESSION = 1
SCHEMA_VERSION_ENGINE_PREF = 1
SCHEMA_VERSION_RUNTIME_SETTINGS = 1
SCHEMA_VERSION_REMOTE_ACCESS = 1

# ============================================================ Moteur Claude par défaut

DEFAULT_ENGINE = "cli_subscription"  # cf. CLAUDE.md §5.3
