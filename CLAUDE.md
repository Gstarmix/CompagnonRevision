# CLAUDE.md — Compagnon_Revision

> **Manuel d'instructions permanent pour Claude Code.**
> Lu au début de chaque session de développement.
> Ne touche pas à ce fichier sans validation explicite de Gstar.

---

## 0. PRÉSENTATION RAPIDE

`Compagnon_Revision/` est un projet sœur de BotGSTAR, autonome dans son runtime mais qui réutilise des briques d'`Arsenal_Arguments/` (notamment le scraper de quota Pro Max `claude_usage.py` et le moteur `faster-whisper` GPU).

**Objectif fonctionnel** : permettre à Gstar de réviser à voix haute un TD ou CC universitaire en dialogue avec Claude (mode colle d'oral, vouvoiement strict). Push-to-talk → Whisper → Claude → texte affiché + TTS sélectif sur passages clés. Réception de photos de brouillon papier via watcher de dossier.

**Public** : Gstar uniquement, étudiant L1 Informatique-Électronique ISTIC Rennes, en préparation des CC3 (mai-juin 2026). Pas de logique multi-utilisateur.

**Non-objectif** : ce n'est pas un produit. C'est un outil personnel. Pas de packaging pip, pas d'installeur, pas de doc utilisateur grand public. Le `README.md` est pour Gstar, point.

---

## 1. SÉPARATION DES RÔLES IA (RÈGLE FONDATRICE)

C'est le pattern habituel de Gstar (cf. COURS/, Arsenal_Arguments/). À respecter strictement :

### 1.1 Claude.ai (chat web) — la conception
- Rédige les fichiers de doctrine : `CLAUDE.md`, `README.md`, `ARCHITECTURE.md`, `_prompts/PROMPT_SYSTEME_COMPAGNON.md`, `CHANGELOG.md`
- Décide l'archi, les noms, les conventions, les phases
- Audit de code à la demande, propositions de refactor
- **N'écrit jamais de code à exécuter.** Si Claude.ai produit du code, c'est à titre d'exemple ou de spec, jamais à coller dans un fichier `.py` du projet.

### 1.2 Claude Code (CLI) — l'exécution
- Code l'orchestrateur, les watchers, les helpers, les wrappers, l'intégration API
- Code les tests
- Lit `CLAUDE.md` + `ARCHITECTURE.md` + `_prompts/PROMPT_SYSTEME_COMPAGNON.md` au début de chaque session pour se calibrer
- **Ne touche jamais à `_prompts/`**, jamais à `CLAUDE.md`, jamais à `README.md`, jamais à `ARCHITECTURE.md`. Ce sont des artefacts de Claude.ai.
- Si Claude Code détecte une incohérence ou un manque dans la doctrine, il demande à Gstar avant de coder un workaround. **Mieux vaut s'arrêter et clarifier que coder en zone grise.**

### 1.3 Gstar — l'arbitrage
- Décide les pivots d'archi
- Valide ou rejette les propositions
- Teste en conditions réelles (sessions de révision)
- Reporte les bugs ou frictions vers le bon canal (Claude.ai pour archi/pédagogie, Claude Code pour bug de code)

### 1.4 Les prompts système du compagnon — sacrés
**Quatre** prompts système coexistent depuis Phase A.9 (2026-05-13) :

- `_prompts/PROMPT_SYSTEME_COMPAGNON.md` (v1.1, Phase A.11) — **mode colle**, colleur d'oral exigeant. C'est le mode par défaut historique. §8 « Consignes épinglées par l'étudiant » + balise `<<<REMEMBER>>>` + règle absolue §4.14 (mémoire persistante de séance). Phase A.11 : suppression du système de points faibles (§5/§6 retirées).
- `_prompts/PROMPT_SYSTEME_GUIDE.md` (v1.9, ex-LECTURE) — **mode guidé**, tuteur patient slide-par-slide avec accès `Read`/`Grep`/`Glob` sur l'arbre `COURS/` et capacité à proposer des corrections via balise `<<<SUGGESTED_EDIT>>>` validées par l'utilisateur. Phase Z.8 (2026-05-09) : absorbe l'ex-mode `lecture` (supprimé). §6 mémoire persistante + balise `<<<REMEMBER>>>`.
- `_prompts/PROMPT_SYSTEME_DECOUVERTE.md` (v1.9, Phase A.12.5) — **mode découverte** (Phase A.8), tuteur explicateur zéro prérequis pour démarrer un sujet jamais (ou peu) suivi en CM. Exposition courte → question simple → validation, max 2 concepts neufs/réplique, pas de barème d'indices. Génère un PDF d'énoncé d'entraînement en début de séance via la balise `<<<SAVE_INVENTED_PDF>>>`. §1.6quater : déclencheurs et cadence des cartes `<<<CAHIER>>>`. §4.6 questions à choix `<<<CHOICES>>>`. Progression idéale : Découverte → Guidé → Colle.
- `_prompts/PROMPT_SYSTEME_WORKSPACE.md` (v1.8, Phase A.12.5) — **mode workspace** (Phase A.9), tuteur sur un dossier disque arbitraire hors COURS/ (codebase, docs, CV…). 3 postures auto-sélectionnées au cadrage : explain (« explique-moi ce dossier »), quiz (« interroge-moi dessus »), deep-dive (« approfondis tel point »). Accès `Read`/`Grep`/`Glob` scopé au workspace (boucle d'outils sur les 5 moteurs depuis A.12). §2.9 cartes `<<<CAHIER>>>`. §2.10 questions à choix `<<<CHOICES>>>` (cadrage propose « 📚 Faites-moi cours »). §4.12 pas de sur-narration des appels d'outils. Garde-fous lecture seule, secrets, hallucination.

Les quatre fichiers définissent le **cœur pédagogique** : *comment* Claude interagit avec Gstar (vouvoiement strict, refus des formulations floues, ancrage sur le corrigé officiel, etc.). **Concertation explicite avec Gstar avant toute modification.** Si une session révèle un problème de comportement (Claude trop bavard, trop tendre, dérive du corrigé, etc.), c'est par discussion qu'on décide d'éditer ces fichiers, jamais en autonomie.

---

## 2. ARBORESCENCE DU PROJET

```
Compagnon_Revision/
├── CLAUDE.md                       # ce fichier
├── README.md                       # guide utilisateur (pour Gstar)
├── ARCHITECTURE.md                 # spec technique détaillée
├── CHANGELOG.md                    # phases datées (A.5, A.6.x, A.7.x livrées)
├── compagnon.py                    # entry point CLI (--mode, --annee, --enable-audio…)
├── gui.py                          # entry point Tkinter (Phase A.6+)
├── start_gui.vbs                   # lanceur silencieux Windows pythonw.exe
├── config.py                       # constantes, chemins, racines, schemas versions
├── requirements.txt                # dépendances Python
│
├── _prompts/
│   ├── PROMPT_SYSTEME_COMPAGNON.md # mode colle (interrogation), v0.7
│   ├── PROMPT_SYSTEME_GUIDE.md   # mode guidé (tuteur slide-par-slide + Read FS + suggestions), v1.6
│   └── PROMPT_SYSTEME_DECOUVERTE.md # mode découverte (tuteur explicateur zéro prérequis + PDF inventé), v1.0 (Phase A.8)
│
├── _generated/                      # PDFs d'énoncés inventés (mode découverte) — gitignored
├── _uploads/                        # Photos / PDF / Excel envoyés au tuteur (Phase A.10.2) — gitignored
│   └── <session_id>/{photos,attachments}/  # un dossier par session
│   └── <MAT>/<session_id>.md
│
├── _scripts/
│   ├── runtime_settings.py         # _secrets/runtime_settings.json (seuils, caps,
│   │                               #   last_selection) — Phase A.6+
│   ├── utils.py                    # atomic_write_json, parse_iso, helpers
│   ├── audio/
│   │   ├── listener.py             # hotkey clavier global (legacy --enable-audio)
│   │   └── transcribe_stream.py    # wrapper faster-whisper large-v3
│   ├── dialogue/
│   │   ├── claude_client.py        # wrapper API/CLI Claude (mode + cours_root + boucle d'outils FS)
│   │   ├── fs_tools.py             # outils Read/Grep/Glob réels pour les moteurs API (Phase A.12)
│   │   ├── prompt_builder.py       # assemble le contexte par session
│   │   ├── parser.py               # balises <<<TTS/SUGGESTED_EDIT/END_SESSION>>>
│   │   ├── session_state.py        # état machine d'une séance
│   │   └── cours_resolver.py       # navigation arbo COURS (find_*, list_*)
│   ├── watchers/                   # vide en l'état (photo_watcher prévu Phase B)
│   ├── web/
│   │   ├── app.py                  # Flask + SSE + endpoints (Phase A.7 inclut
│   │   │                           #   /api/transcribe, /api/apply_edit)
│   │   ├── templates/index.html
│   │   └── static/                 # app.js, style.css
│   └── quota/
│       └── quota_check.py          # wrapper claude_usage.py + seuils dynamiques
│
├── _sessions/                      # logs JSON par séance (atomic write)
│   └── YYYY-MM-DD_{MAT}_{TYPE}{N}_ex{n}.json
│
├── _photos_inbox/                  # Phase B/C — vide en l'état
│
├── _cache/
│   └── tts/                        # Phase B
│
├── _secrets/                       # gitignore
│   ├── engine_pref.json            # CLI subscription vs API Anthropic
│   └── runtime_settings.json       # seuils quota + caps contexte + last_selection
│
├── _logs/                          # rotation quotidienne (auto-créé au boot)
│   └── compagnon_YYYY-MM-DD.log
│
└── tests/                          # 553 tests (Phase A.12.1)
    ├── test_parser.py              # +7 cas SUGGESTED_EDIT depuis A.7-light
    ├── test_session_state.py
    ├── test_prompt_builder.py      # +9 cas pour les sections Phase A.5
    ├── test_cours_resolver.py      # find_* + list_* (A.5 + A.6.1)
    ├── test_runtime_settings.py    # seuils, caps, last_selection
    ├── test_app_transcribe.py      # endpoint POST /api/transcribe (A.6.2)
    └── test_app_apply_edit.py      # endpoint POST /api/apply_edit (A.7-light)
```

---

## 3. CONVENTIONS DE CODE

### 3.1 Python
- Python 3.12 sur Windows 10/11
- PEP 8, sans dogmatisme — lignes 100 chars autorisées (comme dans Arsenal_Arguments/)
- Type hints partout sur les signatures publiques. Pas obligatoire dans le corps.
- Docstrings courts en français pour les fonctions publiques. Format triple-quote, une ligne de résumé suivie d'un bloc paramètres si pertinent.
- Logging via `logging` standard, pas de `print()` en code prod (sauf entry point CLI). Logger nommé par module : `logger = logging.getLogger(__name__)`
- Pas de chemins absolus en dur. Tout passe par `config.py` qui expose les constantes :
  - `COURS_ROOT = Path(r"C:\Users\Gstar\OneDrive\Documents\COURS")`
  - `PROJECT_ROOT = Path(__file__).parent`
  - `SESSIONS_DIR = PROJECT_ROOT / "_sessions"`
  - `UPLOADS_DIR = PROJECT_ROOT / "_uploads"` (Phase A.10.2 — photos / PDF envoyés au tuteur en séance ; sous-arborescence `_uploads/{session_id}/{photos|attachments}/`)
  - etc.

### 3.2 Imports
- Imports standard d'abord, puis tiers, puis locaux. Une ligne vide entre les groupes.
- Pour réutiliser `claude_usage.py` d'Arsenal_Arguments, en Phase A on fait un `sys.path.insert` minimal en tête de `quota_check.py` :
  ```python
  import sys
  from pathlib import Path
  ARSENAL_PATH = Path(__file__).resolve().parents[2] / "Arsenal_Arguments"
  if str(ARSENAL_PATH) not in sys.path:
      sys.path.insert(0, str(ARSENAL_PATH))
  from claude_usage import fetch_usage  # noqa: E402
  ```
  En Phase B, on transformera Arsenal_Arguments en vrai package importable. Pas urgent.

### 3.3 Nommage
- `snake_case` pour fonctions et variables
- `PascalCase` pour classes
- `UPPER_SNAKE` pour constantes
- Préfixe `_` pour privé interne au module
- Fichiers `.py` en `snake_case`, jamais d'espaces ni de tirets

### 3.4 Atomic writes obligatoires
Toute écriture vers `_sessions/`, `_secrets/`, `_cache/` (hors MP3) doit être atomique.

Pattern standard, à reproduire :
```python
import json
import os
from pathlib import Path

def atomic_write_json(path: Path, data: dict) -> None:
    """Écriture atomique d'un JSON via .tmp + os.replace()."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
```

Helper centralisé dans `_scripts/dialogue/session_state.py` ou un futur `_scripts/utils.py`. Pas de `f.write(json.dumps(...))` direct sur le fichier final.

### 3.5 Idempotence
- Un script relancé deux fois doit produire le même résultat. Pas de duplication de session, pas de réécriture si rien n'a changé.
- Pour les fichiers MP3 du cache TTS, dédup par SHA1 du texte d'entrée. Cf. `_cache/tts/<sha1>.mp3`.

### 3.6 Schémas JSON versionnés
Tout fichier JSON persistant inclut un champ `schema_version: int` à la racine.

Versions actuelles :
- `_sessions/*.json` : `schema_version: 1` (champ `mode` ajouté en A.7-light, `annee` en A.5 — pas de bump car additifs et ignorés par les anciens lecteurs)
- `_secrets/engine_pref.json` : `schema_version: 1`
- `_secrets/runtime_settings.json` : `schema_version: 1` (Phase A.6+, champ `last_selection` ajouté en A.7.1 sans bump)

Toute modification **destructive** de schéma incrémente la version et inclut une migration douce (lecture des deux schémas pendant une période, normalisation à l'écriture). Les **ajouts additifs** (nouveaux champs optionnels) ne bumpent pas la version — le merge avec defaults dans `runtime_settings._merge_with_defaults` couvre la rétrocompat.

---

## 4. CONTRAT DES BALISES (PARSER)

Le `_scripts/dialogue/parser.py` extrait des balises spéciales du stream Claude avant affichage. Cf. `_prompts/PROMPT_SYSTEME_COMPAGNON.md` §7 et `_prompts/PROMPT_SYSTEME_GUIDE.md` §3, §5 pour la spec côté prompt.

### 4.1 Balises supportées
| Balise | Format | Action côté Python | Mode actif |
|--------|--------|-------------------|---|
| `<<<TTS>>>...<<<END>>>` | texte libre, ≤50 mots | extrait, envoie au moteur TTS, retourne dans le flux affiché | colle + lecture |
| `<<<SUGGESTED_EDIT>>>{...}<<<END>>>` | JSON minifié `{file, before, after, reason?}` | extrait, valide light, **forward au front** comme event SSE `suggested_edit` | lecture uniquement (Phase A.7) |
| `<<<END_SESSION>>>` | balise nue | déclenche la finalisation propre de la session, **retire** du flux affiché | colle (lecture l'utilise rarement, l'utilisateur ferme via la GUI) |

### 4.2 Streaming SSE — accumulation de buffer
Les balises peuvent arriver coupées en plusieurs chunks SSE. Le parser doit :
1. Accumuler le buffer reçu jusqu'à reconnaître une balise complète (ouverture **et** fermeture pour `<<<TTS>>>`, `<<<SUGGESTED_EDIT>>>`)
2. Pour `<<<END_SESSION>>>`, reconnaître la balise complète (pas de fermeture séparée)
3. Diffuser au front Flask **uniquement** les portions de texte qui sont "stables" (pas en train d'être à l'intérieur d'une balise potentielle)

Pattern : machine à états dans `parser.py` (`OUTSIDE`, `PROBE_OPENING`, `INSIDE_TTS`, `INSIDE_SUGGESTED_EDIT`, `PROBE_CLOSING`).

### 4.3 Validation `<<<SUGGESTED_EDIT>>>` (Phase A.7-light)

Le parser fait une **validation light** :
- Champs requis : `file`, `before`, `after` (strings)
- `before` non vide
- `before != after` (sinon edit no-op ignorée)
- `reason` optionnelle, coercée en string si présente

La **validation de sécurité** (chemin sous `COURS_ROOT`, no traversal `..`, extension whitelist `.md`/`.txt`, unicité de `before` dans le fichier) est faite **côté backend** au moment de l'application (`/api/apply_edit`), pas au parsing. Le parser émet juste l'event `SUGGESTED_EDIT` avec le dict, le front affiche, l'utilisateur clique Appliquer, le backend re-valide et applique avec backup `.bak` + atomic write.

---

## 5. INTÉGRATION QUOTA CLAUDE MAX 5x

### 5.1 Réutilisation de `claude_usage.py`
Le module est dans `Arsenal_Arguments/claude_usage.py`. Pattern d'import : cf. §3.2.

`_scripts/quota/quota_check.py` est un **wrapper mince** qui :
- Importe `fetch_usage()` depuis Arsenal
- Expose deux fonctions au reste du compagnon :
  - `can_start_session() -> tuple[bool, str]` — retourne `(True, "")` si quota OK, `(False, "raison humaine")` sinon
  - `get_usage_snapshot() -> dict` — snapshot pour affichage live dans le front Flask

### 5.2 Seuils par défaut
- **Démarrage de session** : refusé si `five_hour.utilization > 85` ou `seven_day.utilization > 90`
- **En cours de session** : warning visuel si `five_hour > 90`, mais pas d'arrêt forcé (la session a déjà commencé, on ne casse pas le flow)

### 5.3 Switch CLI subscription / API Anthropic
Persistance dans `_secrets/engine_pref.json` :
```json
{
  "schema_version": 1,
  "engine": "cli_subscription",
  "updated_at": "2026-05-01T16:30:00+02:00"
}
```

Valeurs possibles pour `engine` :
- `"cli_subscription"` : appel via `subprocess` du CLI `claude` avec `ANTHROPIC_API_KEY` unset dans l'env (force OAuth/keychain). Mode par défaut.
- `"api_anthropic"` : appel via SDK `anthropic` Python avec clé API à la consommation. Pour les cas où Gstar veut réviser malgré quota tendu.

Le radio button de switch est exposé dans le front Flask. Toute écriture de ce fichier passe par atomic write (cf. §3.4).

### 5.4 Affichage live dans le front
Endpoint Flask `/api/quota` qui retourne le snapshot toutes les 60 secondes côté client (poll, pas SSE — pas besoin de temps réel à la seconde). Affiche 4 barres : session 5h, hebdo 7j Opus, hebdo Sonnet, overage credits.

---

## 6. MODE ÉCONOME EN TOKENS (PHASE DE CONSTRUCTION)

Pendant que Claude Code construit le projet, on bosse en **mode économe** pour préserver le quota Max 5x de Gstar pendant les 8 semaines avant CC3.

### 6.1 Règles côté Claude Code
- **Specs courtes** : Gstar te passe une spec ciblée, tu codes ce qui est demandé, point. Pas d'extension de scope.
- **Code par bouts** : un module à la fois, validation par Gstar, puis module suivant. Pas de génération de 10 fichiers d'un coup.
- **Contexte minimal** : ne charge en lecture que les fichiers nécessaires pour la tâche en cours. Si tu as besoin de comprendre un module pour en coder un autre, demande à Gstar de te le pointer plutôt que d'explorer.
- **Pas de refactor préventif** : si un fichier marche, tu n'y touches pas même si tu trouves le style sous-optimal. Tu signales à Gstar et il décide.
- **Pas de tests exhaustifs en Phase A** : un test par fichier critique (parser, session_state, prompt_builder), pas plus. La couverture viendra en Phase B.

### 6.2 Quand basculer en mode verbeux
Sur autorisation explicite de Gstar uniquement, et seulement pour :
- Pivot d'archi majeur (changement de stack, restructuration globale)
- Bug profond qui nécessite de comprendre le système entier
- Refactor de fin de phase planifié

### 6.3 Commande de session Claude Code recommandée
Au début de chaque session de dev, Gstar lance Claude Code avec une commande type :
```
Lis CLAUDE.md, ARCHITECTURE.md, et le fichier que je vais te pointer.
Mode économe en tokens.
Tâche : [description courte de ce qu'il faut coder].
Ne touche pas à _prompts/, CLAUDE.md, README.md, ARCHITECTURE.md.
Demande avant de coder en cas de doute.
```

---

## 7. NOMMAGE DES SESSIONS

Format de fichier : `_sessions/YYYY-MM-DD_{MAT}_{TYPE}{N}_ex{n}_{mode}_{format}_{anchor}.json`

Exemples :
- `_sessions/2026-05-02_AN1_TD5_ex3_colle_mixte_strict.json`
- `_sessions/2026-05-08_EN1_CC2_ex1_decouverte_oral_aucun.json`
- `_sessions/2026-05-15_PSI_TD7_full_guide_mixte_consultatif.json`

Le suffixe `_{mode}_{format}_{anchor}` (Phase A.8.6) évite l'écrasement quand on relance le même exo le même jour avec une posture différente. Trois sessions peuvent coexister pour le même `(MAT, TYPE, N, exo)` selon les axes choisis.

Champs :
- `MAT` : code matière sur 3-4 lettres (`AN1`, `EN1`, `PSI`, `ISE`, `PRG2`)
- `TYPE` : `TD`, `TP`, `CC`, `CM`, `Examen` ou `Quiz`
- `N` : numéro du TD/TP/CC/CM (entier ou textuel pour PSI : `SHANNON`, `SGF`)
- `n` : numéro de l'exercice traité (entier), ou `full` si la session a couvert tous les exos

### 7.1 Sessions multiples le même jour
Si Gstar fait deux sessions sur le même exo, le même jour, avec la **même** combinaison `(mode, format, anchor)` → même session_id → conflit géré via le modal « Reprendre / Démarrer une nouvelle » côté front (cf. `app.js` `findExistingSession`).

Si la combinaison diffère (par ex. découverte/oral le matin, colle/photos le soir), les deux sessions cohabitent naturellement grâce au suffixe différent — aucun écrasement, l'historique liste les deux.

### 7.2 Sessions interrompues
Si une session s'arrête sans `<<<END_SESSION>>>` propre (crash, fermeture brutale), le fichier garde l'extension `.json` mais inclut un champ racine `"interrupted": true` et `"interrupted_at": ISO`.

À la reprise (flag `[RESUME_SESSION]` envoyé au prompt), le système charge cette session, marque `"resumed_at": ISO`, et continue. À la fin propre, `"interrupted": false` est écrit.

---

## 8. LOGGING

### 8.1 Fichier
- `_logs/compagnon_YYYY-MM-DD.log` (rotation quotidienne)
- Niveau par défaut : `INFO` en prod, `DEBUG` si variable d'env `COMPAGNON_DEBUG=1`
- Format : `%(asctime)s [%(name)s] %(levelname)s: %(message)s`

### 8.2 Console
- Le front Flask redirige les logs `WARNING+` vers une mini-console visible dans une sidebar repliable (utile pour debug en session sans ouvrir de terminal)

### 8.3 Ce qu'on log toujours
- Démarrage/fin de session (timestamp, matière, exo)
- Appels Claude (durée, tokens consommés si dispo, succès/échec)
- Erreurs Whisper, Edge TTS, Piper
- Quota check au démarrage de session

### 8.4 Ce qu'on log jamais
- Le contenu détaillé des transcriptions audio (privacy + verbosité)
- Les prompts complets envoyés à Claude (verbosité — on logge juste la longueur en tokens)
- Les chemins absolus contenant `Gstar` ou `OneDrive` quand on peut log un chemin relatif

---

## 9. PHASES DE CONSTRUCTION (ROADMAP)

> Pour le narratif détaillé (frictions observées, citations utilisateur, choix justifiés), voir **[CHANGELOG.md](CHANGELOG.md)**. Cette section ne donne que le scope vu d'en haut.

### Phases livrées (résumé) — 2026-05-01 → 2026-05-12

Liste compacte. Voir CHANGELOG.md pour le narratif détaillé (frictions observées, citations user, code commit par commit).

- **Phase A** (2026-05-01) — MVP boucle dialogue texte pure : énoncé → SSE → capture WP → quota live + hotkey clavier global. 15 modules, 39 tests.
- **Phase A.5** (2026-05-05) — Ancrage corrigé officiel + matériel perso (`cours_resolver.py`, sections CORRIGÉ/TACHE/SCRIPT du prompt). 64 tests.
- **Phase A.6** (2026-05-05) — GUI Tkinter (`gui.py`), runtime_settings persisté, cascading comboboxes, micro toggle navigateur. 92 tests.
- **Phase A.7** (2026-05-05/06) — Mode lecture (→ guidé absorbé Phase Z.8) : tuteur slide-par-slide + Read FS + `<<<SUGGESTED_EDIT>>>`. Persistance `last_selection`. 109 tests.
- **Phase A.7.2 v6 → v15.7.36** (2026-05-06 → 11) — Refonte massive UI : KaTeX live, tables GFM, sidebar à onglets, Docs panneau rasterizé, photos + Cropper.js, TTS player avancé, multimoteurs (CLI/API/Gemini/DeepSeek/Groq) + quota live multi-engines, sujet libre types, modal fallback IA Gemini, Whisper toggle, ✨ Rewrite, débrief post-séance + récap Gemini Flash, mini-exos, format colle paramétré (oral/photos/mixte), ancrage corrigé paramétré (strict/consultatif/aucun). ~373 tests.
- **Phase A.8** (2026-05-12) — Mode Découverte (3ᵉ posture) + PDF d'énoncé inventé (`<<<SAVE_INVENTED_PDF>>>`) + bugfix slides Docs. 425 tests.
- **Phase A.8.1** — Affinage Découverte cas A (PDF inventé) vs cas B (TP existant comme matériau, posture bottom-up §1.6bis) + archive .md live dans `_archives/<MAT>/`. 443 tests.
- **Phase A.8.2** — Format pédagogique en Découverte (oral/photos/mixte) avec §1.6ter, OCR Flash 2.5 étendu à découverte, slash-cmds `/oral` `/photos` `/mixte`. 454 tests.
- **Phase A.8.3** — Sujet libre (apprendre hors COURS/) : checkbox `💡 Sujet libre` + textarea, bypass combos COURS, sentinelles `LIBRE/SUJET/<slug>/full`, mode guidé refusé, ancrage forcé `aucun`, `slugify_topic(text)`. 471 tests.
- **Phase A.8.4** — Anti-hallucination OCR (marker `[AUCUNE IMAGE DANS CE MESSAGE]` + filtre `strip_hallucinated_ocr_block` + prompt COMPAGNON v0.8), auto-scroll textarea, numérotation listes ordonnées (fix regex `renderMarkdown`), récap non re-posté au reload. 484 tests.
- **Phase A.8.5** — Édition message : paste image / drag-drop / photo mobile redirigés vers textarea édité (`_activeEditTextarea`). Safety net : backup auto dans `_sessions/_trash/` et `_archives/<MAT>/_trash/` avant DELETE/écrasement. Hotfixes UX : syntax error `closeBtn`, Reprendre session, GUI layout console écrasée, hint dynamique sous radio mode (wraplength adaptatif), design pills/chips, overlay sombre `#crop-preview-modal`, bouton croix stylé. 484 tests.
- **Phase A.8.6** (2026-05-13) — Suffixe `_{mode}_{format}_{anchor}` au session_id (`app.py:_build_session_id`) → trois versions du même exo cohabitent. `_should_replay_transcript` simplifié : replay tant que `n < 300` tours (suppression du critère « 6 h d'inactivité » qui faisait perdre tout le contexte fin à la reprise après une nuit). `findExistingSession` côté JS et `/api/sessions` exposent désormais mode/format/anchor. Migration one-shot des 11 sessions existantes via `_scripts/migrate_session_ids.py`. 484 tests.
- **Phase A.9** (2026-05-13) — Nouveau mode `workspace` : tutorat sur un dossier disque arbitraire hors COURS/ (codebase, docs, CV…). Checkbox `📁 Workspace` + folder picker dans la GUI Tk. Quick presets persistés. Pattern excludes personnalisés. Sous-dossier de focus. Heuristique code/doc/mixed auto. Tools `Read`/`Grep`/`Glob` scopés au workspace via `cwd` subprocess. Nouveau `_prompts/PROMPT_SYSTEME_WORKSPACE.md` (3 postures explain/quiz/deep-dive). 498 tests.
- **Phase A.9.1** (2026-05-14) — Galerie photos auto dans la sidebar (onglet `📸 Photos` à côté de 🔖 Notes). Chaque image attachée à un `send_message` est persistée dans `session_photos[]` (champ additif du JSON de séance, pas de bump). Endpoints `GET /api/session_photos` + `DELETE /api/session_photos/<id>` (le fichier disque sous `COURS/.../photos/` reste, seule l'entrée de tracking est retirée). Grille de vignettes (auto-fill 120 px) servies via `/api/cours_file?path=...`, click → `openLightbox`, 🗑 en overlay au hover, tri anti-chrono. 510 tests.
- **Phase A.9.2** (2026-05-14) — Fix bloc OCR Gemini Flash au F5 : `_extractOcrBlocksFromText` (mirror du backend `app.py:1496-1511`) extrait le bloc OCR concaténé au transcript student, re-rend en `<details>.ocr-collapsible` via le même helper que le live. Schéma transcript inchangé, marche sur les sessions existantes. 510 tests.
- **Phase A.10.2** (2026-05-14) — Uploads sortis de COURS/. Friction : les sessions Sujet libre / Workspace n'ont rien à voir avec COURS, c'est incohérent d'y stocker leurs photos. Nouveau `UPLOADS_DIR = PROJECT_ROOT / "_uploads"` (gitignored), arborescence `_uploads/{session_id}/{photos|attachments}/`. `_attachment_target_dir` refactor : signature `(session_id, is_image)`. Markdown injecté avec préfixe `_uploads/` pour les nouvelles, `renderMarkdown` JS route vers `/api/upload_file` (nouveau) vs `/api/cours_file` (legacy). Champ `storage: "uploads"|"cours"` sur chaque entry. Helpers `_attachmentSrcUrl` (desktop) / `_attachmentSrcUrlM` (mobile). Cohabitation sans migration : anciennes sessions restent sous COURS, nouvelles vont dans `_uploads/`. 562 tests (+8 nouveaux).
- **Phase A.10** (2026-05-14) — Mémoire persistante de séance. Onglet `📌 Consignes` entre 📸 Photos et 💬 Historique. Deux origines : (`kind="user"`) chip 📌 hover-only sur bulles student, (`kind="tutor"`) balise `<<<REMEMBER>>>{"text":"..."}<<<END>>>` émise sur demande explicite. Helper `_format_stickies_block_for_llm` injecte `[CONSIGNES ÉPINGLÉES…]` en préfixe de chaque user message LLM (canal séparé, transcript propre). 5 endpoints `/api/stickies` (GET/POST/PATCH/DELETE + import_from). Modal d'import 2 étapes depuis une autre session. Modif des 4 prompts système : COMPAGNON v0.9, GUIDE v1.7, DECOUVERTE v1.3, WORKSPACE v1.4. 546 tests (+37 nouveaux).
- **Phase A.10.13** (2026-05-14) — Méga-itération mode Découverte + UX panneaux :
  - **a)** Suppression invented PDF complète (balise `<<<SAVE_INVENTED_PDF>>>` + module `invented_pdf.py` + endpoints `/api/generated/` + checkbox `📄 Générer PDF` + instructions de prompt). Le tuteur invente ses questions au fil de la conversation.
  - **b)** Export récap PDF+MD on-demand via bouton 📄 dans le footer sidebar. Module `_scripts/dialogue/session_export.py` (reportlab pour PDF, markdown brut pour MD). Endpoint `GET /api/export_recap` retourne un ZIP.
  - **c)** Sommaire dynamique 📑 dans l'onglet Docs (au-dessus des PDFs). Extracteur regex post-stream tuteur détecte `## H2`, `### H3`, `**Exercice N**`, listes numérotées en mode colle. Édition inline (double-click titre), toggle on/off (✓/⏸), suppression (🗑), click corps → scroll bulle source. Endpoints `GET / PATCH / DELETE /api/dynamic_outline[/<id>]`. Persisté dans `session_state.data["dynamic_outline"]`.
  - **d)** Renommage photos via OCR Gemini : `YYYY-MM-DD_HHMM_<kind>_<slug>_vN.ext`. Skip si OCR médiocre.
  - **e)** Hover nom joli photo gallery (helper `_prettifyPhotoFilename`).
  - **f)** Astuces enrichies (5 nouvelles entrées en tête de TIPS_CATALOG).
  - **g)** Script `_scripts/rename_old_photos.py` standalone pour rattraper les anciennes photos (dry-run/--apply, backup auto, ~$0.003 pour 33 photos).
  - **A.10.14** sidebar : retour top tabs horizontaux icons-only (après rejet rail vertical gauche puis droite). Padding uniforme tous panes.
  - **Fix ignore_enonce** persistant : force False au boot (option ponctuelle, plus persistée). Warnings inline 🎲 et 💡.
  - 530 tests, aucune régression.
- **Phase A.10.27** (2026-05-15) — `mark.saved-note-mark` (surligneur 💾 Notes save dans les bulles) passe de jaune hardcodé → **orange par défaut** via CSS variable `--note-saved-hl`. Évite la confusion avec le surligneur jaune cahier (formule vitale). Ajouté comme 9ᵉ ligne dans le panneau 🎨 Couleurs (configurable par color picker, persisté localStorage). Astuce 💾 Save mise à jour (multi-paragraphes, explique que la save marche n'importe où dans le dialogue et que la couleur est configurable).
- **Phase A.10.26** (2026-05-15) — Heuristique sémantique pour inline `<code>` : auto-classification rouge (nom/concept) vs vert (valeur/exemple) via regex sur le contenu — `"..."`/`[]`/`(…)`/digits-only → vert, sinon rouge. Évite de dépendre de la discipline du tuteur LLM qui follow-la-voie-de-moindre-résistance. Nouvelle classe CSS `.cahier-code-inline-value` (vert) en parallèle de `.cahier-code-inline` (rouge). Edge cases comme `Just A` → rouge par défaut, override via `{vert}Just A{/vert}` si besoin.
- **Phase A.10.25** (2026-05-15) — CC3 propagation complète : `_oneshot_convert_cahier_cc3.py` refactor avec 4 patterns en cascade (A = trigger+fenced, B = trigger+prose 1-5 lignes, C = trigger+bold-title+bullets, D = trigger+bold-title+inline-code-prose). 11/12 cahier moments convertis sur CC3 (vs 4/12 initialement). Le 12ᵉ est une mention incidente non pertinente.
- **Phase A.10.24** (2026-05-15) — Tone-toolbar contextuelle (📚 Cours / 🎬 Vidéo / 🌐 Internet) étendue au mode **guidé** (en plus de colle/découverte). Le raisonnement initial « en guidé le tuteur a FS donc bouton inutile » ne tenait que pour 📚 Cours (et même là, bypass tuteur reste utile) — pour 🎬/🌐, le tuteur n'a pas de tools web quel que soit le mode. Workspace reste exclu (pas de contexte COURS). Cohérence : les 3 modes pédagogiques voient la même toolbar.
- **Phase A.10.23** (2026-05-15) — Reposition onglet 🎨 Couleurs (entre Consignes et Historique, au lieu d'en bout de stack). Fusion 🔍 Exo voisin + 📚 Passage CM → 1 bouton **📚 Cours** (1 mot) qui lance les 2 recherches en `Promise.allSettled`. Toolbar contextuelle 5→4 boutons. CC3 re-propagation avec pattern B (prose multiligne post-trigger sans code block) : +1 card (total 4 CC3).
- **Phase A.10.22** (2026-05-15) — Unification gestion couleurs : selection-toolbar passe de 13→5 boutons (1 seul « 🎨 Colorier » qui ouvre l'onglet Couleurs avec sélection active). Onglet Couleurs unifié : input hex = remap global, swatch cliquable = applique-à-sélection (quand bannière `🎯 Sélection active` visible). `_pendingColorSelection` global avec expiry 60s. Astuces fusionnées en 1 entrée explicative.
- **Phase A.10.21** (2026-05-15) — Nouvel **onglet 🎨 Couleurs cahier** : remap rétroactif via CSS variables (`document.documentElement.style.setProperty('--cahier-c-rouge', ...)`). Refactor `.cahier-c-*` et `.cahier-hl-*` pour utiliser `var(--cahier-c-X)` / `rgba(var(--cahier-hl-X), 0.55)`. Persistance `localStorage`. 4 stylos + 4 surligneurs avec color picker hex + bouton ↺ Reset. Fix collision `_applyCahierColor` (sélection toolbar A.10.20) vs nouveau setter CSS var → renommé `_setCahierCSSVar`. Aussi : fix régression — boutons 🔍 Exo voisin / 📚 Passage CM / 🎬 Vidéo YouTube / 🌐 Recherche internet étaient gated `activeMode === "colle"` → étendu à `colle || découverte` (utile en découverte aussi pour les vidéos explicatives).
- **Phase A.10.20** (2026-05-15) — Doctrine cahier raffinée : `**gras**`/`*italique*` strippés (sans sens sur papier), `` `code inline` `` auto en rouge stylo sans monospace, blocs ``` ``` ``` auto en vert avec commentaires `-- # //` en rouge italique. Color picker UI : sélection texte dans `.cahier-card` → toolbar étendue avec 4 stylos + 4 surligneurs + ⌫ clear, PATCH `/api/messages/<i>` silencieux. 23 OCR faux-positifs décapsulés (`_oneshot_undo_ocr_cahier.py`). CC3 propagation partielle (3 cards via `_oneshot_convert_cahier_cc3.py`, pattern trigger+code-block). Tips réordonnés en 5 sections (basics en tête, troubleshooting en bas), `renderTipsList` supporte body multi-paragraphes. Prompt Découverte v1.5.
- **Phase A.10.19** (2026-05-15) — **Carte cahier** : artefact « feuille de cours » coloriée émise par le tuteur en Découverte aux moments « notez sur votre cahier ». Balise `<<<CAHIER titre="...">>>...<<<END>>>` parsée par `_renderCahierBlock` (extraction pré-markdown-it). CSS `.cahier-card` : fond crème, lignes Seyès, marge stylo rouge, sous-titre violet hl. Doctrine couleurs basée sur audit photos cahier réel : Bic 4-couleurs (bleu défaut, rouge concept-clé, vert exemples, noir code) + 4 surligneurs ponctuels (jaune formule vitale, rose piège, violet/vert auto sur titres). Anti-sapin-de-Noël : max 2 surligneurs ponctuels + max 3 mots couleur stylo par carte. Prompt Découverte v1.4 §1.6quater documente la syntaxe + 3 exemples. Astuce ajoutée en tête de TIPS_CATALOG. 48 cartes appliquées rétroactivement sur TP8 / TP9 PRG2 / AN1 CCT via `_scripts/_oneshot_convert_cahier.py` (heuristiques sobres : rouge sur 1er backtick après labels-clefs, vert sur backticks après « Exemple : », code fenced préservé). Doc README §« 📒 Carte cahier ».
- **Phase A.10.18** (2026-05-15) — Détection upstream-unavailable (`\b50[234]\b|UNAVAILABLE|high.demand|overload|temporarily`) dans le handler SSE `error` : message FR explicite + `flashEngineSwitcher()` qui clignote orange + auto-focus. Le handler quota appelle aussi `flashEngineSwitcher` désormais. 2 nouvelles astuces en tête de `TIPS_CATALOG` : « ⚠ 503 UNAVAILABLE — c'est du côté serveur » (avec action spotlight `#engine-switcher`) et « ✏ Éditer un message > en écrire un nouveau pour recharger le contexte ».
- **Phase A.10.17** (2026-05-15) — Boutons du footer input (`🎤`, `✨`, `📎`, `📷`) ciblent désormais `_activeEditTextarea` quand une bulle est en édition (helper `_getActiveTextarea()`). Avant : ✨ regardait `userInput.value` (toujours vide en édition → disabled), 🎤 écrivait la transcription dans `userInput` (jamais dans le textarea édité). Les boutons 📎/📷 routaient déjà via `uploadAttachmentFile` (Phase A.8.5) — généralisation pour cohérence. Aussi : le snapshot pre-mic est **toujours** préservé (refonte de la logique v15.7.24 qui se cassait avec WebSpeech). Friction user : « si y'a du texte déjà actif, le mic ne doit pas l'annuler ». Nouveau global `_recordingTargetTextarea` verrouillé au démarrage de l'enregistrement.
- **Phase A.10.16** (2026-05-15) — Migration `renderMarkdown` (240+ lignes de regex hardcoded) vers **markdown-it v14** via CDN. CommonMark + GFM natifs, streaming-tolérant, edge cases composés gratuits (blockquote+listes, imbrication, etc.). Hooks préservés via `renderer.rules.image` (routing `_uploads/`/`COURS`/externe, tooltip OCR-renamed, `onerror` placeholder, wrap 🗑) + `renderer.rules.table_open` (classe `md-table`). Lazy-init au 1ᵉʳ render parce que `app.js` n'a pas `defer` mais la lib si. Suppression de `_renderBulletList`. Voir CHANGELOG pour le détail et `README.md` §6 pour la doc.
- **Phase A.10.15** (2026-05-15) — Hotfixes session UX :
  - **a)** Modal de conflit cohérent : `findExistingSession` côté JS et le short-circuit `activeSession` du submit handler comparent désormais le contexte complet (matière/type/num/exo/année **+ mode/format/anchor** — la suffixe A.8.6 distingue ces axes). Avant : passer TP8→TP9 affichait un modal qui parlait de TP9 mais montrait la session TP8 ; idem strict↔consultatif sur le même exo. Fall-through vers `findExistingSession(body)` quand le contexte diffère, modal seulement quand match exact.
  - **b)** Sommaire dynamique compatible Gemini API : regex `_OUTLINE_RE_NUM_TITLE` tolère le préfixe optionnel `(?:Titre|Title|Notion|Concept|Th[èe]me)\s*[:\-]?` (engine Gemini émet `**Titre : 1. …**` au lieu de `**1. …**`). Constante `_OUTLINE_EXTRACTOR_VERSION = 2` + version-gate dans `_maybe_backfill_outline` → re-backfill automatique au bump. Tracking `dynamic_outline_deleted_signatures` dans le DELETE endpoint pour préserver l'intention « entry supprimée ne réapparaît pas ». Sort chronologique par position du `source_message_id` dans `current_branch_path`, appliqué au backfill ET au GET (défensif).
  - **c)** Header form sync au resume : `/api/resume_session` expose maintenant matiere/type/num/exo/annee (+ sujet_libre/workspace_root). Helper JS `syncFormToSession(data)` cascade les selects, gère sujet libre (coche checkbox + remplit textarea) et workspace (bypass). Appelé depuis `resumeSession` (modal conflit + panneau Historique) et `restoreActiveSessionIfAny` (F5 / restart). Friction user : *« je vois les champs de prg2 alors que je suis passé en AN1 c'est troublant »*.
  - **d)** Listes à puce dans les blockquotes : `renderMarkdown` re-applique les regex bullets + numérotées sur le contenu interne du blockquote après strip du préfixe `&gt;\s?`. Avant : `> - item` affichait littéralement `*` (pattern Gemini API qui emballe les cartes-cahier dans des blockquotes).
- **Phase A.11** (2026-05-17) — Suppression complète du système de points faibles. Friction : l'user ne trouve pas la mécanique pertinente. Retiré : balise `<<<WEAK_POINT>>>` (parser), tool `capture_weak_point`, champ `cm_anchor`, clés `weak_points[]` / `weak_points_retro[]` / `stats.weak_points_count` du schéma de session, dossier `_points_faibles/`, helper `_read_previous_weak_points` + cap `previous_weak_points_top_n`, section `POINTS FAIBLES HISTORIQUES` du contexte initial, endpoint `/api/export_anki`, référentiel de scoring 0-4, §5/§6 du prompt COMPAGNON. **Conservés** : le débrief post-séance (récap résumé/concepts/exos/suggestions) et le mini-exo ciblé — le mini-exo se déclenche désormais sur un **concept** du récap (bouton 🎯 par concept), plus sur un point faible scoré. 4 prompts système édités (COMPAGNON v1.1, GUIDE v1.9, DECOUVERTE v1.6, WORKSPACE v1.5). Tests : suppression des cas weak-point, 516 tests verts.
- **Phase A.11.1** (2026-05-17) — Anti-troncature Gemini + boutons d'avancement de fin de séance. Bug : un récap de 23 fiches en `<<<CAHIER>>>` (engine `gemini_api`) coupé en plein milieu — `_stream_via_gemini` n'inspectait pas `finish_reason`, et `DEFAULT_MAX_TOKENS=4096` était dépassé. Fix : max_tokens 4096→8192, détection `finish_reason==MAX_TOKENS` → helper `_autoclose_truncated_tags` referme les balises orphelines + avertissement dans le fil. Carte récap de débrief enrichie : bloc « 🚀 Pour aller plus loin » (📄 bloc leçon / 📄 bloc exos / 📝 série d'exos / 🎯 mode colle) via nouvel endpoint `POST /api/recap_action`, + carte post-fermeture « ✅ Séance terminée — et maintenant ? ». Aucune modif de prompt système. 522 tests verts.
- **Phase A.12** (2026-05-21) — Outils filesystem réels pour les moteurs API. Bug audité : séance `2026-05-21_WORKSPACE_tp-recherche-docu` (engine `gemini_api`) — le tuteur a émis un faux `<execute_tool>Read(...)</execute_tool>` puis **halluciné intégralement** le sujet du TP. Cause : les modes `workspace`/`guidé`/`découverte` promettent `Read`/`Grep`/`Glob` mais ces outils n'étaient câblés que pour `cli_subscription` ; sur les 4 moteurs API, aucun canal d'outil → le modèle confabule au lieu de lire. Fix : nouveau module `_scripts/dialogue/fs_tools.py` (schémas 3 formats + exécuteur réel scopé, lecture seule, garde-fous secrets, ingestion native PDF/image) + vraie boucle agentique (`MAX_TOOL_ROUNDS=6`) dans `_stream_via_gemini` / `_stream_via_api` / `_stream_via_openai_compatible`. Aussi : `PROMPT_SYSTEME_DECOUVERTE.md` v1.7 — §1.6quater renforcée (déclencheurs + cadence des cartes `<<<CAHIER>>>`, friction « cartes trop rares »). 546 tests verts (+24 `test_fs_tools.py`).
- **Phase A.12.1** (2026-05-21) — Suite de l'audit workspace. Hallucination confirmée corrigée (le tuteur lit les vrais fichiers). 3 frictions restantes traitées : (1) appels d'outils **invisibles** (« 1 bloc » sans animation) → marqueur `<<<TOOLCALL>>>{json}<<<TOOLEND>>>` injecté dans le flux par la boucle d'outils (`fs_tools.tool_call_marker`), rendu front en **puce animée** « 🔍 Lecture de X » (`app.js _renderToolCallChip` + CSS `.tool-call-chip`) ; (2) aucune carte `<<<CAHIER>>>` en mode workspace → `PROMPT_SYSTEME_WORKSPACE.md` v1.6 §2.9 (portage du système de cartes cahier) + §4.12 (pas de sur-narration des appels d'outils) ; (3) `DEFAULT_GEMINI_MODEL` `gemini-2.5-pro` → **`gemini-3.5-flash`** (2.5-pro a perdu son free tier ; 3.5-flash est stable, free, ~4× plus rapide). 553 tests verts (+7).
- **Phase A.12.2** (2026-05-21) — Fix `400 INVALID_ARGUMENT` Gemini 3 : `gemini-3.5-flash` exige que les `function_call` renvoyés dans l'historique conservent leur `thought_signature`. `_stream_via_gemini` rejoue désormais le tour modèle avec les objets `Part` d'origine (`genai_types.Content`) au lieu de dicts reconstruits. Aussi : libellés moteur GUI (`gui.py` radio + fallback, `app.js` tips) « Gemini 2.5 Pro » → « Gemini 3.5 Flash ». 553 tests verts.
- **Phase A.12.3** (2026-05-21) — (1) Carte cahier malformée : Gemini émet parfois `<<<CAHIER titre="…">` (1 seul `>`) → regex d'extraction tolèrent désormais 1-3 `>`. (2) Modal de conflit absent en workspace : `findExistingSession` matchait matiere/type/num (absents du body en workspace) → `/api/sessions` expose `workspace_root`, match sur le dossier. 553 tests verts.
- **Phase A.12.4** (2026-05-21) — Questions à choix cliquables. Nouvelle balise `<<<CHOICES>>>{"q","multi","options"}<<<END>>>` → le front (`app.js _renderChoicesBlock` + listener délégué `_onChoicesClick` + CSS `.choices-block`) rend boutons cliquables + champ libre « Autre », façon interface Claude.ai. Prompts `PROMPT_SYSTEME_WORKSPACE.md` v1.7 §2.10 et `PROMPT_SYSTEME_DECOUVERTE.md` v1.8 §4.6. Le cadrage workspace propose explicitement « 📚 Faites-moi cours ». 553 tests verts.
- **Phase A.12.5** (2026-05-21) — Bug LaTeX `siunitx` : le tuteur émettait `\SI{}{}` / `\kilo` / `\hertz` / `\per` que KaTeX ne supporte pas → rouge littéral (+ `\SI{}` brut hors `$…$`). Fix : `_normalizeSiunitx` (app.js, branché dans `_protectMathSpans`) convertit siunitx au rendu — forme KaTeX dans les `$…$`, texte plein hors math, remplacement en un seul passage (regex globale + table). Correctif rétroactif (re-rendu). Prompts WORKSPACE v1.8 / DECOUVERTE v1.9 : interdiction de `siunitx`. 553 tests verts.
- **Phase A.12.6** (2026-05-21) — Le surligneur violet des titres de carte cahier ne s'affichait jamais : réservé (A.10.30) aux titres numérotés, or les titres de carte ne le sont jamais → tout en vert, violet inutile. Fix `_renderCahierBlock` : titre de carte **toujours violet**, sous-titres `##`/`###` du corps en vert. Hiérarchie nette, les 2 surligneurs servent. 553 tests verts.

### Phase B — TTS, photos, reprise (à venir)

Scope possiblement réduit par la dispo de Cowork (cf. README §« Pourquoi pas Cowork »). Items qui restent côté Compagnon (parce que Cowork ne les couvre pas) :

- `_scripts/audio/tts.py` Edge TTS primary + Piper fallback
- Pré-génération du cache TTS pour les relances types
- Mode reprise de session (`[RESUME_SESSION]`)

Items potentiellement délégables à Cowork :
- Watcher `_photos_inbox/`

### Phase C — transfert photo téléphone→PC (après les CC3)

- Mini serveur Flask exposé via Tailscale pour réception photos

### Phase D et au-delà

À définir selon retour d'usage. Pistes :
- Stats personnelles (progression dans le temps)
- Intégration avec le cog `cours_pipeline.py` BotGSTAR pour pousser les récaps en Discord
- Upgrade A.7-light → A.7-full si la friction « valider chaque édit » devient gênante

---

## 10. RÈGLES ABSOLUES (À NE JAMAIS ENFREINDRE)

1. **Fichiers de doctrine — autorisation explicite par défaut.** `_prompts/`, `CLAUDE.md`, `README.md`, `ARCHITECTURE.md`, `CHANGELOG.md` sont des artefacts de doctrine. Par défaut, Claude Code n'y touche pas. **Exception** : Gstar peut autoriser explicitement Claude Code à les éditer dans une conversation donnée (« vas-y mets à jour le README », « tu mets à jour les fichiers meta », etc.). Cette autorisation vaut pour la session courante ; au début d'une nouvelle conversation, le défaut redevient « ne pas toucher ». Les règles 6 (prompt système sacré) et le respect de la structure existante restent inviolables même sur autorisation.

2. **Pas de chemin absolu en dur dans le code.** Tout passe par `config.py`. Exception tolérée : le `sys.path.insert` vers Arsenal_Arguments en Phase A (cf. §3.2), à supprimer en Phase B.

3. **Atomic writes obligatoires** sur `_sessions/`, `_secrets/`. Cf. §3.4.

4. **Idempotence** : un script relancé donne le même résultat. Pas de duplication, pas de side-effects cumulatifs. Cf. §3.5.

5. **Mode économe par défaut** pendant la phase de construction. Cf. §6.

6. **Pas de modification du prompt système sans concertation Gstar.** Le prompt système est sacré. Cf. §1.4.

7. **Pas d'upload du dossier `_secrets/` nulle part.** Il doit être dans `.gitignore` à vie.

8. **Pas de log des chemins absolus contenant des infos identifiantes** (`Gstar`, `OneDrive`, etc.) quand un chemin relatif suffit. Cf. §8.4.

9. **Tolérance en runtime, rigidité en schéma** : le parser accepte les malformations Claude (et logge), mais le schéma JSON est strict en lecture-écriture côté code Python.

10. **Pas de scope creep en cours de phase.** Si Claude Code ou Gstar voit une amélioration potentielle qui n'est pas dans la phase courante, ça va dans `TODO_GLOBAL.md` ou en CHANGELOG (note "reporté Phase suivante"), pas dans le code.

---

## 11. POINTERS UTILES

- **Choix des moteurs LLM** (subtilités prix, free tiers, use cases, pourquoi pas GPT, cas Arsenal) : `MOTEURS.md` (Phase v15.6.5+)
- **Spec pédagogique mode colle** : `_prompts/PROMPT_SYSTEME_COMPAGNON.md` (v1.1, Phase A.11, ancrage corrigé **paramétré en 3 modes** §1.4 [strict/consultatif/aucun] + §1.6 format paramétré + neutralité du canal d'upload + protocole OCR obligatoire + **garde-fou anti-hallucination OCR** (marker `[AUCUNE IMAGE DANS CE MESSAGE]`) + §1.7 **phase débrief post-séance** + §1.7bis **mini-exo ciblé** + §4.11/§4.12/§4.13 pas de résistance aux bascules de format/ancrage/débrief + **§8 Consignes épinglées (mémoire persistante)** + balise `<<<REMEMBER>>>` + §4.14)
- **Spec pédagogique mode guidé** : `_prompts/PROMPT_SYSTEME_GUIDE.md` (v1.9, Phase A.11, tuteur slide-par-slide + Read FS + suggestions ; absorbe l'ex-mode lecture supprimé Phase Z.8 ; §6 Consignes épinglées + §4.9)
- **Spec pédagogique mode découverte** : `_prompts/PROMPT_SYSTEME_DECOUVERTE.md` (v1.9, Phase A.12.5, tuteur explicateur zéro prérequis + §1.6 PDF d'énoncé inventé via `<<<SAVE_INVENTED_PDF>>>` conditionnel (cas A) + §1.6bis pédagogie bottom-up sur TP existant (cas B) + §1.6ter format pédagogique paramétré [oral/photos/mixte] avec posture distincte (ancrage mnémonique) + §1.6quater cartes `<<<CAHIER>>>` (syntaxe + déclencheurs + cadence) + §4.6 questions à choix `<<<CHOICES>>>` + cycle exposition→question→validation + max 2 concepts neufs/réplique + pas de barème d'indices + §4.11 pas de résistance aux bascules de format + §6 Consignes épinglées + §3.14. Progression idéale : Découverte → Guidé → Colle)
- **Spec pédagogique mode workspace** : `_prompts/PROMPT_SYSTEME_WORKSPACE.md` (v1.8, Phase A.12.5, tuteur sur dossier disque arbitraire + 3 postures explain/quiz/deep-dive + Read/Grep/Glob réels sur les 5 moteurs + §2.9 cartes `<<<CAHIER>>>` (siunitx interdit) + §2.10 questions `<<<CHOICES>>>` + §4.12 pas de sur-narration des appels d'outils + §5bis Consignes épinglées + §4.11)
- **Mémoire persistante de séance** (Phase A.10) : onglet 📌 Consignes du sidebar. Endpoints `/api/stickies` (GET/POST/PATCH/DELETE + import_from). Helper `_format_stickies_block_for_llm` injecte `[CONSIGNES ÉPINGLÉES…]` en préfixe de chaque user message LLM. Balise `<<<REMEMBER>>>` côté tuteur sur demande explicite. Persisté dans `session_state.data["stickies"]` (champ additif, scope par session). Pattern miroir des Notes et Photos.
- **Sujet libre (hors COURS/)** : Phase A.8.3 (2026-05-12). Checkbox `💡 Sujet libre` dans le form (GUI Tk + web). Bypass des combos matière/type/num/exo, le tuteur enseigne uniquement depuis ses connaissances LLM. Mode guidé refusé. 1er tour = phase de cadrage (questions niveau / objectif / temps dispo). PDF d'entraînement optionnel. Storage `_sessions/YYYY-MM-DD_LIBRE_<slug>_full.json`. Helper `prompt_builder.slugify_topic(text)`.
- ~~**Archive .md des séances**~~ : **supprimée Phase A.10.11** (2026-05-14). Friction user : « honnêtement archive .md sert à quoi ? car y'a déjà le JSON au pire ? ». Vrai, le live-archive ajoutait de l'I/O disque pour zéro usage réel. Le JSON est l'unique source de vérité côté sessions. Si exposition portfolio future, un générateur on-demand du `.md` depuis le JSON sera écrit (~30 min).
- **Spec technique** : `ARCHITECTURE.md` (sync à jour A.7.1)
- **Narratif des phases** : `CHANGELOG.md` (frictions + livré + tests)
- **Guide utilisateur** : `README.md`
- **Module quota** réutilisé : `../Arsenal_Arguments/claude_usage.py`
- **Stack Whisper** réutilisée : faster-whisper large-v3 via `_scripts/audio/transcribe_stream.py` (chargement lazy côté `app.py` pour `/api/transcribe`)
- **Racine des cours** : `C:\Users\Gstar\OneDrive\Documents\COURS\` exposée via `config.COURS_ROOT`
- **Settings runtime éditables à chaud** : `_secrets/runtime_settings.json` via `_scripts/runtime_settings.py` (seuils quota, caps contexte, last_selection)
- **Resolver arbo COURS** (énoncé/corrigé/perso/list_*) : `_scripts/dialogue/cours_resolver.py`
- **Lanceur GUI sans console** : `start_gui.vbs` (double-clic, `pythonw.exe gui.py`)

---

## 12. RAPPEL FINAL

Tu es Claude Code. Tu codes ce qu'on te demande, dans le périmètre de la phase courante, en mode économe en tokens, sans toucher aux fichiers de doctrine.

Si tu hésites, demande. Si tu détectes une incohérence dans la doctrine, signale-la à Gstar. Si une phrase de ce CLAUDE.md te paraît contradictoire avec une autre, **arrête-toi** et demande arbitrage.

L'objectif n'est pas de coder vite. L'objectif est de coder juste, dans un cadre que Gstar peut auditer et faire évoluer pendant 6 mois sans perdre le fil.
