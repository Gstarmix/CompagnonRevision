# ARCHITECTURE.md : Compagnon_Revision

> **Spec technique détaillée pour Claude Code.**
> Lu en complément de `CLAUDE.md` au début de chaque session de développement.
> Édition autorisée par Claude Code uniquement sur autorisation explicite de Gstar (cf. CLAUDE.md §10.1).

---

## 0. À LIRE AVANT TOUTE CHOSE

Ce document spécifie **comment** coder le compagnon de révision. `CLAUDE.md` dit *quoi* coder et *avec quelles règles*. Ce document dit *comment* assembler les briques, quels schémas JSON utiliser, quelles signatures de fonctions exposer, comment gérer le streaming SSE, etc.

L'ordre de lecture recommandé :
1. `CLAUDE.md` (manuel d'instructions générales)
2. `_prompts/PROMPT_SYSTEME_COMPAGNON.md` (mode colle) **et** `_prompts/PROMPT_SYSTEME_GUIDE.md` (mode guidé, Phase A.7+)
3. Ce fichier (spec technique)
4. `CHANGELOG.md` (narratif des phases A.5 → A.7.1, pour comprendre **pourquoi** chaque pivot)

État actuel de la spec : **synchronisée avec Phase A.7.1 (commit doc-sync 2026-05-05)**. Sections initiales décrites comme « Phase A » d'origine, complétées par des paragraphes « **Updates Phase A.5+** » dans les sections impactées.

---

## 1. VUE D'ENSEMBLE : FLUX DE DONNÉES

### 1.1 Boucle de session : schéma général

```
┌─────────────────────────────────────────────────────────────────────┐
│                       FRONT FLASK (navigateur)                      │
│  ┌─────────────────┐    ┌──────────────┐    ┌──────────────────┐    │
│  │ Push-to-talk    │    │ Zone dialogue│    │ Sidebar quota    │    │
│  │ (espace global) │    │ (SSE stream) │    │ (poll 60s)       │    │
│  └────────┬────────┘    └──────▲───────┘    └────────▲─────────┘    │
└───────────┼────────────────────┼─────────────────────┼──────────────┘
            │ keyboard event     │ SSE events          │ HTTP poll
            ▼                    │                     │
  ┌─────────────────────────────────────────────────────────────────┐
  │                     FLASK APP (port 5680)                       │
  │  /api/start_session  /api/send_message  /api/stream_response    │
  │  /api/end_session    /api/quota                                 │
  │  /api/transcribe (Phase A.6.2)  /api/apply_edit (Phase A.7)     │
  └────┬────────────────────────────────┬───────────────┬───────────┘
       │                                │               │
       ▼                                ▼               │
  ┌──────────────┐                 ┌──────────────┐    │
  │ AUDIO        │                 │ DIALOGUE     │    │
  │ listener.py  │ ──[wav bytes]──▶│ claude_client│    │
  │ (sounddevice)│                 │              │    │
  └──────┬───────┘                 │ ┌──────────┐ │    │
         │                         │ │parser.py │ │    │
         ▼                         │ │ (states) │ │    │
  ┌──────────────┐                 │ └──────────┘ │    │
  │ transcribe_  │                 │              │    │
  │ stream.py    │ ──[texte]──────▶│              │    │
  │ (faster-     │                 │              │    │
  │  whisper GPU)│                 │              │    │
  └──────────────┘                 └──────┬───────┘    │
                                          │            │
                                          ▼            │
                                   ┌──────────────┐    │
                                   │session_state │    │
                                   │ (JSON atomic)│    │
                                   └──────────────┘    │
                                                       │
                                          ┌────────────┘
                                          ▼
                                   ┌──────────────┐
                                   │quota_check.py│
                                   │ (Arsenal)    │
                                   └──────────────┘
```

### 1.2 Phases d'une session
1. **Démarrage** : check quota → résolution contexte via `cours_resolver` (énoncé + corrigé officiel + TACHE perso + script perso + slides + transcription CM) → instancie `SessionState` → choix prompt système selon `mode` (colle / lecture) → ouvre conversation Claude → première question.
2. **Boucle dialogue** : entrée utilisateur via clavier OU bouton 🎤 toggle navigateur (Phase A.6.2 ; le hotkey global Espace est legacy) → si audio : `MediaRecorder` → POST `/api/transcribe` → Whisper GPU → texte → champ de saisie → user clique Envoyer → `/api/send_message` → SSE Claude → parser extrait balises → affichage front.
3. **Capture** :
   - Mode guidé : `<<<SUGGESTED_EDIT>>>` → forward SSE au front → carte avec diff + boutons Appliquer/Rejeter → POST `/api/apply_edit` après clic Appliquer → backup `.bak` + atomic write du fichier perso ciblé.
   - Mode guidé/guidé (Phase A.7.2 v15.1) : `<<<SHOW_DOC>>>{"kind":"enonce|correction|script","page":N}<<<END>>>` → forward SSE au front → switch tab Docs + jump à la page + bulle système marker. Gated par auto-advance opt-in (même flag que `<<<NEXT_SLIDE>>>`).
4. **Fin** : `<<<END_SESSION>>>` (mode colle) ou clic « Terminer » (mode guidé) → finalisation JSON (`ended_at`, `interrupted: false`) → réponse front avec récap → fermeture front.

### 1.3 Heartbeat (pour reprise de session interrompue)
En parallèle de la boucle dialogue, un thread daemon écrit `last_alive: ISO timestamp` toutes les 30 secondes dans le JSON de session via atomic write.

Au démarrage suivant du compagnon, scan de `_sessions/*.json` :
- Si une session a `interrupted: true` ou (`ended_at` absent ET `last_alive` < maintenant - 5 min), elle est marquée comme reprenable.
- Le front propose à Gstar : "Session AN1 TD5 ex3 du 02/05 interrompue, reprendre ?" (oui = `[RESUME_SESSION]` envoyé au prompt, non = nouvelle session).

### 1.4 Stratégie de reprise : replay vs résumé (Phase A.8.6)
`POST /api/resume_session` reconstruit l'historique du `ClaudeClient` selon `_should_replay_transcript(data)` (`app.py:6092`).

- **Replay (défaut)** : chaque tour du transcript est ré-injecté dans `client._history` un par un (rôle student/claude). Le tuteur reprend avec **tout le contexte fin** (notes prises, points abordés, où on s'arrêtait). Coût en tokens à la prochaine réplique = somme du transcript.
- **Résumé (cap hard)** : si `stats.total_exchanges >= REPLAY_HARD_CAP_EXCHANGES` (constante = `300`), bascule sur un résumé Gemini Flash ≤120 mots injecté comme tour synthétique. Cache dans `data["resume_summary"]` + invalidation auto si `last_alive > resume_summary_at`. Le tag UI `[résumé]` s'affiche dans `sessionInfo`.

Avant Phase A.8.6 le seuil était bien plus agressif (`< 10 tours OU last_alive < 6 h`), ce qui faisait perdre le contexte au moindre passage de nuit. Le user a explicitement validé le coût en tokens d'un replay quasi-systématique.

---

## 2. SCHÉMA JSON D'UNE SESSION (DÉTAILLÉ)

### 2.1 Format complet
Fichier `_sessions/YYYY-MM-DD_{MAT}_{TYPE}{N}_ex{n}_{mode}_{format}_{anchor}.json`
(Phase A.8.6 : suffixe `_{mode}_{format}_{anchor}` ajouté pour permettre la
cohabitation de plusieurs sessions d'un même exo avec des postures différentes ;
cf. CHANGELOG Phase A.8.6 et CLAUDE.md §7) :

```json
{
  "schema_version": 1,
  "session_id": "2026-05-02_AN1_TD5_ex3_colle_mixte_strict",
  "matiere": "AN1",
  "type": "TD",
  "num": "5",
  "exo": "3",
  "annee": null,
  "mode": "colle",
  "colle_format": "mixte",
  "corrige_anchor": "strict",

  "started_at": "2026-05-02T19:30:00+02:00",
  "ended_at": "2026-05-02T20:18:42+02:00",
  "last_alive": "2026-05-02T20:18:42+02:00",
  "interrupted": false,
  "interrupted_at": null,
  "resumed_at": null,
  "duration_seconds": 2922,

  "engine": "cli_subscription",
  "model": "claude-opus-4-7",

  "context_files": {
    "enonce": "AN1/TD/TD5/enonce_TD5_AN1.pdf",
    "corrections": ["AN1/TD/TD5/corrections/correction_TD5_ex3_AN1.pdf"],
    "tache": "AN1/TD/TD5/TACHE_AN1_TD5_ex3.md",
    "script_oral": "AN1/TD/TD5/scripts_oraux/script_oral_AN1_TD5_global_transcription.txt",
    "slides_pdf": "AN1/TD/TD5/scripts_oraux/slides_AN1_TD5_global_transcription.pdf",
    "transcription_cm": "AN1/CM/CM6_AN1_dérivation.txt",
    "poly_cm": "AN1/CM/poly_AN1_ISTIC_Etude_fonction.pdf"
  },

  "transcript": [
    {
      "role": "claude",
      "at": "2026-05-02T19:30:05+02:00",
      "text": "Exercice 3. Énoncez la première chose que vous comptez faire."
    },
    {
      "role": "student",
      "at": "2026-05-02T19:30:24+02:00",
      "text": "Heu, je vais dériver la fonction.",
      "audio_path": "_logs/audio/2026-05-02_19-30-24.wav"
    },
    {
      "role": "claude",
      "at": "2026-05-02T19:30:32+02:00",
      "text": "« Heu » n'est pas une démarche. Pourquoi dériver ?"
    }
  ],

  "stats": {
    "total_exchanges": 47,
    "claude_tokens_input": 18432,
    "claude_tokens_output": 3214,
    "whisper_seconds": 612.4,
    "tts_calls": 3,
    "photos_received": 0,
    "silences_detected": 4
  }
}
```

### 2.2 Champs obligatoires en écriture initiale
Au démarrage, le JSON est créé avec ces champs minimum :
```json
{
  "schema_version": 1,
  "session_id": "...",
  "matiere": "...",
  "type": "...",
  "num": "...",
  "exo": "...",
  "started_at": "...",
  "last_alive": "...",
  "interrupted": false,
  "engine": "...",
  "model": "...",
  "context_files": {...},
  "transcript": [],
  "stats": {
    "total_exchanges": 0,
    "claude_tokens_input": 0,
    "claude_tokens_output": 0,
    "whisper_seconds": 0.0,
    "tts_calls": 0,
    "photos_received": 0,
    "silences_detected": 0
  }
}
```

`ended_at`, `interrupted_at`, `resumed_at` restent à `null` jusqu'à l'événement correspondant. `duration_seconds` est calculé à la fin.

### 2.3 Conventions
- **Toutes les dates en ISO 8601 avec timezone** : `2026-05-02T19:30:00+02:00`. Utiliser `zoneinfo.ZoneInfo("Europe/Paris")` (cf. pattern Arsenal).
- **`session_id`** : identique au nom du fichier sans `.json`. Format Phase A.8.6 = `YYYY-MM-DD_{MAT}_{TYPE}{N}_ex{n}_{mode}_{format}_{anchor}` (le mode est slugifié en ASCII : `guidé→guide`, `découverte→decouverte`). Le suffixe permet à plusieurs versions du même exo de cohabiter selon la posture choisie. Utilisé pour les références croisées (logs).
- **`audio_path`** dans transcript : chemin relatif au projet, peut être absent si Whisper a transcrit en streaming sans persister le WAV.

### 2.4 Migration de schéma
Pour toute évolution **destructive** de schéma :
1. Incrémenter `schema_version`
2. Ajouter une fonction `_migrate_v{N-1}_to_v{N}(data: dict) -> dict` dans `session_state.py`
3. Au load d'un JSON, si `schema_version` < courant, appliquer toutes les migrations en chaîne avant validation
4. Le fichier est réécrit (atomic write) à la version courante au prochain `flush()`

Les **ajouts additifs** (nouveaux champs optionnels) ne bumpent pas la version. Exemple : `mode` (Phase A.7) et `annee` (Phase A.5) ont été ajoutés sans bump car les anciens lecteurs les ignorent et les anciens fichiers récupèrent les défauts via `_default_settings`-like dans `runtime_settings.py` (pour les settings) ou un simple `data.setdefault(...)` au load (pour les sessions).

### 2.5 Updates Phase A.5+

- **Champ `annee`** (Phase A.5) : string ou null. Requis pour les CC multi-millésimes (ex `"2025-26"`), null sinon. Le resolver `cours_resolver.find_enonce_pdf` filtre dessus.
- **Champ `mode`** (Phase A.7 → Z.8) : `"colle"` (défaut) ou `"guidé"`. L'ex-mode `"lecture"` a été supprimé Phase Z.8 (2026-05-09), absorbé par `"guidé"`. Le backend choisit le bon prompt système (`PROMPT_SYSTEME_COMPAGNON.md` ou `PROMPT_SYSTEME_GUIDE.md`) et configure le `ClaudeClient` avec ou sans tools FS.
- **`context_files`** (Phase A.5) : 4 nouveaux chemins possibles, à savoir `corrections` (liste, peut être multi pour mode `full`), `tache`, `script_oral`, `slides_pdf`. Tous optionnels, omis si non trouvés par le resolver.

---

## 3. MACHINE À ÉTATS DU PARSER SSE

### 3.1 Problème à résoudre
Le streaming SSE de Claude renvoie le texte en chunks. Une balise `<<<TTS>>>...<<<END>>>` peut arriver sur 5 chunks séparés. Le front Flask ne doit jamais voir le contenu d'une balise (qui est destiné au parser, pas à Gstar).

Solution : machine à états qui buffère pendant qu'on est "à l'intérieur potentielle" d'une balise.

### 3.2 États
```python
from enum import Enum

class ParserState(Enum):
    OUTSIDE = "outside"              # texte normal, on flush vers le front
    PROBE_OPENING = "probe_opening"  # on a vu '<' ou '<<' ou '<<<', incertitude
    INSIDE_TTS = "inside_tts"        # on est entre <<<TTS>>> et <<<END>>>
    INSIDE_SUGGESTED_EDIT = "inside_suggested_edit"  # Phase A.7-light, mode guidé
    INSIDE_GOTO_SLIDE = "inside_goto_slide"          # mode guidé, saut arbitraire
    INSIDE_SHOW_DOC = "inside_show_doc"              # mode guidé, panneau Docs
    INSIDE_SAVE_INVENTED_PDF = "inside_save_invented_pdf"  # Phase A.8, mode découverte
    INSIDE_END_SESSION = "inside_end_session"  # on a vu <<<END_S, on attend la fin
    PROBE_CLOSING = "probe_closing"  # on a vu '<' à l'intérieur d'une balise
```

### 3.3 Transitions

```
État courant         Input              → Nouvel état           Action
──────────────────────────────────────────────────────────────────────────
OUTSIDE              char != '<'        OUTSIDE                 flush char
OUTSIDE              '<'                PROBE_OPENING           buffer '<'

PROBE_OPENING        complète à '<<<TTS>>>'           INSIDE_TTS              consomme la balise
PROBE_OPENING        complète à '<<<END_SESSION>>>'   END                     émet event END_SESSION
PROBE_OPENING        ne matche aucun pattern         OUTSIDE                 flush le buffer

INSIDE_TTS           char != '<'        INSIDE_TTS              accumule dans tts_buffer
INSIDE_TTS           '<'                PROBE_CLOSING (depuis INSIDE_TTS)

PROBE_CLOSING        complète à '<<<END>>>'          OUTSIDE                 émet event TTS(tts_buffer), reset
PROBE_CLOSING        ne matche pas      retour à l'état parent  buffer rejoint le contenu
```

### 3.4 Implémentation suggérée : `_scripts/dialogue/parser.py`

```python
import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)

class ParserEventType(Enum):
    TEXT_CHUNK = "text_chunk"        # texte à afficher au front
    TTS = "tts"                       # phrase à vocaliser
    END_SESSION = "end_session"       # fin de séance

@dataclass
class ParserEvent:
    type: ParserEventType
    payload: str | dict

# Balises supportées (ouverture)
_TAG_TTS_OPEN = "<<<TTS>>>"
_TAG_END_SESSION = "<<<END_SESSION>>>"
_TAG_CLOSE = "<<<END>>>"

# Pour la reconnaissance partielle pendant le buffering
_OPENING_PATTERNS = [_TAG_TTS_OPEN, _TAG_END_SESSION]

class StreamParser:
    """Machine à états qui consomme un stream SSE caractère par caractère
    et émet des événements pour le front et la couche dialogue.

    Tolérant aux malformations : une balise au JSON invalide est loggée
    comme warning et l'événement n'est pas émis (la session continue).
    """

    def __init__(self, on_event: Callable[[ParserEvent], None]):
        self._on_event = on_event
        self._state: ParserState = ParserState.OUTSIDE
        self._buffer: str = ""        # buffer pendant probe
        self._inner_buffer: str = ""  # contenu entre balises (TTS text, WP json)
        self._return_state: Optional[ParserState] = None  # pour PROBE_CLOSING

    def feed(self, chunk: str) -> None:
        """Consomme un chunk de stream et émet les événements appropriés."""
        for char in chunk:
            self._step(char)

    def flush(self) -> None:
        """Vide ce qui reste à la fin du stream. Le buffer en cours, s'il existe,
        est traité comme du texte normal (cas de stream tronqué sans balise fermante).
        """
        if self._buffer:
            self._emit(ParserEventType.TEXT_CHUNK, self._buffer)
            self._buffer = ""
        if self._state != ParserState.OUTSIDE:
            logger.warning(
                "Stream tronqué dans état %s, contenu %r perdu",
                self._state, self._inner_buffer
            )
            self._inner_buffer = ""
            self._state = ParserState.OUTSIDE

    def _step(self, char: str) -> None:
        # Implémentation de la machine à états (voir §3.3)
        # ... (à coder par Claude Code en suivant la table de transitions)
        raise NotImplementedError

    def _emit(self, event_type: ParserEventType, payload) -> None:
        self._on_event(ParserEvent(type=event_type, payload=payload))
```

### 3.5 Tests `tests/test_parser.py`
Cas Phase A :
1. Texte simple sans balise → tout flushé en TEXT_CHUNK
2. `<<<TTS>>>Bonjour<<<END>>>` complet en un chunk → 1 event TTS
3. `<<<TTS>>>Bonjour<<<END>>>` coupé en 5 chunks → 1 event TTS
4. `Salut <<<TTS>>>OK<<<END>>> suite` → 3 events (TEXT, TTS, TEXT)
5. `<<<END_SESSION>>>` seul → 1 event END_SESSION
6. Faux positif `<<<X>>>` (pas une balise reconnue) → flush comme texte
7. Stream tronqué pendant `<<<TT...` → buffer perdu, warning logué, état revient à OUTSIDE

Cas Phase A.7-light (7) ajoutés pour `SUGGESTED_EDIT` :
1. Balise valide → 1 event SUGGESTED_EDIT avec dict parsé (file/before/after/reason)
2. Balise coupée en chunks de 7 → 1 event quand même
3. JSON malformé → 0 event, warning logué
4. Champ requis manquant → 0 event, warning logué
5. `before == after` (no-op) → 0 event, warning logué
6. `before` vide → 0 event, warning logué
7. `reason` absent (optionnel) → event émis sans erreur

### 3.6 Spec balise `<<<SUGGESTED_EDIT>>>` (Phase A.7-light)

Format :
```
<<<SUGGESTED_EDIT>>>{"file":"<rel>","before":"<exact>","after":"<new>","reason":"<court>"}<<<END>>>
```

Validation **light** côté parser :
- 3 champs requis strings : `file`, `before`, `after`
- `before` non-vide
- `before != after`
- `reason` optionnelle, coercée en string si présente

La validation de **sécurité** (chemin sous COURS_ROOT, no traversal `..`, extension whitelist `.md`/`.txt`, unicité de `before` dans le fichier) est faite au moment de l'**application** par `/api/apply_edit` (cf. §8.1.B). Le parser émet juste l'event `SUGGESTED_EDIT` avec le dict : c'est le backend qui ré-arbitre quand l'utilisateur clique Appliquer.

### 3.7 Spec balise `<<<SAVE_INVENTED_PDF>>>` (Phase A.8, mode découverte)

Format :
```
<<<SAVE_INVENTED_PDF>>>{"title":"<court>","content_md":"<markdown>","source_label":"inspiré du corrigé officiel|sans corrigé"}<<<END>>>
```

Validation **light** côté parser (`_try_parse_save_invented_pdf`) :
- 2 champs requis non-vides : `title`, `content_md` (strings)
- `source_label` optionnel, défaut « sans corrigé », coercé en string si présent
- Cap soft sur `content_md` à 50 000 chars (au-delà : warning + troncation)

La **génération effective du PDF** (render markdown → PDF reportlab, sauvegarde dans `_generated/<session_id>_enonce.pdf`, rasterisation des PNGs, injection dans le panneau Docs) est faite côté backend Flask quand l'event `SAVE_INVENTED_PDF` arrive dans le pipeline SSE. Le tuteur émet la balise une seule fois par séance, en début de séance (cf. `PROMPT_SYSTEME_DECOUVERTE.md` §1.6).

L'event SSE `invented_pdf_ready` est poussé au front avec `{path, pages, bytes, title, source_label, duration_s, label, filename, pdf_url}`. Le front pose un marker chat « 📄 Énoncé sauvegardé en X.Ys » et déclenche `initCorrectionsPanel()` pour rafraîchir le picker Docs (le PDF inventé apparaît en TÊTE, kind `enonce_invente`).

Le PDF généré est servi via `/api/generated/<filename>` (PDF lui-même) et ses PNGs rasterisés via `/api/generated_file?path=<rel>`, pendant de `/api/cours_file` mais scopé à `_generated/` au lieu de `COURS/`. Sécurité anti-traversal par `Path.resolve().relative_to(GENERATED_DIR.resolve())`.

---

## 4. CLIENT CLAUDE : `_scripts/dialogue/claude_client.py`

### 4.1 Responsabilités
- Lit `_secrets/engine_pref.json` pour savoir s'il appelle CLI subscription ou API Anthropic
- Construit la requête (system prompt + historique + nouveau message utilisateur)
- Streame la réponse en SSE
- Délègue le parsing au `StreamParser`
- Track les tokens consommés (si dispo)

### 4.2 Interface publique
```python
from typing import Iterator, Callable
from pathlib import Path
from .parser import StreamParser, ParserEvent

class ClaudeClient:
    """Wrapper unique pour les deux moteurs (CLI subscription / API Anthropic)."""

    def __init__(
        self,
        engine: str,                          # "cli_subscription" | "api_anthropic"
        system_prompt: str,                    # contenu du prompt système courant
        model: str = "claude-opus-4-7",
        max_tokens: int = 4096,
        mode: str = "colle",                   # Phase A.7 : "colle" | "guidé"
        cours_root: Path | None = None,        # Phase A.7 : requis si mode=lecture
    ):
        # Phase A.7 : `mode` détermine le subset d'outils CLI activé.
        # Mode guidé → `claude --print --allowedTools "Read,Grep,Glob"` +
        # `cwd=cours_root` pour scoper les Read au sous-arbre COURS/.
        # Mode colle → CLI sans flag tools (comportement par défaut).
        self._engine = engine
        self._system_prompt = system_prompt
        self._model = model
        self._max_tokens = max_tokens
        self._mode = mode
        self._cours_root = Path(cours_root) if cours_root else None
        self._history: list[dict] = []  # [{"role": "user"|"assistant", "content": "..."}]

    def append_user_message(self, text: str) -> None:
        """Ajoute un message utilisateur à l'historique sans appeler Claude."""
        self._history.append({"role": "user", "content": text})

    def stream_response(
        self,
        on_event: Callable[[ParserEvent], None],
    ) -> dict:
        """Appelle Claude avec l'historique courant, streame la réponse,
        et délègue le parsing à StreamParser.

        Returns: dict avec stats {"input_tokens": int, "output_tokens": int}
        Note: la réponse complète de Claude est ajoutée à l'historique.
        """
        if self._engine == "cli_subscription":
            return self._stream_via_cli(on_event)
        elif self._engine == "api_anthropic":
            return self._stream_via_api(on_event)
        else:
            raise ValueError(f"Engine inconnu : {self._engine}")

    def _stream_via_cli(self, on_event) -> dict:
        # subprocess.Popen sur `claude --print --output-format stream-json ...`
        # Parse les chunks JSON émis par le CLI, extrait le delta texte,
        # le passe à un StreamParser local.
        # En fin de stream : récupère les stats tokens depuis le dernier event JSON.
        ...

    def _stream_via_api(self, on_event) -> dict:
        # Utilise le SDK anthropic en mode streaming
        # client.messages.stream(...) avec system=self._system_prompt
        ...
```

### 4.3 CLI subscription : détails techniques
La CLI Claude expose un mode JSON streaming. Forme exacte utilisée en Phase A.7+ :

```
claude --print --output-format stream-json --include-partial-messages --verbose
       --append-system-prompt "<contenu prompt>"
       [--allowedTools "Read,Grep,Glob"]   # mode guidé seulement
       "<prompt user>"
```

Avec `cwd=COURS_ROOT` quand `mode=lecture` (les `Read` de Claude résolvent depuis cette racine).

L'env doit avoir `ANTHROPIC_API_KEY` unset pour forcer OAuth/keychain (cf. `start_claude_code_session.ps1`).

**Format des events stream-json** (CLI 2.1+) :
```json
{"type":"stream_event",
 "event":{"type":"content_block_delta",
          "delta":{"type":"text_delta","text":"ok"}}}
```
Le code `_extract_cli_delta` lit ce wrapping ; les events `"type":"assistant"` (qui contiennent le message complet) sont ignorés pour ne pas doublonner le streamé.

**Tools en mode guidé.** Le CLI exécute lui-même les outils (Read fichier, Grep regex, Glob pattern) et renvoie en flux mêlé : événements `tool_use` et `tool_result` cohabitent avec les `content_block_delta` text. Le parser SSE Compagnon ignore les events tool (il ne consomme que `text_delta`) : les résultats de tool ne sont pas affichés à l'utilisateur, seul le texte final de Claude après synthèse l'est. C'est exactement ce qu'on veut : Claude utilise les tools en silence, on voit juste sa réponse.

### 4.4 API Anthropic : détails techniques
```python
import anthropic
client = anthropic.Anthropic()  # lit ANTHROPIC_API_KEY depuis env
with client.messages.stream(
    model="claude-opus-4-7",
    max_tokens=4096,
    system=self._system_prompt,
    messages=self._history,
) as stream:
    for text in stream.text_stream:
        parser.feed(text)
    parser.flush()
    final_message = stream.get_final_message()
    return {
        "input_tokens": final_message.usage.input_tokens,
        "output_tokens": final_message.usage.output_tokens,
    }
```

### 4.5 Gestion d'erreurs
- **CLI quota épuisé** : la CLI retourne un code erreur ou un message JSON spécifique. Catch, log, propose à Gstar via le front de switcher en API Anthropic.
- **API rate limit** : retry exponential backoff (max 3 tentatives, 1s/2s/4s).
- **Network error** : log + retry x1, sinon erreur remontée au front avec message clair.

---

## 5. PROMPT BUILDER : `_scripts/dialogue/prompt_builder.py`

### 5.1 Responsabilités
- Charge le prompt système (`_prompts/PROMPT_SYSTEME_COMPAGNON.md`), invariant
- Assemble le **contexte initial** de la session (variable selon TD/CC/exo)
- Compose le premier message utilisateur qui démarre la conversation

### 5.2 Format du contexte initial
Le contexte initial est envoyé comme **premier message utilisateur** (role=user) à Claude. Il inclut :

```
=== CONTEXTE DE LA SÉANCE ===

Matière : AN1 (Analyse 1)
Type : TD 5
Exercice ciblé : exercice 3
Date : 2026-05-02
Heure de début : 19:30
Durée prévue : 45-60 minutes

=== ÉNONCÉ DE L'EXERCICE ===

[contenu extrait du PDF AN1_TD5_enonce.pdf, exercice 3 uniquement
 si extractible, sinon TD entier avec mention "ciblez ex3"]

=== TRANSCRIPTION CM PERTINENTE ===

[contenu de AN1/CM/CM6_AN1_dérivation.txt, sections relatives au sujet
 de l'exercice si identifiables, sinon CM entier avec un cap à ~4000 mots]

=== POLY DU PROF (extraits) ===

[si disponible : extraits OCR/lecture du PDF poly relevant
 sinon section omise]

=== INSTRUCTIONS ===

Démarrez la séance. Posez la première question selon §2.2 du prompt système.
```

### 5.3 Interface publique
```python
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

@dataclass
class SessionContext:
    matiere: str
    type: str           # "TD" | "CC" | "Examen"
    num: str
    exo: str            # "3" ou "full"
    enonce_path: Path   # absolu
    cm_transcription_path: Optional[Path] = None
    cm_poly_path: Optional[Path] = None

class PromptBuilder:
    def __init__(self, system_prompt_path: Path, cours_root: Path):
        self._system_prompt = system_prompt_path.read_text(encoding="utf-8")
        self._cours_root = cours_root

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    def build_initial_context_message(
        self,
        ctx: SessionContext,
        is_resume: bool = False,
    ) -> str:
        """Construit le premier message user à envoyer à Claude.

        Si is_resume=True, ajoute le marker [RESUME_SESSION] et un récap court
        des derniers échanges de la session interrompue.
        """
        ...
```

### 5.4 Extraction de l'énoncé d'un PDF
Phase A : extraction texte via `pypdf2` ou `pdfplumber`. Si l'extraction est de mauvaise qualité (PDF scanné), fallback : injection du PDF entier en multimodal Claude (mais ça consomme plus de tokens).

Pour Phase A, on accepte l'extraction texte simple. La qualité sera évaluée à l'usage.

---

## 6. SESSION STATE : `_scripts/dialogue/session_state.py`

### 6.1 Responsabilités
- Crée et maintient le JSON de session
- Atomic write à chaque modification structurelle
- Heartbeat thread qui met à jour `last_alive` toutes les 30s
- Gère la finalisation (calcul `duration_seconds`, écriture `ended_at`, etc.)

### 6.2 Interface publique
```python
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional

class SessionState:
    HEARTBEAT_INTERVAL_SECONDS = 30

    def __init__(
        self,
        session_id: str,
        sessions_dir: Path,
        context: SessionContext,
        engine: str,
        model: str,
    ):
        self._path = sessions_dir / f"{session_id}.json"
        self._data: dict = self._build_initial_data(...)
        self._lock = threading.Lock()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_heartbeat = threading.Event()

    def start(self) -> None:
        """Crée le fichier JSON et démarre le heartbeat thread."""
        ...

    def append_exchange(self, role: str, text: str, audio_path: Optional[Path] = None) -> None:
        """Ajoute un échange au transcript, atomic write."""
        ...

    def increment_stat(self, key: str, delta: float = 1) -> None:
        """Incrémente une stat (tokens, photos, etc.)."""
        ...

    def finalize(self, interrupted: bool = False) -> None:
        """Stoppe le heartbeat, écrit ended_at et duration_seconds, atomic write final."""
        ...

    @classmethod
    def load(cls, path: Path) -> "SessionState":
        """Charge une session existante (pour reprise)."""
        ...

    @classmethod
    def find_resumable(cls, sessions_dir: Path) -> list[Path]:
        """Liste les sessions reprenables (interrupted=true ou last_alive ancien)."""
        ...
```

### 6.3 Atomic write helper
À placer dans un module partagé (`_scripts/utils.py` à créer en Phase A) :
```python
import json
import os
from pathlib import Path

def atomic_write_json(path: Path, data: dict) -> None:
    """Écrit data en JSON dans path de façon atomique (.tmp + os.replace)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
```

### 6.4 Heartbeat thread
```python
def _heartbeat_loop(self) -> None:
    while not self._stop_heartbeat.is_set():
        with self._lock:
            self._data["last_alive"] = _now_iso()
            atomic_write_json(self._path, self._data)
        self._stop_heartbeat.wait(self.HEARTBEAT_INTERVAL_SECONDS)
```

Daemon=True pour qu'il meure automatiquement avec le process principal en cas de crash brutal. Le `last_alive` ancien permettra alors la détection à la reprise.

---

## 7. AUDIO : DEUX VOIES POUR L'ENTRÉE VOCALE

> **Phase A.6.2 update.** L'entrée vocale principale est désormais le **bouton 🎤 toggle** dans le navigateur (`MediaRecorder` côté browser → `POST /api/transcribe`), à la Claude.ai. Le hotkey clavier global Espace via `listener.py` reste comme **legacy** (case décochée par défaut dans la GUI), conservé pour les workflows hands-on-keyboard ou en cas de fallback. Les deux voies aboutissent au même `WhisperTranscriber` côté Python.

### 7.0 Voie principale : `MediaRecorder` côté navigateur (Phase A.6.2)

Le front (`static/app.js`) :
1. Click micro → `navigator.mediaDevices.getUserMedia({audio:true})`
2. `MediaRecorder` avec MIME préféré `audio/webm;codecs=opus` (fallback laissé au navigateur)
3. Chunks accumulés dans `recordedChunks`
4. Click stop → `mediaRecorder.stop()` → `Blob` envoyé en multipart à `POST /api/transcribe`
5. Stream tracks libérées (le voyant micro de l'OS s'éteint)

Le backend (`app.py /api/transcribe`) :
1. Reçoit le multipart, sauve dans un tempfile (suffix dérivé du mimetype)
2. Lazy-load `WhisperTranscriber` au premier appel (singleton thread-safe via double-checked locking, ~5-10 s + 3 Go VRAM la première fois)
3. Renvoie `{"text": <transcription>, "duration_seconds": <float>}`
4. Cleanup du tempfile dans `finally`

Le front injecte la transcription dans le champ de saisie (concat si du texte est déjà tapé), l'utilisateur valide d'un clic Envoyer ou d'un Entrée. Pattern « édit avant envoi » à la Claude.ai.

### 7.1 Voie legacy : `_scripts/audio/listener.py` (push-to-talk)
```python
import sounddevice as sd
import numpy as np
import keyboard  # global hotkey, Windows-friendly
from pathlib import Path
from datetime import datetime

class PushToTalkListener:
    SAMPLE_RATE = 16000  # Whisper natif
    CHANNELS = 1
    HOTKEY = "space"

    def __init__(self, on_recording_complete):
        self._on_complete = on_recording_complete  # callback(wav_path: Path)
        self._is_recording = False
        self._frames: list[np.ndarray] = []
        self._stream: Optional[sd.InputStream] = None

    def start(self) -> None:
        keyboard.on_press_key(self.HOTKEY, self._on_press)
        keyboard.on_release_key(self.HOTKEY, self._on_release)

    def stop(self) -> None:
        keyboard.unhook_all()

    def _on_press(self, e) -> None:
        if self._is_recording:
            return
        self._is_recording = True
        self._frames = []
        self._stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            callback=self._audio_callback,
        )
        self._stream.start()

    def _on_release(self, e) -> None:
        if not self._is_recording:
            return
        self._is_recording = False
        self._stream.stop()
        self._stream.close()
        wav_path = self._save_wav()
        self._on_complete(wav_path)

    def _audio_callback(self, indata, frames, time, status):
        if status:
            logger.warning("Audio status: %s", status)
        self._frames.append(indata.copy())

    def _save_wav(self) -> Path:
        ...
```

### 7.2 `_scripts/audio/transcribe_stream.py` : wrapper Whisper
Phase A : version simple, **non-streaming** (transcription complète après que le WAV est sauvé). Le streaming Whisper viendra en Phase B si besoin.

```python
from faster_whisper import WhisperModel
from pathlib import Path

class WhisperTranscriber:
    def __init__(
        self,
        model_size: str = "large-v3",
        device: str = "cuda",
        compute_type: str = "int8_float16",
    ):
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, wav_path: Path, language: str = "fr") -> tuple[str, float]:
        """Retourne (texte_concaténé, durée_audio_secondes)."""
        segments, info = self._model.transcribe(
            str(wav_path),
            language=language,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
        )
        text = " ".join(seg.text.strip() for seg in segments)
        return text, info.duration
```

### 7.3 Détection de silence (pour `[SILENCE_10S]`)
Phase A : détection côté front Flask via le hotkey. Si aucune frappe espace dans les 10 secondes après une réponse Claude, le front envoie un message synthétique `[SILENCE_10S]` au backend, qui l'injecte comme un message utilisateur dans la conversation Claude.

---

## 8. FRONT FLASK : `_scripts/web/app.py`

### 8.1 Endpoints

| Méthode | Path | Description |
|---------|------|-------------|
| GET | `/` | Page principale, sert `index.html` |
| GET | `/api/quota` | Snapshot quota (JSON), poll côté client toutes les 30 s (Phase v15.6.5). Retourne le snapshot Pro Max (`session_pct`, `weekly_pct`, etc.) **plus** un bloc `engines` : balance live DeepSeek via `GET /user/balance` + `key_present` / tier free RPM/TPM/RPD pour Groq/Gemini/Anthropic. Cache backend 30 s. |
| POST | `/api/start_session` | Démarre une session. Body : `{matiere, type, num, exo, annee?, mode?, colle_format?, corrige_anchor?, enonce_path?, …}`. Auto-résolution des chemins via `cours_resolver` si non fournis (Phase A.5). `mode` ∈ `{"colle"`, `"guidé"}` (Phase A.7 → Z.8 : `lecture` supprimé, absorbé par `guidé`). **Phase v15.7.4** : `colle_format` ∈ `{"oral", "photos", "mixte"}` (défaut `"mixte"`), persisté dans `session_state.data["colle_format"]` et propagé au `prompt_builder` qui injecte `[FORMAT COLLE : <fmt>]` après l'en-tête de séance (uniquement en mode colle). **Phase v15.7.30** : `corrige_anchor` ∈ `{"strict", "consultatif", "aucun"}` (défaut `"strict"` = comportement v0.5), aliases tolérés `sans_corrigé` / `sans corrige` → `aucun`. Persisté dans `session_state.data["corrige_anchor"]`, propagé au `prompt_builder` qui injecte `[ANCRAGE CORRIGÉ : <mode>]` (uniquement en mode colle) **et** skippe l'injection du bloc CORRIGÉ OFFICIEL si mode=`aucun`. Bascule à chaud via `/api/set_corrige_anchor` ou slash-commands. |
| POST | `/api/send_message` | Envoie un message user, retourne 202 puis SSE prend le relai |
| GET | `/api/stream_response` | SSE qui streame la réponse Claude après envoi user (events `text`, `tts`, `suggested_edit`, `end`, `done`, `error`) |
| POST | **`/api/transcribe`** | **Phase A.6.2** : Multipart audio → Whisper transcrit → `{text, duration_seconds}`. Lazy-load Whisper au premier appel. |
| POST | **`/api/apply_edit`** | **Phase A.7** : Body `{file, before, after}` → backup `.bak` + atomic write du fichier perso ciblé. Sécurités : chemin relatif sous COURS_ROOT, no traversal, whitelist `.md`/`.txt`, before unique. |
| GET | **`/api/saved_selections`** | **Phase v15.7.23** : Liste les sélections de texte sauvegardées de la session active. Réponse `{selections: [{id, text, message_id, role, captured_at}], active: bool}`. |
| POST | **`/api/saved_selections`** | **Phase v15.7.23** : Sauvegarde une sélection. Body `{text, message_id?, role?}`. Validation text non vide ≤ 5000 chars, role ∈ {claude, student} default claude. Persiste dans `session_state.data["saved_selections"]` (additif, conservé en reprise). Réponse 200 = `{id, text, message_id, role, captured_at}`. Codes 400 (text vide / trop long), 409 (pas de session). |
| DELETE | **`/api/saved_selections/<id>`** | **Phase v15.7.23** : Supprime une sélection par id. Codes 204 (OK), 404 (id inconnu), 409 (pas de session). |
| GET | **`/api/session_photos`** | **Phase A.9.1** : Liste les photos archivées de la session active. Réponse `{photos: [{id, rel_path, filename, original_name, mime, size_bytes, sent_at}], active: bool}`. Galerie auto alimentée par chaque `send_message` qui embarque des attachments `is_image=True` (champ additif `session_photos[]` dans le JSON de séance, pas de bump). Whitelist viewer (lecture seule). |
| DELETE | **`/api/session_photos/<id>`** | **Phase A.9.1** : Retire une photo de la galerie de session. Le fichier disque (sous `_uploads/{session_id}/photos/` depuis A.10.2, ou `COURS/.../photos/` pour les sessions legacy) est **conservé** (cohérent avec `pending_attachments` DELETE qui ne touche que la queue). Codes 204 (OK), 404 (id inconnu), 409 (pas de session). |
| GET | **`/api/upload_file?path=...`** | **Phase A.10.2** : Pendant de `/api/cours_file` mais sert depuis `UPLOADS_DIR` (`Compagnon_Revision/_uploads/`) au lieu de `COURS_ROOT`. Reçoit le path relatif à `UPLOADS_DIR` (format typique `{session_id}/photos/{file_vN.ext}`). Sécurité anti-traversal + whitelist d'extensions identique (png/jpg/jpeg/webp/gif/svg/pdf). Route appelée par le front quand le markdown contient un préfixe `_uploads/` (cf. helper `_attachmentSrcUrl` dans `app.js`). Codes 400 (param/chemin invalide), 403 (hors UPLOADS_DIR), 404 (fichier introuvable), 415 (extension non servable). Whitelist viewer. |
| GET | **`/api/stickies`** | **Phase A.10** : Liste les consignes épinglées de la session active. Réponse `{stickies: [{id, kind, text, source_message_id, created_at, edited_at, enabled}], active: bool}`. `kind ∈ {"user", "tutor"}`, `enabled` toggle pour désactiver l'injection LLM sans perdre la consigne. Whitelist viewer. |
| POST | **`/api/stickies`** | **Phase A.10** : Crée une sticky. Body `{text, source_message_id?, kind?}`. Validation : `text` ≤ 200 chars **après normalisation** (`" ".join(text.split())` collapse les espaces/newlines en un seul espace), kind default `"user"` (alias inconnu → fallback `"user"`). Réponse 200 = sticky dict complet. Codes 400 (text vide / trop long), 409 (pas de session). |
| PATCH | **`/api/stickies/<id>`** | **Phase A.10** : Édite une sticky existante. Body `{text?, enabled?}` (au moins l'un des deux). text re-normalisé et re-capé à 200 chars, `edited_at` set à now. Codes 200 (sticky updated), 400 (body vide / text invalide), 404 (id inconnu), 409 (pas de session). |
| DELETE | **`/api/stickies/<id>`** | **Phase A.10** : Supprime une sticky par id. Codes 204 (OK), 404 (id inconnu), 409 (pas de session). |
| POST | **`/api/stickies/import_from/<session_id>`** | **Phase A.10** : Importe les stickies d'une autre session. Body `{sticky_ids?: list[str]}` (si omis, importe **toutes** les enabled de la source ; sinon filtre). Anti-traversal sur `session_id` (refuse `..` / `/` / `\`). Nouveau ID régénéré par sticky, conserve kind + source_message_id, ajoute `imported_from`. Réponse `{ok, imported_count, imported: [...]}`. Codes 200 OK, 400 sticky_ids invalide, 404 session source introuvable, 409 pas de session active. |
| POST | **`/api/cancel_stream`** | **Phase v15.7.21** : Body `{action: "resume"|"delete_last_user"}` → set `_state.cancel_requested = True`. Le `_sse_generator` checke ce flag à chaque tick (`queue.get(timeout=0.5)`) et yield `event: cancelled` puis return. Si `action="delete_last_user"` : retire aussi le dernier message `role=user` du `client._history` ET le dernier `role=student` du `current_branch_path` du transcript persisté (atomic via `set_meta`). Helper `_remove_last_student_message`. Codes : 200 OK `{ok, action_applied, deleted_msg_id?}`, 400 (action invalide), 409 (pas de session). Sub-process LLM peut continuer en background quelques secondes : tokens consommés quoi qu'il arrive (compromis assumé vs `subprocess.kill()` par moteur). |
| POST | **`/api/ocr_photo`** | **Phase v15.7.20** : Body `{attachment_id, hint?}` → `{ocr_markdown, kind_detected, completeness_pct, warnings, engine, model}`. Pré-traitement OCR d'une photo via Gemini Flash 2.5 (engine forcé). Trouve l'image dans `_state.pending_attachments`, appelle `_run_isolated_lookup` avec `model_override="gemini-2.5-flash"` + system prompt `OCR_PHOTO_PROMPT` qui exige reproduction case par case avec marqueurs `(vide)` / `(illisible)` / `(raturé)`. Détecte `kind_detected` ∈ `{table_de_verite, schema_logique, calcul_pose, equation, dessin, pseudo_code, texte, autre}`. Codes : 400 (id manquant / non-image), 404 (id inconnu), 409 (pas de session), 429/502 (Gemini). Helper `_ocr_attachment_internal(att, hint)` réutilisable, best-effort. Intégré automatiquement dans `/api/send_message` quand mode colle + colle_format ∈ {photos, mixte} + image attachée → bloc OCR injecté dans le contexte tuteur ET renvoyé en `ocr_blocks` dans la réponse 202 pour affichage frontend. |
| POST | **`/api/refine_search_query`** | **Phases v15.7.14 + v15.7.15** : Body `{description, target: "web"\|"youtube", exclude?: [...]}` → `{query, alternatives, engine: "gemini_api", model: "gemini-2.5-flash", target, concept, level}`. **Engine forcé Gemini Flash** (peu importe la pref user, voir README). **Workflow 2-étapes (v15.7.15)** : (1) `INFER_CONCEPT_PROMPT` infère le concept sous-jacent + specs traduites en français + niveau pédagogique inféré (pas hardcodé) → balise `<<<CONCEPT>>>{json}<<<END>>>` ; (2) `REFINE_SEARCH_QUERY_PROMPT` compose la query depuis le concept clean + niveau → balise `<<<REFINED>>>{json}<<<END>>>`. Coût 2× ~$0.0001, latence ~3s. `exclude` propagé uniquement à l'étape 2. Codes : 400 (description vide), 429 (quota Gemini), 502 (SDK error / réponse vide à l'étape 1 ou 2, `step` indique laquelle). Utilisé par `performWebSearchExo` / `performFindYoutube` côté front (refine en amont, puis passe `refined_query` aux endpoints de recherche). |
| POST | **`/api/pending_attachments/<id>/replace`** | **Phase v15.7.10** : Multipart/form-data avec champ `file` = nouveau blob image (typiquement output de `canvas.toBlob` après Cropper.js côté client). Trouve l'attachment par id, refuse si non-image (400), écrit le nouveau fichier dans le même dossier avec suffixe `_cropped_vN`, mute l'entry en place (`rel_path`, `filename`, `mime`, `size_bytes`, `uploaded_at`, `cropped: true`). L'ancien fichier reste sur disque (cohérent avec DELETE qui ne touche que la queue). Garde anti-cumul de suffixes (`_cropped_v1_cropped_v1` → `_cropped_v2`). Codes : 200 OK, 400 (file manquant / non-image), 404 (id inconnu), 409 (pas de session). |
| POST | **`/api/set_colle_format`** | **Phase v15.7.4** : Body `{format: "oral"\|"photos"\|"mixte"}` (tolérance singulier `photo` → `photos`, casse insensible) → `{ok, colle_format}`. Persiste via `session_state.set_meta("colle_format", ...)` (atomic write) **et** injecte un marker synthétique `[FORMAT BASCULÉ → <fmt>]` dans le `_history` du `ClaudeClient` courant : le tuteur le verra à sa prochaine réplique et doit acquitter brièvement + adapter (règle §4.11 du prompt COMPAGNON, pas de discussion). Codes : 200 OK, 400 format invalide, 409 pas de session active. La **slash-command** `/oral`, `/photos` (ou `/photo`), `/mixte` détectée par `_SLASH_COLLE_FORMAT_RE` en début de message dans `/api/send_message` appelle le même `_apply_colle_format_change` interne et retourne 202 `{ok, slash_command:true, colle_format}` sans pousser au tuteur. |
| POST | **`/api/set_corrige_anchor`** | **Phase v15.7.30** : Body `{anchor: "strict"\|"consultatif"\|"aucun"}` (aliases tolérés `sans_corrigé` / `sans corrige` → `aucun`, casse insensible) → `{ok, corrige_anchor}`. Persiste via `session_state.set_meta("corrige_anchor", ...)` (atomic write) **et** injecte un marker synthétique `[ANCRAGE BASCULÉ → <mode>]` dans le `_history` du `ClaudeClient` : le tuteur acquitte d'un fragment et adapte (règle §4.12 du prompt COMPAGNON v0.6 : pas de résistance, interdit explicite de « le corrigé est pourtant la référence »). Codes : 200 OK, 400 invalide, 409 pas de session. **Limite assumée** : la bascule en cours de séance ne re-injecte PAS le bloc CORRIGÉ OFFICIEL dans le contexte si on est parti en `aucun` au start : le tuteur reste avec le contexte initial. Pour récupérer le corrigé, redémarrer la session. La **slash-command** `/strict`, `/consultatif`, `/aucun`, `/sans_corrigé` détectée par `_SLASH_CORRIGE_ANCHOR_RE` dans `/api/send_message` retourne 202 `{ok, slash_command:true, corrige_anchor}` sans pousser au tuteur. |
| POST | **`/api/session_recap`** | **Phase v15.7.31** : Sans body. Lance `_generate_session_recap(transcript)` (Gemini Flash 2.5, ~3-8s) qui produit JSON structuré `{summary, concepts_covered, exercises_handled, suggestions}`. Persiste `recap` + `phase="debrief"` + `recap_at` via `session_state.set_meta` (atomic write). Injecte `[PHASE DÉBRIEF ENGAGÉE]` dans le `_history` du tuteur (§1.7 du prompt → posture relâchée). **NE FINALISE PAS** la session (heartbeat continue, _state reste actif). **Idempotent** : si `phase` est déjà `debrief`/`closed`, retourne le cache sans re-générer. **Fail-soft** : si Gemini échoue ou produit du JSON cassé, retourne `recap` dégradé `{summary: raw_text, ...empty}` avec code 200. Codes : 200 OK, 409 pas de session. |
| POST | **`/api/session_close`** | **Phase v15.7.31** : Sans body. Vraie finalisation après débrief. Set `phase="closed"` + `final_closed_at` + appelle `session_state.finalize()` (ended_at, duration_seconds, stop heartbeat). Retourne `{ok, session_id, duration_seconds}`. Appelé par le bouton « 🚪 Fermer définitivement » de la carte récap frontend. L'ancien `/api/end_session` reste pour rétrocompat et fermeture brutale sans débrief. Codes : 200 OK, 409 pas de session. |
| POST | **`/api/mini_exo`** | **Phase v15.7.31** : Body `{concept, detail?, exercise_context?}` où `concept` est requis (souvent repris d'un concept du récap de débrief). Injecte marker `[MINI-EXO : concept='...' ; difficulté='...' ; context='...']` dans le `_history` du tuteur (§1.7bis du prompt → produit un exo court 3-5 questions ciblées). Set `st.retry_pending = True` pour que le prochain `GET /api/stream_response` streame sans `pending_user_text` à fournir (marker = la requête). Le front appelle ensuite `streamResponse()` directement. Codes : 200 OK, 400 (concept manquant), 409 pas de session. |
| POST | **`/api/browse_folder`** | **Phase v15.7.35** : Body `{path}` (relatif à COURS_ROOT, leading `/` strip). Retourne `{cwd, parent_path, entries: [{name, path_rel, is_dir, size?, kind?}]}`. Sécurité anti-traversal via `_is_under_cours_root` (path résolu doit être strictement sous COURS_ROOT). Heuristique `_classify_file` détecte 9 kinds : `script_md`, `script_txt`, `script_imprimable`, `slides_pdf`, `annale`, `aide_memoire`, `pdf`, `md`, `txt`, `other`. Filtre `.bak`, `.tmp`, `.pyc`, dotfiles. Tri : dossiers d'abord, alpha. Codes : 200 OK, 400 traversal détecté, 404 dossier inexistant, 500 IOError. |
| POST | **`/api/scan_with_ai`** | **Phase v15.7.35** : Body `{folder_path, force_refresh?}`. Cache `{dossier}/_compagnon_scan.json` valide tant que `cache_mtime >= max(folder_mtime, sub_folder_mtimes_lvl1)`. Sinon (ou `force_refresh=true`), `_scan_with_ai_internal` walke récursivement 2 niveaux + appelle Gemini Flash 2.5 (engine forcé) avec system prompt JSON-only. Parse + normalise les paths vers COURS_ROOT-relatif. Persist atomic write. Fail-soft : Gemini fail / JSON cassé → 200 avec payload dégradé `{script_oral_path: null, ..., error: "..."}`. Réponse : `{script_oral_path, slides_pdf_path, script_imprimable_path, confidence_0_100, reasoning, cached, scanned_at}`. Codes : 200 OK (toujours en happy path, dégradé inclus), 400 folder_path manquant, 404 dossier inexistant. |
| POST | **`/api/claude_code_prompt`** | **Phase v15.7.36** : Body `{kind, matiere?, type_code?, num?, ...}`. 2 kinds : `regen_script_md` (régénère SCRIPT_*.md Feynman depuis script_oral_*.txt continu + slides PDF) et `audit_matiere_cc` (rapport read-only orphelins script/slides). Si matière/type/num pas fournis explicitement → résolus depuis la session active (409 si pas de session ET pas d'overrides). Helpers `_build_prompt_regen_script_md` + `_build_prompt_audit_matiere_cc` génèrent ~80 lignes de prompt français aligné strictement sur `COURS/CLAUDE.md` (§1 séparation Claude Code/AI, §3 conventions nommage, §4 D workflow SCRIPT→.txt+slides, §6 RÈGLES ABSOLUES PRESERVE.md / atomic writes / pas suppression directe, §7 SPEC_script_oral_v2.md). Réponse `{prompt: str, kind, matiere, type_code, num}`. Codes 200/400 (kind invalide)/409. |
| GET | **`/api/guided/init`** *(étendu Phase v15.7.36)* | Quand `parse_script` retourne `structure.slides == []` (cas `.txt` sans headers `## [SLIDE N]`), **plus de 422**. Helper `_build_guided_init_lite_response` rasterise les slides PDF page-par-page et expose 1 slide synth par page (`title: "Page N/M"`, `oral_excerpt: début_txt si N==1 else ""`). Le tuteur a déjà le `.txt` complet via SCRIPT ORAL PERSO. Réponse 200 enrichie de `lite: true, lite_reason: str`. Le frontend affiche une bulle orange `.guided-lite-notice` avec bouton « 📝 Régénérer via Claude Code » qui appelle `/api/claude_code_prompt`. |
| POST | **`/api/rewrite`** | **Phase A.7.2 v15.6 + v15.7.1** : Body `{text, intent, context_tutor?}` avec `intent ∈ {reformulate, concise, expand, fix_typos}` → `{rewritten, intent, engine, context_chars}`. **v15.7.1** : `context_tutor` (str optionnel) = dernier message du Compagnon, capé à `REWRITE_MAX_CONTEXT_CHARS = 2000` chars (truncation par le **début**, on garde la fin du tour où la question reformulée se trouve typiquement). Si présent, préfixé en bloc `[Contexte : dernier message du tuteur] … [/Contexte]` dans le `user_msg`. `REWRITE_SYSTEM_PROMPT` durci : le contexte sert UNIQUEMENT à résoudre les pronoms (`celle/il/ça`) et aligner le vocabulaire technique sur celui du tuteur ; **interdit explicitement** d'ajouter/corriger/supprimer raisonnement, fait ou conclusion du brouillon (sinon le mode colle perd son intérêt : l'étudiant doit *trouver* son erreur de fond). One-shot Claude/Gemini/etc. via le moteur courant (`_read_engine_pref()`), mini-prompts dédiés par intent. Cap `REWRITE_MAX_INPUT_CHARS = 8000`. Strip des guillemets enveloppants `"…"` `'…'` `«…»`. Codes 400 (text vide / intent invalide / texte trop long), 429 (quota), 502 (SDK / réponse vide). |
| GET | **`/api/corrections/init`** | **Phase A.7.2 v15+ → Z.8.4** : liste les documents lisibles pour la session active : énoncé (`find_enonce_pdf`) **+** corrigés officiels (`resolve_corrections`) **+** script imprimable (`find_perso_script_imprimable`). Chaque entrée a `kind` (`"enonce"\|"correction"\|"script"`), `label`, `filename`, `pdf_path`, **`exo`** (extrait du filename via regex, Phase Z.8.4, `null` si pas de pattern `_exN` détecté), `total_pages`, `pages: [{n, png_url}]`. Ré-résout les chemins à chaque appel (fonctionne sur reprise). |
| POST | **`/api/find_similar_exo`** | **Phase Z.8.4 → Z.8.8 → Z.9** : Body `{description, difficulty?, exclude?}`. `difficulty ∈ {easier, harder, different, null}` (Z.9 B1). `exclude: [{matiere, type, num, exo}]` cap 20 : exos déjà proposés à éviter (Z.9 B2). Lance UN ClaudeClient jetable en `MODE_GUIDE` avec `cours_root=COURS/{matiere}/`. INTERDIT `Read` du corrigé du `(type, num)` en cours. Sortie `<<<EXO_FOUND>>>{json}<<<END>>>`. Réponse `{found, exo: {matiere, type, num, exo, label, why, enonce, enonce_pdf_path?, correction_pdf_paths?}, engine}` ou `{found: false, reason}`. Codes 400 / 409 / 429 / 502. **Conv principale non polluée**. |
| POST | **`/api/find_cm_passage`** | **Phase Z.9 (C2)** : Body `{description}`. Mode GUIDE scopé `COURS/{matiere}/CM/`. INTERDIT le corrigé en cours. System prompt `FIND_CM_PASSAGE_PROMPT_TEMPLATE` exige sortie `<<<CM_FOUND>>>{filename, label, page, extract, why}<<<END>>>`. Backend résout `pdf_path` via rglob. Réponse `{found, passage: {…, pdf_path}, engine}`. |
| POST | **`/api/web_search_exo`** | **Phase Z.9 (A1)** : Body `{description, exclude_urls?}`. Engines supportés : `api_anthropic` (tool `web_search_20250305`) et `gemini_api` (Search Grounding). Autres → 400 `engine_unsupported`. System prompt `WEB_SEARCH_EXO_PROMPT` privilégie sites éducatifs FR (Bibmath, Exo7, Wikiversité, Khan Academy FR, fiches-bac, kartable). Sortie `<<<WEB_FOUND>>>{results: [{title, url, source, why, kind}]}<<<END>>>`. |
| POST | **`/api/find_youtube_video`** | **Phase Z.9 (C3)** : Body `{description, exclude_urls?}`. Mêmes contraintes engine que `/api/web_search_exo`. Privilégie Yvan Monka, JeChercheUneOrange, Heu?reka, Science Étonnante. Sortie `<<<YT_FOUND>>>{results: [{title, url, channel, why}]}<<<END>>>`. |
| POST | `/api/upload_photo` | Upload manuel d'une photo (Phase B, stub en Phase A) |
| POST | `/api/end_session` | Force la fin propre |

**Body étendu `/api/send_message` (Phase A.7.2 v15)** :
```json
{
  "text": "Ok je vois la formule, expliquez-moi le passage à l'avant-dernière ligne.",
  "reading_state": {
    "kind": "correction",
    "label": "Toutes les corrections",
    "filename": "concat_TD5_EN1.pdf",
    "page": 2,
    "total": 4
  }
}
```
Si `reading_state` est présent et complet (`page > 0` et `total > 0`), le backend prefixe une ligne `[Contexte lecture actuelle : l'étudiant consulte la page 2/4 du corrigé « Toutes les corrections » (concat_TD5_EN1.pdf)]` au texte avant de le stocker comme `pending_user_text`. Pas de tracking séparé : l'annotation n'apparaît que sur les messages réellement envoyés (canal sans pollution d'historique).

#### 8.1.B Sécurités `/api/apply_edit`

```python
# 1. Chemin relatif obligatoire
if path.startswith("/") or len(path) > 2 and path[1] == ":":   # Unix abs / Windows lecteur
    return 400 "chemin absolu interdit"
if ".." in Path(path).parts:
    return 400 "traversal '..' interdit"

# 2. Résolution + check sous COURS_ROOT
target = (COURS_ROOT / path).resolve()
target.relative_to(COURS_ROOT.resolve())  # ValueError → 400 "hors COURS_ROOT"

# 3. Extension whitelist
if target.suffix.lower() not in (".md", ".txt"):
    return 400 "extension non éditable"

# 4. Unicité de `before`
if original.count(before) == 0: return 422 "introuvable"
if original.count(before) > 1:  return 422 "ambigu, élargir le contexte"

# 5. Backup + atomic write
backup.write_bytes(target.read_bytes())     # .bak à côté
tmp.write_text(new_content, "utf-8"); os.replace(tmp, target)
```

### 8.2 SSE streaming
```python
from flask import Response, stream_with_context

@app.route("/api/stream_response")
def stream_response():
    def generate():
        # Le ClaudeClient.stream_response émet des events au parser,
        # le parser émet des ParserEvent qu'on transforme en SSE
        for event in get_pending_events():
            if event.type == ParserEventType.TEXT_CHUNK:
                yield f"event: text\ndata: {json.dumps(event.payload)}\n\n"
            elif event.type == ParserEventType.TTS:
                yield f"event: tts\ndata: {json.dumps(event.payload)}\n\n"
            elif event.type == ParserEventType.SUGGESTED_EDIT:
                # Phase A.7 : forwarder au front qui affiche un panneau
                yield f"event: suggested_edit\ndata: {json.dumps(event.payload)}\n\n"
            elif event.type == ParserEventType.END_SESSION:
                yield f"event: end\ndata: {{}}\n\n"
                break
    return Response(stream_with_context(generate()), mimetype="text/event-stream")
```

### 8.3 Front HTML : squelette minimal Phase A

```html
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>Compagnon de révision</title>
  <link rel="stylesheet" href="/static/style.css">
</head>
<body>
  <div class="layout">
    <main id="dialogue">
      <!-- les échanges Claude/étudiant s'ajoutent ici en temps réel -->
    </main>
    <aside id="sidebar">
      <div id="quota-panel"></div>
      <div id="record-indicator">Maintenir [Espace] pour parler</div>
      <button id="end-session">Terminer la séance</button>
    </aside>
  </div>
  <script src="/static/app.js"></script>
</body>
</html>
```

Pas de framework JS Phase A. Vanilla JS suffit pour SSE + fetch.

### 8.4 Lancement
```python
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5680, debug=False, threaded=True)
```

Port 5680 pour ne pas conflicter avec `arsenal_agent.py` (5679).

---

## 9. QUOTA : `_scripts/quota/quota_check.py` + `_scripts/runtime_settings.py`

### 9.1 Wrapper

```python
import sys
from pathlib import Path

# Phase A : ajout au path d'Arsenal_Arguments
ARSENAL_PATH = Path(__file__).resolve().parents[2] / "Arsenal_Arguments"
if str(ARSENAL_PATH) not in sys.path:
    sys.path.insert(0, str(ARSENAL_PATH))

from claude_usage import fetch_usage  # noqa: E402
from runtime_settings import get_session_threshold_pct, get_weekly_threshold_pct

def can_start_session() -> tuple[bool, str]:
    """Retourne (autorisé, raison_si_non)."""
    try:
        usage = fetch_usage()
    except Exception as e:
        logger.warning("Quota check échoué : %s ; autorisation par défaut", e)
        return True, ""

    # Phase A.6 : seuils LUS DYNAMIQUEMENT à chaque appel depuis
    # _secrets/runtime_settings.json. La GUI peut les modifier à la
    # volée, le prochain check les prend en compte sans relance.
    session_threshold = get_session_threshold_pct()
    weekly_threshold = get_weekly_threshold_pct()

    if usage.session_pct > session_threshold:
        return False, f"Quota 5h à {usage.session_pct:.0f}% (seuil {session_threshold}%)"
    if usage.weekly_pct > weekly_threshold:
        return False, f"Quota hebdo à {usage.weekly_pct:.0f}% (seuil {weekly_threshold}%)"
    return True, ""

def get_usage_snapshot() -> dict:
    """Snapshot pour affichage front (sidebar Flask + GUI Tkinter)."""
    try:
        usage = fetch_usage()
    except Exception as e:
        return {"error": "unavailable", "detail": f"{type(e).__name__}: {e}"}
    return _quota_to_dict(usage)
```

### 9.2 `_secrets/runtime_settings.json` (Phase A.6+)

Source de vérité unique pour les paramètres modifiables à chaud par la GUI :

```json
{
  "schema_version": 1,
  "session_threshold_pct": 85,
  "weekly_threshold_pct": 90,
  "context_caps": {
    "cm_transcription_words": 4000,
    "perso_material_words": 6000,
    "correction_total_chars": 80000
  },
  "last_selection": {
    "matiere": "AN1", "type": "TD", "num": "5", "exo": "3",
    "annee": "", "mode": "guidé",
    "enable_audio": false, "skip_quota": false
  },
  "updated_at": "2026-05-05T20:42:00+02:00"
}
```

API publique de `runtime_settings.py` :

- `load_settings(path=None) -> dict` : merge avec defaults, fallback total si fichier absent ou corrompu. `path` résolu à l'appel pour permettre les tests via `patch.object`.
- `save_settings(data, path=None)` : atomic write, met à jour `updated_at`.
- `update_settings(**kwargs)` : patch partiel des seuils ou caps.
- `get_session_threshold_pct()` / `get_weekly_threshold_pct()` / `get_context_cap(name)` : accesseurs typés.
- `get_last_selection()` / `update_last_selection(**kwargs)` : Phase A.7.1, mémoire du formulaire de lancement de la GUI.

Tolérant : malformations loggués en warning, fallback aux défauts. Schémas additifs (nouveaux champs optionnels) ne bumpent pas `schema_version`.

---

## 10. ENTRY POINTS : CLI + GUI

> **Phase A.6 update.** Le compagnon a maintenant deux entry points : `compagnon.py` (CLI direct) et `gui.py` (Tkinter, recommandé pour usage régulier, double-clic sur `start_gui.vbs` pour le lanceur silencieux Windows). La GUI lance `compagnon.py` en sous-process avec les bons args, donc le runtime est identique.

### 10.1 Mode CLI (Phase A → A.7+)
```python
import argparse
import logging
from pathlib import Path

import config
from _scripts.dialogue.prompt_builder import PromptBuilder, SessionContext
from _scripts.dialogue.claude_client import ClaudeClient
from _scripts.dialogue.session_state import SessionState
from _scripts.dialogue.parser import StreamParser
from _scripts.audio.listener import PushToTalkListener
from _scripts.audio.transcribe_stream import WhisperTranscriber
from _scripts.quota.quota_check import can_start_session
from _scripts.web.app import run_flask_app

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("matiere", help="AN1, EN1, PSI, ...")
    parser.add_argument("type", help="TD, CC, Examen")
    parser.add_argument("num", help="Numéro du TD/CC")
    parser.add_argument("exo", help="Numéro de l'exercice ou 'full'")
    parser.add_argument("--resume", action="store_true", help="Reprendre une session interrompue")
    args = parser.parse_args()

    # 1. Check quota
    ok, reason = can_start_session()
    if not ok:
        print(f"❌ Impossible de démarrer : {reason}")
        return 1

    # 2. Construit le contexte
    ctx = SessionContext(...)

    # 3. Lance Flask en thread + ouvre navigateur
    run_flask_app(ctx, args.resume)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

### 10.2 Mode GUI Tkinter (Phase A.6+)

`gui.py` (~580 lignes, fenêtre Tk unique). 6 panneaux :

1. **▶ Lancer une session** : comboboxes cascading peuplés depuis `cours_resolver.list_*` (matière → type → num → exo + année). Radio Mode (Colle/Lecture). 3 checkboxes (audio legacy, skip-quota, resume). Boutons Lancer/Stop, Ouvrir UI navigateur, 📖 Ouvrir script, 📊 Ouvrir slides, 🔄 Rescan COURS.
2. **📊 Quota Pro Max (live)** : 4 barres (session 5h / hebdo 7j / hebdo Sonnet / overage), pourcentages, **timers de reset** (Phase A.6.x : `Dans 2h17`, `Dans 3j 14h`, `(reset)` si dépassé). Spinboxes seuils session/hebdo persistés dans `runtime_settings.json`. Bouton Sauvegarder/Recharger.
3. **🤖 Moteur Claude** : radio CLI subscription / API Anthropic, écrit `_secrets/engine_pref.json`.
4. **⚙️ Caps contexte (avancé)** : 4 spinboxes pour les caps de prompt builder (CM transcription, perso, corrigés cumulés, top N WP).
5. **📁 Sessions** : liste des derniers JSON `_sessions/`, marqueur ↩ pour les reprenables, double-clic ouvre une preview, raccourcis dossiers.
6. **💻 Console** : `ScrolledText` foncé qui tail le stdout/stderr du subprocess `compagnon.py` (queue drainée toutes les 150 ms par le main loop Tk, capée à 400 lignes).

**Subprocess management**. La GUI lance `python -u compagnon.py ...` via `subprocess.Popen` avec `CREATE_NEW_PROCESS_GROUP` sur Windows pour permettre un stop propre via `CTRL_BREAK_EVENT`. Fallback hard-kill via `taskkill /F /T /PID` après 5 s si le process ne s'arrête pas.

**Lanceur silencieux** : `start_gui.vbs` à la racine. Double-clic → `pythonw.exe gui.py` sans console parasite. Fallback sur les chemins courants `Python312` / `Python313` si pythonw n'est pas dans le PATH.

### 10.3 Lancement type

```powershell
# CLI direct
python compagnon.py AN1 TD 5 3
python compagnon.py EN1 CC 1 full --annee 2025-26 --mode guidé

# GUI (recommandé)
.\start_gui.vbs                  # double-clic Windows OK aussi
```

CLI args reconnus : `matiere`, `type`, `num`, `exo`, `--annee`, `--mode {colle,lecture}`, `--enable-audio` (legacy), `--skip-quota-check`, `--resume`, `--enonce-path` (override).

Tous ouvrent le navigateur sur `http://127.0.0.1:5680/`, démarrent Claude qui pose la première question (mode colle) ou attend (mode guidé).

---

## 11. PLAN DE TESTS

> **Phase A → A.7.1 update.** 114 tests automatiques (au commit doc-sync). Section Phase A originale conservée ci-dessous, additionnée des tests Phase A.5+.

### 11.1 Tests automatiques (`tests/`)

| Fichier | Cas | Phases |
|---|---|---|
| `test_parser.py` | 16 | 9 Phase A (cf. §3.5) + 7 SUGGESTED_EDIT (Phase A.7-light) |
| `test_session_state.py` | 14 | Phase A : create / append_exchange / finalize / load / atomic write integrity |
| `test_prompt_builder.py` | 24 | Phase A + 9 cas pour les sections enrichies Phase A.5 (CORRIGÉ OFFICIEL, TACHE PERSO, SCRIPT, SLIDES, caps) **+v15.7.4** (6 cas) : default `mixte` quand mode=colle, override `oral`/`photos`, fallback sur valeur invalide, **omission du bloc `[FORMAT COLLE]` en mode `guidé`**, helper `_normalize_colle_format` (casse insensible). |
| `test_cours_resolver.py` | 25 | Phase A.5 (find_*) + Phase A.6.1 (list_*) : TD numérique, CC flat, CC nesté, PSI textuel SHANNON, edge cases |
| `test_runtime_settings.py` | 12 | Phase A.6 (seuils, caps, defaults, fallback corrupt, merge partiel) + Phase A.7.1 (last_selection roundtrip + coerce bool) |
| `test_app_transcribe.py` | 6 | Phase A.6.2 : endpoint `/api/transcribe` avec `WhisperTranscriber` mocké |
| `test_app_apply_edit.py` | 10 | Phase A.7-light : endpoint `/api/apply_edit` (happy path + backup, traversal, absolu Unix/Windows, .pdf, fichier manquant 404, before introuvable 422, before non-unique 422, no-op rejet, champs manquants 400) |
| `test_app_refine_search_query.py` | 10 | **Phases v15.7.14 + v15.7.15** : endpoint `/api/refine_search_query` (description vide → 400, happy path retourne query + alts + concept + level, target youtube vs web, target invalide → fallback web, **engine Gemini + model Flash forcés sur LES 2 calls**, exclude propagé à l'étape 2 uniquement, query vide étape 2 → 502 `step: "compose_query"`, concept vide étape 1 → 502 `step: "infer_concept"`, alternatives cappées à 3, propagation concept/level/key_specs/domain dans le sys_prompt étape 2). Helper `_make_fake_client_pair` pour mocker 2 calls successifs via `side_effect`. |
| `test_app_attachment_replace.py` | 6 | **Phase v15.7.10** : endpoint `/api/pending_attachments/<id>/replace` (409 sans session, 404 id inconnu, 400 attachment non-image, 400 file manquant, 200 happy path : nouveau fichier écrit + entry mutée + ancien préservé sur disque, garde anti-cumul de suffixes `_cropped_v1_cropped_v1`). |
| `test_app_colle_format.py` | 13 | **Phase v15.7.4** : endpoint `/api/set_colle_format` (409 sans session, 400 invalide, 200 happy + persist + marker injecté dans _history, tolérance singulier `photo` → `photos`, casse insensible) + détection slash-command dans `/api/send_message` (`/oral`, `/photos.` dictation, `/MIXTE` casse, slash + texte après = pas intercepté, texte normal sans slash = flow inchangé) + 3 tests de doctrine sur `PROMPT_SYSTEME_COMPAGNON.md` (§1.6 présent avec les 3 formats, règle 11 présente avec « êtes-vous sûr », garde-fou « jamais silencieusement »). |
| `test_app_rewrite.py` | 16 | Phase A.7.2 v15.6 : endpoint `/api/rewrite` (text vide, whitespace, intent invalide, texte trop long, succès, strip guillemets simples/français, quota 429, erreur SDK 502, réponse vide 502, loop sur les 4 intents) avec `ClaudeClient` mocké. **+v15.7.1** (4 cas) : sans `context_tutor` = legacy (pas de bloc `[Contexte]`, `context_chars: 0`) ; avec contexte = injecté en bloc `[Contexte : dernier message du tuteur]`, brouillon préservé en queue ; contexte > `REWRITE_MAX_CONTEXT_CHARS` = truncation par le début, queue préservée ; whitespace = traité comme absent. **+v15.7.2** (1 cas doctrine) : `REWRITE_INTENTS["fix_typos"]` mentionne explicitement « faux départ », « hésitation » et un mot normatif fort (« interdiction » / « interdit »), casse si quelqu'un assouplit la consigne par inadvertance. |
| `test_app_saved_selections.py` | 12 | **Phase v15.7.23** : endpoints saved_selections (GET no-session / GET liste, POST no-session / text vide / text trop long 5001 chars / happy path complet / role default claude / role student préservé / appends non-remplace, DELETE no-session / id inconnu 404 / suppression OK 204). |
| `test_app_session_photos.py` | 15 | **Phase A.9.1** (7) : endpoints GET / DELETE classiques + **Phase A.10.1** (8) : backfill depuis transcript : marker présent → pas de scan, session_photos déjà populée → marker only, scan transcript→files réels (2 photos PNG+JPG), fichier manquant → skip, dedup, URLs externes refusées, bulles claude ignorées, marker posé même sur résultat vide. |
| `test_app_upload_file.py` | 8 | **Phase A.10.2** : endpoint `GET /api/upload_file` (param manquant 400, chemin absolu 400/403, traversal `..` 400, fichier introuvable 404, extension non whitelistée 415, happy path JPG + PNG avec mime correct, path résolvant hors UPLOADS_DIR refusé). |
| `test_app_stickies.py` | 28 | **Phase A.10** : endpoints `/api/stickies` (22 cas : GET no-session / liste, POST no-session / text vide / trop long / happy path / kind tutor / kind invalide / normalisation whitespace / source_message_id, PATCH no-session / body vide / id inconnu / text only / enabled only / text trop long, DELETE no-session / id inconnu / happy path, import_from no-session / traversal / real source filtre enabled) + helper `_format_stickies_block_for_llm` (6 cas : empty, all disabled, enabled only, missing enabled defaults true, empty text, robust to None data). |
| `test_parser.py` (+8 cas) | 8 | **Phase A.10** : balise `<<<REMEMBER>>>` (REMEMBER valid simple, with surrounding text, split en 5 chunks, JSON invalide, champ text manquant, text vide, text > 200 chars tronqué à 197 + …, whitespace normalisé). |
| `test_app_cancel_stream.py` | 6 | **Phase v15.7.21** : endpoint `/api/cancel_stream` (action invalide → 400, pas de session → 409, action=resume flag set + history/transcript intacts, action=delete_last_user retire du _history client ET tronque current_branch_path + re-dérive transcript, no student in path → ok silencieux, default action = resume). |
| `test_app_ocr_photo.py` | 8 | **Phase v15.7.20** : endpoint `/api/ocr_photo` (id manquant → 400, pas de session → 409, id inconnu → 404, non-image → 400, happy path retourne ocr_markdown + kind + completeness + warnings, **engine Gemini + model Flash forcés peu importe la pref user**, ocr_markdown vide → 502, warnings cappés à 10). |
| `test_claude_client_multimodal.py` | 13 | **Phase v15.7.18** : helpers multimodal `_extract_inline_images` (7 cas : pas d'image, single, fichier manquant, ext non supportée, > 5 MB, multiples, path absolu) + transformations par moteur (`_messages_to_anthropic_multimodal` 3 cas, `_messages_to_openai_multimodal` 1 cas, `_messages_to_gemini_parts` 2 cas). Pas de tests d'intégration SDK (mock trop fragile). |
| **Total au commit v15.7.23** | **304** | (114 historiques + extensions Phase A.6.2 → A.7.2 v15.7.23) |

### 11.2 Tests manuels (à faire par Gstar, Phase A originelle)
1. **Smoke test** : lancer `python compagnon.py AN1 TD 5 3` avec quota OK, vérifier que Claude pose la première question.
2. **Audio bouton 🎤** : Phase A.6.2, clic, parler 3 secondes, clic stop, vérifier que la transcription apparaît dans le champ + Claude répond après envoi.
3. **Heartbeat** : démarrer une session, attendre 60s, killer brutalement le process, redémarrer, vérifier que la session est listée comme reprenable.
5. **Quota tendu** : modifier `_secrets/runtime_settings.json` `session_threshold_pct: 5`, vérifier que `compagnon.py` refuse de démarrer.
6. **End session** : balise `<<<END_SESSION>>>` reçue, vérifier que `ended_at` et `duration_seconds` sont bien écrits.
7. **Mode guidé + édit** : Phase A.7-light, lancer en mode guidé sur un script qui contient une faute volontaire, demander à Claude de vérifier la cohérence avec le CM, accepter la correction proposée, vérifier que le `.bak` est créé et le fichier mis à jour.
8. **Persistance sélection** : Phase A.7.1, lancer la GUI, sélectionner AN1 TD 5 ex3, fermer, ré-ouvrir, vérifier que les comboboxes sont pré-remplies sur la même sélection.

### 11.3 Critère de validation Phase A (cf. CLAUDE.md §9)
> Gstar peut faire une session de révision de 30 min, AN1 TD5, dialogue texte propre, transcript persisté en JSON, quota tracké en live dans la sidebar. Pas de TTS, pas de photo : juste la boucle.

Phase A validée le 2026-05-01 (cf. CHANGELOG). Phases A.5 → A.7.1 livrées dans la foulée le 2026-05-05.

---

## 12. ORDRE DE CODAGE RECOMMANDÉ : PHASE A

Pour Claude Code, ordre suggéré pour minimiser les blocages mutuels :

1. **`config.py`** : constantes de chemins. ~30 lignes.
2. **`_scripts/utils.py`** : `atomic_write_json`, helpers ISO timestamps. ~50 lignes.
3. **`_scripts/dialogue/parser.py`** : la machine à états. **Le morceau central, à coder en premier après les utils.** ~250 lignes avec tests.
4. **`tests/test_parser.py`** : les 9 cas. À coder **immédiatement après** parser.py, validation indispensable avant de continuer.
5. **`_scripts/dialogue/session_state.py`** : gestion JSON + heartbeat. ~200 lignes.
6. **`tests/test_session_state.py`**.
7. **`_scripts/quota/quota_check.py`** : wrapper minimal. ~80 lignes.
8. **`_scripts/audio/transcribe_stream.py`** : wrapper Whisper. ~80 lignes.
9. **`_scripts/audio/listener.py`** : push-to-talk. ~120 lignes.
10. **`_scripts/dialogue/prompt_builder.py`** : assemblage contexte. ~150 lignes.
11. **`tests/test_prompt_builder.py`**.
12. **`_scripts/dialogue/claude_client.py`** : wrapper API/CLI. ~250 lignes.
13. **`_scripts/web/app.py`** : Flask + SSE. ~200 lignes.
14. **`_scripts/web/templates/index.html` + `static/app.js`** : front minimal. ~150 lignes total.
15. **`compagnon.py`** : entry point qui colle tout ensemble. ~80 lignes.

Total Phase A estimé : ~2000 lignes Python + 300 front + 400 tests. **Réalisé** au commit Phase A : 2300 + 220 + 560.

À faire par bouts (cf. CLAUDE.md §6), avec validation Gstar à chaque module avant de passer au suivant.

### 12.bis Modules ajoutés Phase A.5 → A.7.1

Ordre observé en pratique (cf. CHANGELOG.md pour le narratif des frictions) :

16. **`_scripts/dialogue/cours_resolver.py`** (Phase A.5) : résolution chemins COURS, ~280 lignes. `find_enonce_pdf`, `resolve_corrections`, `find_perso_*`, puis `list_*` ajoutés en A.6.1. Standalone, miroir de `cours_pipeline.resolve_correction_pdf` côté BotGSTAR mais sans dépendance Discord.
17. **`tests/test_cours_resolver.py`** : 25 cas (TD, CC flat, CC nesté, PSI textuel, edge cases vides).
18. **Extension `_scripts/dialogue/prompt_builder.py`** (Phase A.5) : `SessionContext` étendu (`correction_paths`, `tache_path`, `script_oral_path`, `slides_pdf_path`, `annee`), nouvelles sections du prompt initial avec caps.
19. **Mise à jour `_prompts/PROMPT_SYSTEME_COMPAGNON.md`** v0.2 : §1.4 ancrage corrigé officiel.
20. **`gui.py`** (Phase A.6) : Tkinter, ~580 lignes, 6 panneaux, subprocess management, comboboxes cascading (A.6.1), boutons Ouvrir script/slides (A.6.3), radio Mode (A.7-light), timer reset quota.
21. **`_scripts/runtime_settings.py`** (Phase A.6) : persistance atomic write avec fallback aux défauts. Étendu en A.7.1 avec `last_selection`.
22. **`tests/test_runtime_settings.py`** : 12 cas.
23. **`start_gui.vbs`** (Phase A.6) : lanceur silencieux Windows.
24. **Endpoint `/api/transcribe`** (Phase A.6.2) dans `app.py` : Whisper lazy-load thread-safe + cleanup tempfile.
25. **Bouton 🎤 toggle** (Phase A.6.2) dans `templates/index.html` + `static/app.js` + `static/style.css`. Pattern Claude.ai.
26. **`tests/test_app_transcribe.py`** : 6 cas (mock `WhisperTranscriber`).
27. **`_prompts/PROMPT_SYSTEME_GUIDE.md`** v1.0 (Phase A.7-light) : prompt tuteur avec spec `<<<SUGGESTED_EDIT>>>`.
28. **Extension `_scripts/dialogue/parser.py`** (Phase A.7-light) : `INSIDE_SUGGESTED_EDIT`, validateur `_try_parse_suggested_edit`. 7 cas test ajoutés.
29. **Extension `_scripts/dialogue/claude_client.py`** (Phase A.7-light) : params `mode` + `cours_root`, `--allowedTools "Read,Grep,Glob"` + `cwd=cours_root` en mode guidé.
30. **Endpoint `/api/apply_edit`** (Phase A.7-light) dans `app.py` : sécurités chemin, whitelist extensions, unicité before, backup `.bak`, atomic write.
31. **Card de suggestion** dans `app.js` : diff before/after côte-à-côte, boutons Appliquer/Rejeter.
32. **`tests/test_app_apply_edit.py`** : 10 cas.
33. **`compagnon.py --mode` + radio dans `gui.py`** (Phase A.7-light + A.7.1).
34. **`get_last_selection` / `update_last_selection`** dans `runtime_settings.py` (Phase A.7.1) + restauration au boot de la GUI.

---

## 13. RAPPEL FINAL

Cette spec n'est plus l'état au démarrage Phase A : elle est synchronisée avec **Phase A.7.1 (2026-05-05)** (système de points faibles retiré Phase A.11, 2026-05-17). Pour les modifications structurelles à venir (TTS, photos, mode reprise propre, upgrade A.7-light → A.7-full…), passe par Gstar avant de toucher au code. Pas de scope creep en cours de phase.

Si Claude Code détecte que la spec est insuffisante ou ambiguë sur un point en cours de codage, il **arrête** et pose la question. Mieux vaut une question de plus que 200 lignes de code basé sur une devinette.

Le narratif détaillé des phases (frictions observées, citations utilisateur, choix justifiés) vit dans **`CHANGELOG.md`**, pas ici. Cette spec est descriptive ; le CHANGELOG est historique.