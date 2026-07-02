# CHANGELOG : Compagnon_Revision

> Historique narratif des phases du projet : pourquoi chaque pivot, quelles
> frictions rencontrées, ce qui a été remplacé. Format inspiré de
> `BotGSTAR/CHANGELOG.md` (Phases Y.x).
>
> Pour le mode d'emploi user-facing, voir [README.md](README.md). Pour la
> doctrine et les règles permanentes, voir [CLAUDE.md](CLAUDE.md). Pour la
> spec technique, voir [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Phase S5 (Cartable) : harmonisation visuelle + fenêtre applicative (2026-07-02)

User : *« Améliore aussi l'interface du compagnon revision pour qu'il soit adapté comme celui de Cartable … soit tu fusionnes soit deux logiques, à toi de voir. »*

Contexte : Cartable est devenu une application locale (serveur stdlib + front web dans une fenêtre Edge `--app`, thème nuit bleutée / accent ambre) et sait désormais ouvrir une séance droit directement dans le Compagnon (lien profond `?source=droit&autostart=1` si Flask 5680 tourne, sinon `compagnon.py <slug> <CM|TD> <n> full --source droit --autostart`). Décision d'architecture : **pas de fusion des codes** (les deux moteurs restent indépendants), mais **une seule expérience visuelle et de lancement**.

Deux changements, volontairement minimaux :

1. **Palette `:root` de `style.css`** alignée sur celle de Cartable (`--bg #0f1319`, `--bg-elev #161c26`, `--fg #e8ecf2`, `--fg-dim #9aa7b8`, `--accent #e8b04b` ambre au lieu du bleu, `--student`/`--claude` adoucis dans les mêmes tons). Aucune des règles CSS n'est retouchée : seules les 9 variables changent, retour arrière trivial.
2. **`compagnon.py` : `_open_ui(url)`** ouvre l'UI dans une fenêtre applicative Edge (`--app=`, sans barre de navigateur), comme Cartable. Repli sur `webbrowser.open` (comportement historique) si Edge est introuvable. Prompts, endpoints, logique de séance : intouchés.

Compile OK. Le rendu visuel des vues denses (cahier, surligneurs, chips) reste à vérifier à l'écran en vraie séance : les couleurs fonctionnelles (`--student`, `--claude`, violet/vert cahier) n'ont pas changé de rôle.

---

## Phase A.12.6 : Titre de carte cahier : violet systématique (2026-05-21)

User : *« pourquoi tous les titres sont surlignés en vert et non en violet ? … ça veut dire qu'une des couleurs ne sert à rien. »*

Le surligneur **violet** était réservé (A.10.30) aux titres de carte **numérotés** (`8. …`, `11. …`) ; un titre non numéroté basculait en **vert**. En pratique les titres de carte ne sont jamais numérotés → le violet ne s'affichait quasiment jamais, et le titre de carte se confondait visuellement avec les sous-titres `##`/`###` (verts eux aussi). Couleur morte.

Fix (`app.js` `_renderCahierBlock`) : le **titre de la carte est désormais toujours violet** (suppression du test `titreNumbered` + de la classe `cahier-titre-vert` à l'émission). Hiérarchie visuelle nette : **violet = titre de la carte**, **vert = sous-titres du corps** (`##`/`###`, lignes « Méthode : » / « Définition : »…). Les deux surligneurs sont enfin tous deux utiles. Labels du panneau 🎨 Couleurs + astuces du catalogue mis à jour. Effet rétroactif : re-rendu correct au rechargement.

**553 tests verts.**

---

## Phase A.12.5 : Bug LaTeX `siunitx` dans les cartes cahier (2026-05-21)

Audit d'une carte cahier rendue : des `\SI` `\kilo` `\hertz` `\per` **rouges littéraux**, et pire, des `\SI{1.4}{\mega bit\per\second}` bruts affichés tels quels hors `$…$`.

### Cause

Le tuteur a utilisé le package LaTeX **`siunitx`** (`\SI{valeur}{unités}`, `\kilo`, `\hertz`, `\per`, `\mega`…). **KaTeX ne l'implémente pas** : commande inconnue → rendu en rouge littéral. Et certains `\SI{}` étaient émis **hors `$…$`** → restaient du texte brut.

### Fix : normalisation au rendu (`app.js`)

`_normalizeSiunitx` convertit les commandes siunitx avant le rendu, branché dans `_protectMathSpans` (donc actif pour `renderMarkdown` ET les cartes cahier `_renderCahierBlock`) :
- dans un span `$…$` → forme KaTeX : `\SI{20}{\kilo\hertz}` → `20\,\mathrm{kHz}` ;
- hors math → texte plein : `\SI{1.4}{\mega bit\per\second}` → `1.4 Mbit/s`.

Le remplacement des macros se fait en **un seul passage** par regex globale (`/\\([a-zA-Z]+)(?![a-zA-Z])/g` + table de correspondance) : un remplacement séquentiel cassait `\per\second` : `\second`→`s` d'abord donnait `\pers`, où `\per` est collé à une lettre et n'est plus reconnu. Les vraies commandes KaTeX (`\geq`, `\cdot`, `\mathrm`, `\perp`…) sont laissées intactes (remplacement gardé uniquement pour les noms connus).

**Effet rétroactif** : le correctif agit au rendu ; au rechargement du navigateur, le message déjà émis s'affiche correctement, sans édition manuelle du JSON de séance.

### Prévention au source

Prompts `PROMPT_SYSTEME_WORKSPACE.md` v1.8 (§2.9) et `PROMPT_SYSTEME_DECOUVERTE.md` v1.9 (§4.4) : interdiction explicite du package `siunitx` : unités en clair (`44,1 kHz`, `1,4 Mbit/s`) ou `\text{}`.

**553 tests verts.**

---

## Phase A.12.4 : Questions à choix cliquables `<<<CHOICES>>>` (2026-05-21)

User : *« il peut y avoir une question qui apparaît un peu comme ce que fait claude ai avec son interface où on sélectionne les réponses qu'on veut transmettre à l'IA et toujours un dernier champ pour personnaliser »* + *« compagnon doit me proposer s'il veut me faire cours… mais là il ne le fait pas »*.

Nouvelle balise `<<<CHOICES>>>{"q","multi","options"}<<<END>>>` que le tuteur émet pour toute question fermée. Le front (`app.js` `_renderChoicesBlock`, extraction pré-markdown comme les cartes cahier) rend :
- la question + des **boutons d'options cliquables** ;
- sélection multiple si `multi=true`, choix unique sinon ;
- **un champ libre « ✍️ Autre / précise ta réponse… »** toujours présent ;
- un bouton **Envoyer** qui compose la sélection (+ texte libre) en message étudiant et l'envoie (listener délégué `_onChoicesClick`, robuste aux re-render de bulle).

Le bloc se grise (`.is-answered`) une fois répondu. CSS `.choices-block` dans `style.css`.

Prompts : `PROMPT_SYSTEME_WORKSPACE.md` **v1.7** §2.10 et `PROMPT_SYSTEME_DECOUVERTE.md` **v1.8** §4.6 : le tuteur pose ses questions fermées (cadrage inclus) via `<<<CHOICES>>>`. Surtout, le **cadrage workspace** propose désormais explicitement « 📚 Faites-moi cours dessus » comme option, si bien que l'étudiant n'a plus à deviner que le Compagnon peut faire cours, c'est offert d'emblée (réponse à la friction « faire cours pas proposé »).

**553 tests verts.**

---

## Phase A.12.3 : Carte cahier malformée + modal de conflit workspace (2026-05-21)

### Carte cahier : balise d'ouverture malformée

Audit d'une séance workspace : la carte `<<<CAHIER>>>` ne se rendait pas, elle s'affichait en texte brut. Cause : Gemini a émis la balise d'ouverture avec **un seul `>`** (`<<<CAHIER titre="…">`) au lieu de `>>>`, comme s'il fermait une balise XML après l'attribut `titre="…"`. Les regex d'extraction (`renderMarkdown`, `_hoistCahierTitles`, `_autoclose_truncated_tags`) exigeaient `>>>` exact → aucun match → rendu littéral du tag.

Fix (doctrine §9 « tolérance runtime ») : les regex acceptent désormais **1 à 3 `>`** (`>{1,3}`) après les attributs. La balise canonique reste `>>>`.

### Modal de conflit absent en mode workspace

Relancer une séance sur un workspace déjà ouvert ne proposait jamais le modal « Reprendre / Démarrer une nouvelle ». Cause : `findExistingSession` (JS) matchait sur matiere/type/num/exo, or en workspace ces champs sont synthétisés backend-side (`WORKSPACE`/`DIR`/slug) et **absents du body du formulaire au submit** ; de plus le filtre mode/format/anchor rejetait le match (`body.mode` = radio ≠ `s.mode` = `workspace`).

Fix : `/api/sessions` expose désormais `workspace_root` ; `findExistingSession` matche les séances workspace sur le seul `workspace_root` (un dossier = une conv), en ignorant mode/format/anchor.

### Nettoyage

Session `2026-05-21_WORKSPACE_tp-recherche-docu…` déplacée vers `_sessions/_trash/` à la demande de l'utilisateur (repartir sur des bases saines).

**553 tests verts.**

---

## Phase A.12.2 : Fix thought_signature Gemini 3 + libellés moteur GUI (2026-05-21)

Premier test live de la boucle d'outils sur `gemini-3.5-flash` :

> `[Erreur stream] Gemini erreur : 400 INVALID_ARGUMENT : Function call is missing a thought_signature in functionCall parts.`

### Cause

Gemini 3.x attache une **`thought_signature`** (jeton opaque lié au raisonnement du modèle) à chaque `Part` qui contient un `function_call`. Quand on renvoie ce `function_call` dans l'historique au tour suivant, la signature **doit** être présente. La boucle d'outils A.12 reconstruisait l'appel en **dict** (`{"function_call": {"name", "args"}}`) → la `thought_signature` était perdue → 400 INVALID_ARGUMENT dès le 2ᵉ round (le 1ᵉʳ appel passait, le renvoi échouait).

### Fix : `claude_client._stream_via_gemini`

Le tour modèle est désormais rejoué avec les **objets `Part` d'origine** (renvoyés tels quels par le SDK google-genai, `thought_signature` intacte) au lieu de dicts reconstruits :

```python
model_parts = [genai_types.Part(text="".join(round_text))] + fcall_parts
gemini_contents.append(genai_types.Content(role="model", parts=model_parts))
```

Ajout aussi du champ `id` dans la `function_response` quand Gemini le fournit (corrélation des appels parallèles).

### Libellés moteur GUI

`gui.py` affichait encore « Gemini 2.5 Pro » : radio du sélecteur de moteur (`text="Gemini 2.5 Pro · API…"`) + dialogue de fallback quota (`_FALLBACK_PROVIDERS`). Corrigés en « Gemini 3.5 Flash ». Idem 2 astuces du catalogue web (`app.js`, mention « typiquement Gemini 2.5 Pro » dans les tips 503 → « typiquement Gemini »). L'OCR garde `gemini-2.5-flash` (toujours en free tier, inchangé).

**553 tests verts.**

---

## Phase A.12.1 : Puces d'appels d'outils + carte cahier en workspace + Gemini 3.5 Flash (2026-05-21)

Re-test de la séance `2026-05-21_WORKSPACE_tp-recherche-docu` après A.12. **L'hallucination est corrigée** : le tuteur lit réellement les fichiers et trouve le vrai sujet (« transmission d'un flux audio par Bluetooth »). Mais l'user pointe deux frictions restantes + une demande moteur.

### Friction 1 : appels d'outils invisibles (« 1 bloc »)

> *« lorsqu'il dit qu'il fait des recherches … c'est débile car il délivre le message en 1 bloc alors que cela doit fonctionner comme fonctionne claude : il parle puis fait des recherches entre temps et il continue la rédaction, il doit y avoir de l'animation. »*

La boucle d'outils marche, mais les appels étaient **invisibles** : le texte d'avant et d'après un `Read` se collaient sans aucun marqueur (« …`rapport.tex`.**Bien, j'ai lu**… »). Aucune animation, aucune indication d'action.

- Nouveau marqueur `<<<TOOLCALL>>>{json}<<<TOOLEND>>>` (helpers `fs_tools.tool_call_marker` / `tool_call_label`) injecté dans le flux par la boucle d'outils des 3 moteurs API, entre le texte d'avant et d'après chaque appel.
- Front (`app.js` `_renderToolCallChip`, extraction pré-markdown façon carte cahier) → **puce animée** « 🔍 Lecture de `rapport.tex` » : icône par outil (📄 Read / 🔎 Grep / 🗂️ Glob), point lumineux pulsant, animation d'entrée, style erreur si l'appel échoue. CSS `.tool-call-chip` dans `style.css`.
- Le `\n\n` autour du marqueur règle aussi la concaténation collée des textes inter-rounds.

### Friction 2 : aucune carte `<<<CAHIER>>>` en workspace

> *« je vois rien du mode <<<CAHIER>>> ».*

Cause : la séance est en **mode `workspace`**, or les cartes cahier n'existaient que dans le prompt `découverte`. Le prompt `WORKSPACE` n'avait aucune section CAHIER.

`PROMPT_SYSTEME_WORKSPACE.md` **v1.6** : §2.9 *Carte cahier* portée depuis découverte (syntaxe `<<<CAHIER>>>`, doctrine couleurs sobre, déclencheurs, cadence 5-12 cartes/séance en `photos`/`mixte`). + §4.12 *Appels d'outils : pas de sur-narration* : le tuteur ne doit plus dire « je vais lire X, je reviens vers vous dans un instant » (formulation absurde pour un appel d'outil instantané) ; il appelle l'outil et enchaîne.

### Demande moteur : Gemini 3.5 Flash

> *« google a mis gemini 3.5 flash en gratuit … tu peux faire le remplacement ? »*

Vérifié sur la doc officielle Google : `gemini-3.5-flash` (sorti le 2026-05-19) est **stable**, contexte 1M, ~4× plus rapide, et **accessible en free tier**. Surtout : `gemini-2.5-pro` est passé **payant-only** sur l'API (plus de free tier), si bien que l'ancien défaut `DEFAULT_GEMINI_MODEL = "gemini-2.5-pro"` cassait le « Gemini gratuit » du Compagnon. `DEFAULT_GEMINI_MODEL` → **`gemini-3.5-flash`**. Override possible via env `GEMINI_MODEL` (ex. `gemini-2.5-pro` pour une clé payante).

### Tests

`tests/test_fs_tools.py` : +7 tests (`TestToolCallMarker` : labels, round-trip JSON, marqueur sur une ligne, délimiteurs distincts des balises parser). **553 tests verts.**

### Suivis de doc + UX

- `MOTEURS.md` mis à jour : encadré daté en tête (2026-05-21 : Gemini 2.5 Pro n'est plus gratuit, annonce 3.5 Flash le 2026-05-19), table des moteurs/tarifs, free-tier, §4.1, §7, §8. README : note datée du changement de moteur.
- `gui.py` : quand un dossier libre (nommage hors conventions COURS, ex. `PSI/TP_recherche_docu` : `rapport.tex`, `script_oral.pdf`…) ne contient aucun matériau reconnu par les détecteurs, le bouton Lancer **et** les modes Découverte/Guidé sont grisés (seul Colle reste, mais ne se lance pas non plus). Friction user : « pas normal que seul colle soit proposé ». Le hint du launcher pointe désormais explicitement vers la case **📁 Workspace** : le bon outil pour un dossier libre (il lit tous les fichiers sans dépendre du nommage, et fait CAHIER + puces depuis A.12/A.12.1).

---

## Phase A.12 : Outils filesystem réels pour les moteurs API (2026-05-21)

User : *« Y'a un gros souci là. Fais un audit sur ma conv → `2026-05-21_WORKSPACE_tp-recherche-docu…` et essaie de comprendre … pourquoi compagnon s'est mis à autant halluciner »*.

### Le bug

Séance `2026-05-21_WORKSPACE_tp-recherche-docu` (mode `workspace`, engine `gemini_api`). Le tuteur devait analyser le sujet d'un TP de recherche documentaire. Il a émis `<execute_tool>Read('TP-rech-doc-aboeka-anli.pdf')</execute_tool>` puis a enchaîné, **dans le même message**, en inventant intégralement le sujet du TP (« le rôle de l'IA dans la détection des maladies neurodégénératives »). L'étudiant corrige (« non ce n'est pas le sujet ») ; le tuteur recommence, réinvente des « métadonnées erronées », puis abandonne.

### La cause racine

Les modes `workspace` / `guidé` / `découverte` promettent au tuteur un accès `Read`/`Grep`/`Glob` au dossier de travail. Mais ces outils n'étaient câblés **que pour le moteur `cli_subscription`** (la CLI Claude Code les fournit nativement via subprocess). Sur les 4 moteurs API (`gemini_api`, `api_anthropic`, `deepseek_api`, `groq_api`) : **aucun canal d'outil**.

Conséquence : le prompt WORKSPACE ordonnait « lis le fichier avant d'affirmer, ne bluffe jamais », mais Gemini n'avait aucun moyen de lire. Le stream ne s'arrête jamais pour attendre un résultat d'outil → Gemini *simule* la lecture (`<execute_tool>` est une syntaxe qu'il a inventée, inconnue de tout le code) et **confabule le contenu**. Le prompt censé l'ancrer est précisément ce qui a induit l'hallucination.

Le mode `workspace` était le plus exposé : contrairement aux modes COURS (où `prompt_builder` pré-injecte le texte de l'énoncé/corrigé dans le contexte), le résumé auto workspace ne contient que l'arbre des fichiers + les fichiers-pivots (README/CLAUDE.md…). Le contenu d'un PDF de sujet n'y figure jamais : Gemini ne voyait qu'un nom de fichier.

### Le fix : boucle d'outils agentique sur les 4 moteurs API

Nouveau module `_scripts/dialogue/fs_tools.py` :
- schémas des 3 outils `Read`/`Grep`/`Glob` dans les 3 formats de tool-calling (Gemini `function_declarations`, Anthropic `input_schema`, OpenAI-compatible `function`) ;
- exécuteur réel `execute_fs_tool` scopé à une racine, **lecture seule**, garde-fous secrets (`_secrets/`, `.env`, `*.key`, `.git/`, `node_modules/`, venv…), rejet du `..` et des chemins hors racine ;
- `Read` numérote les lignes (citation `chemin:ligne`), gère le texte/code et les **PDF/images en ingestion native** ; `Grep` regex sur les fichiers texte ; `Glob` motifs de chemins. Toute erreur est renvoyée en douceur (le modèle voit l'erreur et se corrige, le stream ne casse pas).

`claude_client.py` : vraie **boucle agentique** dans `_stream_via_gemini`, `_stream_via_api` et `_stream_via_openai_compatible` : le modèle émet un appel d'outil → le backend l'exécute réellement → ré-injecte le résultat → relance, jusqu'à `MAX_TOOL_ROUNDS = 6` round-trips ; au dernier tour les outils sont retirés pour forcer une réponse texte. PDF/image renvoyés au modèle en `inline_data` (Gemini) ou content block `document`/`image` (Anthropic). DeepSeek/Groq étant text-only, un `Read` de PDF y renvoie un message honnête (« ce moteur ne lit pas les binaires, bascule sur Gemini/Claude »).

Les outils FS ne sont exposés que pour les modes à dépendance disque (`guidé`/`découverte`/`workspace`, helper `_should_use_fs_tools`) et désactivés si la recherche web Gemini est active (`google_search` grounding et `function_declarations` ne coexistent pas).

### CAHIER trop rare en mode découverte

User : *« ce que je voulais via le mode découverte c'était qu'il fasse cours en utilisant les `<<<CAHIER>>>` mais même ça il n'est pas capable de gérer »*.

Symptôme (audité, choix « trop rares / au mauvais moment ») : le tuteur émettait les cartes `<<<CAHIER>>>` trop rarement ou seulement en récap de fin. `PROMPT_SYSTEME_DECOUVERTE.md` **v1.7** : nouvelle sous-section §1.6quater « Quand émettre une carte cahier : déclencheurs » : liste de déclencheurs explicites (définition, syntaxe, formule, méthode, exemple canonique, distinction), cadence cible (1 carte par notion-clef, **5-12 par exercice**), règle absolue (en format `photos`, aucune notion enseignée sans carte ; la carte arrive au moment de l'explication, pas en récap groupé).

### Tests

`tests/test_fs_tools.py` : **24 tests neufs** (schémas 3 formats, exécution Read/Grep/Glob, scoping sécurité anti-traversal, refus secrets, ingestion PDF, robustesse « ne lève jamais »). **546 tests verts** (522 + 24), aucune régression sur les suites moteur (`test_provider_routing`, `test_tool_calling`, `test_claude_client_multimodal`, `test_switch_engine`).

---

## Phase A.11.1 : Réponse Gemini tronquée + boutons d'avancement de fin de séance (2026-05-17)

User : *« le dernier message a bugué. Tu peux corriger ? »* puis *« pense à fix cela pour plus que ça arrive pour de prochaines sessions »* et *« quand la session est terminé que ça arrête de mute la conv, qu'à la place ça me propose d'autres trucs pour avancer comme avoir un bloc de la leçon et des exo »*.

### Le bug

En fin de séance Découverte (`2026-05-14_AN1_CCT…`, engine `gemini_api`), le tuteur compilait un récap de 23 fiches méthodologiques dans une balise `<<<CAHIER>>>`. Le stream s'est coupé en plein milieu de la fiche 19, balise jamais refermée → bloc cahier non rendu côté front, titre annonçant « 23 fiches » pour 19 affichées.

**Cause** : la boucle de stream Gemini (`_stream_via_gemini`) lisait `chunk.text` mais **n'inspectait jamais `finish_reason`**. Avec `DEFAULT_MAX_TOKENS = 4096` et un récap très dense en LaTeX (> 4096 tokens de sortie), Gemini coupait sur `MAX_TOKENS` : coupure totalement silencieuse (ni exception, ni warning).

Réparation du JSON de séance touché : fiche 19 complétée et fiches 20-23 reconstruites depuis le contenu réel de la séance (cartes cahier 164/196/202/244 + exos d'intégrales), balise `<<<CAHIER>>>` refermée.

### Fix anti-troncature (`claude_client.py`)

- `DEFAULT_MAX_TOKENS` : 4096 → **8192** (reste sous la limite de tous les moteurs ; `gemini-2.5-pro` va jusqu'à 65536).
- `_stream_via_gemini` inspecte désormais `finish_reason` sur le candidat de chaque chunk. Si `MAX_TOKENS` :
  - helper `_autoclose_truncated_tags(text)` compte les balises ouvrantes (`<<<CAHIER…>>>`, `<<<TTS>>>`, `<<<SUGGESTED_EDIT>>>`, `<<<GOTO_SLIDE>>>`, `<<<SHOW_DOC>>>`, `<<<REMEMBER>>>`) non refermées et renvoie les `<<<END>>>` manquants → le rendu ne casse plus jamais ;
  - un avertissement `> ⚠ Réponse tronquée…` est ajouté au fil pour que l'utilisateur sache demander « continue ».
- 6 tests neufs dans `test_claude_client_multimodal.py` (`TestAutocloseTruncatedTags`).

### Boutons d'avancement de fin de séance

Avant : la carte récap de débrief proposait seulement 💬 Continuer / 🚪 Fermer, et `🚪 Fermer définitivement` désactivait tout l'input (« mute » de la conversation).

- Nouveau bloc **🚀 Pour aller plus loin** dans la carte récap, 4 boutons :
  - 📄 **Bloc complet de la leçon** : le tuteur compile toutes les fiches/leçons de la séance ;
  - 📄 **Bloc complet des exos** : regroupe les exos traités + leur correction rédigée ;
  - 📝 **Série d'exos d'entraînement** : génère de nouveaux énoncés sur les concepts du jour ;
  - 🎯 **Passer en mode colle** : pré-arme le formulaire pour relancer en mode colle sur la même matière.
- Nouvel endpoint `POST /api/recap_action {action}` (`bloc_lecon` / `bloc_exos` / `serie_exos`) qui injecte une requête pré-rédigée dans l'historique du tuteur + arme `retry_pending`, même mécanique que `/api/mini_exo`. **Aucune modification de prompt système** (le tuteur sait déjà répondre à ces demandes).
- Après `🚪 Fermer définitivement` : plus d'écran mort, une carte **✅ Séance terminée, et maintenant ?** propose 🎯 mode colle / 🔁 nouvelle séance.

**Tests** : 522 verts (516 + 6).

---

## Phase A.11 : Suppression complète du système de points faibles (2026-05-17)

User : *« supprime de partout que ce soit dans le code ou les docs la logique de point faible car je trouve pas ça pertinent »*.

Le système de points faibles (capture en séance d'un blocage scoré, agrégation, SRS Anki) était dans le projet depuis la Phase A. Jugé non pertinent à l'usage, il est retiré intégralement.

**Retiré** :
- Balise `<<<WEAK_POINT>>>` : état `INSIDE_WEAK_POINT`, event `ParserEventType.WEAK_POINT`, helpers `_try_parse_weak_point` / `_normalize_cm_anchor` du `parser.py`.
- Tool calling `capture_weak_point` (`tool_schemas.py`) et son mapping.
- Champ `cm_anchor` + validation associée.
- `SessionState.add_weak_point`, clés `weak_points[]` / `weak_points_retro[]` / `stats.weak_points_count` du schéma de session (champs simplement plus écrits ; les anciennes sessions gardent leurs clés mortes, lecture inchangée, pas de bump de `schema_version`).
- Dossier `_points_faibles/` + constante `POINTS_FAIBLES_DIR`, helper `_read_previous_weak_points` + constante `PREVIOUS_WEAK_POINTS_TOP_N` + cap `previous_weak_points_top_n`, champ `SessionContext.previous_weak_points_path`, section `POINTS FAIBLES HISTORIQUES` du contexte initial.
- Endpoint `GET /api/export_anki` + bouton « 📥 Export Anki » de la carte récap.
- Référentiel de scoring 0-4, §5/§6 du prompt COMPAGNON.

**Conservé** : le débrief post-séance et le mini-exo ciblé. Le récap Gemini Flash produit toujours `{summary, concepts_covered, exercises_handled, suggestions}` (sans `weak_points_retro`). Le mini-exo se déclenche désormais sur un **concept** du récap (bouton 🎯 à côté de chaque concept couvert) via `POST /api/mini_exo {concept, detail?}`, plus sur un point faible scoré.

**Prompts** (édition autorisée explicitement par Gstar pour cette session) : COMPAGNON v0.9→v1.1 (§5/§6 supprimées, §7→§5, §8→§6, §9→§7, §10→§8, §11→§9), GUIDE v1.8→v1.9 (§5.4 retirée), DECOUVERTE v1.5→v1.6 (§2.8 reformulée, ex-règle §13 retirée), WORKSPACE v1.4→v1.5 (§3 retirée).

**Tests** : suppression des cas weak-point dans `test_parser`, `test_session_state`, `test_prompt_builder`, `test_tool_calling` ; réécriture de `test_app_post_session` (mini-exo reciblé, plus d'export Anki). 516 tests verts.

---

## Phase A.10.31 : Balises couleur émises dans / autour d'une formule LaTeX (2026-05-16)

User : *« y'a un bug latex ici »* → *« le bug est précisément ici : `Résultat : $\sin^3(x) = -\frac{1}{4}\sin(3x) + \frac{3}{4}\sin(x)$.` »*.

Fiche récap de carte cahier (engine `gemini_api`). Le tuteur a écrit le résultat avec une balise couleur **à l'intérieur** du `$…$` :

```
Résultat : $\sin^3(x) = {vert}-\frac{1}{4}\sin(3x) + \frac{3}{4}\sin(x){/vert}$.
```

`_protectMathSpans` protégeait bien le `$…$` (placeholder), mais au **restore** le LaTeX revenait avec le `{vert}…{/vert}` à l'intérieur. La passe STYLOS de `_renderCahierBlock` convertissait alors ce `{vert}` en `<span class="cahier-c-vert">` : **scindant la formule en deux nœuds texte** autour du span. KaTeX auto-render traite les `$…$` par nœud texte : les deux `$` n'étant plus dans le même nœud, il ne pouvait plus les apparier → `$` affichés en clair + formule éclatée.

Second symptôme dans le même message : `{hl-jaune}` **non fermé** par le tuteur → la passe HIGHLIGHTS (qui exige `{hl-jaune}…{/hl-jaune}`) ne matchait pas → `{hl-jaune}` affiché littéralement.

**Fix** : deux nettoyages, via la constante partagée `_CAHIER_TAG_RE` (`{rouge}`, `{hl-jaune}`, fermetures `{/…}`…) :
1. `_protectMathSpans` strippe les balises couleur **à l'intérieur** de chaque `$…$` capturé avant de le stocker. La formule rend en noir (doctrine A.10.29 ; colorer l'intérieur d'une formule n'a de toute façon aucun effet visible puisque tout le LaTeX cahier est noir).
2. `_renderCahierBlock` strippe les balises couleur **orphelines** restantes après les passes STYLOS/HIGHLIGHTS (balise ouverte sans fermeture, ou désordonnée) → plus de `{hl-jaune}` littéral.

Les balises bien appariées **hors** `$…$` (ex. `{vert}$z_1 = 1-2i${/vert}`) ne sont pas affectées : `_protectMathSpans` ne capture que l'intérieur des `$`, et les passes STYLOS/HIGHLIGHTS consomment les paires valides avant le nettoyage orphelin.

Fix UI/regex pur, pas de test unitaire neuf (cf. convention A.10.15) ; validé par script jetable sur les deux cas. Pas de modification de prompt.

---

## Phase A.10.30 : Surligneur vert = sous-titres de carte cahier (2026-05-16)

User : *« je pense qu'il est bien de surligné les sous titres d'une autre couleur genre vert vu que […] il en sert à rien actuellement »* puis *« aussi titre ## et ### en vert »* puis *« vu que c'est pas un titre numéroté par 1. 2. 3. […] il doit être en vert et non violet le surligneur »*.

Suite logique d'A.10.29 : après avoir donné un rôle au stylo **noir** (LaTeX), on en donne un au surligneur **vert** (`hl-vert`), jusqu'ici inutilisé : la doctrine le réservait au « titre de fiche root », jamais émis.

**Nouvelle répartition violet / vert** :
- 🟣 **Violet** = titre de carte **numéroté** (« 8. Limite en +∞ », « 11. Limite avec racines »), une vraie section.
- 🟢 **Vert** = **sous-titres**, détectés automatiquement côté frontend (le tuteur ne balise rien) :
  - titre de carte **non numéroté** (« Factorisation du dénominateur : », « Application… »), via la classe `cahier-titre-vert` ;
  - lignes-label du corps : `<p>` commençant par `Méthode :`, `Définition :`, `Théorème :`, `Propriété :`, `Proposition :`, `Lemme :`, `Corollaire :`, `Règle :`, `Notation :`, `Rappel :`, `Remarque :`, `Astuce :`, `Exemple :`, `Démonstration :`, `Preuve :` → `<mark class="cahier-hl-vert">` ;
  - titres markdown `##` / `###` (rendus `<hN>` par markdown-it) → `<mark class="cahier-hl-vert">`, ramenés à une taille de sous-titre via CSS.

Détection dans `_renderCahierBlock` : un titre est « numéroté » s'il matche `^\s*\d+\s*[.)]`. Sinon → `cahier-titre-vert` (fond `rgba(var(--cahier-hl-vert), 0.60)`).

Annexe : la règle KaTeX-noir d'A.10.29 passe de `.cahier-body .katex` → `.cahier-card .katex` (couvre aussi une formule présente dans un titre de carte). *Note* : le rapport user « la formule LaTeX du cahier n'est pas en noir » s'expliquait par l'absence de rechargement depuis le commit A.10.29 : le HTML rendu fourni confirme que le `.katex` est bien dans `.cahier-body`, donc capté par la règle après un F5. Pas de bug, juste un cache de session.

Docs : astuces (lignes violet/vert de la doctrine), libellés de l'onglet 🎨 Couleurs (vert + violet), table README §Carte cahier.

---

## Phase A.10.29 : Rendus LaTeX du cahier en noir (rôle dédié au stylo noir) (2026-05-16)

User : *« Possible de mettre tous les rendus latex dans le cahier en noir juste histoire que le noir serve à quelque chose ? »*.

Constat juste : depuis A.10.20, le code fenced est rendu en **vert** (`.cahier-body pre`), pas en noir. Le stylo noir de la palette Bic 4-couleurs n'avait donc plus aucun rôle réel : `.cahier-body .katex` était en `color: inherit` (donc bleu prose par défaut, ou rouge/vert selon le span englobant).

Fix : `.cahier-body .katex` passe de `inherit` → `var(--cahier-c-noir)`. La règle cible `.katex` directement, ce qui **bat la couleur héritée** d'un éventuel `{rouge}`/`{vert}` englobant : toute formule `$…$` / `$$…$$` d'une carte est donc en noir, sans exception. Reste configurable via l'onglet 🎨 Couleurs (variable `--cahier-c-noir`).

Mises à jour de doc associées :
- **Onglet 🎨 Couleurs** : libellé du stylo noir « (neutre) » → « (formules LaTeX / maths) ».
- **Astuces** (`TIPS_CATALOG`, carte cahier) : ligne ⚫ Noir réécrite pour décrire le rôle LaTeX.
- **README §Carte cahier** : table de doctrine, ligne Noir = « Formules mathématiques (LaTeX) » ; ligne Vert complétée avec « code fenced (auto) » ; correction de la mention périmée « code reste noir neutre » (faux depuis A.10.20).

Pas de modification de prompt : le tuteur n'émet aucune balise couleur pour les maths (KaTeX rend les `$…$`), c'est un choix de rendu purement frontend.

---

## Phase A.10.28 : Titres de carte cahier émis hors balise + protection LaTeX (2026-05-16)

Audit de la session `2026-05-14_AN1_CCT_exfull_decouverte_photos_consultatif_1` (engine `gemini_api`, replay). Deux familles de bugs.

### Bug 1 : titre de carte cahier émis en prose, hors de la balise

Sur les **14 cartes cahier** de la séance, **5 sont en balise nue** `<<<CAHIER>>>` ; dans 4 d'entre elles le tuteur a écrit le titre **en prose juste avant** la balise. Trois formes observées :

```
a)  Titre : **9. Théorème des gendarmes (application)**          (balise nue)
    <<<CAHIER>>>

b)  Titre : **8. Limite en +∞ (forme indéterminée "∞/∞")**       (balise + attribut)
    <<<CAHIER titre="Méthode : Factoriser par le terme dominant.">>>

c)  **Racine carrée d'un nombre complexe (méthode)**             (ligne full-bold)
    Sous ce titre, écrivez ceci :
    <<<CAHIER>>>
```

Conséquence : ligne « Titre : … » parasite dans le dialogue, et carte sans bandeau (a/c), ou **avec un titre incohérent** (b : le tuteur a mis le vrai titre en prose et collé une sous-ligne du corps, « Méthode : … », dans l'attribut). C'est **le même tic Gemini** qu'A.10.15b (préfixe `Titre :` parasite). Doctrine reprise d'A.10.26 : on n'attend **pas** de discipline du tuteur, on récupère côté frontend.

**Fix : `_hoistCahierTitles(text)`** : pré-traitement dans `renderMarkdown`, avant l'extraction des blocs CAHIER.
- Ligne **« Titre : … »** (mot-clé explicite) → titre **autoritaire**, aspiré dans `titre=` que la balise soit nue **ou déjà pourvue**. Si un ancien `titre=` existait (cas b), il n'était pas le vrai titre : il est **rapatrié en 1ʳᵉ ligne du corps** pour ne rien perdre (fidèle au cahier réel de l'étudiant : « 8. Limite… » = titre, « Méthode : Factoriser… » = sous-ligne).
- Ligne **entièrement en gras** `**…**` (signal plus faible) → ne remplit **que les balises nues**, jamais d'écrasement d'un `titre=` existant.

Ligne d'amorce optionnelle (« Sous ce titre… », « Notez… », « Recopiez… ») tolérée et supprimée. Garde-fou : titre ignoré si vide ou > 120 chars. Validé sur msg 2/14/28/64/72 de la session auditée.

*Note* : la 1ʳᵉ itération du fix ne traitait que les balises nues (`indexOf("<<<CAHIER>>>")` + regex sur le littéral) → le cas b (msg 64) passait au travers même après F5. Corrigé : garde sur `"<<<CAHIER"` et regex `<<<CAHIER([^>]*)>>>`.

### Bug 2 : LaTeX corrompu par markdown-it (régression A.10.16)

Message `msg_92e85af1cde8` : `$$ \underbrace{\frac{e^{3x}}{e^x}}_{\text{Bloc 1}} \times \underbrace{…}_{\text{Bloc 2}} $$` rendu avec `}<em>{\text{Bloc 1}} … </em>{\text{Bloc 2}}`. Cause : markdown-it traite le `_…_` **à l'intérieur** de la formule comme de l'emphase, **avant** que KaTeX (event `done`) ne passe sur le DOM. L'ancien `renderMarkdown` regex (pré-A.10.16) ne touchait jamais l'intérieur des `$` : d'où la régression introduite par la migration markdown-it.

**Fix : `_protectMathSpans` / `_restoreMathSpans`** : les spans `$…$` et `$$…$$` sont remplacés par un placeholder ASCII neutre (`ZZMATHPLACEHOLDERnZZ`) **avant** `md.render`, puis le LaTeX **brut** est réinjecté après le rendu, et KaTeX le traite ensuite intact. Appliqué dans `renderMarkdown` **et** dans `_renderCahierBlock` (le corps des cartes a le même risque).

### Fix annexe : strip du markdown résiduel dans le titre de carte

`_renderCahierBlock` faisait `escapeHtml(titre)` brut → un titre contenant `*(partie réelle de w)*` affichait les `*` en clair. Conformément à la doctrine A.10.20 (gras / italique n'ont pas de sens sur une feuille), les marqueurs `*` et `` ` `` sont strippés. Le `$…$` est conservé : KaTeX walke tout le bubble, `.cahier-titre` inclus.

Fixes UI/regex purs, pas de test unitaire neuf (cf. convention A.10.15). Pas de modification de prompt.

---

## Phase A.10.27 : Surligneur 💾 Save passe en ORANGE + configurable dans 🎨 Couleurs (2026-05-15)

User : *« il peut aussi y avoir une couleur quand on save avec la possibilité de changer de couleur (de surlignement) ? genre mets une autre couleur que ceux existant genre orange par ex (de base il est jaune). Après dans couleur cahier ben tu donne la possibilité de changer de couleur »*.

Historique : Phase v15.7.26 a introduit le `<mark class="saved-note-mark">` (highlight persistant des sélections sauvegardées dans la bulle source). Couleur hardcodée en jaune (`rgba(255, 235, 80, 0.32)`). Conflit avec le surligneur jaune du cahier (formule vitale) → confusion visuelle.

Fix :
- CSS : refactor `mark.saved-note-mark` pour utiliser `var(--note-saved-hl)`, triplet RGB stocké dans `:root` (défaut `251, 146, 60` = **orange** clair).
- JS : ajout d'une 9ᵉ entrée dans `_CAHIER_COLOR_DEFAULTS` : `"note-saved-hl"` (kind: "hl", default: `#fb923c`, label: « Surligneur 💾 Notes save (n'importe où dans le dialogue) »). Le panneau 🎨 Couleurs cahier l'affiche maintenant comme 9ᵉ ligne, change-able via color picker, persisté dans localStorage.
- Astuce mise à jour : titre devient « 💾 Sauvegarder une phrase comme note (surligneur orange) », body multi-paragraphes explique que le 💾 marche n'importe où dans le dialogue (pas seulement dans une cahier-card) et que la couleur est configurable.

Pourquoi orange et pas autre : suffisamment distinct du jaune (formule vitale cahier) + rose (piège cahier) + vert + violet. Tons chauds visuellement reliés à « action » (sauvegarder = action utilisateur).

---

## Phase A.10.26 : Heuristique sémantique pour inline `<code>` (rouge=nom vs vert=valeur) (2026-05-15)

User : *« tu penses que tuteur à partir de mtn sera assez intelligent pour choisir les bonnes couleurs selon les situations et pas juste faire que si habituellement il mettait `<code>` ben il le mettra qd même mais un parser / regex simulera que c pas code mais rouge ? car je ne veux pas du scénario pas intelligible »*.

Réponse honnête : **non**, Gemini Pro suit la voie de moindre résistance. Si on attend que le tuteur wrap explicitement `{vert}"ATGC"{/vert}` vs `{rouge}charToBase{/rouge}`, il oublie systématiquement et tout finit en backticks neutres. Solution : **inférer la sémantique côté frontend**.

Heuristique JS dans `_renderCahierBlock` (ajout au pass post-markdown-it) :

```js
innerHtml = innerHtml.replace(
  /<code>([\s\S]*?)<\/code>/g,
  (_m, content) => {
    const trimmed = content.trim();
    const isValue =
      /^[-+]?\d+(?:\.\d+)?$/.test(trimmed) ||  // nombre pur
      /["']/.test(trimmed) ||                   // guillemets
      /[\[\]{}]/.test(trimmed) ||               // brackets
      /^\([^)]*\)$/.test(trimmed);              // tuple (...)
    const cls = isValue ? "cahier-code-inline-value" : "cahier-code-inline";
    return `<span class="${cls}">${content}</span>`;
  },
);
```

CSS : nouvelle classe `.cahier-code-inline-value` (vert) en parallèle de l'existante `.cahier-code-inline` (rouge). Tous deux sans monospace (= sur papier on écrit juste le mot, c'est la couleur qui distingue).

**Exemples auto-classifiés** :
- `charToBase`, `BinTree`, `Maybe`, `List Base`, `String` → rouge (nom/concept).
- `"ATGC"`, `[A, T, G, C]`, `(us, vs)`, `42`, `[1, 2, 3]` → vert (valeur/exemple).

**Edge cases mal classés** (acceptables, l'override existe) : `Just A` / `Nothing` (valeurs Maybe sans pattern reconnaissable) → rouge par défaut. Le tuteur peut wrap explicitement `{vert}Just A{/vert}` pour les cas où la sémantique compte.

Doctrine : on n'attend PAS de discipline du tuteur. Le frontend infère la sémantique automatiquement. Override explicite dispo pour les cas ambigus.

Doc : README §« Auto-coloriage intelligent » mis à jour avec exemples + rationale.

---

## Phase A.10.25 : CC3 propagation complète (4 → 11 cards) avec patterns A/B/C/D (2026-05-15)

User : *« j'ai stop+relance mais je vois pas le mode cahier dans cc3 prg2, y'a des endroits où ça en manque, tu peux faire un audit ? »*.

Audit révèle 8 cahier moments avec trigger phrase mais sans `<<<CAHIER>>>` sur CC3 (sur 12 légitimes). Patterns variés que mes regex initiaux ne couvraient pas. Refactor du script `_oneshot_convert_cahier_cc3.py` avec 4 patterns en cascade :

- **Pattern A** : trigger + ``` ``` ``` (code fenced direct). Existait, fix bug `Recopiez-le :\n```` (espace entre `le` et `:` ratait). Tolérance `\s*(?::|\.)` ajoutée.
- **Pattern B** : trigger + prose multi-ligne (1-5 lignes, sans code block). Pour les cahier moments « notez ceci » suivis d'explication courte.
- **Pattern C** (nouveau) : trigger + titre bold `**Question N : ...**` (sur **même ligne** que le trigger, pas nécessairement après newline) + optionnellement bridge phrase + bullets `*  ...`. Pattern le plus fréquent en CC3 (Question 2/3/4/5 avec pseudo-code en bullets).
- **Pattern D** (nouveau) : trigger + titre bold + 1-4 lignes de prose avec inline code `` `xxx` `` (pas de bullets, pas de fenced). Pour les définitions courtes type « Type d'Arbre Binaire (`BT a`) : `data BT a = Leaf a | Node (BT a) a (BT a)` ».

Résultat : **11 cards** sur CC3 (vs 4 avant). 1 message restant non converti (`msg_45ad11a6f693` = mention incidente « corriger ce `:::` en `::` sur votre cahier », pas un vrai cahier moment).

---

## Phase A.10.24 : Boutons contextuels (📚 Cours / 🎬 Vidéo / 🌐 Internet) étendus au mode Guidé (2026-05-15)

User : *« dans guidé y'a aussi les boutons supplémentaires ? »*.

Non auparavant. La tone-toolbar contextuelle (Phase Z.8.6 → Z.9.6) avait initialement gated les 4 boutons (🔍 Exo voisin / 📚 Passage CM / 🎬 Vidéo YouTube / 🌐 Recherche internet) sur `activeMode === "colle"` uniquement. Raisonnement du commentaire : *« en guidé, le tuteur a déjà accès FS (Read/Grep/Glob) et peut piocher naturellement »*.

Phase A.10.21 a étendu à découverte. Phase A.10.24 étend aussi à **guidé** :

```js
if (activeMode === "colle" || activeMode === "découverte" || activeMode === "guidé") {
```

**Raisonnement révisé** : l'argument FS du tuteur en guidé ne tient que pour 📚 Cours (qui scanne `COURS/` côté Python). Pour 🎬 Vidéo YouTube et 🌐 Recherche internet, le tuteur **n'a pas de tools web** quel que soit le mode : ces boutons étaient donc injustement bloqués en guidé. Et même pour 📚 Cours, le bouton reste utile pour bypass le tuteur (récupère exo voisin + passage CM dans des bulles isolées sans avoir à lui poser la question).

**Workspace** reste exclu (pas de contexte COURS).

Cohérence : la 4-tab tone-toolbar (🎛 Modifier / 📚 Cours / 🎬 Vidéo / 🌐 Internet) est désormais visible dans **les 3 modes pédagogiques** (colle, découverte, guidé). Plus de distinction arbitraire.

Doc : README §« Tone-toolbar sous chaque bulle Compagnon » mis à jour (titre passe de « (en mode colle) » à « (modes colle, découverte et guidé) »).

---

## Phase A.10.23 : Reposition onglet Couleurs + fusion Exo voisin + Passage CM → 📚 Cours (2026-05-15)

User : *« l'onglet couleur doit être placé à un endroit différent et pas tout à la fin. De plus exo voisin et passage cm je sais pas y'a pas moyen de rassembler la logique en un pour trouver à la fin les cm et les exo […] libellé en 1 mot »*.

**Reposition** 🎨 Couleurs entre 📌 Consignes et 💬 Historique (au lieu d'en bout de stack). Logique : outil de personnalisation occasionnel, mérite d'être visible sans être marginalisé.

**Fusion** 🔍 Exo voisin + 📚 Passage CM → un seul bouton **📚 Cours** (1 mot). `Promise.allSettled([findSimilarExo, findCmPassage])` lance les 2 recherches en parallèle, chacune produit sa bulle dans le dialogue. Toolbar contextuelle passe de 5 → 4 boutons (🎛 Modifier / 📚 Cours / 🎬 Vidéo / 🌐 Internet).

**CC3 re-propagation** : pattern B ajouté (trigger + prose multiligne sans code block, max 5 lignes). +1 card, total **4 cards** CC3.

---

## Phase A.10.22 : Unification gestion couleurs en UN seul onglet (2026-05-15)

User : *« assemble la logique en un car je trouve ça moche »*.

Avant : selection-toolbar 13 boutons (4 Save/Quote/Explain/Copy + 9 cahier-color-btn) + onglet 🎨 Couleurs séparé + 2 astuces séparées.

Après : selection-toolbar 5 boutons (4 originaux + 1 « 🎨 Colorier » qui ouvre l'onglet Couleurs avec sélection active) + onglet 🎨 Couleurs unifié (input hex = remap global, swatch cliquable = applique-à-sélection). Astuces fusionnées en 1 entrée explicative.

Mécanique : `_pendingColorSelection` global stocke la sélection au moment du clic « 🎨 Colorier », expire après 60s ou si bulle détruite. `renderColorsPanel()` détecte la sélection pendante → bannière `🎯 Sélection active : « xxx »` + swatches deviennent des `<button>` cliquables avec hover scale 1.15. Bouton ⌫ dans la bannière pour clear le coloriage de la sélection.

---

## Phase A.10.21 : Onglet 🎨 Couleurs cahier (remap rétroactif via CSS vars) + fix boutons disparus (2026-05-15)

User : *« pourquoi pas un onglet supplémentaire où on peut changer les couleurs par concept ? et le changement est évidemment rétroactif et tous les anciens trucs seront changé aussi »*.

Excellente idée, plus propre que d'éditer chaque message un par un. Implémentation via CSS variables.

### Onglet 🎨 Couleurs

Nouvel onglet sidebar (entre 🎓 Astuces et la fin) avec :
- 4 lignes stylos (bleu / rouge / vert / noir) : input `type="color"`, preview swatch coloré, label sémantique
- 4 lignes surligneurs (jaune / vert / rose / violet) : idem mais preview avec fond translucide
- Bouton ↺ Reset aux valeurs par défaut (avec confirm)

Mécanique : refactor CSS pour utiliser des **CSS variables** dans `:root` :
```css
:root {
  --cahier-c-rouge: #b91c1c;
  --cahier-hl-jaune: 253, 224, 71;   /* triplet RGB pour rgba() */
  ...
}
.cahier-c-rouge { color: var(--cahier-c-rouge); }
.cahier-hl-jaune { background: rgba(var(--cahier-hl-jaune), 0.55); }
```

Au changement (input `color` event) : `document.documentElement.style.setProperty('--cahier-c-rouge', '#xxx')` → **toutes les cards existantes** (passées et futures) prennent la nouvelle couleur instantanément, sans toucher au texte des messages. Pour les surligneurs, conversion hex → triplet RGB pour rgba(alpha) cohérent.

Persistance : `localStorage['compagnon_cahier_colors_v1']`, format `{name: hex, ...}`. Chargé au boot via `_loadCahierColorsFromStorage()` (avant render UI). Per-device (pas de sync cross-machine, choix UX assumé).

### Renommage helper anti-collision

`_applyCahierColor(name, hex)` qui devait écrire les CSS vars **collisionnait** avec `_applyCahierColor(info, tag)` du color picker sélection-toolbar (Phase A.10.20). JS prend la dernière définition → cassait le picker au scalpel. Renommé en `_setCahierCSSVar(name, hex)`.

### Fix régression : boutons 🔍 Exo voisin / 📚 Passage CM / 🎬 Vidéo / 🌐 Internet disparus

User : *« sais-tu pourquoi les boutons recherche sur internet et youtube ont disparu ? y'a que le bouton modifier avant il y était et d'un jour comme ça ça a disparu j'ai pas fait gaffe depuis »*.

La tone-toolbar contextuelle (Phase Z.8.6 → Z.9.6) ajoute 4 boutons sous chaque bulle Compagnon : 🔍 exo voisin, 📚 passage CM, 🎬 vidéo YouTube, 🌐 recherche internet. Tous gated par `if (activeMode === "colle")` car le commentaire indiquait *« en guidé, le tuteur a déjà accès FS et peut piocher »*. Mais en **découverte**, ces boutons étaient aussi utiles (vidéo YouTube qui explique un concept = très pédagogique) et le user ne les voyait plus depuis qu'il était passé en mode découverte (TP9 / TP8 / AN1 CCT / CC3).

Fix : condition étendue à `colle || découverte`.

### Astuces refformulées pour clarifier les 2 usages

- *« 🎨 Changer la couleur d'UN mot précis (édition au scalpel) »* : color picker sur sélection toolbar, persisté côté serveur (texte du message édité).
- *« 🎨 Remapper une COULEUR globalement (rétroactif, toutes cards) »* : onglet Couleurs, persisté côté navigateur (CSS vars), aucun message touché.

Deux features complémentaires : édition fine vs personnalisation thématique globale.

---

## Phase A.10.20 : Doctrine cahier raffinée + color picker + CC3 propagation (2026-05-15)

Itération immédiate post-A.10.19 après tests visuels user. Quatre frictions résolues :

### Faux positifs OCR (23 cards décapsulées)

User : *« je vois que certaines cards sont en réalité l'OCR de mes photos ».*

Le script auto a converti TOUS les blockquotes `> ...` du tuteur en cartes CAHIER. Or Gemini formate aussi `📸 Ce que je lis dans votre photo :\n> texte\n> texte` : la section OCR de la photo de l'étudiant. Ces blocs ne sont PAS des cahier moments (= consignes d'écriture), ce sont des lectures du tuteur.

Fix : `_scripts/_oneshot_undo_ocr_cahier.py` détecte les `<<<CAHIER>>>` précédés de `📸` / `Ce que je lis dans` dans les 250 chars qui précèdent, et les decapsule en blockquote standard. Résultat :
- TP8 : 7 reverts (12 → 5 vraies cards)
- TP9 : 6 reverts (13 → 7)
- AN1 CCT : 10 reverts (22 → 12)
- **Total : 23 cards OCR-faux-positif décapsulées**

### Doctrine raffinée (« gras et code n'ont pas de sens sur papier »)

User audit : *« le gras / italique / code inline c'est quoi sur cahier ? »*

Sur du papier, `**gras**`, `*italique*`, `` `code inline` `` ne se transcrivent pas. Seules les couleurs + surligneurs + lignes de texte ont du sens. Doctrine raffinée :

- **`<strong>` et `<em>`** : stripped dans `_renderCahierBlock` (juste le texte plat). Le tuteur ne doit pas s'embêter à mettre du gras, il met de la couleur si nécessaire.
- **`<code>` inline** : rendu en rouge stylo (`.cahier-code-inline`) sans monospace. *« Les `` `backticks` `` étaient utilisés pour les noms de variables/types/fonctions = concepts à reconnaître. Sur cahier, tu écris juste le mot, c'est la couleur qui distingue. »* Auto-coloriage = pas besoin de wrapper explicitement.
- **`<pre>` bloc fenced** : rendu en vert stylo (`.cahier-body pre` → `#15803d`) avec fond vert pâle. *« Code = exemple écrit, cohérent avec doctrine "vert = exemples". »* Commentaires détectés par regex `^\s*(--|#|//)` → wrappés en `.cahier-code-comment` rouge italique. *« Code en vert et commentaires en rouge, c'est pas bizarre, c'est même très naturel sur papier. »*
- **Limites couleurs = guides, pas absolues** : *« Faut pas non plus que ce soit que bleu mais un truc harmonieux. Y'aura des trucs où il faudra éditer le message du tuteur. »* Doctrine v1.5 du prompt Découverte assouplit les quotas : rouge 1-3 indicatif (peut monter), vert 0-3 indicatif. Règle absolue maintenue : pas de carte tout-bleue ni tout-multicolore.

### Color picker UI (sélection texte → couleur)

User : *« code le truc pour changer la couleur ».*

Extension de la `#selection-toolbar` existante. Quand la sélection est DANS une `.cahier-card` (détection via `_isSelectionInCahierCard(range)`), un groupe `.cahier-toolbar-group` apparaît avec 9 boutons :

- 🔵 stylo bleu, 🔴 rouge, 🟢 vert, ⚫ noir
- 🟡 surligneur jaune, 🟩 vert, 🩷 rose, 🟣 violet
- ⌫ clear (retire tout color/hl tag autour de la sélection)

Logique `_applyCahierColor` :
1. Récupère le `.turn` parent, son `data-raw-text` (source markdown).
2. Calcule l'`index` du message dans `transcript[]` (mêmes critères que `editTurn`).
3. Trouve la 1ère occurrence du texte sélectionné dans le raw (avec fallback regex tolérant aux espaces multiples).
4. Wrap dans `{couleur}…{/couleur}` ou `{hl-X}…{/hl-X}`.
5. PATCH `/api/messages/<index>` silencieux (`silent: true` skippe OCR refresh).
6. Update `data-raw-text` local + re-render via `renderMarkdown` + re-applique `linkifyPageRefs` + KaTeX.

Action « clear » : regex `\{(?:bleu|rouge|...)\}(\s*sélection\s*)\{/...\}` → retire les tags. Limite : ne peut clear qu'un tag wrappant exactement la sélection (pas un span englobant).

### Tips réordonnés + cahier multi-paragraphes

User : *« la note carte cahier est illisible, change la disposition de toutes les notes y'en a c'est pas normal qu'elles soient mises tout en bas alors que c'est des trucs de base »*.

`renderTipsList` supporte maintenant `body` sous forme de string OU array de strings (multi-paragraphes). Nouvelle classe CSS `.tip-body-para` avec spacing inter-paragraphes.

Catalogue réordonné en 5 sections :
1. **Basics** (en tête) : 🎙 mic, ⌨ Espace push-to-talk, 📷 photo, ✏ édit message, ✨ rewrite, 🛑 annuler
2. **Carte cahier** : doctrine couleurs (en multi-para) + 🎨 color picker
3. **Session management** : 💬 historique, 📊 quota, 📄 récap
4. **Notes/Consignes/Photos/Docs** : 💾 notes, 📌 stickies, 🤖 REMEMBER, 📋 import, 📸 photos, 🏷 OCR rename, 📚 docs
5. **Mode switching** : 🔀 format, 📘 ancrage, 🎲 sans énoncé, 💡 sujet libre
6. **Troubleshooting** (en bas) : ⚠ 503 UNAVAILABLE

### CC3 propagation partielle

User : *« propages cela à CC3 aussi ».*

CC3 a un pattern différent (pas de blockquote, mais trigger phrase + bloc fenced) : `_scripts/_oneshot_convert_cahier_cc3.py` détecte `(Recopiez-le|Sur votre cahier|Notez|...)\s*:\n```...```` et wrap dans `<<<CAHIER>>>...<<<END>>>` avec extraction de titre via contexte amont (« **Question N** » ou « **N. ...** »).

**3 cards converties** sur CC3. Les autres moments (textes prose sans code block) restent en blockquote (édition manuelle via le color picker si besoin).

---

## Phase A.10.19 : Carte cahier : artefact « feuille de cours » coloriée (2026-05-15)

User : *« en mode découverte, le LLM nous dit de noter des choses sur cahier. Mais pourquoi pas en plus si le LLM reproduisait genre une sorte de modale ou artefact ou que sais-je du cahier ou feuille blanc avec ses couleurs de texte et surligneurs, evidemment quand il s'agit d'expliquer des choses c'est comme d'habitude mais quand il nous dit de rédiger sur cahier eh ben là le truc apparait et du coup on sait exactement quel couleur utiliser, quoi surligner, etc »*.

Vraie différenciation pédagogique vs ChatGPT/Claude/Gemini : aucun LLM grand public ne fait ça. Boucle close : *tuteur montre le modèle → étudiant recopie → photographie → OCR valide*.

### Itérations doctrine couleurs

**v1 (rejetée par user)** : 4 stylos sémantiques + 4 surligneurs sémantiques, mécanique. Le user a fait remarquer que les surligneurs jaune/rose/violet n'étaient pas universels dans une trousse standard.

**v2 (rejetée par moi sur retour audit photos)** : refined : que jaune surligneur + Bic 4 stylos. Mais audit du cahier réel (4 photos OCRisées via Read tool) a montré que **le user écrit TOUT en bleu stylo** et utilise les 4 surligneurs (vert titre / violet sous-titre / jaune labels / rose mots-clés) : sa convention réelle n'avait rien à voir avec ma théorie.

**v3 (finale, validée)** : fidèle à l'usage réel + force la diversité stylo (anti tout-bleu) + surligneurs ponctuels (anti sapin-de-Noël) :

| Élément | Couleur | Limite |
|---|---|---|
| Texte par défaut | 🔵 Bleu stylo | ~60% du texte |
| Concept-clé / résultat à retenir | 🔴 Rouge stylo | 1-3/carte |
| Exemple concret / valeur | 🟢 Vert stylo | 0-3/carte |
| Code à recopier (bloc fenced) | ⚫ Noir | Auto, jamais surligné |
| Sous-titre (titre de carte) | 🟣 Violet surligneur | Auto |
| Titre de fiche (root) | 🟢 Vert surligneur | 0-1 |
| Formule vitale | 🟡 Jaune surligneur | 0-1 |
| Piège / erreur classique | 🩷 Rose surligneur | 0-1 |

**Anti-sapin-de-Noël** : max 2 surligneurs ponctuels (jaune+rose) + max 3 mots couleur stylo par carte. Pas de couleur DANS les blocs code.

### Syntaxe

```
<<<CAHIER titre="N. Nom de section">>>
Markdown standard + {rouge}…{/rouge} + {vert}…{/vert} + {hl-jaune}…{/hl-jaune} + {hl-rose}…{/hl-rose}.
$KaTeX inline$ et $$display$$ supportés.
<<<END>>>
```

### Implémentation

- **Parser JS** (`_scripts/web/static/app.js`) : `renderMarkdown` extrait les blocs CAHIER avant markdown-it via placeholders ` CAHIER_N `, render le markdown global, puis réintègre les cards via `_renderCahierBlock(block)`. Le helper md.render le contenu interne, puis regex-substitue les balises couleur/surligneur en `<span class="cahier-c-X">` / `<mark class="cahier-hl-X">`. Raccourci `==texte==` → `<mark.cahier-hl-jaune>` (extension non-CommonMark, raccourci fréquent).
- **CSS** (`_scripts/web/static/style.css`) : `.cahier-card` avec dégradé lignes Seyès, marge stylo rouge à gauche, fond crème `#fefef2`, palette stylos Bic + surligneurs semi-transparents. Sous-titre `cahier-titre` avec hl violet par défaut.
- **Prompt Découverte v1.4** (`_prompts/PROMPT_SYSTEME_DECOUVERTE.md` §1.6quater) : documentation complète syntaxe + doctrine + 3 exemples concrets + règles anti-sapin-de-Noël. Le tuteur Gemini API/Claude doit émettre la balise au lieu d'un blockquote.
- **Migration rétroactive** : `_scripts/_oneshot_convert_cahier.py` scanne les 4 sessions auditées, convertit les blockquotes du tuteur (déclencheurs « notez/prenez votre cahier/sur votre cahier/titre :/écrivez/écrivons/notons ») en cartes CAHIER. Heuristiques sobres : rouge sur 1er backtick après « Définition : »/« Théorème : »/« Méthode : », vert sur backticks après « Exemple : » (max 3), code fenced préservé en noir, backup `text_history[]`. Résultat : **48 cartes** appliquées (TP8 : 12, TP9 PRG2 : 12, AN1 CCT : 24, CC3 skip car aucun blockquote propre).
- **Astuce** ajoutée en tête de TIPS_CATALOG (« 📒 Carte cahier : la doctrine couleurs »).
- **README** : nouvelle section « 📒 Carte cahier » au-dessus de « 📑 Sommaire dynamique » avec doctrine, syntaxe, anti-sapin-de-Noël, pointeur portfolio.

### Limites connues

- Les cartes générées par script auto ont du coloriage minimal (heuristiques conservatives) : quelques cards restent monochromes bleues quand le pattern de label/backtick ne matche pas. Acceptable car le bleu par défaut est lisible. Si besoin d'enrichir, édition manuelle via ✏ Modifier.
- CC3 PRG2 n'a aucun blockquote propre dans le tuteur (Gemini a écrit en prose conversationnelle pour cette session) → aucune carte générée rétroactivement. Les futures sessions CC3 auront des cartes via le prompt v1.4.
- La doctrine n'est pas (encore) ajoutée au prompt Colle ni Guidé : applicable seulement en Découverte pour l'instant. Extension possible si l'usage le mérite.

---

## Phase A.10.18 : Détection upstream-unavailable + astuces 503 / édition (2026-05-15)

User : *« dans compagnon c'est normal malgré le rechargement du contexte et connexion fonctionnel j'ai cette erreur ? : [Erreur stream] Gemini reseau : 503 UNAVAILABLE. {'error': {'code': 503, 'message': 'This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.'}} » → *« tu peux mettre ce genre d'erreur dans les astuces et aussi quand ce genre d'erreur intervient que le select moteur clignote en orange pour indiquer à l'user de changer de moteur. Aussi mets aussi dans astuce qu'il faut mieux modifier le message pour recharger le contexte plutot que d'écrire encore un message à la suite etc »*.

### Détection 503 / overloaded / UNAVAILABLE

Le handler `es.addEventListener("error", ...)` ne catchait jusqu'ici que les erreurs **quota** (402/413/insufficient/TPM/context.length/rate.limit) via `looksLikeQuota`. Nouveau test parallèle `looksLikeUpstreamUnavailable` qui matche `\b50[234]\b|UNAVAILABLE|high.demand|overload|temporarily|service.unavailable` (case-insensitive). Quand vrai :

- Message système FR explicite : « ⚠ {engine} en surcharge temporaire, réponse refusée par le serveur upstream » + 2 solutions numérotées (retry 30s-2min OU bascule moteur) + détail technique.
- `flashEngineSwitcher()` appelé → le `#engine-switcher` clignote orange 1.8s + auto-focus pour qu'un ↑/↓ suffise à changer.

Le handler quota appelle aussi `flashEngineSwitcher()` désormais (au lieu de juste l'ajouter dans le `window.confirm` pour le rewrite). Cohérence : toute erreur où basculer aide → on flash le sélecteur.

### 2 nouvelles astuces (TIPS_CATALOG)

- *« ⚠ 503 UNAVAILABLE ou high demand, c'est du côté serveur »* : explique que c'est upstream, donne les 2 solutions, action `▶ Voir le sélecteur de moteur` qui spotlight `#engine-switcher`.
- *« ✏ Éditer un message > en écrire un nouveau pour recharger le contexte »* : encourage à utiliser ✏ (et le sous-bouton « 🔄 Recharger contexte » qui modifie + supprime tout ce qui suit + regénère) plutôt que de renvoyer un nouveau message à la suite. Bénéfices listés : économies tokens, état propre du tuteur, historique lisible. Pas d'action `_spotlight` (ça s'applique au hover sur n'importe quelle bulle déjà visible).

Les 2 nouvelles entrées sont en TÊTE du catalogue (`renderTipsList` itère dans l'ordre, donc premières visibles).

---

## Phase A.10.17 : Boutons input ciblent l'édition + mic préserve toujours le snapshot (2026-05-15)

User : *« quand je veux modifier un message faut que les boutons améliorer le brouillon, joindre un fichier, prendre une photo, cliquer pour démarrer un vocal soit actif. D'ailleurs pour le vocal si y'a du texte déjà actif même quand il ne s'agit pas de modification bref, eh bien il faut que ça n'annule pas l'ancien texte mais ça continue par la suite »*.

### Helper `_getActiveTextarea()`

Nouvelle fonction qui retourne `_activeEditTextarea` si une bulle est en édition (et son textarea existe dans le DOM), sinon `userInput`. Les 4 boutons du footer (`#mic-btn`, `#rewrite-btn`, `#media-btn`, `#photo-btn`) opèrent désormais sur la cible active. Les 2 boutons fichier (📎, 📷) routaient déjà via `uploadAttachmentFile` qui checke `_activeEditTextarea` : ce comportement est généralisé. Helper `_autoResizeTextarea(ta)` pour gérer le resize de l'edit textarea (cap 400px) vs main (cap CSS via `autoResizeUserInput`).

### ✨ Rewrite ciblé sur l'édition

- `refreshRewriteBtnState` lit désormais `_getActiveTextarea().value` (avant : toujours `userInput.value`). Le bouton ✨ s'active maintenant quand on tape ≥8 chars dans une bulle en édition.
- `performRewrite` lit/écrit la cible active, mémorise le textarea-source dans `_lastRewriteTargetTextarea` pour que `undoLastRewrite` restaure sur le bon textarea (même si l'édition s'est terminée entre temps, avec fallback userInput).
- L'edit textarea a un listener `input` qui appelle `refreshRewriteBtnState`, et un appel initial à l'ouverture. La cleanup de l'édition invalide aussi `_lastRewriteTargetTextarea` + le banner d'undo s'il pointait sur le textarea fermé (sinon clic Undo restaurerait sur userInput, étrange).

### 🎤 Mic ciblé sur l'édition + snapshot toujours préservé

Nouveau global `_recordingTargetTextarea` verrouillé au démarrage de l'enregistrement (édition active → edit textarea, sinon userInput). WebSpeech preview, Whisper write-back et abort utilisent cette cible. Si l'édition se ferme pendant qu'on parle, fallback userInput (best-effort).

**Refonte de la logique snapshot** : l'ancien check `userTouchedInput = currentInput.trim() !== snapshot.trim()` (Phase v15.7.24, censé détecter quand l'user efface manuellement l'input pour reformuler) était **cassé en présence de WebSpeech** : WebSpeech remplit `currentInput` en continu avec sa preview, ce qui faisait toujours diverger de `snapshot` → la logique perdait systématiquement le snapshot, donc le texte d'avant le clic 🎤 disparaissait.

Comportement définitif : **toujours** préserver le snapshot pre-mic et appender la transcription Whisper derrière. Si l'utilisateur veut repartir de zéro, il efface manuellement post-transcription. Friction perdue (cas marginal) vs friction gagnée (cas commun « j'avais déjà tapé du texte, le mic l'a effacé »).

### Boutons 📎 / 📷 inchangés (déjà OK)

`uploadAttachmentFile` consulte déjà `_activeEditTextarea` (Phase A.8.5) et insère le markdown dans le textarea d'édition via `_insertImageMarkdownInEdit`. La généralisation A.10.17 vise les 2 boutons restants (mic + rewrite) pour cohérence d'ensemble.

---

## Phase A.10.16 : Migration markdown-it (2026-05-15)

User : *« une question pour ce genre de markdown y'a pas déjà une librairie un truc du genre de tout fait plutot que de hardcodé les choses à faire fois ? »*.

Légitime. `renderMarkdown` avait grandi à 240+ lignes de regex (Phase A → A.10.15d) couvrant gras, italique, listes à puce/numérotées avec imbrication, blockquotes, tables GFM, code blocks, headings, HR, paragraphes, `<br>`, images custom-routées. Chaque nouveau pattern émergent côté Gemini/Claude révélait des bugs composés :
- Listes à puce dans blockquotes (A.10.15d : `> - item` rendu littéralement)
- Listes numérotées avec blank lines internes (A.8.4)
- Sous-listes 4-spaces (Z.8.1)
- Bullets en `*` vs `-` (Z.8.1)
- Tables GFM (A.7.2 v8)
- HR `---` vs séparateur de table `|---|` (Z.8.1)
- Et c'était parti pour continuer.

Migration vers **markdown-it v14** via CDN (`https://cdn.jsdelivr.net/npm/markdown-it@14/dist/markdown-it.min.js`, ~100 KB minified). CommonMark + GFM natifs, edge cases déjà testés par des milliers d'utilisateurs, streaming-tolérant (entrée partielle ne throw pas).

### Ce qui est gardé identique (hooks renderer)

- **Routing images custom** : `_uploads/...` → `/api/upload_file`, externe → src direct, relatif → `/api/cours_file`. Backslashes Windows normalisés en `/`.
- **Tooltip joli au hover** via `_prettifyPhotoFilename` (« Pseudo Code Leaf2 · 14/05 10:42 » pour les OCR-renamed A.10.13d).
- **Placeholder `onerror`** quand l'image 404 (au lieu de l'icône cassée silencieuse du navigateur).
- **Wrap `<span class="md-img-wrap" data-md=...>`** + bouton **🗑** pour retirer pile cette image du texte source du message.
- **Classe `md-table`** sur les tables GFM (CSS existant inchangé).

### Ce qui devient gratuit avec markdown-it

- Listes à puces dans blockquotes (fix A.10.15d devient redondant, donc supprimé)
- Listes imbriquées multi-niveaux quelle que soit la profondeur
- Listes numérotées avec continuation, blank lines, sous-éléments
- Fenced code blocks ```python (classe `language-python` ajoutée par markdown-it)
- Tables GFM avec alignement de colonnes
- Tous les cas composés (blockquote → liste → bold → code, etc.)

### Ce qui reste séparé (à dessein)

- **`linkifyPageRefs(rootEl)`** : walk les text nodes du DOM après rendu pour transformer « page 3 du corrigé » en liens cliquables. Indépendant du markdown (logique de la Phase Z.8.4 préservée).
- **KaTeX auto-render** : `$...$`, `$$...$$` traités sur l'event SSE `done`. Pas markdown standard, gardé séparé.
- **Balises custom `<<<TTS>>>` `<<<WEAK_POINT>>>` etc.** : strippées en amont par `parser.py` (côté Python) avant d'arriver au front. Aucun changement.

### Lazy-init

`app.js` est chargé sans `defer` (à la fin du `<body>`) alors que `markdown-it.min.js` est `defer` (dans `<head>`). Conséquence : au parse de `app.js`, `window.markdownit` n'est **pas encore** disponible (il l'est juste avant `DOMContentLoaded`). Une init au top-level retournerait toujours `null` au boot.

Solution : helper `_getMarkdownIt()` qui résout au **premier appel** à `renderMarkdown`. Si la lib n'est pas encore là (très improbable en pratique, le 1ᵉʳ render attend une réponse tuteur qui prend ≥1s), fallback `<p>${escapeHtml(text)}</p>`. Une fois résolu, l'instance est cachée.

### Suppression

- `_renderBulletList()` (54 lignes) : la logique d'indentation 4-spaces et de pile de niveaux est native dans markdown-it. Supprimée.
- 240+ lignes de regex dans `renderMarkdown` : remplacées par ~100 lignes principalement du hook `renderer.rules.image`.

### Doc

`README.md` §6 mis à jour avec lien GitHub markdown-it, liste des hooks préservés, et explication du lazy-init.

### A.10.16.1 : Hotfix sauts de ligne + spacing blockquote

User immédiatement après la migration : *« il y a beaucoup de saut de ligner au lieu d'un j'ai l'impression y'en a deux et dans les quote quand y'a une liste eh bien la liste est en dehors de la ligne de texte »*.

Cause :
1. **Sauts doublés** : markdown-it pretty-print sa sortie avec un `\n` entre chaque block tag (`<blockquote>\n<p>...</p>\n<ul>...`). L'ancien `renderMarkdown` n'en émettait jamais. Le CSS `.turn { white-space: pre-wrap }` (nécessaire pour préserver le formatting des bulles user plain text) rendait ces `\n` comme des sauts de ligne visibles.
2. **Liste séparée du texte intro dans blockquote** : `<p>**Exemple :**</p>` suivi de `<ul>` avait 0.4em margin chacun + margin collapse = ~6-7px de gap visuel.

Fix :
1. Post-process dans `renderMarkdown` : `.replace(/(<br\s*\/?>|>)\s*\n+\s*/g, "$1")` collapse les `\n` cosmétiques entre tags et après `<br>`. Le contenu textuel n'est pas touché (les `\n` dans du texte sont entre lettres, pas après `>`/`<br>`). Les `<pre>` ont leur propre `white-space: pre` (default browser), donc le code n'est pas affecté.
2. CSS spacing serré pour blockquote interne (`style.css`) :
   - `blockquote > p { margin: 0.25em 0 }` (vs 0.4em par défaut)
   - `blockquote > ul, blockquote > ol { margin: 0.15em 0 0.25em }`
   - `blockquote > p + ul, blockquote > p + ol { margin-top: 0 }` : la liste colle pile à la fin de l'intro
   - Première/dernière `<p>` du blockquote : margins nulles (pas de gap aux bords du cadre)
3. Suppression de la règle stale `blockquote > br:first-child { display: none }` (héritage de l'ancien renderMarkdown qui mettait parfois un `<br>` parasite au début).

---

## Phase A.10.15 : Hotfixes modal de conflit + sommaire dynamique Gemini (2026-05-15)

Deux frictions découvertes en session live de révision (TP9 PRG2, mode découverte, engine Gemini API). Pas de tests unitaires neufs (cas heuristiques côté UI/regex), validation en conditions réelles.

### A.10.15a : Modal de conflit qui mentait sur le contexte

User : *« je veux changer de session directement depuis l'entête et j'ai voulu passer du TP8 PRG2 à TP9 PRG2. Cependant y'a le popup session existante détectée qui apparait et c'est incohérent ce qui se passe. […] D'autant que si je voulais par exemple changer le mode strict en consultatif, en étant toujours au tp8, un popup ne devrait pas non plus apparaitre car c'est deux types de session différente »*.

Bug : dans `startForm` submit handler, quand `activeSession` était set, le code affichait **systématiquement** le modal de conflit avec la session active comme « existante », sans vérifier si son contexte matchait celui du `body` à lancer. Résultat absurde : message « Une session pour PRG2 TP9 exfull existe déjà » avec meta `2026-05-14_PRG2_TP8_exfull_decouverte_photos_strict_1` (TP8, pas TP9).

Fix dans `_scripts/web/static/app.js` :
- Comparaison `sameContext` complète (matière/type/num/exo/année **+ mode/colle_format/corrige_anchor** : Phase A.8.6 ces 3 axes font partie du suffixe session_id donc déterminent une session distincte).
- Si match exact → modal de conflit affiché (Reprendre / Conserver+nouvelle / Écraser / Annuler) avec la session active comme « existante ».
- Sinon → fall-through vers `findExistingSession(body)` qui scanne le disque pour le **vrai** target. Le backend `/api/start_session` finalise automatiquement la session active (`_state.session_state.finalize(interrupted=True)`) avant d'en démarrer une nouvelle, donc pas de perte côté serveur.
- Helper `_isCurrentSessionSameContext` (jusque-là inutilisé) aligné sur la même logique pour cohérence future.

### A.10.15b : Sommaire dynamique vide avec Gemini API

User : *« → 2026-05-15_PRG2_TP9_exfull_decouverte_photos_strict_1 (engine: gemini_api) pourquoi les titres n'apparaissent pas dans le sommaire ? regarde les logs d'hier pour comprendre ce dont je parle »*.

Comparaison TP8 hier (engine Claude, 10 entries) vs TP9 aujourd'hui (engine Gemini API, 0 entry) :
- Hier : `**1. Les deux types d'arbres du TP8**` : matché par `_OUTLINE_RE_NUM_TITLE`.
- Aujourd'hui : `**Titre : 1. Représentation de l'ADN : \`List Base\`**` (Gemini préfixe systématiquement par `Titre :` dans les blockquotes-cahier). Le regex `\*\*(\d+)\.\s+...\*\*` ratait à cause du préfixe.

Fix multi-couches dans `_scripts/web/app.py` :

1. **Regex étendu** : `\*\*(?:(?:Titre|Title|Notion|Concept|Th[èe]me)\s*[:\-–—]?\s*)?(\d+)\.\s+([^*\n]{5,120})\*\*` avec `re.IGNORECASE`. Le préfixe optionnel n'est pas capturé → le titre extrait reste propre (`1. Représentation de l'ADN…`).

2. **Version-gate du backfill** : nouvelle constante `_OUTLINE_EXTRACTOR_VERSION = 2`. Le gate passe de :
   ```python
   if data.get("dynamic_outline_backfilled"): return
   ```
   à :
   ```python
   stored = int(data.get("dynamic_outline_extractor_version") or 0)
   if data.get("dynamic_outline_backfilled") and stored >= _OUTLINE_EXTRACTOR_VERSION: return
   ```
   Bump de version = re-balayage garanti au prochain GET, sans intervention manuelle. **Auto-déployant pour les futures évolutions des regex.**

3. **Tracking des signatures supprimées** : nouveau champ `dynamic_outline_deleted_signatures` (liste). Le DELETE endpoint y ajoute la signature de l'entry retirée. Le backfill skip les signatures dans cette liste → garantit que les entries manuellement supprimées par l'user **ne réapparaîssent jamais**, même après bump de version. Préserve l'intention initiale de l'idempotence A.10.13c (« si l'user supprime une entry elle ne réapparaît pas magiquement ») mais sans bloquer les re-extractions légitimes.

4. **Tri chronologique** par position du `source_message_id` dans `current_branch_path`. Bug observé : après le 1ʳᵉ Stop+Lancer, les entries live `[4, 5]` étaient déjà en disque, et le backfill rétroactif insérait `[1, 2, 3]` à la fin → ordre `[4, 5, 1, 2, 3]`. Sort stable appliqué dans `_maybe_backfill_outline` (sortie disque correcte pour les futures sessions) **et** dans `GET /api/dynamic_outline` (défensif, normalise à la lecture quel que soit l'état du disque).

### A.10.15c : Header form pas sync à la session reprise

User : *« quand je change de session via l'historique par exemple, eh bien l'entête démarrer doit aussi changer pour correspondre à la session que je suis en train de faire, c'est pas normal que je vois les champs de prg2 alors que je suis passé en AN1 c'est troublant malgré le titre ci dessous »*.

Bug : `resumeSession` (JS) restaurait les chips colle_format/corrige_anchor + le transcript, mais **pas** les selects matière/type/num/exo/année du form de démarrage. Même friction sur `restoreActiveSessionIfAny` au F5/restart. Conséquence : après un Reprendre dans le panneau 💬 Historique, l'entête continuait d'afficher la matière précédente, source de confusion en cas de switch rapide entre exos de matières différentes.

Fix :
1. **Backend `/api/resume_session`** expose désormais `matiere`/`type`/`num`/`exo`/`annee` (+ `sujet_libre`/`workspace_root` pour les cas spéciaux) dans la réponse. `/api/current_session` les exposait déjà, donc pas de migration côté restore.
2. **Helper JS `syncFormToSession(data)`** : applique le contexte au form via le pattern cascade (mêmes appels `cascadeFromMatiere(autoSelect)` que le boot init). Cas spéciaux :
   - `matiere=LIBRE` → coche la checkbox 💡 Sujet libre + remplit le textarea.
   - `matiere=WORKSPACE` → bypass (la GUI Tk gère le folder picker).
   - Décoche Sujet libre si on revient d'une session libre vers une session COURS.
3. **Call sites** : `resumeSession` (panneau Historique + modal de conflit) et `restoreActiveSessionIfAny` (F5 / restart). Best-effort `try/catch` pour ne jamais bloquer la reprise si une option n'existe plus sur disque.

### A.10.15d : Listes à puce dans les blockquotes

User : *« les listes à puce ne sont pas pris en compte dans les quotes dans le chat, il apparaissent avec \* faut que tu corriges ça »*.

Bug `renderMarkdown` : le pass global des listes à puce (regex `(?:^|\n)([ \t]*[-*][ \t]+...)`) exige le tiret en début de ligne. À l'intérieur d'un blockquote (`> - item`), le `-` est précédé de `&gt; ` (après `escapeHtml`) : le pass global skip la ligne, et le pass blockquote (plus bas) joignait naïvement les lignes avec `<br>` sans rouvrir la grammaire markdown interne. Conséquence : `- Chaîne de caractères : "ATGC"` apparaissait littéralement avec le tiret en clair, sans `<ul><li>`.

Pattern récurrent depuis Gemini API (cartes-cahier blockquote-wrappées) :
```
> **Exemple :**
> - Chaîne de caractères : `"ATGC"`
> - Liste de bases : `[A, T, G, C]`
```

Fix : la handler blockquote strippe désormais `&gt;\s?` de chaque ligne, ré-applique les regex de bullets ET de listes numérotées sur le contenu interne, puis remplace les retours simples restants par `<br>` (en évitant d'en ajouter autour des balises `<ul>`/`<ol>` fraîchement injectées). Italique/gras/code inline restent OK car leurs passes globales tournent **avant** le pass blockquote et opèrent au niveau caractère, pas ligne.

Limitations connues (acceptées) : citations imbriquées (`>> ...`) non gérées (déjà le cas avant), titres `# H1` à l'intérieur d'un blockquote non rendus (low-priority, pas observé en pratique).

### Friction réelle : heartbeat race condition

Pendant le diagnostic, premier essai de fix : reset `dynamic_outline_backfilled=False` directement sur disque pour forcer la re-extraction. Mais le heartbeat thread (`session_state._heartbeat_loop`, intervalle 30s) écrit l'état in-memory **complet** sur disque atomiquement, et il a clobberisé ma modif avant que l'user ne redémarre. D'où l'intérêt de la version-gate : la décision est portée par le **code en mémoire** (constante Python), pas par un flag disque manipulable de l'extérieur.

### Numérotation

Phase A.10.14 réservée au 2026-05-14 pour le retour des tabs horizontaux + padding panes + scroll fix (cf. wrap-up Phase A.10.13). A.10.15 = série hotfix du 2026-05-15.

---

## Phase A.10.13 : Suppression invented PDF + export récap + rename photos OCR + sommaire dynamique (2026-05-14)

Méga-itération sur le mode Découverte et l'UX des panneaux sidebar. Décomposée en 7 sous-phases push-able indépendamment.

### A.10.13a : Suppression invented PDF
User : *« le mode qui créé des énoncés ça sert à rien car vaut mieux que compagnon créé en fonction de la personne »*. Retrait complet : balise `<<<SAVE_INVENTED_PDF>>>` (parser), endpoints `/api/generated/`, `_generated/` dir, module `invented_pdf.py`, checkbox `📄 Générer PDF`, prompt instructions associées. Tuteur invente ses questions au fil de la conversation.

### A.10.13b : Export récap PDF + MD on-demand
Bouton **📄 Récap** dans le footer sidebar (à côté de Terminer). Génère un ZIP avec PDF lisible (via reportlab) + MD léger (transcript role-balisé + WP + audit rétro + stickies). Module `_scripts/dialogue/session_export.py`. Endpoint `GET /api/export_recap`. Click → blob download. Disponible à tout moment de la séance (pas seulement à la fin).

### A.10.13c : Sommaire dynamique dans Docs
Panneau **📑 Sommaire de la séance** auto-construit en haut de l'onglet 📚 Docs. Extracteur regex post-stream tuteur qui détecte les patterns structuraux :
- Headings markdown `## H2`, `### H3`
- Patterns explicites `**Exercice N**`, `**Question N**`, `**Étape N**`, `**Chapitre N**`, `**Partie N**`
- Listes numérotées de questions (mode colle uniquement, sinon trop de bruit)

Dédup par signature normalisée (kind + title lowercased). Entries persistées dans `session_state.data["dynamic_outline"]` (champ additif). Endpoints `GET / PATCH / DELETE /api/dynamic_outline[/<id>]`. Front : list cliquable (scroll vers bulle source), édition inline au double-click sur le titre, toggle on/off via ✓/⏸, suppression via 🗑. Refresh après chaque réponse tuteur (SSE done) + au switch sur l'onglet Docs.

### A.10.13d : Renommage photos via OCR Gemini
Après l'OCR Gemini Flash 2.5 sur une photo en mode colle/découverte (format photos/mixte), le backend renomme le fichier :
```
YYYY-MM-DD_HHMM_<kind>_<slug>_vN.ext
```
Helpers `_extract_slug_from_ocr(ocr_md, kind)` (stopwords FR filtrés, max 40 chars) + `_rename_photo_from_ocr(att, ocr_block)` (skip si kind="?" ou completeness < 50%). `_rebuild_user_text_with_renamed_attachments` régénère les markdowns du user_text. Persisté dans `session_photos[]` + transcript.

### A.10.13e : Hover nom joli photo gallery
Au survol d'une vignette dans l'onglet 📸 Photos, tooltip natif affiche le nom formaté : `"Pseudo Code Leaf2 Function · 14/05 10:42"`. Helper JS `_prettifyPhotoFilename(filename)` reconnaît 3 patterns (OCR-renamed, legacy cropped, fallback générique).

### A.10.13f : Astuces enrichies
TIPS_CATALOG enrichi en tête avec 5 nouvelles entrées : 📄 Récap, 🏷 Photos OCR-renamed, 📌 Demander au tuteur de retenir, 🎲 Sans énoncé (prudence), 💡 Sujet libre (LLM-only).

### A.10.13g : Script rename rétroactif
`_scripts/rename_old_photos.py` standalone qui rattrape les photos pré-A.10.13d. Dry-run par défaut, `--apply` pour exécuter, `--limit N`, `--session-id X`. Backup auto. Appelle Gemini Flash 2.5 directement avec prompt court (3-5 mots-clés). Coût ~$0.0001/image. 33 photos détectées sur la machine user.

### Autres fixes A.10.14 (sidebar)
- A.10.14 : retour top tabs horizontaux icons-only (après rejet rail vertical gauche puis droite par l'user)
- A.10.14.6 : padding uniforme sur tous les panes (quota, corrige, mobile, history)
- A.10.14.5 : scroll restauré dans tab-content (overflow-y: auto + min-height: 0 simple)
- ignore_enonce : force False au boot (gui.py + app.js + clé supprimée de runtime_settings.json), warnings inline pour 🎲 et 💡

530 tests passed, aucune régression. 7 commits push (A.10.13a, b, c, d+e+f consolidé, g, A.10.14, A.10.14.6, A.10.14.5).

---

## Phase A.10.11 : Suppression de la feature « archive .md » (2026-05-14)

User : *« honnêtement archive .md sert à quoi ? car y'a déjà le JSON au pire ? »*.

Audit honnête : le live-archive `.md` à chaque tour (Phase A.8.1) ajoutait de l'I/O disque pour un cas d'usage qui n'existait pas en pratique. Le JSON de session est l'unique source de vérité, l'UI permet déjà de relire toutes les sessions via l'onglet 💬 Historique. Les usages potentiels (survit à suppression JSON, lisible hors-app, export portfolio, grep) sont soit inutilisés (l'user ne supprime pas ses sessions), soit générables à la demande quand on en aura besoin (un générateur `.md` from JSON sera écrit en ~30 min si le portfolio public en a besoin).

Retrait complet :
- `_scripts/archive_session_md.py` (deleted)
- `tests/test_archive_session_md.py` (deleted, 15 tests retirés)
- `config.ARCHIVES_DIR` (retiré, dossier `_archives/` ignoré par le code maintenant, peut subsister sur disque, gitignored)
- `_maybe_archive_md(st)` helper + 3 call sites dans `app.py` (start, send_message, post-stream, resume)
- `archive_to_md` field dans `session_state.data`, sortie de `/api/start_session` et `/api/resume_session`
- Checkbox `📁 Archiver .md` dans `index.html`
- BooleanVar + Checkbutton + propagation `--no-archive` dans `gui.py`
- `--no-archive` arg + `params["archive_to_md"]` dans `compagnon.py`
- `archive_to_md` clef de `DEFAULT_LAST_SELECTION` dans `runtime_settings.py`
- Pré-coche/patch URL `archive_to_md` dans `app.js`
- One-shots datés `cleanup_sessions_one_shot.py` + `migrate_session_ids.py` (déjà exécutés, références `ARCHIVES_DIR` cassées sinon)

Tests : 547 passed (562 → -15 du fichier supprimé). Aucune régression.

Docs : CLAUDE.md (arbo + pointeur §11), README.md (section « Archives .md » remplacée par marker de suppression).

---

## Phase A.10.4 : Rail vertical sidebar + onglet 🎓 Astuces (2026-05-14)

User : *« ça fait moche 7 onglets dans la sidebar, pour un 8ème onglet tu proposes quoi ? […] genre astuces avec pleins de trucs et quand on clique dessus ça peut faire des actions intelligente genre le même truc d'effet quand on clique sur photo dans navigateur et ça illumine accès distant en jaune »*.

### A.10.4 : Rail vertical (VSCode-style)

Évolution des onglets sidebar :
- **A.7.2 v11** : tabs horizontaux top
- **A.10.1** : icons-only + label sur active → écrasait les inactifs
- **A.10.3** : grid 4×2 avec labels → asymétrique et serré (3+1 sur ligne 2)
- **A.10.4** : **rail vertical à gauche** (44 px), pane à droite plein écran

Refactor HTML : `<div id="sidebar-main">` wrappe `<div id="sidebar-tabs">` (en colonne, icons-only) + `<div id="sidebar-tab-content">` (panes). Grid sidebar passe de 4 rows à 3 (guided / main / footer). Le label de chaque onglet est porté par le `<h2>` du pane actif → plus de risque de tronquage. Scale linéairement à 15-20 onglets sans souci. Tooltip natif via `title=` pour la découvrabilité au survol.

CSS clés :
- `#sidebar-main { display: grid; grid-template-columns: 44px 1fr }`
- `#sidebar-tabs { flex-direction: column; overflow-y: auto }` (scroll si trop d'onglets)
- `.sb-tab { padding: 10px 0; font-size: 18px; border-left: 2px solid transparent }`
- `.sb-tab.active { border-left-color: var(--accent); background: rgba(126,182,255,.08) }`

### A.10.5 : Onglet 🎓 Astuces avec coach marks

Nouveau **8ᵉ onglet** : `🎓 Astuces et raccourcis`. Liste curated de 15 astuces couvrant les fonctionnalités les plus utiles mais peu discoverable :
- Photo téléphone, épingler une consigne, balise `<<<REMEMBER>>>`, sauvegarder une note, galerie photos, ✨ rewrite, micro Whisper, slash-commands `/oral` `/photos` `/mixte`, slash `/strict` `/consultatif` `/aucun`, panneau Docs avec contexte lecture, reprise de session, import de consignes, surveillance quota, push-to-talk Espace, annulation stream.

Chaque astuce est une carte avec titre + description + bouton `▶ Voir où` (sauf les 2 dernières qui sont des raccourcis clavier sans cible visuelle). Le clic déclenche un **coach mark** via le helper `_spotlight(target, opts)` :

- **`target` = sélecteur CSS ou Element** : résolu en `document.querySelector` si string
- **Si la cible est un `.sb-tab`** → click() avant le pulse (bascule sur le bon onglet AVANT de scintiller)
- **Animation CSS** : `@keyframes spotlight-pulse` ou `tab-spotlight-pulse` → contour jaune + box-shadow scintillant 2 fois sur ~3 s
- **`scrollIntoView` smooth, block center** par défaut (désactivable via opts)

Helper bonus `_prefillTextarea(text)` : pour les astuces slash-commands (/oral, /strict, etc.) ou « retiens que… », le bouton pré-remplit le draft + focus + spotlight sur Envoyer. L'utilisateur voit *où* taper, pas juste *quoi* taper.

Catalogue dans `TIPS_CATALOG` (tableau global, facile à étendre). Rendu via `renderTipsList()` au DOMContentLoaded + à chaque switch sur l'onglet.

### Tests
562 passed (inchangé : features UI sans logique critique testable en unit).

### Bug fix complémentaire : backfill _uploads/ + repopulate sessions migrées

L'onglet Photos était vide pour les 2 sessions migrées A.10.3 :
- PRG2 TP8 avait `session_photos_backfilled: True` posé AVANT la migration (sur empty), le marker bloquait le re-scan.
- PSI Shannon avait `session_photos_backfilled: None`, mais le backfill A.10.1 ne traitait que les paths COURS-relatifs et skippait les `_uploads/`.

Fix : `_maybe_backfill_session_photos` étendu pour détecter le préfixe `_uploads/` et router vers `UPLOADS_DIR` au lieu de `COURS_ROOT` (storage="uploads"). Sessions déjà migrées : one-shot script de repopulation supprimé après run (11 + 22 = 33 photos peuplées dans les 2 JSON).

---

## Phase A.10.3 : Migration des anciennes photos vers _uploads/ + sidebar grid (2026-05-14)

User : *« pourquoi ne pas déplacer les anciennes photos aussi ? »* et *« la sidebar est tjr trop étroite ta solution n'est pas idéale trouve une nouvelle façon pour disposer les éléments »*.

### Sidebar : grid 4×2 (vraie solution)

La 1ʳᵉ tentative A.10.1 (icons-only par défaut + label sur active) écrasait les onglets inactifs dès que l'active était large. Friction visuelle confirmée par l'user. Solution A.10.3 :

- **`display: grid; grid-template-columns: repeat(4, 1fr)`** : 4 colonnes fixes, 2 lignes auto (7 onglets → 4 + 3).
- **Labels TOUJOURS visibles** (icon + label par tab), font compact (11 px), padding 6px 4px, gap 3px.
- `text-overflow: ellipsis` pour les tabs qui dépassent vraiment (rare en pratique).
- Layout déterministe, prévisible, scale propre quand on ajoutera un 8ᵉ ou 9ᵉ onglet.

### Migration physique des anciennes photos COURS → _uploads/

Phase A.10.2 avait gardé les anciennes photos en place (cohabitation via le champ `storage`). L'user a raison : code dual à maintenir + COURS/ pollué. A.10.3 = script one-shot `_scripts/migrate_photos_to_uploads.py`.

Pour chaque session JSON dans `_sessions/` :
1. **Scan** le transcript student pour les `![alt](rel_path)` qui pointent sous COURS/ (pas de préfixe `_uploads/`, pas d'URL).
2. **Vérifie** que le fichier existe sur disque sous COURS_ROOT.
3. **Déplace** vers `UPLOADS_DIR/{session_id}/photos/` (collision → suffixe `_migN`).
4. **Update** le markdown dans `messages[id].text` → préfixe `_uploads/` + nouveau rel_path.
5. **Re-dérive** `transcript[]` depuis `current_branch_path` + `messages` (cohérent au prochain replay F5).
6. **Update** `session_photos[]` si présent : nouveau `rel_path`, `storage = "uploads"`, marker `migrated_from`.
7. **Atomic write** du JSON.

Garde-fous :
- **Backup auto** des sessions JSON vers `_sessions/_backup_pre_a10_3/` avant toute modif (refuse de tourner si le backup existe déjà).
- **Dry-run par défaut** (le script affiche le plan complet sans rien toucher). `--apply` requis pour exécuter.
- **Idempotent** : un re-run ne refait rien (les markdowns sont déjà `_uploads/`).
- **Dedup** : si la même image apparaît dans plusieurs messages, un seul move physique.
- **Skip** silencieux des fichiers manquants (déplacés / supprimés entretemps) et des extensions non-image.
- Photos orphelines (présentes sous `COURS/.../photos/` mais référencées par aucune session) → **laissées en place**. C'est le bon comportement : ces fichiers peuvent appartenir au matériel COURS perso (pipeline Discord BotGSTAR `cours_pipeline.py`), pas à un upload Compagnon.

Résultat sur la machine de l'user (2026-05-14) :
- **33 photos** déplacées dans 2 sessions (PSI Shannon découverte 22 + PRG2 TP8 11).
- **34 références markdown** updated dans les transcripts.
- 0 fichier manquant.
- Dossiers COURS résiduels (AN1/TD/TD5/photos/, PSI orphelins) = matériel perso non lié aux sessions, restés en place comme attendu.
- Backup créé : `_sessions/_backup_pre_a10_3/` (8 sessions copiées).

### Tests
562 passed (inchangé : le script de migration n'a pas de test dédié car il est destructif sur disque ; le code est simple et le dry-run sert d'audit).

---

## Phase A.10.2 : Uploads déplacés de COURS/ vers _uploads/ (2026-05-14)

User : *« c'est débile que les photos soit dans COURS/ car tout ne concerne pas les cours faut déplacer ça dans un endroit plus logique dans le dossier compagnon révision et aussi changer les références de ceci dans les docs si c'est mentionné »*.

Friction de fond : les sessions **Sujet libre** (Phase A.8.3) et **Workspace** (Phase A.9) n'ont rien à voir avec COURS/. Pourtant les photos / PDF envoyés au tuteur étaient routés vers `COURS/{MAT}/{TYPE}/{TYPE}{N}/photos/`, ce qui n'a même pas de sens (pas de matière COURS pour ces modes). Solution : tout migre vers `Compagnon_Revision/_uploads/{session_id}/{photos|attachments}/`.

### Backend (`config.py` + `_scripts/web/app.py`)
- **Nouvelle constante** `UPLOADS_DIR = PROJECT_ROOT / "_uploads"`.
- `_attachment_target_dir(session_id, is_image)` refactor : signature passe de `(ctx, is_image)` à `(session_id, is_image)`, retourne `UPLOADS_DIR / session_id / ("photos" | "attachments")`. Plus de routage par matière/type/num.
- `api_upload_attachment` : `rel_path` calculé relatif à `UPLOADS_DIR` (format `{session_id}/photos/{filename_vN.ext}`). Nouveau champ `storage: "uploads"` dans le tracking pour distinguer du legacy `"cours"`.
- **Markdown injecté** dans `api_send_message` : préfixe `_uploads/` ajouté aux paths des nouvelles photos (`![p.jpg](_uploads/session_X/photos/p.jpg)`) pour que le `renderMarkdown` JS route vers `/api/upload_file` au lieu de `/api/cours_file`. Legacy `storage="cours"` reste sans préfixe.
- **Persistance `session_photos[]`** (hook A.9.1) : propage `storage` depuis l'attachment dans l'entry sticky de la galerie. Défaut `"uploads"` pour les nouvelles, `"cours"` pour le backfill A.10.1.
- **Nouvel endpoint** `GET /api/upload_file?path=...` : pendant de `/api/cours_file`, sert depuis `UPLOADS_DIR` avec anti-traversal + whitelist d'extensions (png/jpg/jpeg/webp/gif/svg/pdf). Ajouté au `_VIEWER_GET_ALLOW`.
- **`api_pending_attachments_replace`** (crop) : récupère la base selon `target.storage` (`UPLOADS_DIR` ou `COURS_ROOT`). Re-crop d'une photo legacy reste dans COURS/, re-crop d'une photo A.10.2 reste dans `_uploads/`. Cohérence sans cassure.

### Front (`app.js` + `mobile.html`)
- **Helper `_attachmentSrcUrl(att)`** : retourne l'URL serveur selon `att.storage`. Utilisé dans la galerie photos, l'attachment tray, la modal crop. Mirror `_attachmentSrcUrlM` côté `mobile.html`.
- **`renderMarkdown`** étendu : si le path commence par `_uploads/`, strip le préfixe et route vers `/api/upload_file?path=...`. Sinon (legacy, et URLs externes inchangées) → `/api/cours_file?path=...`.
- `makeItem` de `mobile.html` propage le `storage` reçu de l'API.

### `.gitignore`
- `_uploads/` ajouté (les uploads ne doivent jamais être commit).

### Migration
- **Aucune migration des photos existantes** : les sessions antérieures gardent leurs photos sous `COURS/.../photos/`, le backfill A.10.1 les détecte via le markdown du transcript et leur pose `storage: "cours"`. Les nouvelles photos vont dans `_uploads/`. Cohabitation propre, jamais de move massif.

### Tests
- Nouveau `tests/test_app_upload_file.py` (8 cas) : param manquant, chemin absolu, traversal `..`, fichier introuvable, extension non whitelistée, happy path JPG + PNG (mime correct), path qui résout hors `UPLOADS_DIR`.
- 562 passed (554 + 8 nouveaux).

### Docs
- CLAUDE.md : §3.1 `UPLOADS_DIR` listé dans les constantes, §5 `_uploads/` mentionné dans l'arborescence, pointer §11.
- ARCHITECTURE.md : nouvel endpoint `/api/upload_file` documenté.
- CHANGELOG (cette entrée).
- Le doc `_scripts/web/app.py` (docstring de `api_upload_attachment`) reflète déjà le nouveau routage.

---

## Phase A.10.1 : Sidebar tabs compacts + backfill galerie photos (2026-05-14)

Suite de Phase A.10. Deux frictions remontées par l'user après livraison :

### Friction 1 : Sidebar tabs en `…`

User : *« à force de mettre des éléments dans la sidebar-tabs c'est devenu trop étroit du coup les textes s'affiche tous par "..." faut que tu trouves une solution ? »*

Cause : 7 onglets (Quota / Docs / Notes / Photos / Consignes / Historique / Distant) dans une sidebar de ~340 px ; `flex: 1 1 0` distribuait équitablement → chaque tab < 50 px → `text-overflow: ellipsis` clippait tout.

Fix : mode **compact icons-only** par défaut, label visible uniquement sur l'onglet actif (et au hover natif via `title=`). Refactor du markup en `<span class="sb-tab-icon">📊</span><span class="sb-tab-label">Quota</span>` ; CSS `.sb-tab-label { display: none }` + `.sb-tab.active .sb-tab-label { display: inline }`. Le tab actif passe en `flex: 1 1 auto` pour s'agrandir au besoin, les inactifs restent en `flex: 0 1 auto` (largeur de l'icône). UX inspirée de VSCode / Discord.

### Friction 2 : Anciennes photos absentes de la galerie

User : *« c'est normal que dans une session existant avec la fonctionnalité photo, après avoir stop et relancer la session pour recharger et voir ce nouvel onglet, au sein de cet onglet, je ne vois pas les anciennes photos datant ? (normalement dans l'arbo les photos sont pas censé être enregistré tu peux les retrouver là-bas non?) »*

Cause : `session_photos[]` n'existe que depuis A.9.1 (le hook `api_send_message` persiste à l'envoi). Les sessions antérieures ont les fichiers sur disque (sous `COURS/{MAT}/{TYPE}/{TYPE}{N}/photos/`) et les références dans le transcript (`![filename](rel_path)` injecté par Phase v15.7.8), mais pas le champ tracking.

Fix : nouveau helper `_maybe_backfill_session_photos(st)` qui scanne le transcript student au 1ᵉʳ GET `/api/session_photos`, extrait les `![alt](path)` via regex, valide chaque chemin (sous COURS_ROOT, fichier existe, extension dans `_IMAGE_EXTS`), reconstitue chaque entrée avec ID neuf + flag `backfilled: True`. Idempotent via marker `session_photos_backfilled: True` posé même si la liste finale est vide (un transcript sans photo, ou des fichiers supprimés du disque, ne doivent pas re-déclencher le scan à chaque GET).

Garde-fous :
- Skip URLs externes (`http(s)://`), chemins absolus (`/`, `C:`), endpoints API (`/api/`).
- Dédup par `rel_path` (même image envoyée 2× = 1 entrée).
- Skip bulles claude (le tuteur peut citer une image qui n'a pas été envoyée par l'étudiant).
- Set le marker même quand 0 photo trouvée → pas de re-scan inutile.
- Best-effort : toute exception est swallowée par try/except, le GET continue.

### Tests
- `test_app_session_photos.py` enrichi (+8 cas backfill) : marker présent → pas de scan, session_photos déjà populée → marker only, transcript→files réels (2 photos PNG + JPG), fichier manquant → skip, dedup, URLs externes refusées, bulles claude ignorées, marker posé même sur résultat vide.
- 554 passed (510 base + 36 A.10 + 8 nouveaux).

---

## Phase A.10 : Mémoire persistante de séance (« sticky consignes », 2026-05-14)

User : *« il omet les signatures et je lui demande explicitement de ne pas oublier, mais je pense qu'il va oublier c'est déjà arrivé dans d'autres session qu'il oublie. Comme dans les llm sota il peut pas y avoir un truc du genre mémoire persistante qui se remplit au fur et à mesure en fonction de ce qu'il vaut est pertinent et surtout de ce qu'on dit ? et que cette mémoire persistante soit visible à un endroit pour voir tout ce qui est enregistré et qu'on puisse supprimer ou modifier etc. »*

Phase A.10.2 sous-jacente (`<<<REMEMBER>>>`) ; cf. CHANGELOG ci-dessous pour détail. Approche retenue après arbitrage user : **épinglage explicite** (chip 📌 manuel OU balise `<<<REMEMBER>>>` émise par le tuteur sur demande), **pas d'extraction automatique** (trop de risque de bruit / dérive). Portée **par session** (pas globale, pas cross-matières, l'user a choisi). Réinjection à chaque tour en préfixe du user message LLM, persisté dans le JSON de séance.

### A.10.1 : Backend stickies (schema + endpoints)
- `session_state.data["stickies"] = [...]` (champ additif, pas de bump de `schema_version`).
- Structure d'une sticky : `{id, kind, text, source_message_id, created_at, edited_at, enabled}` avec `kind ∈ {"user", "tutor"}` et `enabled: bool` (désactiver = ne plus injecter dans le contexte LLM sans perdre la consigne).
- 5 endpoints :
  - `GET /api/stickies` : liste de la session active.
  - `POST /api/stickies` : body `{text, source_message_id?, kind?}` : text ≤ 200 chars après normalisation whitespace, kind default `user`.
  - `PATCH /api/stickies/<id>` : body `{text?, enabled?}` : édition inline + toggle.
  - `DELETE /api/stickies/<id>` : suppression.
  - `POST /api/stickies/import_from/<session_id>` : copie depuis une autre session (filtre optionnel `sticky_ids`, sinon toutes les enabled). Nouveau ID, conserve kind + source_message_id, ajoute `imported_from`. Anti-traversal sur `session_id`.
- Helper `_format_stickies_block_for_llm(st)` : produit le bloc `[CONSIGNES ÉPINGLÉES…]` injecté en préfixe de chaque user message dans `_run_claude_streaming` (canal séparé `pending_user_text` vs `llm_text`, pattern identique à `reading_line` Phase v15.7.30.1). Le transcript student persisté reste propre : la sticky est rappelée à chaque tour côté LLM uniquement.
- Whitelist `_VIEWER_GET_ALLOW`.

### A.10.2 : Balise `<<<REMEMBER>>>` parser + handler SSE
- `parser.py` : nouvelle balise `<<<REMEMBER>>>{"text": "..."}<<<END>>>`. `ParserState.INSIDE_REMEMBER` + `ParserEventType.REMEMBER`. Validation light : JSON syntaxique, `text` string non vide, normalisation whitespace, cap soft 200 chars (tronque à 197 + `…` + warning).
- `app.py` (SSE pipeline) : handler `REMEMBER` qui persiste via `set_meta("stickies", existing + [new])` avec `kind="tutor"` et émet event SSE `sticky_added` au front. Le front affiche un toast `📌 Consigne ajoutée par le tuteur : « … »` + auto-refresh.

### A.10.3 : Front (onglet 📌 Consignes + chip + import)
- Onglet **📌 Consignes** entre 🔖 Notes et 💬 Historique.
- Header : titre + boutons `📋 Importer…` (modal) + `🔄`.
- Carte par sticky : icône `📌 Toi` (user) ou `🤖 Tuteur`, timestamp, body éditable au double-clic (textarea inline, Enter pour valider, Esc pour annuler), bouton `✅ Active`/`⏸ Désactivée` (toggle PATCH), bouton `↪ Voir` (scroll vers source_message_id), bouton `🗑` (delete avec confirm).
- **Chip 📌 hover-only** sur chaque bulle `.turn.student` (sauf markers). MutationObserver pour les nouvelles bulles. Click → modal pré-rempli pour ajustement si > 200 chars, sinon POST direct + toast `📌 Consigne épinglée` + bascule sur l'onglet.
- **Modal d'import** 2 étapes : (1) liste des autres sessions avec `stickies_count > 0`, click pour drill-down (2) checkboxes par sticky de la source (toggle all + import partiel via `sticky_ids`).
- Handler SSE `sticky_added` côté EventSource → toast + refresh.
- Endpoint `/api/sessions` enrichi avec `stickies_count` (filtré enabled).

### A.10.4 : Modif des 4 prompts système
- **COMPAGNON v0.8 → v0.9** : nouvelle §10 « Consignes épinglées par l'étudiant (mémoire persistante de séance) » avec sous-section §10bis sur la balise `<<<REMEMBER>>>`, règles d'émission (uniquement sur demande explicite), critères de bonne/mauvaise consigne. Nouvelle règle absolue **§4.14** « pas de résistance aux consignes épinglées » (clone §4.11/§4.12/§4.13). RAPPEL FINAL décalé en §11.
- **GUIDE v1.6 → v1.7** : nouvelle §6 « Consignes épinglées » + §6bis balise + règle absolue §4.9. RAPPEL FINAL décalé en §7.
- **DECOUVERTE v1.2 → v1.3** : nouvelle §6 + §6bis + règle absolue §3.15. RAPPEL FINAL décalé en §7.
- **WORKSPACE v1.3 → v1.4** : nouvelle §5bis « Consignes épinglées » + sous-section balise + règle absolue §4.11.

### A.10.5 : Tests (+37 cas)
- `tests/test_app_stickies.py` (28 cas) : 22 endpoints (GET/POST/PATCH/DELETE/import_from : happy paths, no-session 409, validation 400, ID inconnu 404, anti-traversal, idempotence, normalisation whitespace, kind defaults, sticky_ids filter, import enabled-only) + 6 helper `_format_stickies_block_for_llm` (empty, all-disabled, enabled-only, missing `enabled` field, empty text, robust to None data).
- `tests/test_parser.py` enrichi (+8 cas REMEMBER) : valid simple, with surrounding text, split chunks, invalid JSON, missing text field, empty text, truncate at 200 chars, whitespace normalized.
- Suite complète : **546 passed** (510 + 36 nouveaux, 4 supplémentaires de l'incrément A.9.2 collecté). Pas de régression.

### A.10.6 : Docs + push
- CHANGELOG (cette entrée), CLAUDE.md (roadmap A.10 + mention onglet), README.md (section dédiée 📌 Consignes), ARCHITECTURE.md (endpoints + tests).

---

## Phase A.9.2 : Bloc OCR rerender F5 en details collapsible (2026-05-14)

Friction user post-A.9.1 : *« après redémarrage sur F5 le css de ceci disparait `<summary>🔍 OCR pré-vérifié par Gemini Flash · pseudo_code · complétude 100%</summary>` , ça se change en `<p>[OCR pré-traitée par Gemini Flash 2.5 : …]</p>` et `<p>--- OCR de l'image ---<br>…</p>`. Summary et div se change en p et c'est pas beau ça fait tache. »*

Cause : `api_send_message` concatène le bloc OCR Gemini au `user_text` persisté (cf. v15.7.20 : le tuteur garde son contexte OCR en cas de reprise). En live, le front affiche le bloc en `<details>.ocr-collapsible` via `_appendOcrCollapsibleBlock` depuis la réponse 202. Au F5, `renderMarkdown` traite la concat brute → `<p>` plats.

Fix : nouveau parseur JS `_extractOcrBlocksFromText(text)` miroir du backend (`app.py:1496-1511`). Au replay, extrait le header `[OCR pré-traitée par Gemini Flash 2.5 : …]:` + split sur `\n\n--- OCR de l'image ---\n`, parse `Type détecté` / `Complétude estimée` / `Warnings` + body markdown, et re-injecte les blocs via `_appendOcrCollapsibleBlock`. `dataset.rawText` aussi nettoyé. Schéma transcript inchangé, marche sur les sessions existantes (zéro migration).

---

## Phase A.9.1 : Galerie photos auto dans la sidebar (2026-05-14)

User : « après avoir lancé une session, dans le web, je veux quelques part une galerie photo qui enregistre toutes les photos transmises (et aussi avoir possibilité de les supprimer on sait jamais pour gagner en clarté sur la longue) … j'envoie des photos mais quand la discussion va devenir plus longue j'aimerais bien revoir ces photos un peu comme ce qui est fait dans notes mais cette fois ci ce n'est pas moi qui décide quoi save en note mais ça se fait automatiquement à chaque photo envoyé ».

Pattern jumeau de l'onglet 🔖 Notes (Phase v15.7.23) mais avec **archivage automatique** au lieu de manuel. Chaque envoi de photo (📷 webcam, 📎 fichier image, paste/drag-drop, photo mobile) qui transite par `send_message` est désormais persisté dans `session_photos[]` du JSON de séance : l'image markdown reste injectée dans le transcript pour le tuteur multimodal, mais en plus on indexe l'attachment pour l'afficher en galerie.

### Backend (`_scripts/web/app.py`)
- **Hook persistance** : dans `api_send_message`, juste avant `pending_user_text = text`, on filtre les attachments `is_image=True` et on les pousse dans `session_photos[]` via `set_meta` (champ additif, pas de bump de `schema_version`).
- **Endpoints** : `GET /api/session_photos` (liste pour le sidebar), `DELETE /api/session_photos/<photo_id>` (retire l'entrée, le fichier disque sous `COURS/{MAT}/{TYPE}/{TYPE}{N}/photos/` reste, cohérent avec `pending_attachments` DELETE). Pattern miroir de `saved_selections`.
- **Whitelist viewer** : `/api/session_photos` ajouté à `_VIEWER_GET_ALLOW` (les viewers en lecture seule voient la galerie).

### Front (`_scripts/web/templates/index.html` + `static/app.js` + `static/style.css`)
- **Onglet 📸 Photos** entre 🔖 Notes et 💬 Historique, avec header (titre + bouton 🔄 refresh) et grille `#photos-grid` (`grid-template-columns: repeat(auto-fill, minmax(120px, 1fr))`).
- **`refreshSessionPhotos()`** : fetch `/api/session_photos`, render des `.photo-card` avec vignette `<img loading="lazy">` servie via `/api/cours_file?path=...`, méta (timestamp court + taille kB), bouton 🗑 en overlay (apparaît au hover). Tri anti-chronologique (plus récente en premier).
- **Click vignette** → `openLightbox(src)` (réutilise le même composant que les slides guidées). Pas de gestion EXIF, pas de re-crop : la galerie est lecture seule.
- **Hooks d'auto-refresh** : (a) au switch sur l'onglet `photos`, (b) après chaque `send_message` réussi (à côté de `refreshAttachmentsTray`).
- **`error` handler image** : fallback `🗎 (fichier introuvable)` si le fichier a été déplacé hors COURS/.

### Tests
- Nouveau `tests/test_app_session_photos.py` (7 cas) : listing avec/sans session active, photos vides, DELETE happy path / 404 inconnu / 409 sans session / idempotence (1ʳᵉ DELETE 204, 2ᵉ 404).
- Suite complète : **510 passed** (503 + 7 nouveaux), aucun cassé.

---

## Phase A.9.x : Itérations UX workspace (2026-05-13, série de hotfixes après 1ᵉʳ test réel)

Suite de frictions remontées lors du 1ᵉʳ workflow workspace utilisateur. Toutes consolidées ici plutôt qu'en lignes séparées du roadmap §9.

### Hotfix 1 : `ClaudeClient` rejetait `mode="workspace"` (commit `2864273a`)
`claude_client.py:387` validait `mode` contre `(MODE_COLLE, MODE_GUIDE, MODE_DECOUVERTE)` : `MODE_WORKSPACE` oublié. `start_session` levait `ValueError`, Flask retournait 500 HTML, front parsait `<!doctype...>` en JSON → alert « Unexpected token '<' ». Fix one-liner + test de régression `test_start_session_workspace_returns_200_json`.

### Hotfix 2 : Création PDF : phasage strict + UX expressive (commit `8932b2d6`)
Frictions multiples sur la balise `<<<SAVE_INVENTED_PDF>>>` :
- Pas de signal pendant la génération (5 s de silence → user pense que c'est cassé).
- Pas de lien vers Docs après création.
- Tuteur émettait au tour 1 avant que l'user ait répondu au cadrage.
- Pas de possibilité de régénérer si les questions ratent leur cible.

Fix :
- **Backend** : nouvel event SSE `invented_pdf_started` émis avant le rendu PDF.
- **Front** : 3 handlers SSE coordonnés (started/ready/error). Bulle « ⏳ Génération en cours (Ns) » avec compteur live + pulse CSS pendant la génération, remplacée par bulle finale avec bouton « 📂 Ouvrir dans Docs » au succès. Le bouton active l'onglet Docs et navigue automatiquement vers le PDF par filename.
- **Prompt v1.0 → v1.1** : §2.7 refondue avec phasage strict en 9 étapes (cadrage → annonce → balise → review → ajustements → régénération → enchaînement). Régénération maintenant explicitement autorisée (cap soft 3 essais).

### Hotfix 3 : Suffixe `_N` + 4ᵉ option modal conflit (commit `2b258218`)
User : « si on veut refaire la même session à l'identique … sans écraser l'historique … les sessions se renommeront _1 et _2 etc. … de base que tout soit à _1 pour éviter de devoir renommer l'ancienne ».

Fix : toutes les nouvelles sessions sont suffixées `_1` par défaut. Helper `_resolve_session_id(base_id, force_new_session)` ajouté dans `app.py` :
- `force_new_session=False` → `base_id_1` (overwrite si déjà là).
- `force_new_session=True` → scanne `_1.json`, `_2.json`, ..., retourne le 1ᵉʳ libre.

`_build_session_id` retourne désormais le base sans `_N`, le resolver pose le suffixe au moment du `start_session`.

Nouveau bouton dans le modal de conflit : `📑 Démarrer une nouvelle (conserver l'ancienne, suffixe _2/_3…)`. Clic → `doStartSession({...body, force_new_session: true})`. Migration one-off de la session Shannon en `_1`. 4 tests de régression dans `test_workspace.py` (`TestResolveSessionId`).

### Hotfix 4 : UX consolidée : raccourcis renommés, Parcourir focus, PDF déplacé (commits `a10f0a23`, `6d656ee6`, `b8e835ae`, `48d2e164`)
Plusieurs micro-frictions UX :
- « c'est quoi 'presets' » → renommé en **« Raccourcis »** dans la GUI Tk (label, messageboxes, logs). API interne `workspace_presets` conservée.
- Focus sous-dossier : ajout d'un bouton **« Parcourir… »** scopé au workspace (`_workspace_focus_browse` ouvre filedialog avec `initialdir=workspace_root`, calcule `path.relative_to`).
- Layout raccourcis : `+/−` regroupés dans un sub-Frame avec le combobox en col 1 (au lieu d'une col 2 ou col 3 séparée qui décalait les `Parcourir…` des autres rows). Col 2 ne contient maintenant que les `Parcourir…`, alignement vertical propre.
- Checkbox PDF : déplacée APRÈS le bloc workspace (au lieu d'entre Sujet libre et Workspace), pour qu'elle soit visuellement attachée au bloc actif. Label étendu : `(Découverte / Sujet libre / Workspace)`.

### Hotfix 5 : Layout GUI 2 sous-colonnes pack (commit `d602601d`)
User : « session dans le gui est trop vers le bas car caps contexte à trop de hauteur par rapport à moteur (modèle) et même soucis lancer une session à trop de hauteur par rapport à quota pro max ça fait moche un peu ». Cause : grid 2×3 avec `sticky="new"` → chaque row prenait la hauteur du plus grand des 2 cells.

Fix : 2 sous-colonnes `Frame` avec `pack` interne, indépendantes verticalement. Chaque LabelFrame se cale juste sous le précédent dans sa propre colonne.

### Hotfix 6 : Format en workspace + ancrage corrigé grisé (commit `8621ccfb`)
User : « que ce soit pour sujet libre ou workspace faut avoir le choix du format (par contre pour ancrage corrigé c'est incohérent dans gui mais aussi dans la nav, peut-être griser les choses incohérentes pour éviter à l'user de devoir changer depuis la nav et créer des bugs) ».

Fix :
- `_refresh_colle_format_visibility` : visible aussi en workspace (le format pédagogique garde du sens, il calibre la stratégie photo).
- `_refresh_corrige_anchor_visibility` : en sujet libre OU workspace, force `corrige_anchor="aucun"` + grise les radios via `state="disabled"`.
- Backend : étend le force `aucun` aux workspaces.
- Front nav : `applyCorrigeAnchorChips` désactive le `<select>` quand `activeMode === "workspace"` ou `session_id` match `_LIBRE_`, avec tooltip explicatif.
- Cleanup : 3 sessions test parasites `WORKSPACE_tmpXXX` supprimées, test d'intégration ajoute un `try/finally` pour nettoyer ses artefacts.

### Hotfix 7 : Lock selects mid-session dans la nav (commit `dd4dd6c5`)
User : « pareil dans la nav web faut que les sélections dans l'entête démarrer soit grisé si non switchable ». Cause : pendant une séance active, seuls les `<input>` étaient grisés, les `<select>` (matière, type, num, exo, année, mode) restaient interactifs alors qu'ils ne sont pas switchables.

Fix : 2 helpers globaux `_lockStartFormForActiveSession()` / `_unlockStartFormAfterSessionEnd()` qui appliquent / lèvent l'état disabled sur la liste `_UNSWITCHABLE_SELECTS`. `colle_format` et `corrige_anchor` restent en dehors (switchables mid-session, sauf anchor en workspace/libre déjà géré).

### Hotfix 8 : Format photos vraiment honoré + audit contextualisé + modal direct mid-session (commit `0244020f`)
3 frictions en chaîne :
- **Format `photos` ignoré** : user : « j'ai sélectionné le mode photo mais il me propose jamais d'envoyer une photo ». Cause : le prompt workspace v1.1 ne référençait pas `[FORMAT PÉDAGOGIQUE]`. Fix : injection du marker dans `prompt_builder` + nouvelle §2.8 dans le prompt.
- **Audit biaisé** : `_generate_session_recap` utilisait un prompt hardcodé révision orale → terminologie « TD5 ex1 » fictive sur séance workspace. Fix : paramètres `mode` et `matiere` qui adaptent le vocabulaire LLM (workspace → « module xxx », sujet libre → « concept de Y », COURS → « TD5 ex1 »).
- **Clic Lancer mid-session** : ouvrait `window.confirm` tronqué car `body.num="_"` ≠ `data.num=slug` en workspace. Fix : on saute direct au modal de conflit (4 options) avec les infos `/api/current_session` (qui expose maintenant `last_alive`, `interrupted`, `label`).

### Hotfix 9 : Spécificité oral et mixte symétrique avec photos (commit final ce CHANGELOG)
User : « et du coup t'as pris en compte la spécificité de oral et mixte aussi ? ». §2.8 v1.2 ne détaillait que `photos` par posture, `oral` et `mixte` étaient en 1 phrase chacun. Fix : v1.3 enrichit `oral` et `mixte` par posture (explain / quiz / deep-dive), avec critère explicite de décision pour `mixte` (quel contenu bénéficie du papier vs reste verbal) et règle « sortie de secours autorisée » en `mixte`.

---

## Phase A.9 : Mode workspace : tutorat sur dossier disque arbitraire (2026-05-13)

User feedback :
> *« j'ai imaginé une nouvelle fonctionnalité actuellement il y a le mode sujet libre (hors COURS/, apprendre n'importe quel sujet) mais pour ceci il faut écrire un prompt. Donc c'est bien faut conserver. Mais faut un nouveau truc pour donner cours à partir d'un workspace dans notre pc. Par exemple j'ai un entretien bientôt pour présenter mes logiciels j'ai besoin de comprendre ce que l'IA à fait et tout et explorer en profondeur en redécouvrant tout. … Cela peut aussi être sur C:\\RoleplayOverlay, C:\\Users\\Gstar\\OneDrive\\Documents\\BotGSTAR\\Arsenal_Argument, ou même des trucs triviaux ou il n'y a pas de code mais une sorte de concept par exemple C:\\Users\\Gstar\\OneDrive\\Documents\\CV. Compagnon se débrouille quoi. »*

### 1. Nouveau mode `workspace` (4ᵉ posture, parallèle à colle/guidé/découverte)

- `claude_client.MODE_WORKSPACE = "workspace"` + `WORKSPACE_ALLOWED_TOOLS = "Read,Grep,Glob"`. Subprocess CLI Claude Code lancé avec `cwd=workspace_root` pour scope FS automatique.
- Nouveau `_prompts/PROMPT_SYSTEME_WORKSPACE.md` (v1.0, 6 sections, 3 postures explain/quiz/deep-dive auto-sélectionnées au cadrage). Écrit par Claude Code sur autorisation explicite de l'user (cf. CLAUDE.md §10.1).
- Sélection via checkbox `📁 Workspace` dans la GUI Tk (orthogonale au radio Mode). Mutex avec Sujet libre. Désactive Guidé. Combos COURS désactivés.
- `_build_session_id` étendu : sessions workspace → `YYYY-MM-DD_WORKSPACE_<slug>_full_workspace_mixte_aucun` (slug = basename normalisé du chemin, par ex. `compagnon-revision`, `cv`, `arsenal-arguments`).

### 2. Compagnon « se débrouille » face à différents types de workspace

- `prompt_builder.detect_workspace_type(root)` → `"code"` / `"doc"` / `"mixed"` selon le ratio d'extensions reconnues (code-heavy = >60% `.py`/`.js`/`.cs`/etc., doc-heavy = <40% code parmi les fichiers à extension reconnue). Cap 500 fichiers scannés pour éviter de bloquer sur un dépôt géant.
- `prompt_builder.build_workspace_summary(root, excludes, focus_subdir)` génère un résumé textuel injecté au contexte initial : arbre depth 3 (cap 20% du budget chars) + contenu intégral des fichiers-pivots détectés (`README*`, `CLAUDE.md`, `AGENTS.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `pyproject.toml`, `package.json`, `Cargo.toml`, `Dockerfile`, `.github/copilot-instructions.md`, etc., cap 8 k bytes par pivot, total ≤ 50 k chars). Excludes par défaut : `.git`, `node_modules`, `__pycache__`, `_archives`, `_sessions`, `_secrets`, `*.pyc`, `*.dll`, `*.log`, etc.
- Marker `[WORKSPACE_TYPE : code|doc|mixed]` injecté dans le header de session : le prompt §1.4 sélectionne la posture pédagogique correspondante (code = explication module-par-module ; doc = synthèse de chapitres ; mixed = hybride).

### 3. Fonctionnalités annexes demandées par l'user

- **Quick presets** : Listbox + Combobox dans la GUI Tk pour sauvegarder les chemins workspace fréquents (`Compagnon_Revision`, `RoleplayOverlay`, `Arsenal_Arguments`, `CV`…) et y revenir d'un clic. Persistés dans `_secrets/runtime_settings.json` → `workspace_presets`. Boutons `+` / `−` pour ajouter/retirer.
- **Pattern exclude personnalisé** : Entry comma-separated pour des excludes spécifiques au-delà des défauts (`_archives, *.log` par exemple). Persistés dans `runtime_settings.json` → `workspace_excludes` (additifs aux `WORKSPACE_DEFAULT_EXCLUDES` hard-codés).
- **Sous-dossier de focus** : Entry pour zoomer sur un sous-dossier précis (`_scripts/dialogue/`). Quand fourni, l'arbre injecté part de ce sous-dossier au lieu de la racine du workspace, et un marker `[WORKSPACE_FOCUS : <subdir>]` est injecté pour orienter le tuteur.

### 4. Garde-fous (cf. PROMPT_SYSTEME_WORKSPACE.md §4)

- **Lecture seule** : `Read`, `Grep`, `Glob` uniquement. Pas d'`Edit`, `Write`, `Bash`. Le tuteur n'écrit jamais dans le workspace (même pas de balise `<<<SUGGESTED_EDIT>>>`).
- **Secrets** : `.env`, `_secrets/`, `*.key`, `*.pem`, fichiers nommés `*secret*`/`*password*`/`*token*` ne sont jamais restitués même si accidentellement lus.
- **Pas d'exfiltration** : extraits ciblés (chemin:ligne-ligne) plutôt que dump complet des gros fichiers.
- **Pas d'hallucination** : si le résumé n'a pas couvert un aspect, le tuteur fait un `Read` avant de répondre, jamais de « je crois que ça fait X ».
- **Pas de jugement de qualité** non sollicité. Pas de flatterie. Vouvoiement strict.

### 5. CLI args + URL params + propagation back-to-front

- `compagnon.py` : nouveaux args `--workspace-root <path>`, `--workspace-focus <subdir>`, `--workspace-exclude <pattern>` (cumulatif). Propagés via URL query params `workspace_root`, `workspace_focus_subdir`, `workspace_excludes`.
- `app.js` : lit les params au boot, stocke dans `window._pendingWorkspace`, injecte dans le body POST `/api/start_session` au submit du form.
- `app.py:_build_session_context` short-circuit workspace : pas de résolution énoncé/corrigé/perso/CM, retourne directement un `SessionContext` avec `workspace_root`/`workspace_excludes`/`workspace_focus_subdir` remplis.
- `ClaudeClient` reçoit `cours_root=workspace_root` quand mode=workspace → subprocess `cwd=workspace_root` → FS scope automatique.
- `/api/resume_session` reconstruit le ctx workspace depuis le JSON persisté.

### 6. Tests

`tests/test_workspace.py` (14 tests) couvre : `slugify_workspace` (basename Windows/Unix, fallback empty), `detect_workspace_type` (code-heavy, doc-heavy, mixed, empty), `build_workspace_summary` (tree + pivots, focus_subdir), `SessionContext.workspace_root`, `_build_session_id` format workspace, `runtime_settings._default_settings` + `_merge_with_defaults` (presets/excludes dedup).

**498 tests verts** au total.

---

## Phase A.8.6.1 : Hotfix GUI Tk : propagation chips découverte + seuil replay éditable (2026-05-13)

Trois frictions remontées après le déploiement initial de A.8.6 :

User feedback :
> *« Je dois voir le seuil résumé dans le GUI pour pouvoir le changer quand j'ai envie. Y'a un souci quand j'ai lancé une session PSI TP_Shannon mode découverte, format photos, sans corrigé eh bien dans le nav ça l'ouvre en mode mixte et strict. Évidemment dans le gui que le seuil soit persistant comme pour les autres, au redémarrage le changement soit tjr effecté et ne reviens pas à sa valeur par défaut. »*

### 1. Bug : la GUI Tk droppait silencieusement format/anchor en mode découverte (commit hotfix)

`gui.py:1269-1273` gatait l'ajout des CLI args `--colle-format` et `--corrige-anchor` sur `mode == "colle"`. Le radio « Format pédagogique » et « Ancrage corrigé » sont pourtant **visibles** en découverte aussi (`_refresh_colle_format_visibility` accepte `colle` ET `découverte` depuis Phase A.8.2). Conséquence : sélectionner Découverte + photos + aucun dans le launcher produisait une URL `?mode=découverte` sans `colle_format` ni `corrige_anchor` → le front retombait sur les défauts mixte/strict → fichier nommé `..._decouverte_mixte_strict.json` au lieu de `..._decouverte_photos_aucun.json`.

Fix : `if self.mode.get() in ("colle", "découverte")` pour les deux args. Aligné avec la condition de visibilité du radio.

### 2. Seuil replay éditable + persistant (`runtime_settings.replay_hard_cap_exchanges`)

Avant : `REPLAY_HARD_CAP_EXCHANGES = 300` était une constante module dans `app.py`. Non éditable sans toucher au code.

Après :
- `runtime_settings.DEFAULT_REPLAY_HARD_CAP_EXCHANGES = 300` (constante).
- Champ additif `replay_hard_cap_exchanges` au schéma de `_secrets/runtime_settings.json` (pas de bump version : couvert par `_merge_with_defaults`).
- Accesseur `get_replay_hard_cap_exchanges()` exposé.
- `app._should_replay_transcript` lit la valeur **live** à chaque reprise (import lazy dans la fonction pour éviter le coût au démarrage).
- GUI Tk : Spinbox `Replay complet si tours ≤ [N]` ajouté dans le panneau Quota, dans le `LabelFrame` « Seuils (refus de démarrer si dépassés) », sous les 2 spinboxes existants. Placement choisi parce qu'il y avait « un gros vide entre Quota Pro Max live et Caps contexte (avancé) » (citation user) : ce 3ᵉ seuil est conceptuellement du même registre que les 2 autres (limites à l'usage runtime).
- Auto-save 500 ms via le même `_schedule_thresholds_save` que les 2 autres. `_reload_thresholds` synchronise les 3 ensemble. `_save_thresholds_silent` accepte les 3 kwargs.
- Trace_add étendu pour câbler `self.replay_hard_cap` au debounce.
- Range Spinbox 10-2000 (incrément 10) : couvre les vraies bombes (1500+) jusqu'aux configs économes (10-50 si l'user veut forcer résumé tôt).

Persistant à travers les redémarrages : la valeur survit dans `_secrets/runtime_settings.json`, restaurée au boot via `IntVar(value=settings["replay_hard_cap_exchanges"])`. Le default 300 ne sert que si le fichier n'existe pas du tout.

### 3. Nettoyage one-shot des sessions résiduelles

Suite à la migration A.8.6 + au bug GUI Tk, l'utilisateur avait 12 sessions sur disque dont une seule importait (PSI Shannon, 115 tours). Le reste : tests, sessions abandonnées 0-2 tours, sessions EN1 non utilisées.

`_scripts/cleanup_sessions_one_shot.py` (script jetable, gardé pour traçabilité) :
- Backup atomique de toutes les sessions dans `_sessions/_cleanup_backup_<TS>/`.
- Supprime tout sauf `2026-05-12_PSI__revision_CC2TP_Shannon_exfull_colle_photos_aucun.json`.
- Renomme la Shannon en `_decouverte_photos_aucun` (suffixe demandé par l'user pour refléter l'intention pédagogique de la séance : exo de découverte sur Shannon avec photos et sans corrigé brandi comme autorité).
- Met à jour les 3 champs du JSON (`mode`, `colle_format`, `corrige_anchor`) + `session_id` pour rester cohérent.
- Renomme l'archive `.md` correspondante et patche son frontmatter YAML.

Note : le rename change la sémantique annoncée mais pas le transcript (115 tours qui restent stylistiquement « colle » dans le contenu). À la reprise, le prompt Découverte s'appliquera aux tours futurs ; l'historique reste tel quel.

### Tests

484/484 verts. Pas de nouveau test dédié (3 changements ciblés : 1 condition logique GUI, 1 accesseur runtime_settings déjà couvert par le pattern existant, 1 script one-shot).

---

## Phase A.8.6 : Suffixe mode/format/anchor + replay agressif à la reprise (2026-05-13)

Deux frustrations user signalées en clair après une reprise de la session `2026-05-12_PSI__revision_CC2TP_Shannon_exfull` :

User feedback :
> *« En reprenant de 0 la discussion … il a oublié tout le contexte de ce qui s'était fait avant, il me dit qu'il n'a qu'un simple résumé hors là je suis demande de me faire un récap des grands points qu'il m'a dit de noté et il est incapable de me le faire. … ben c'est pas grave si la reprise ça dépense plus de tokens je préfère ça plutot que d'avancer dans le flou. »*
>
> *« Si tu pouvais en même temps différencier de l'historique les sessions en fonction du mode et pas en fonction de la matière. Par exemple si je sélectionne PSI TP_Shannon mode découverte, et demain c'est PSI TP_Shannon mode colle, eh bien que je n'ai pas à écraser l'ancien historique. Pareil pour le format … pareil si l'ancrage corrigé y est ou pas. »*

### 1. Résumé à la reprise → seulement en dernier recours (`_should_replay_transcript`)

Avant : `< 10 tours OU last_alive < 6 h → replay`, sinon résumé Gemini Flash ≤120 mots. Conséquence : toute reprise après une nuit perdait les notes que l'utilisateur avait demandé au tuteur de mémoriser pendant la séance, parce que le résumé ne les détaille jamais (il a 120 mots pour tout).

Après (`app.py:6092`) : un seul critère, **`n < 300 tours → replay`**. La condition « 6h écoulées » est supprimée. Au-delà de 300 tours (≈ plusieurs centaines de milliers de tokens, cas extrême et jamais rencontré en pratique), le résumé reprend la main pour éviter une vraie bombe de tokens. Constante `REPLAY_HARD_CAP_EXCHANGES = 300` exposée au top du module.

Le tag UI `[résumé]` reste affiché dans ce cas rare, pour que l'utilisateur sache si la reprise s'est faite en replay ou en résumé.

### 2. Suffixe `_{mode}_{format}_{anchor}` au session_id (`_build_session_id`)

Avant : `YYYY-MM-DD_{MAT}_{TYPE}{N}_ex{n}`. Si l'utilisateur relançait le même exo le même jour avec une posture différente (colle vs découverte, oral vs photos, ancrage strict vs aucun), `_build_session_id` produisait un ID identique et `start_session` écrasait silencieusement la session précédente via `atomic_write_json` : perte directe du transcript.

Après (`app.py:7529`) :
- `2026-05-13_PSI_TP1_exfull_colle_mixte_strict.json`
- `2026-05-13_PSI_TP1_exfull_decouverte_oral_aucun.json`
- `2026-05-13_PSI_TP1_exfull_guide_mixte_consultatif.json`

Le mode est slugifié en ASCII (`guidé→guide`, `découverte→decouverte`) pour rester compatible avec la whitelist `[A-Za-z0-9_-]` de `_session_path` (cf. app.py:5874) et éviter les soucis OneDrive/git sur les caractères accentués.

Signature : `_build_session_id(ctx, mode=MODE_COLLE, colle_format="mixte", corrige_anchor="strict")`. Les défauts permettent aux 2 tests existants (`test_sujet_libre.py:184-201`) de continuer à passer avec leur appel `_build_session_id(ctx)`. L'appel réel dans `start_session` est mis à jour pour passer les 3 valeurs lues du body.

### 3. findExistingSession (JS) match aussi mode/format/anchor

`app.js:1850` : Le filtre de match dans `findExistingSession` ajoute mode + colle_format + corrige_anchor. Sinon, démarrer « PSI TP_Shannon colle » alors qu'une session « PSI TP_Shannon découverte » existe déclencherait le modal de conflit alors qu'aucun écrasement n'est en jeu (les IDs ont des suffixes différents).

Tolérance pour anciennes sessions : si le champ est `null` dans le JSON existant (sessions pré-A.8.6), on ignore la contrainte pour ce champ : l'utilisateur a sans doute une seule version en stock, autant la lui proposer.

### 4. Affichage historique enrichi

`refreshHistoryList()` dans `app.js:7373` affiche désormais `mode · format · anchor` à la place du seul `mode` dans la ligne meta de chaque carte d'historique. Les champs vides (sessions legacy) sont silencieusement omis.

L'endpoint `GET /api/sessions` ajoute `colle_format` et `corrige_anchor` au JSON par session.

### 5. Migration des 11 sessions existantes (`_scripts/migrate_session_ids.py`)

Script standalone idempotent qui scanne `_sessions/*.json`, lit `mode`/`colle_format`/`corrige_anchor` du JSON, applique les défauts si null (`colle` / `mixte` / `strict`), convertit le legacy `mode="lecture"` (absorbé Phase Z.8) en `guide`, puis :

1. Backup le JSON original dans `_sessions/_migration_backup/<old_name>.json`
2. Rename `_sessions/<old>.json` → `_sessions/<new>.json`
3. Met à jour le champ `session_id` à l'intérieur du JSON
4. Rename `_archives/<MAT>/<old>.md` → `<new>.md` si présent

Mode dry-run par défaut, `--apply` pour exécuter. Idempotent : un fichier déjà suffixé est ignoré.

Résultat exécution 2026-05-13 : 11 sessions renommées, 0 erreur. Archive `.md` Shannon TP renommée en parallèle.

### Tests

484 tests passent. Pas de nouveau test dédié (la migration est one-shot, le suffixe est trivialement vérifiable via les 2 tests `test_sujet_libre.py` existants qui utilisent `assertIn` : l'ajout du suffixe après `_full` / `_ex3` passe naturellement).

---

## Phase A.8.5 : Édition message enrichie (paste/mobile) + safety net + design (2026-05-12)

Phase consolidée de UX/bugfixes après la livraison de A.8.4. Une douzaine de hotfixes regroupés par thème.

### 1. Édition de message : paste image + photo mobile vers textarea actif (commit `a60003e3`)

User feedback :
> *« Si je veux modifier un message pour lui ajouter une photo, que je puisse coller une photo dans le chat. Voire si je prends une photo depuis mon tel en mobile et que je suis dans le champ éditer, que la photo aille par-dessus et non pas dans son endroit habituel. »*

Cas concret tour 10:36 : user dicte, oublie d'attacher la photo, le tuteur s'en plaint (post-fix A.8.4 §1.6 v0.8). User veut éditer le message pour ajouter la photo via Ctrl+V ou capture mobile, sans avoir à sauvegarder localement.

3 voies redirigées vers le textarea d'édition quand un édit est ouvert :
- **Variable globale `_activeEditTextarea`** + snapshot `_editAttachmentSeenIds` (ids déjà présents à l'ouverture de l'édit).
- **`uploadAttachmentFile(file)`** étendue : si édit actif, upload en `staged=1` + insère le markdown `![alt](path)` à la position curseur. Pré-preview Cropper conservé. Toast feedback `📷 Image ajoutée à l'édition`.
- **`refreshAttachmentsTray()`** (polling 2s) étendue : détecte les NOUVEAUX attachments pendant édit, les insère dans le textarea + DELETE backend pour éviter doublon. Couvre la photo mobile asynchrone.

### 2. Hotfix archive_to_md activé au resume (commit `07d0e8be`)

User constate que le `.md` archive ne se met pas à jour. Cause : sessions legacy (démarrées avant Phase A.8.1) n'avaient pas le champ `archive_to_md` dans le JSON → `_maybe_archive_md` skipait toujours. Fix : `api_resume_session` force `archive_to_md=True` au resume si absent. Appelle aussi `_maybe_archive_md(_state)` en fin de resume pour régénérer le `.md` complet depuis le JSON courant. Rattrape les sessions legacy en une passe atomique.

### 3. Hotfix syntax error closeBtn + redesign checkboxes pills (commit `75f9c539`)

User signale que cliquer Lancer affiche « Pas de session active... » sans rien faire. Cause : SyntaxError dans `app.js` : `closeBtn` redéclaré dans `renderSessionRecapCard` (Phase A.8.4 hotfix) alors que cette variable existait déjà dans le scope (bouton « 🚪 Fermer définitivement »). Le browser plantait au chargement → tout le JS muet → submit ne marchait plus. Fix : renommé en `recapCloseBtn`. Vérifié avec `node -c app.js`.

User feedback bonus : « Les checkboxes Sans énoncé / Archive .md / Sujet libre sont moches ». Style des pills revisité : `.start-form-toggle` devient une chip avec état actif visuel (background accent + texte sombre + gras quand coché), border-radius 3px (carré, cohérent avec selects), checkbox native cachée via `opacity:0`. CSS dédié pour `#sujet-libre-zone` (carte avec bordure gauche accent quand visible).

### 4. Hotfixes UX : Reprendre session + GUI layout + chips moins arrondis (commit `0a8b85e1`)

3 points :
- **Bouton « Reprendre la session existante » mort** : `resumeSession(sid)` avait un early return `if (sid === activeSession) return;` qui tuait l'action quand la session était déjà chargée par `restoreActiveSessionIfAny()` au boot. Fix : retiré le short-circuit.
- **GUI Tk : console écrasée + bloc vide sous Refresh** : `root.geometry("980x780")` trop petit + `sticky="nsew"` sur Quota frame le forçait à s'étirer à la hauteur du Launch frame. Fix : `geometry("1100x900")` + `minsize(900, 800)` + `sticky="new"` (au lieu de `nsew`) sur les 4 frames row 0/1.
- **Chips trop ronds** (user feedback) : `border-radius: 14px` → `3px`, cohérent avec les selects/inputs du form.

### 5. Hint dynamique sous radio mode (commits `10236d7d`, `071c1031`, `fd6e4cad`)

User : « Il manque une explication pour Colle, et quand je clique sur l'un des 3 le texte est le même, c'est pas cohérent. »

Avant : `ttk.Label` statique listant les 3 modes en une ligne. Le même texte affiché en permanence.

Après : `_refresh_mode_hint()` câblée via `self.mode.trace_add("write", ...)` qui met à jour le label selon le radio sélectionné. 3 descriptions distinctes (🌱 Découverte / 📖 Guidé / 🎯 Colle) avec pédagogie + cas d'usage. Wraplength dynamique via binding `<Configure>` qui s'adapte à la largeur réelle du label (-20 px de marge) : plus de débordement à droite en fenêtre minisée.

### 6. Safety net `_trash/` avant DELETE session + écrasement .md (commit `51817063`)

User a perdu sa session PSI TP_Shannon de 55 messages + 1 weak_point capturé + 4 weak_points rétro Gemini Flash + récap débrief en cliquant par mégarde « Démarrer une nouvelle (l'ancienne sera supprimée) » dans le modal conflict.

Récupération possible via OneDrive Version History (les fichiers sont sous `OneDrive\Documents\BotGSTAR\`) mais c'est manuel. 3 défenses ajoutées :

- **`/api/sessions/<id>` DELETE** → copie le JSON dans `_sessions/_trash/<id>__deleted_<YYYYMMDD-HHMMSS>.json` AVANT unlink. Rotation FIFO 20 backups.
- **`write_session_archive()`** → si le nouveau .md serait < 50 % de l'ancien ET l'ancien > 5 KB, copie l'ancien dans `<matière>/_trash/<id>__pre_overwrite_<ts>.md` avant écrasement. Détecte les régénérations sur JSON vide.
- **Modal « Démarrer une nouvelle »** → `window.prompt` exige de taper `OUI` explicitement avant DELETE. Affiche n_tours + dernière activité pour que l'user voie ce qu'il perd.

### 7. Hotfix `_activeEditTextarea` orphelin après « Recharger contexte » (commit `7e41eabb`)

User : « J'envoie une photo depuis mon mobile mais la photo n'est pas interceptée, ça dit "Photo insérée dans l'édition" alors qu'y'a rien en édition. »

Cause : « 🔄 Recharger contexte » appelait `rerenderDialogueFromTranscript()` qui détruisait le DOM, mais sans cleanup local → `_activeEditTextarea` restait pointer sur le textarea ORPHELIN. Tous les uploads suivants étaient redirigés vers cet élément détaché au lieu du tray.

Fix double :
- Source du bug : `reloadBtn` libère `_activeEditTextarea` AVANT le rerender
- Défense en profondeur : sanity check `!document.body.contains(ta)` dans 3 fonctions (`_insertImageMarkdownInEdit`, `uploadAttachmentFile`, `refreshAttachmentsTray`) qui consultent la variable. Garantit qu'aucune voie de fermeture (cleanup, rerender, navigation, F5) ne laisse de fantôme.

### 8. Overlay sombre sur `#crop-preview-modal` (commit `a78c51b9`)

User : « Quand j'importe une photo via Ctrl+V au lieu que ça apparaisse en bas, je préfère qu'il y ait une sorte de popup avec le fond arrière légèrement noir (overlay). »

Cause : `#crop-preview-modal` (Phase v15.7.22 : pré-preview au paste/drag/mobile/📎) partage la structure HTML de `#crop-modal` mais n'avait AUCUN CSS dédié. Sans `position: fixed` ni overlay, la div s'affichait nue en flux normal en bas du body.

Fix : merge dans la règle CSS de `#crop-modal` (overlay `rgba(0,0,0,0.75)` + centrage flex + `z-index: 1500`).

### 9. Design du bouton croix des modals crop (commit `aaaa90a0`)

User : « Rend le bouton croix plus joli car il n'a pas de css. »

Avant : `#crop-close` style basique (background transparent, font 22px). `#crop-preview-close` n'avait aucun CSS.

Après : 1 règle commune pour les 2 boutons, carré 32×32 arrondi (border-radius 6px), background subtil `rgba(255,255,255,0.06)`, bordure `#333`, **hover rouge destructif** `rgba(220,60,60,0.85)` qui signale clairement « fermer », `:active` plus sombre, transition smooth 0.15s.

### Tests

Pas de tests dédiés A.8.5 (fixes principalement frontend / UX). **484 tests OK** maintenus tout au long de la phase.

---

## Phase A.8.4 : 2 fixes UX/bug : auto-scroll textarea + anti-hallucination OCR photo (2026-05-12)

**User feedback** :
> *« Quand je suis en vocal (voir même à l'écrit) et que le texte devient long dans le champ où faut taper la réponse, eh bien quand le textarea devient trop grand il doit scroller vers le bas pour que je suive ce qui est dicté or ça le fait pas du coup je dois scroller manuellement. »*
>
> *« Y'a un bug : dans mon message envoyé à 10:13 j'avais oublié de poster la photo et Compagnon à 10:13 a répondu qu'il lit une photo mais il ment, j'ai pas envoyé de photo. »*

### Friction 1 : Textarea ne scroll pas vers le bas

`autoResizeUserInput()` (Phase A.7.2 v8) faisait `style.height = scrollHeight + "px"` mais avec un `max-height: 200px` côté CSS. Dès que le contenu dépasse 200px, le textarea devient scrollable en interne, mais ne scrolle pas automatiquement vers le bas. Conséquence : en dictée vocale longue ou saisie clavier prolongée, les dernières lignes sont coupées et l'utilisateur doit scroller manuellement.

**Fix** : 1 ligne dans `autoResizeUserInput()`. Après le set `style.height`, on fait `userInput.scrollTop = userInput.scrollHeight`. Couvre la dictée WebSpeech live (qui appelle déjà `autoResizeUserInput`) ET la saisie clavier (event `input` qui appelle aussi).

### Friction 2 : Hallucination du bloc OCR sans photo attachée

Session PSI TP_Shannon 2026-05-12 tour 51 : le user a dicté longuement une note de cahier (« alors je note ceci, je note cela… »), oublié de joindre la photo, appuyé sur Envoyer. Le tuteur Gemini Pro 2.5 a répondu :

```
📸 Ce que je lis dans votre photo :
> 9. Une fonction qui renvoie un résultat `return`
> Une fonction peut calculer un résultat...
Vérification : La transcription est parfaite. Vous avez correctement...
```

**Aucune photo n'avait été envoyée.** Le tuteur a fabriqué une transcription complète de toutes pièces. Cas particulièrement grave côté pédagogie : l'étudiant débutant ne peut pas détecter que c'est inventé → il accepte la validation faussée → il croit avoir juste alors qu'il a peut-être faux.

Cause : dérive contextuelle. Sur N tours avec photo, le tuteur entre en « mode attendre photo » ; le N+1ᵉ tour sans photo doit casser le pattern, mais Gemini n'a pas reset et a continué à générer le bloc OCR comme un automate.

### Triple défense côté Python

**1. Backend (`app.py`)** : helper `_HAS_IMAGE_MARKDOWN_RE` détecte les `![alt](path)` dans le `user_text`. Si aucune image, injecte `[AUCUNE IMAGE DANS CE MESSAGE]\n\n` en préfixe avant le user_text dans le `llm_text` qui part au tuteur. Le tuteur voit explicitement qu'il n'y a pas de photo dans ce tour. Stocke aussi `st.last_user_had_image` (bool) pour le post-stream.

**2. Filtre déterministe (`output_filters.py`)** : nouvelle fonction `strip_hallucinated_ocr_block(text, user_had_image)`. Machine à états qui détecte le bloc `📸 Ce que je lis dans votre photo :` + son blockquote `> ...` + paragraphe `Vérification : ...`, et le retire si `user_had_image=False`. Intégré dans `apply_all_filters(text, user_had_image=True)` (signature étendue rétrocompat). `app.py` propage `user_had_image` au filtre.

**3. Prompt système COMPAGNON v0.7 → v0.8** : §1.6 enrichie d'un sous-paragraphe « Garde-fou anti-hallucination : pas de photo, pas de bloc OCR ». Règle absolue : si le marker `[AUCUNE IMAGE DANS CE MESSAGE]` est présent, interdit absolu d'émettre `📸 Ce que je lis...`. Demander explicitement la photo manquante à la place. Cite la friction 2026-05-12 comme exemple à ne jamais reproduire.

### Tests

- `tests/test_output_filters.py` (+6 cas) : `TestStripHallucinatedOcrBlock` : bloc retiré sans image, gardé avec image, no-op si pas de bloc, suite légitime préservée après retrait, `apply_all_filters` default kept block, `apply_all_filters(user_had_image=False)` retire.
- `tests/test_app_no_image_marker.py` (nouveau, 7 cas) : `_HAS_IMAGE_MARKDOWN_RE` matche/no-match, `CompanionSession.last_user_had_image` default False, `apply_all_filters` propagation, doctrine §1.6 v0.8 (marker mentionné, règle absolue présente).
- **484 tests OK** (était 471 avant A.8.4, +13).

### Pourquoi triple défense ?

Approche **belt-and-suspenders** :
- Le marker (1) est la garantie principale : le tuteur voit explicitement qu'il n'y a pas d'image et ne devrait pas émettre le bloc.
- Le filtre (2) est le filet de sécurité déterministe : même si le tuteur ignore le marker (cas observable avec n'importe quel LLM), le bloc halluciné est retiré silencieusement avant affichage et avant stockage dans l'historique.
- Le prompt (3) durcit la doctrine et explique pourquoi (incident référencé), ce qui augmente la probabilité que le LLM obéisse spontanément.

Sans (2), un tuteur particulièrement obstiné peut produire le bloc malgré (1) et (3). Sans (1), le tuteur n'a aucune information explicite sur l'absence d'image. Sans (3), pas de traçabilité doctrinale pour les évolutions futures.

### Bonus Friction 3 : Numérotation des listes ordonnées cassée

User feedback (session PSI TP_Shannon tour ~10:19) :
> *« Je vois "1. … 1. …" alors que ça devrait être "1. … 2. …" »*

Cause : regex `(?:\d+\.[ \t]+[^\n]+(?:\n|$))+` dans `renderMarkdown()` ne capturait que les lignes avec marker `N.` direct. Quand un item a une sous-ligne indentée en continuation (« Exemple : foo »), le bloc est cassé en deux `<ol>` séparés, et chaque `<ol>` redémarre son compteur à 1 (comportement HTML par défaut).

**1ʳᵉ tentative** (commit `a9a6ef9b`) : regex étendu à `(?:\d+\.[ \t]+[^\n]+(?:\n[ \t]+[^\n]+)*\n?)+` pour inclure les lignes de continuation directement collées. Parsing en 2 passes : capturer le bloc complet, puis split sur `\n(?=\d+\.[ \t]+)` (lookahead début d'item).

**Régression observée tour 10:20** : le 1ʳᵉ fix ne couvrait pas le cas où l'item N et l'item N+1 sont séparés par une **blank line** (pattern observé en session) :
```
1.  Pour obtenir...
    *Exemple :* `.values()`

2.  Pour additionner...     ← blank line entre les items
    *Exemple :* `sum()`
```
Le regex `\n?` final n'autorisait qu'un seul `\n` après l'item, donc le `\n\n` cassait le bloc en deux `<ol>` séparés.

**2ᵉ fix** : `\n?` remplacé par `\n*` à la fin de chaque item pour consommer les blank lines, split sur `\n+(?=\d+\.[ \t]+)` (au lieu de `\n(?=...)`) pour gérer le multi-newline. Continuations indentées préservées en `<br>`, blank lines internes à un même item préservées en `<br><br>`.

Avant :
```
1. Pour obtenir...
   Exemple : ...

2. Pour additionner...
```
→ rendu 2 `<ol>` séparés → affichage « 1. ... 1. ... ».

Après :
```
<ol><li>Pour obtenir...<br>Exemple : ...</li><li>Pour additionner...</li></ol>
```
→ affichage « 1. ... 2. ... » correct.

### Bonus Friction 5 : Édition d'un message : paste image + photo mobile vers édition active

User feedback :
> *« Si je veux modifier un message pour lui ajouter une photo, que je ne sois pas obligé que de joindre la photo mais que je puisse coller une photo dans le chat. Voir plus astucieux : si je prends une photo depuis mon tel en mobile et que je suis dans le champ éditer (fin que le champ éditer soit actuellement ouvert quelque part), eh bien que la photo aille par-dessus et non pas dans son endroit habituel. »*

Cas concret : tour 10:36, user dicte, oublie d'attacher la photo, le tuteur s'en plaint (correctement, post-fix A.8.4 §1.6 v0.8). User veut éditer le message pour ajouter la photo et utiliser « 🔄 Recharger contexte ». Avant Phase A.8.4 :

- ✏ Édition → textarea avec bouton 📎 « Joindre une image » → seul moyen, demande de naviguer dans l'arbo fichiers
- Paste (Ctrl+V) d'une image → va dans le tray pending_attachments habituel, **pas** dans le textarea édité
- Photo via `/mobile` → idem, va dans le tray

**Fix** : 3 voies redirigées vers le textarea d'édition quand un édit est ouvert.

- **Variable globale `_activeEditTextarea`** + snapshot `_editAttachmentSeenIds` des ids déjà présents à l'ouverture, pour distinguer les nouveaux arrivants (mobile, paste) des attachments pré-existants.
- **`uploadAttachmentFile(file)`** étendue : si `_activeEditTextarea` actif, upload en `staged=1` + insère le markdown `![alt](path)` à la position curseur du textarea (au lieu du tray). Feedback toast `📷 Image ajoutée à l'édition`. Pré-preview Cropper conservé (rotation/crop avant insertion). Non-images (PDF/Excel) insérés en `[Pièce jointe : ...]` texte.
- **`refreshAttachmentsTray()`** (polling 2s) étendue : si édit actif ET nouveaux ids dans pending_attachments → insère dans le textarea + DELETE backend pour éviter doublon dans le tray. Couvre le cas mobile où la photo arrive de manière asynchrone.
- **Helper `_insertImageMarkdownInEdit(rel_path, name)`** : insère à la position curseur (ou fin), gère les séparateurs `\n\n` avant/après, auto-resize.

Maintenant : `Édit ouvert → Ctrl+V image / drag-drop image / photo mobile depuis /mobile` → tout va automatiquement dans le textarea édité. Le user clique « 🔄 Recharger contexte » pour relancer le tuteur avec le message enrichi. **Aucun fichier à sauvegarder localement.**

User feedback :
> *« J'ai fait ctrl+F5 dans ma session actuelle et le récap de séance s'est posté à 10h37 et je peux même pas le supprimer, c'est pas censé faire ça c'est hors sujet. »*

Cause : `restoreActiveSessionIfAny()` (appelée au boot du front) ré-affichait la carte récap quand `phase=debrief`, avec `ts.dataset.atIso = nowIso` → la carte apparaît avec le timestamp du reload (10:37) au lieu du `recap_at` original (06:41). Pire : la carte est `dataset.localOnly = "1"`, donc pas dans le transcript backend → pas de bouton ✏/🗑 standard → impossible à fermer.

**Fix double** :
- **Pas de re-affichage automatique** : suppression de l'appel `renderSessionRecapCard()` dans `restoreActiveSessionIfAny()`. La carte n'apparaît plus qu'au moment de la fin de séance déclarée (1 fois). Le user accède au récap via l'archive .md (Phase A.8.1) qui contient la section dédiée.
- **Bouton ✕ de fermeture** : ajout d'un bouton de fermeture sur la carte récap pour permettre de la dismisser quand elle apparaît au moment de la fin de séance. CSS dédié (`.session-recap-close`) qui retire le `wrapper` du DOM au clic.

Le statut « phase débrief » reste affiché dans `sessionInfo` (suffixe `[🎓 débrief]`).

---

## Phase A.8.3 : Sujet libre (apprendre n'importe quoi hors COURS/) (2026-05-12)

**User feedback** :
> *« D'ailleurs si un jour je veux apprendre un truc qui n'est pas dans mes cours et genre je n'ai aucun matériau que ce soit en découvert, script ou colle. Faudrait déjà que compagnon fasse ce qu'il a à faire genre inventer l'énoncé et le stocker quelque part [...] mais en plus faudrait un nouveau truc dans le gui pour écrire un prompt par exemple je veux apprendre le python si j'écris ça et peut-être pour mieux cibler compagnon posera des questions [...] est-ce possible de faire ça ou c'est de nouveau un gros chantier ? »*

### Friction et constat de faisabilité

Toutes les séances Compagnon jusqu'à Phase A.8.2 étaient ancrées dans l'arbre `COURS/` (matière / type / num / exo). L'utilisateur ne pouvait pas réviser un sujet qu'il n'avait pas suivi à l'université : Python sans cours d'algo, japonais, comptabilité personnelle, conduite à tenir face à un employeur, etc.

Or la plomberie Phase A.8 / A.8.1 / A.8.2 fait déjà 80 % du boulot : mode Découverte qui invente un énoncé sans corrigé, PDF généré, archive .md, formats pédagogiques oral/photos/mixte. Il manquait juste l'**entrée utilisateur** pour passer un sujet libre + le **bypass** des combos COURS au niveau form/backend. Chantier moyen, pas une refonte.

### Livré

#### 1. SessionContext + slug

- `prompt_builder.SessionContext` enrichi de 2 champs additifs : `sujet_libre: Optional[str]` (texte brut du sujet utilisateur) et `generate_invented_pdf: bool = True` (checkbox PDF d'entraînement).
- `prompt_builder.slugify_topic(text)` : helper qui produit un slug court ASCII lowercase depuis un texte libre. Strip mots-vides FR/EN courants, normalise accents, garde les 30 chars significatifs. Exemples :
  - `"je veux apprendre python"` → `"apprendre-python"` (Note : « apprendre » conservé quand c'est tout ce qui reste après strip)
  - `"Le théorème de Bayes en probabilité"` → `"theoreme-bayes-probabilite"`
  - `"Math/Stats : inférentielles !"` → `"math-stats-inferentielles"`
  - `""` ou whitespace → `"libre"`

#### 2. Prompt builder adapté

- Nouveau marker `[SUJET LIBRE]` dans le header de contexte (déclenche l'instruction de cadrage 1er tour).
- Nouvelle section `=== SUJET LIBRE (choisi par l'étudiant) ===` qui injecte le texte du sujet (capé à 1500 chars) + mention explicite que **aucun matériel COURS** n'est attaché (le tuteur s'appuie sur ses connaissances LLM).
- Section INSTRUCTIONS adaptée pour mode `découverte` + sujet libre :
  - 1er tour = phase de cadrage avec 2-3 questions courtes (niveau actuel / objectif concret / temps dispo / pré-acquis), **toutes dans une seule réponse** (pas une question par message).
  - À partir du 2ᵉ tour : cycle Découverte classique (exposition courte → question simple → validation → suite).
  - PDF d'entraînement conditionnel selon `generate_invented_pdf` (instruction explicite d'émettre ou pas la balise `<<<SAVE_INVENTED_PDF>>>`).
  - source_label forcé à `"sans corrigé"` (pas de corrigé officiel en sujet libre).
- Section INSTRUCTIONS adaptée pour mode `colle` + sujet libre : posture colle classique avec cadrage rapide (1-2 questions), ancrage corrigé `aucun` automatique (cf. §1.4 mode `aucun` du COMPAGNON).
- `_build_session_header(ctx)` raccourci en sujet libre (juste sujet + date + heure + durée, pas de matière/type/num qui sont des sentinelles).

#### 3. Backend (`app.py`)

- `/api/start_session` accepte `body.sujet_libre`. Si présent et non vide :
  - Synthétise `matiere='LIBRE'`, `type='SUJET'`, `num=<slug>`, `exo='full'` (sentinelles).
  - Refuse `mode='guidé'` (400 : pas de script Feynman ni slides en libre).
  - Force `corrige_anchor='aucun'` (pas de corrigé officiel disponible).
  - Persiste `session_state.data["sujet_libre"]` et `["generate_invented_pdf"]`.
- `_build_session_context` : short-circuit retourne un SessionContext libre sans aucune résolution COURS (tous les paths None, correction_paths vide).
- `_build_session_id(ctx)` : format simplifié `YYYY-MM-DD_LIBRE_<slug>_full` en sujet libre (au lieu du `_MAT_TYPENUM_exN` classique).
- Storage `_sessions/YYYY-MM-DD_LIBRE_<slug>_full.json` et `_archives/LIBRE/<id>.md` (réutilise le sous-dossier par matière de Phase A.8.1 : toutes les séances libres regroupées sous `LIBRE/`).

#### 4. GUI Tk

- Checkbox `💡 Sujet libre (hors COURS/, apprendre n'importe quel sujet)` dans le panneau Lancer.
- Quand cochée : désactive combos matière/type/num/exo/année, désactive radio Guidé (force colle/découverte), affiche un Text widget multi-lignes pour décrire le sujet + checkbox `📄 Générer un PDF d'exos d'entraînement`.
- Méthode `_toggle_sujet_libre_ui()` gère la visibilité/disabled state, fallback vers `découverte` si on coche le mode libre alors qu'on était sur Guidé.
- `_launch()` propage `--sujet-libre <text>` et `--no-invented-pdf` au CLI compagnon.py.

#### 5. CLI `compagnon.py`

- 2 flags neufs : `--sujet-libre <text>` et `--no-invented-pdf`. Propagés en query params au navigateur (`?sujet_libre=...&generate_invented_pdf=0`).
- En mode sujet libre, les 4 args positionnels matière/type/num/exo sont remplis par des sentinelles côté GUI (`LIBRE SUJET _ full`) et ignorés par le backend.

#### 6. Web form (index.html + app.js)

- Checkbox `💡 Sujet libre` dans le bandeau du form.
- Zone `#sujet-libre-zone` (textarea + checkbox PDF) hidden par défaut, expand au check.
- `_toggleSujetLibreZone()` désactive les combos COURS + l'option Guidé du select mode quand sujet libre actif.
- Submit du form injecte `body.sujet_libre` + `body.generate_invented_pdf` côté `/api/start_session` si la checkbox est cochée.
- Pré-remplissage depuis l'URL (`?sujet_libre=...`) à l'ouverture de la page.

#### 7. Tests

- `tests/test_sujet_libre.py` (17 cas) :
  - `TestSlugifyTopic` (6 cas) : simple "python", strip mots-vides, accents, chars spéciaux, fallback "libre", cap longueur.
  - `TestPromptBuilderSujetLibre` (8 cas) : marker `[SUJET LIBRE]`, section dédiée, pas de corrigé injecté, instructions cadrage 1er tour, PDF actif/désactivé, colle libre, etc.
  - `TestApiStartSessionSujetLibre` (3 cas) : mode guidé refusé 400, format session_id libre, format session_id COURS inchangé (régression), build_context libre sentinelles.
- **471 tests OK** (était 454 avant A.8.3, +17).

### Limites assumées

- **Slug imparfait** : `slugify_topic("je veux apprendre python")` peut produire `"apprendre-python"` au lieu du `"python"` idéal (la stop-list est minimale). C'est un slug technique de fichier, pas un titre d'UI : l'utilisateur ne le voit qu'indirectement dans le nom de la session JSON.
- **Pas de catégorisation auto** : toutes les séances libres vont dans `_archives/LIBRE/` quel que soit le sujet (Python, japonais, philosophie…). On peut l'envisager en Phase B si le volume justifie une catégorisation par slug du sujet, mais en l'état c'est trop tôt.
- **`ancrage corrigé` masqué** : en sujet libre, le radio Ancrage corrigé reste affiché mais sans effet pratique (forcé à `aucun` côté backend). On pourrait le masquer aussi pour la cohérence UX, à voir avec usage réel.
- **Pas de validation du sujet** : si l'utilisateur entre un sujet bidon (« asdf »), le tuteur essaiera quand même de poser des questions de cadrage et plantera élégamment au 2ᵉ tour. Compromis assumé : on fait confiance à l'utilisateur sur son input.

---

## Phase A.8.2 : Format pédagogique en mode Découverte (oral / photos / mixte) (2026-05-12)

**User feedback** :
> *« Du coup quand je prendrais le mode découvert en mode photo, tu penses il se passera quoi ? [...] quel est la pédagogique d'apprentissage que le mode découvert avec options photo fera ? et il fera quoi avec option oral ? et option mixte ? »*

### Friction

Phase A.8 / A.8.1 ont laissé le `colle_format` ignoré en mode Découverte (radio masqué côté GUI, marker non injecté dans le prompt DECOUVERTE). Or les 3 formats ont une vraie valeur pédagogique distincte en Découverte aussi :

- **Oral** : révision sans matériel papier (transports, écran seul). Ancrage par répétition orale.
- **Photos** : papier + cahier disponibles. Ancrage par l'écrit fort, photos régulières de validation. C'est exactement la méthode improvisée par Gemini Pro 2.5 aux tours 23-27 de la session PSI TP_Shannon 2026-05-12 (dictée structurée + photo de cahier + OCR validation).
- **Mixte** : au cas par cas selon nature du contenu.

L'utilisateur a explicitement demandé de paramétrer Découverte selon ce flag pour avoir 3 postures pédagogiques distinctes.

### Livré

#### Prompt DECOUVERTE v1.1 → v1.2

- **§1.6ter, Format pédagogique paramétré** (`[FORMAT PÉDAGOGIQUE : oral|photos|mixte]`) :
  - `oral` : pas de photo demandée, ancrage par reformulation orale systématique (« redites avec vos mots »), analogies mémorables, **§1.6bis désactivé** (pas de dictée structurée au cahier).
  - `photos` : application complète de §1.6bis (dictée structurée titre+définition+exemple à recopier au cahier + photo + OCR validation). Méthode validée par observation rétro.
  - `mixte` (défaut) : décision au cas par cas par le tuteur, photo proposée sur les définitions/syntaxes/formules/exemples concrets, oral sur les explications conceptuelles et reformulations.
  - **Protocole OCR transparent** identique au mode Colle §1.6 v0.5 (`📸 Ce que je lis dans votre photo : ...` puis `Vérification : ...`) appliqué quel que soit le format dès qu'une photo arrive. Le tuteur compare sa lecture multimodale avec l'OCR Gemini Flash 2.5 pré-traité et signale toute divergence.
- **Règle absolue §4.11** « Pas de résistance aux bascules de format pédagogique » (clone §4.11 COMPAGNON). Acquittement d'un fragment + adaptation immédiate. Interdit explicite « êtes-vous sûr ? », etc.
- Marker bascule : `[FORMAT PÉDAGOGIQUE BASCULÉ → <fmt>]` (distinct du `[FORMAT BASCULÉ → ...]` du COMPAGNON, postures différentes).

#### Backend (app.py)

- `prompt_builder.build_initial_context_message` : en mode découverte, injecte `[FORMAT PÉDAGOGIQUE : <fmt>]` (au lieu de `[FORMAT COLLE : ...]` qui reste colle-only). Storage technique `session_state.data["colle_format"]` inchangé (rétrocompat).
- `_apply_colle_format_change` : lit `session_state.data["mode"]` et injecte le bon marker selon le mode (`[FORMAT BASCULÉ]` en colle, `[FORMAT PÉDAGOGIQUE BASCULÉ]` en découverte).
- **OCR Gemini Flash 2.5 étendu** : la condition `sess_mode == MODE_COLLE` devient `sess_mode in (MODE_COLLE, MODE_DECOUVERTE)`. En mode Découverte avec format `photos` ou `mixte`, l'OCR pré-traité est activé pour les photos du cahier : il sert au tuteur de double-check anti-hallucination sur ce que l'étudiant a recopié.

#### Frontend

- **GUI Tk** : `_refresh_colle_format_visibility` et `_refresh_corrige_anchor_visibility` étendues à `mode in ("colle", "découverte")`. Label « Format colle » renommé en « Format » (générique, marche pour les 2 modes, chacun a sa §1.6/§1.6ter paramétrée).
- **Web form** (index.html + app.js) : `_refreshColleFormatSelectVisibility` étendue à découverte. Tooltip du select actualisé pour expliquer les 2 sémantiques (colle = objets structurés, découverte = ancrage mnémonique).
- **Slash-commands** `/oral`, `/photos`, `/mixte` fonctionnent désormais en mode découverte aussi (gratuit grâce à la généricité de `_apply_colle_format_change` + au shared storage `colle_format`).

#### Tests

- `tests/test_decouverte_mode.py` (+6 cas) : marker `[FORMAT PÉDAGOGIQUE : ...]` injecté correctement par mode/format, distinction avec `[FORMAT COLLE : ...]`, fallback mixte sur valeur invalide, pas de marker en mode guidé.
- `tests/test_app_colle_format.py` (+5 cas) : `TestDecouvertePromptFormat` (§1.6ter présente, §4.11 anti-résistance, protocole OCR cloné) + `TestApiSlashFormatDecouverte` (marker `[FORMAT PÉDAGOGIQUE BASCULÉ]` en découverte, `[FORMAT BASCULÉ]` en colle).
- **454 tests OK** (était 443 avant A.8.2, +11).

### Pédagogiquement, ça donne quoi ?

Table comparative dans le README mise à jour. En résumé :

| | 🎙 Oral | 📸 Photos | 🔀 Mixte |
|---|---|---|---|
| **Cahier** | Jamais demandé | Systématique sur défs/formules | Au cas par cas |
| **Photos** | Jamais | Validation régulière | Sur passages clés |
| **OCR Flash 2.5** | Inactif | Actif | Actif si photo |
| **Reformulation orale** | Centrale | Optionnelle (l'écrit ancre) | Adaptée |
| **Mémoire visée** | Court terme + répétition | Long terme via cahier | Mixte |
| **Cas idéal** | Transport / écran seul | Boulot calme avec papier | Défaut adaptatif |

---

## Phase A.8.1 : Affinage Découverte (cas TP existant) + archive .md des séances (2026-05-12)

**User feedback** (après lecture de la suite de la session PSI TP_Shannon en mode colle, 27 tours) :
> *« Au tour 20 j'ai demandé "Et tu peux pas me faire la formation par rapport au TP shannon ? genre en même temps que je découvre python on part sur tp shannon ?". Le tuteur a fait un mode hybride micro-leçon→connexion-au-TP qui a très bien marché. Le mode Découverte devrait gérer ce cas. »*
>
> *« Aussi ajoute un truc pour enregistrer le chat dans un .md comme ça quand je supprimerai l'historique je pourrais revoir mes anciens trucs si j'ai décidé d'enregistrer et que ça me le met automatiquement dans un dossier de mon projet [...] un dossier avec des sous dossier par matière pour m'y retrouver »*

### Friction observée

Mode Découverte v1.0 émet **systématiquement** un PDF d'énoncé inventé en début de séance. Or 2 cas se présentent en pratique :

- **Cas A** : révision globale d'un chapitre sans TP cible (cas anticipé en Phase A.8). PDF inventé pertinent.
- **Cas B** : l'étudiant cible un TP/exercice précis qu'il **n'a pas les bases pour aborder**. Inventer un autre énoncé serait contre-productif (deux supports concurrents). Cas non géré par Phase A.8.

La session 2026-05-12 PSI TP_Shannon (27 tours) a montré que Gemini Pro 2.5 sait improviser ce mode hybride micro-leçon→connexion-au-TP, mais seulement après que l'étudiant l'a explicitement demandé (tour 20/27). C'est fragile : dépend de la lucidité de l'utilisateur.

Par ailleurs, le user n'a aucun moyen de garder une trace persistante d'une séance après suppression du JSON dans le panneau Historique. Pas d'archive lisible long-terme.

### Livré

#### 1. Affinage prompt Découverte v1.0 → v1.1

- `_prompts/PROMPT_SYSTEME_DECOUVERTE.md` v1.1 :
  - §1.6 raffinée : génération du PDF **conditionnelle** (Cas A vs Cas B).
  - §1.6bis nouveau : « TP existant comme matériau d'application », pédagogie **bottom-up** : extraire les prérequis du TP cible, faire des micro-leçons ancrées, **reconnecter immédiatement** au TP fonction par fonction. Mécanique d'ancrage par l'écrit décrite (titre + définition + exemple à recopier au cahier + photo de validation + OCR). Méthode validée 2026-05-12 par observation rétroactive.
  - Garde-fou : *« pas de scope creep, vous ne transformez pas la séance en cours Python complet. Uniquement les prérequis nécessaires aux fonctions du TP ciblé, dans l'ordre où elles arrivent. »*

#### 2. Marker `[MATÉRIEL APPLIQUÉ : ...]` dans le contexte initial

- `prompt_builder._describe_applied_material(ctx)` (nouveau) : décrit en 1 ligne le matériel d'application identifié dans le SessionContext (énoncé / script / slides présents). Retourne `""` si aucun → bascule cas A.
- `prompt_builder.build_initial_context_message` mode découverte : injecte le marker `[MATÉRIEL APPLIQUÉ : sujet TPShannon, matériaux disponibles : énoncé, script oral, slides]` après l'ANCRAGE quand applicable.
- Section INSTRUCTIONS adaptée : cas A → tuteur invité à émettre `<<<SAVE_INVENTED_PDF>>>`. Cas B → tuteur invité à **NE PAS** émettre, suivre la posture bottom-up §1.6bis, proposer l'ancrage par l'écrit si pertinent.

#### 3. Archive .md des séances en live

Toutes les séances sont automatiquement archivées dans `_archives/<MATIÈRE>/<session_id>.md` (sous-dossiers par matière pour s'y retrouver). Le .md est mis à jour atomiquement **après chaque tour** (student + claude), donc même un crash brutal préserve tout ce qui a été dit. Survit à la suppression du JSON dans le panneau Historique.

Contenu du .md :
- **Frontmatter YAML** : session_id, matière, type, num, exo, mode, engine, model, ancrage, colle_format, started_at, last_alive, interrupted.
- **Header lisible** : titre, date, mode, engine. Lien vers le PDF d'énoncé inventé si présent.
- **Conversation** role-balisée `## 🤖 Tuteur` / `## 👤 Étudiant` avec timestamps. Photos préservées en référence `![alt](path)` (pas dupliquées).
- **🎯 Points faibles** : captures live (par le tuteur) + audit rétro (Gemini Flash) si présent.
- **📋 Audit rétro (phase débrief)** : résumé + concepts + exos + suggestions, quand la phase débrief a été engagée.

Activé par **défaut** (opt-out via checkbox `📁 Archiver .md` dans la GUI Tk et le form web). Persisté dans `runtime_settings.last_selection.archive_to_md`. CLI : `--no-archive` pour désactiver.

#### 4. Livrables techniques

- `_scripts/archive_session_md.py` (nouveau) : `render_session_to_md(data)`, `write_session_archive(data, root)`, `archive_path_for(root, data)`, `safe_matiere_dirname(s)`. Atomic write `.tmp` + `os.replace`. Best-effort sur les exceptions (ne casse jamais le flux normal).
- `config.ARCHIVES_DIR = PROJECT_ROOT / "_archives"`.
- `app.py` : helper `_maybe_archive_md(st)`, hooké après chaque `append_exchange` (student + claude) + au `start_session` (création immédiate du .md).
- `gui.py` : checkbox `📁 Archiver .md`, BooleanVar `archive_to_md` (default True), trace_add auto-save, propagation `--no-archive` au lancement CLI.
- `compagnon.py` : flag `--no-archive`, propagation URL param `archive_to_md=0` quand désactivé.
- `index.html` : checkbox `📁 Archiver .md` (checked default).
- `app.js` : pré-remplissage de la checkbox depuis `?archive_to_md=0`, patch explicite côté FormData (les checkboxes décochées sont omises par défaut, on force le bool depuis le DOM).
- `runtime_settings.DEFAULT_LAST_SELECTION["archive_to_md"] = True`.
- `.gitignore` : `_archives/`.

#### 5. Tests

- `tests/test_archive_session_md.py` (15 cas) : safe_matiere_dirname, archive_path_for, render_session_to_md (frontmatter, transcript, WP, audit rétro, recap, PDF inventé), write_session_archive (atomic, idempotent, best-effort).
- `tests/test_decouverte_mode.py` (+3 cas) : cas B marker quand énoncé présent (posture bottom-up §1.6bis mentionnée), cas A default sans matériel (SAVE_INVENTED_PDF mentionné), cas B avec script_oral_path.
- **443 tests OK** (était 425 avant A.8.1, +18).

### Limites assumées

- **Photos en référence absolue/relative** : les photos `![alt](path)` du transcript pointent vers `pending_attachments/` (chemins relatifs à COURS_ROOT ou absolus). Si tu supprimes ce dossier source, les images se cassent dans le .md. Compromis assumé (pas de duplication d'images = .md léger).
- **Cas B avec ancrage `aucun`** : le tuteur a quand même le corrigé injecté (cf. §1.4) pour calibrer ses micro-leçons, mais il a interdiction de le citer directement. C'est une contrainte de prompt, dépendante de l'obéissance LLM.

---

## Phase A.8 : Mode Découverte + PDF d'énoncé inventé + bugfix Docs panneau (2026-05-12)

**User feedback** (suite immédiate de l'analyse de la session PSI TP Shannon, cf. ci-dessous v15.7.36.10) :
> *« Le mode guidé au final j'ai parfois envie d'apprendre sans lire un script faudrait que j'essaye et le bot m'accompagne au fur et à mesure donc peut-être créer un nouveau mode comme ça pour un début d'entrainement car franchement lire le script j'ai essayé mais c'est si passive puis y'a les questions autour du script de feynmann j'y comprends rien vu qu'il manque les bases donc faut un truc. J'pense faire le nouveau mode que tu vas inventer puis le mode script pour consolider puis le mode colle pour etre strict »*
>
> *« il doit prendre le temps d'écrire un pdf de l'énoncé (et que ce temps soit afficher dans le chat) puis ensuite c'est accessible dans les documents »*
>
> *« Pour le script je vois pas pourquoi il ne serait pas dispo dans les docs non plus en mode colle »*

### Friction observée

Session 2026-05-12 PSI `_revision_CC2/TP_Shannon` (engine Gemini Pro 2.5, mode colle, format photos, ancrage `aucun`) :

- 11 tours, 5 minutes seulement.
- L'étudiant déclare dès le tour 2 : *« je ne sais rien de Shannon, on le fait en quel langage ? »* et au tour 6 : *« je ne sais même pas de quoi ça parle »*.
- Au tour 4, signal UI : *« je ne vois pas l'énoncé dans les docs y'a rien qui s'affiche »* : pour `TP_Shannon`, seul `slides_TP_Shannon.pdf` existait sur disque mais n'était PAS exposé dans le panneau Docs (uniquement dans le panneau du mode guidé).
- Le tuteur en mode colle a ignoré les 3 signaux, a continué à enchaîner des questions. Score `0` capturé sur « Dictionnaire Python » (brique L1 de base).

**Diagnostic** : mismatch profond entre mode colle (qui présuppose un socle) et état réel de l'étudiant (parts de zéro). Le mode guidé suppose un script Feynman préparé, qui n'existe pas non plus en démarrage d'un sujet jamais suivi. **Une troisième posture manque** : tuteur explicateur qui prend l'étudiant à zéro.

### Livré

#### Nouveau mode `découverte`

Tuteur explicateur, zéro prérequis, pédagogie par cycles courts (exposition 2-5 phrases → question simple → validation/recadrage → exposition suivante). Max 2 concepts neufs par réplique, pas de barème d'indices (on donne l'explication directement si l'étudiant bloque), pas de capture de `<<<WEAK_POINT>>>` (trop précoce pour qualifier un blocage de « point faible »).

Progression idéale d'un cours nouveau : **Découverte** (acquisition) → **Guidé** (consolidation) → **Colle** (vérification stricte). Suggérée dans le récap de fin de séance Découverte.

- `_prompts/PROMPT_SYSTEME_DECOUVERTE.md` v1.0 (nouveau, ~400 lignes : 6 sections + exemples)
- `claude_client.MODE_DECOUVERTE = "découverte"` + `DECOUVERTE_ALLOWED_TOOLS = "Read,Grep,Glob"` (mêmes capacités FS qu'en guidé : le tuteur peut piocher dans les CM/polys au besoin)
- `compagnon.py --mode {colle,guidé,découverte}` + propagation URL
- `gui.py` : 3 radios mode avec emoji `🌱 Découverte` / `📖 Guidé` / `🎯 Colle`. Persistance `last_selection.mode` inchangée (string-typed, le merge garde n'importe quelle valeur)
- `index.html` : 3 options dans le select mode du form web

#### PDF d'énoncé inventé en début de séance

Le tuteur Découverte produit, dès son 2ᵉ ou 3ᵉ message, un PDF d'énoncé d'entraînement (2-4 exercices courts, progressifs en difficulté) via la balise :

```
<<<SAVE_INVENTED_PDF>>>{"title":"…","content_md":"…","source_label":"inspiré du corrigé officiel|sans corrigé"}<<<END>>>
```

Le système Python parse la balise, render le markdown en PDF (reportlab), sauve dans `_generated/<session_id>_enonce.pdf`, rasterise les PNGs, injecte en TÊTE du panneau Docs (`kind=enonce_invente`, label « Énoncé (généré par le tuteur) »). Un marker chat affiche le timing (`📄 Énoncé sauvegardé dans Docs en X.Ys`).

**Source du tuteur** : le corrigé officiel est **TOUJOURS injecté** dans le contexte du tuteur Découverte, même quand l'étudiant a choisi l'ancrage `aucun`. Justification : le tuteur en a besoin pour pondre un énoncé calibré sur le programme réel. **Le tuteur a interdiction stricte de le citer directement** à l'étudiant pendant le dialogue (cf. §1.4 du prompt) ; il s'en sert comme référence silencieuse. Le PDF généré annote sa source dans son pied de page (« inspiré du corrigé officiel » vs « sans corrigé »).

- `_scripts/dialogue/invented_pdf.py` (nouveau) : `render_invented_pdf(out_path, title, content_md, source_label, session_id=None)` : markdown → PDF reportlab via parser minimaliste (h1/h2/h3, listes bullets/numérotées, paragraphes, bold/italic/code inline). Atomic write `.tmp` + `os.replace`. Cap soft 50k chars.
- `_scripts/dialogue/parser.py` : nouvelle balise `<<<SAVE_INVENTED_PDF>>>`, état machine `INSIDE_SAVE_INVENTED_PDF`, validation light (title+content_md requis, source_label optionnel défaut « sans corrigé »).
- `_scripts/web/app.py` : event SSE `invented_pdf_ready` / `invented_pdf_error`. Endpoint `/api/generated_file?path=<rel>` qui sert les PNGs rasterisés sous `_generated/`. Endpoint `/api/generated/<filename>` pour le PDF lui-même. `_build_document_entry` adapté pour les PDFs hors COURS_ROOT.
- `_scripts/web/static/app.js` : listeners SSE `invented_pdf_ready` (marker chat + refresh `initCorrectionsPanel`) et `invented_pdf_error`.
- `_kindLabelFr` côté frontend : ajout des kinds `enonce_invente` (« Énoncé (généré) ») et `slides` (« Slides »).

#### Bugfix bonus : slides PDF visibles dans le panneau Docs (tous modes)

Régression historique : `find_perso_slides_pdf` n'était appelé que dans le panneau du mode guidé (via `/api/guided/init`), pas dans `/api/corrections/init`. Pour les types libres avec uniquement `slides_<theme>.pdf` mais pas `script_imprimable.pdf` (cas TP_Shannon), le panneau Docs restait vide alors qu'il y avait pourtant un PDF affichable. Fix : `find_perso_slides_pdf` appelé aussi dans `/api/corrections/init`, ajouté à la pré-rasterisation au boot.

#### Tests

- `tests/test_decouverte_mode.py` (nouveau, 11 cas) : câblage mode, prompt_builder (corrigé injecté en `aucun`, marker `[MODE : découverte]`, section INSTRUCTIONS spécifique, `SAVE_INVENTED_PDF` mentionné, anchor hint dans instructions), parser de la balise (happy path, source_label default, JSON invalide, chunked streaming, etc.)
- `tests/test_invented_pdf.py` (nouveau, 6 cas) : render PDF (taille, titre dans metadata, atomic write, escape HTML, contenu vide, source_label dans footer)
- `tests/test_app_docs_panel.py` (nouveau, 3 cas) : `/api/corrections/init` 409 sans session, énoncé inventé en tête de liste, slides exposées quand dispo
- **425 tests OK** (était 405 avant Phase A.8, +20)

### Limites assumées

- En mode Découverte + ancrage `aucun`, le tuteur **voit** le corrigé pour pondre le PDF mais s'engage à ne pas le citer. C'est une contrainte de prompt, donc dépendante de l'obéissance du LLM. Si une session révèle un cas où le tuteur cite le corrigé en clair en mode `aucun`, il faudra durcir le prompt (§1.4) ou ajouter un filtre post-stream.
- Le PDF généré est inscrit dans `_generated/` (gitignoré). Une seule génération par séance par défaut : re-générer = écrasement. Si l'utilisateur veut un historique, ça viendra en Phase B.
- Mode Découverte sans `<<<WEAK_POINT>>>` : l'audit rétro post-séance (Phase v15.7.31) ne sera pas alimenté côté capture live, seulement côté analyse Gemini Flash du transcript final. Compromis assumé : le mode Découverte est trop précoce pour qualifier un blocage de « point faible à revoir », c'est la posture « tu sais pas, c'est normal, voilà ».

---

## Phase A.7.2 v15.7.36.10 : Picker Docs filtré par thème pour types libres (2026-05-12)

**User feedback** :
> *« je vois annale dans documents (énoncé · corrigé · script) et je trouve ça incohérent que ce soit dans → 2026-05-11_PSI__revision_CC2Bit_information_exfull »*

### Friction

Pour une session par thème comme PSI `_revision_CC2/Bit_information`, le picker Docs affichait :
- ~~Annale Q&A : CC2 (N pages)~~ (couvre les 4 thèmes : Bit_info / RAID / TP_Shannon / USB)
- Script imprimable (N pages)

L'annale est globale (tous thèmes confondus) alors que la session est ciblée sur **Bit_information**. Incohérent visuellement.

### Fix

Dans `/api/corrections/init`, filtrage par thème pour types libres avec `num != "full"` :

```python
is_themed_free_type = (
    not _is_canonical_type(type_code)
    and num and num.lower() != "full"
)
theme_lower = num.lower() if is_themed_free_type else None

# Pour chaque correction_path :
if is_themed_free_type and theme_lower not in pdf_path.name.lower():
    continue  # skip : fichier global non-thématique
```

L'annale (nom de fichier `annale_synthese_CC2.pdf` ne contient pas `bit_information`) est **exclue du picker** pour ce thème. Mais elle **reste accessible au tuteur** via `correction_paths` du SessionContext (prompt initial section CORRIGÉ OFFICIEL). On filtre uniquement l'affichage frontend.

### Résultat pour PSI `_revision_CC2/Bit_information`

```
PICKER AVANT :                                       PICKER APRÈS :
- Annale Q&A : CC2 (24 pages)          (exclu)
- Script imprimable (N pages)          - Script imprimable (N pages)
```

### Comportement par mode

| Mode | Items du picker |
|---|---|
| `num=full` (révision globale) | Annale + Script imprimable + aide_memoire si présent (tous gardés) |
| `num=Bit_information` (thème) | Seulement les fichiers dont le nom contient « bit_information » (script imprimable du thème, exos_thème si présents) |
| TD/TP canoniques | Inchangé (énoncé + corrections par exo + script) |

### Cas de `exos_TP_Shannon.pdf` pour `num=TP_Shannon`

Le nom contient « tp_shannon » → gardé dans le picker. C'est le bon comportement : exos thématique reste visible pour son thème.

**399 tests OK** (inchangé).

---

## Phase A.7.2 v15.7.36.9 : Skip préfixe « Corrigé : » quand le label est auto-descriptif (2026-05-12)

**User feedback** :
> *« j'ai redémarré et pourtant je vois corrigé annale q&a dans → 2026-05-11_PSI__revision_CC2Bit_information_exfull »*

### Friction

Le picker du panneau Docs formatait `${kindLbl} : ${c.label} (${totalP} pages)`. Pour `annale_synthese_CC2.pdf` qui a maintenant le label « **Annale Q&A : CC2** » (v15.7.36.8), ça donnait :

```
Corrigé : Annale Q&A : CC2 (N pages)
```

Doublon de descripteur. L'user voit « corrigé » devant alors que le label dit déjà ce qu'est le fichier.

### Fix

Regex `_SELF_DESC_RE = /^(Annale|Aide-mémoire|Exos|Toutes|Script)\b/i` détecte les labels qui commencent déjà par un descripteur explicite. Si match → skip le préfixe `${kindLbl} : `, format devient :

```
Annale Q&A : CC2 (N pages)              (au lieu de « Corrigé : Annale Q&A : CC2 (N pages) »)
Aide-mémoire : CC2 (imprimable A4) (N pages)
Exos : TP_Shannon (N pages)
Toutes les corrections (N pages)
Script imprimable (N pages)
```

Pour les cas canoniques où le label seul ne suffit pas (« Exercice 3 »), le préfixe est conservé :

```
Corrigé : Exercice 3 (N pages)          (inchangé, canonique TD/TP)
Énoncé : TD5 énoncé (N pages)           (inchangé)
```

**399 tests OK** (fix purement frontend display).

---

## Phase A.7.2 v15.7.36.8 : Labels Docs corrects pour annale/aide-mémoire/exos (2026-05-12)

**User feedback** :
> *« Le visionnage du script est bien correct. Cependant dans les docs y'a "corrigé globale" et ça fait un peu bizarre non ? »*

### Friction

Le panneau Docs (sidebar) du Compagnon utilise `_label_for_correction_pdf` pour générer un libellé lisible. Pour PSI `_revision_CC2/annale_synthese_CC2.pdf`, l'ancien regex `_(CC\d+)` capturait le match `CC2` → label « **CC2 : corrigé global** ». Or ce fichier est une **annale Q&A** (questions + corrections), pas un corrigé d'exercice classique. Libellé trompeur.

### Fix

Patterns spécifiques ajoutés dans `_label_for_correction_pdf` **avant** les regex génériques :

| Pattern fichier | Ancien label | Nouveau label |
|---|---|---|
| `annale_synthese_CC{N}.{pdf,md}` | « CC{N} : corrigé global » | **« Annale Q&A : CC{N} »** |
| `aide_memoire_CC{N}.{pdf,md}` | « CC{N} : corrigé global » | **« Aide-mémoire : CC{N} »** |
| `aide_memoire_CC{N}_a4_recopie.pdf` | « CC{N} : corrigé global » | **« Aide-mémoire : CC{N} (imprimable A4) »** |
| `exos_{theme}.{pdf,md}` | stem brut | **« Exos : {theme} »** |
| `correction_TD5_AN1_ex3.pdf` *(canonique)* | « Exercice 3 » | *inchangé* |
| `concat_TD5_AN1.pdf` *(canonique)* | « Toutes les corrections » | *inchangé* |
| `correction_CC2_2024-25_AN1.pdf` *(canonique)* | « CC2 : corrigé global » | *inchangé* |

Les types libres `_revision_CC*` ont maintenant un libellé qui reflète le **vrai contenu** du fichier dans le picker Docs. Plus de « corrigé global » trompeur sur un Q&A.

Bonus : fix d'un `SyntaxWarning: invalid escape sequence '\d'` dans le docstring (échappement `\\d` dans le block r-doc).

**399 tests OK** (inchangé : fix purement cosmétique sur le label).

### Smoke-test

```
annale_synthese_CC2.pdf       → 'Annale Q&A : CC2'              ✓
aide_memoire_CC2.pdf          → 'Aide-mémoire : CC2'            ✓
aide_memoire_CC2_a4_recopie.pdf → 'Aide-mémoire : CC2 (imprimable A4)' ✓
exos_TP_Shannon.pdf           → 'Exos : TP_Shannon'             ✓
correction_TD5_AN1_ex3.pdf    → 'Exercice 3'                    ✓ (régression OK)
concat_TD5_AN1.pdf            → 'Toutes les corrections'        ✓ (régression OK)
correction_CC2_2024-25_AN1.pdf → 'CC2 : corrigé global'         ✓ (régression OK)
```

---

## Phase A.7.2 v15.7.36.7 : Fix CSS bouton ✎ Modifier + détection SCRIPT_*.md Feynman dans `_revision_CC*/scripts/` (2026-05-12)

**User feedback** :
> *« le design de "✎ Modifier (parcourir manuellement)" est moche il est basique par rapport à tout le reste on dirait qu'il n'a pas de css corrige ça »*
>
> *« et y'a beau eu avoir un correctif compagnon continue d'envoyer ce message "🎯 Mode guidé : lancement avec script script_oral_Bit_information.txt et slides slides_Bit_information.pdf" + "ℹ Mode guidé (lite) : Le script source script_oral_Bit_information.txt n'a pas de headers ## [SLIDE N] Feynman" »*

### Fixes

**1. CSS `.gfb-ai-modify`** : oublié au commit v15.7.36.4 (panneau IA result simplifié). Style ajouté : teinte warning orange (matchant les `partial-btn`), padding/border-radius cohérents avec les autres `.gfb-ai-*`, hover state. La regex CSS `.gfb-ai-accept, .gfb-ai-refresh, .gfb-ai-browse-fallback` étendue à `.gfb-ai-modify`.

**2. Mode lite résiduel sur PSI `_revision_CC2/Bit_information`** :

Cause : après la régénération du SCRIPT.md Feynman (v15.7.36.5 → audit + agent), le fichier `SCRIPT_Bit_information.md` existe dans `PSI/_revision_CC2/scripts/`, mais :

- **`find_perso_script_md`** (cours_resolver) ne scannait que `{folder}/scripts_oraux/` via `_candidate_exercise_folders`. Pour un type libre, `_candidate_exercise_folders` ne renvoie rien → SCRIPT.md jamais trouvé → `/api/guided/init` retombe sur `find_perso_script_md` qui retourne None → fallback path.
- **`_resolve_themed_files_direct`** (matching par thème de `/api/scan_with_ai`) cherchait `script_oral_*.{txt,md}` mais pas `SCRIPT_*.md`. Quand l'user laissait l'auto-IA proposer, c'était toujours le `.txt` qui sortait → ▶ Lancer → backend prend le `.txt` → `parse_script` 0 slides → bascule en lite.

Fixes :

- **`find_perso_script_md`** étendu : pour les types libres (`_get_free_type_dir(...) is not None`), scan direct `{free_dir}/scripts/` (et `scripts_oraux/`) pour `SCRIPT_{theme}.md` avec matching exact par thème (casse insensible). Le `num` de session sert de `theme`. Validation case-sensitive `name.startswith("SCRIPT_")` selon §3 de COURS/CLAUDE.md (uppercase strict).
- **`_resolve_themed_files_direct`** : priorité 1 = `SCRIPT_{theme}.md` Feynman, priorité 2 (fallback) = `script_oral_{theme}.{txt,md}`. Avec garde `name.startswith("SCRIPT_")` pour éviter les faux positifs sur `script_oral_*.md` qui matcherait aussi le préfixe générique `script_`.

### Résultat smoke-test (PSI `_revision_CC2/Bit_information`)

```
SCRIPT.md trouvé : PSI/_revision_CC2/scripts/SCRIPT_Bit_information.md  ← Feynman v2
Slides PDF      : PSI/_revision_CC2/scripts/slides_Bit_information.pdf
```

Au prochain restart, le mode guidé canonique trouve le SCRIPT.md, `parse_script` retourne 13 slides, **plus de bascule en mode lite**. Vraie navigation slide-par-slide avec découpage oral structuré.

**399 tests OK** (inchangé).

### Pour les 3 autres orphelins (RAID, TP_Shannon, USB)

Même protocole à appliquer : régénérer le `SCRIPT_{theme}.md` Feynman via le bouton « 📝 Régénérer via Claude Code » du Compagnon. Une fois fait, `find_perso_script_md` les trouvera automatiquement (le scan v15.7.36.7 est générique).

---

## Phase A.7.2 v15.7.36.6 : Nettoyage GUI Tk : retrait Hotkey / Bypass quota / Sessions reprenables (2026-05-12)

**User feedback** :
> *« supprime le bypass quota check (vu que depuis y'a un seuils pour les quota) et le lister les sessions reprenables je pense qu'il sert à rien, le hotkey clavier y'a pas besoin d'un bouton pour ça ça peut être paramétrable depuis le web en activant ou désactivant l'option via un toggle ou que sais-je d'autres »*

### Friction

3 checkboxes dans le LabelFrame Lancer encombraient l'UI sans valeur ajoutée :
- **⌨ Hotkey clavier global Espace** : déjà marqué « legacy » dans le label, le bouton 🎤 navigateur fait le job depuis v15.6.2 (re-click pour annuler + WebSpeech preview).
- **⏭️ Bypass quota check** : les seuils Quota éditables du panneau (Session 5h et Hebdo 7j) font le job (mettre les 2 à 100 % = jamais de refus).
- **↩ Lister les sessions reprenables** : la sidebar Historique du front affiche déjà les sessions reprenables avec clic = reprise direct.

### Livré

**`gui.py`** :
- Les 3 `ttk.Checkbutton` retirés du form Lancer. Seul le checkbox **🎲 Le tuteur invente ses propres questions** est conservé (utile et récent).
- Les `BooleanVar` `self.enable_audio` / `self.skip_quota` restent en mémoire (toujours `False`) pour compat avec `update_last_selection` qui les accepte en kwargs : leur valeur n'est plus modifiable depuis l'UI. `self.resume_mode` reste aussi (jamais touché sans son checkbox).
- Les flags `--enable-audio` / `--skip-quota-check` / `--resume` retirés de la construction de `args` dans `_launch`. La commande spawn est donc plus courte et propre.
- Suppression des 3 vars de l'auto-save trace_add (elles ne changent plus → pas besoin de re-persister à chaque trace).

**Flags CLI conservés pour les users avancés**. `python compagnon.py PSI _revision_CC2 Bit_information full --enable-audio` reste valide pour ceux qui veulent le hotkey global. C'est juste plus exposé dans la GUI Tk standard.

### Tests

**399 tests OK** (inchangé : pas de logique testable nouvelle, juste suppression d'éléments UI).

---

## Phase A.7.2 v15.7.36.5 : Bouton Lancer débloqué sans énoncé + mode « tuteur invente » (2026-05-12)

**User feedback** :
> *« Pourquoi dans PSI bit information en mode guidé, parce qu'il n'y a pas de pdf d'énoncé eh bien le mode ne peut pas se lancer (le bouton lancer est grisé) alors que c'est juste de la lecture de texte c'est pour apprendre le cm à ma manière et pas faire des exercices. Encore ce serait en mode colle ça se comprendrait quoi que non on peut demander à l'ia d'inventer ces questions »*
>
> Puis : *« ben du coup si y'a pas d'énoncé peu importe le mode faut s'adapter et même on peut aussi faire un mode sans énoncé même si y'a énoncé ça peut être sympathique »*

### Friction observée

Depuis v15.7.36.3 (fix faux énoncé pour types libres), `find_enonce_pdf` retournait `None` pour PSI `_revision_CC2/`. La gate `_refresh_avail_buttons` du GUI Tk exigeait pourtant un énoncé pour activer le bouton Lancer (sauf pour CM qui acceptait script OU slides) → bouton **grisé pour de la révision globale** où il n'y a pas d'énoncé strict, alors que tout le matériel (script + slides + annale + poly) est présent.

De plus, l'user voudrait pouvoir **explicitement** demander au tuteur d'inventer ses propres questions même quand un énoncé existe (mode révision libre / exploration), pour sortir du cadre exercice prédéfini.

### Livré

**1. Bouton Lancer adapté aux types libres** (`_refresh_avail_buttons` dans `gui.py`)

Critère de lancement par type :
- **TD/TP/CC canoniques** : énoncé PDF requis (inchangé)
- **CM** : script OU slides (inchangé)
- **Types libres (`_revision_CC*`, etc.)** (Phase v15.7.36.5) : lance si **au moins UN matériau pédagogique** existe parmi `enonce` / `annale (free_corrections)` / `poly (free_poly)` / `script` / `slides`. Pas d'énoncé strict requis. Hint d'erreur clair si vraiment tout est vide.

Le radio « Guidé » est également activé pour types libres dès qu'il y a slides OU script (le mode lite v15.7.36 sait gérer le cas).

**2. Toggle « 🎲 Le tuteur invente ses propres questions »**

Nouveau paramètre **`ignore_enonce: bool`** :
- **GUI Tk** : checkbox sous « Bypass quota check » dans le LabelFrame Lancer, label « 🎲 Le tuteur invente ses propres questions (ignore l'énoncé si présent) ». Persisté via `runtime_settings.last_selection.ignore_enonce` (auto-save sur trace_add comme les autres champs).
- **Web form** : checkbox `name="ignore_enonce"` avec label « 🎲 Sans énoncé » entre le select corrige_anchor et le bouton 🔄 Rescan. Style `.start-form-toggle` compact inline. Lu depuis URL param `?ignore_enonce=1` au boot.
- **CLI `compagnon.py`** : flag `--ignore-enonce`. Propagé en URL `?ignore_enonce=1`.
- **GUI Tk** : ajoute `--ignore-enonce` aux args spawn si coché.

**3. Backend `_build_session_context`** force `enonce=None` quand `body.get("ignore_enonce")` truthy (analogue à `corrige_anchor=aucun` qui skip le corrigé). Si type canonique TD/TP/CC + ignore_enonce, **plus de FileNotFoundError** : l'user a explicitement demandé.

**4. `prompt_builder` injecte une section dédiée** dans INSTRUCTIONS quand `ctx.enonce_path is None`, peu importe le type :

```
**Mode révision sans énoncé** : il n'y a pas d'énoncé d'exercice
précis pour cette séance (sujet : « Bit_information », matière : PSI).
L'étudiant veut réviser le contenu d'un thème, pas résoudre un
exercice donné. À toi de prendre l'initiative :

- En mode colle : annonce-toi à l'étudiant en 1 phrase, préviens-le
  que tu vas créer ta propre série de questions depuis les matériaux
  disponibles (CORRIGÉ OFFICIEL, POLY DU PROF, SCRIPT ORAL PERSO,
  SLIDES). Demande-lui s'il préfère un parcours dans l'ordre, ou s'il
  cible un point précis. Puis enchaîne en posture colle (§2.2).
- En mode guidé : accompagne la lecture du script oral / slides.
  Demande à l'étudiant où il veut commencer.

Ressources disponibles : matériaux dans les sections ci-dessus. Tu
n'as PAS besoin d'énoncé externe, l'annale + le poly te donnent
assez de matière pour 1 h+.
```

Le tuteur sait alors qu'il doit prendre l'initiative et **prévenir l'étudiant** qu'il va créer son propre programme (ce que l'user demandait : *« prendre un peu de temps pour se lancer (il prévient dans la nav) pour qu'il créer lui même une série d'énoncé »*).

### Workflow utilisateur

**Cas 1 : Pas d'énoncé sur disque (PSI `_revision_CC2/`)** :
- Bouton Lancer activé automatiquement.
- `ignore_enonce` checkbox optionnel (sans effet ici car déjà pas d'énoncé).
- Prompt initial inclut la note « Mode révision sans énoncé » → tuteur invente.

**Cas 2 : Énoncé présent mais user veut une révision libre** :
- User coche « 🎲 Le tuteur invente ses propres questions ».
- Backend force `enonce_path=None` malgré le fichier sur disque.
- Prompt initial inclut la note « Mode révision sans énoncé ».
- Le tuteur invente, ignore l'énoncé.

**Cas 3 : Énoncé présent, comportement classique** :
- Checkbox décochée (défaut).
- Énoncé injecté dans le prompt comme avant.
- Pas de note « Mode révision sans énoncé ».

### Tests

Smoke-test manuel : `_revision_CC2/Bit_information` → bouton Lancer activé, mode guidé activable, prompt contient bien « Mode révision sans énoncé » avec sujet `Bit_information`. **399 tests OK** (inchangé : fix purement structurel + ajout config, pas de logique testable nouvelle).

---

## Phase A.7.2 v15.7.36.4 : UX modal simplifiée + matching direct par thème + fixes (2026-05-11/12)

**User feedback** (suite v15.7.36.3) :
1. *« je trouve que le 📂 Mode guidé : matériau introuvable n'est pas assez ergonomique surtout quand je fais un mode cherche avec IA et que ça ne me propose pas le bon fichier… simplifie la logique »*
2. *« et que la recherche soit mieux c'est pas normal en si peu de fichier ça me propose ça 📝 Script : ...script_oral_Bit_information.txt 🖼 Slides : ...slides_TP_Shannon.pdf alors que c'est évident que c'est slide bit d'information qu'il faut prendre »*
3. *« je crois que c'est encore bugué malgré avoir stop + relance »*
4. *« du coup après avoir enfin réussi à choisir ça me fait ça [lite notice]… c'est moche faut rendre ça plus beau y'a trop d'espace »*
5. *« quand je clique sur régénérer proprement via claude code ça me fait Erreur : 500 en début de message »*

### Fixes

**1. Matching direct par thème** (priorité #1)

`/api/scan_with_ai` accepte désormais un param `theme` (string). Si fourni, helper `_resolve_themed_files_direct(folder, theme)` cherche **directement** par suffix dans `folder/scripts/` (ou `folder/scripts_oraux/`) :
- `script_oral_{theme}.{txt,md}`
- `slides_{theme}.pdf`
- `script_imprimable_{theme}.pdf`

Si **≥2 fichiers** trouvés par matching de suffix exact (insensible casse), bypass complet de Gemini Flash, retourne avec `confidence_0_100: 100`, `method: "direct_suffix_match"`, reasoning explicite. **Aucun appel LLM, aucune hallucination de thème possible.**

Côté frontend, `gfbRunAiScan` récupère `num` de la session active via `/api/current_session` et le passe en `theme`. Avant le scan, message UI : « 🎯 Recherche directe par thème `Bit_information`… » (vs « 🤖 Gemini Flash scanne… » pour fallback).

**Plus jamais de proposition incohérente type « script_oral_Bit_information.txt + slides_TP_Shannon.pdf »** quand le `num` de session est défini.

**2. UX modal simplifiée** (priorité #2)

- **Auto-lancement du scan IA** à l'ouverture de la modal de fallback. Avant : l'user devait cliquer « 🤖 Chercher avec IA » d'abord. Maintenant : la modal s'ouvre déjà avec un spinner « 🎯 Recherche en cours… ». Si match direct trouvé (~50 ms) → affichage instantané du résultat avec bouton ▶ Lancer.
- **Panneau résultat compacté** quand `method === "direct_suffix_match"` : header « ✅ Trouvé directement par thème » + 2 boutons (▶ Lancer / ✎ Modifier) au lieu de 6+ boutons. Pas de partial actions (inutiles puisque le matching direct est trivialement correct).
- Pour Gemini Flash en fallback : panneau complet conservé (confidence badge, partial actions).
- **Boutons « 🔍 Parcourir » / « ↩ Repli colle » toujours disponibles** dans le panneau actions principales (auto-masqué quand le scan auto démarre).

**3. Bug 500 sur clic « 📝 Régénérer proprement via Claude Code »**

Cause : `_build_prompt_regen_script_md` recevait `script_oral_rel: None` (si `context_files.script_oral` était None côté session) → `None.split("/")` levait `AttributeError` → wrapper try/except → 500. L'user voyait « Erreur : 500 » dans la textarea de la modal. Fix : coerce `None → ""` au début du helper.

**4. CSS `.guided-lite-notice` compacté**

Avant : `display: block` avec marges verticales 8px, role/body/actions en colonnes empilées → 3 lignes minimum + espacements vides → moche.

Après : `display: flex; align-items: flex-start; gap: 10px; flex-wrap: wrap` → role + body + bouton CC sur une ligne quand l'espace le permet, wrap propre sinon. `font-size: 11px`, paddings réduits, `code` mono inline. Compact, dense, lisible.

### Workflow utilisateur après fixes

1. PSI `_revision_CC2/Bit_information` en mode guidé → `/api/guided/init` 404 `guided_fallback_required:true`.
2. Modal s'ouvre → spinner « 🎯 Recherche directe par thème `Bit_information`… » (< 100 ms).
3. Match direct trouvé via `_resolve_themed_files_direct` :
   - script = `scripts/script_oral_Bit_information.txt`
   - slides = `scripts/slides_Bit_information.pdf`
   - imprimable = `scripts/script_imprimable_Bit_information.pdf`
4. Affichage compact : « ✅ Trouvé directement par thème, confiance 100 » + ▶ Lancer / ✎ Modifier.
5. ▶ Lancer → ferme modal, init mode guidé.
6. `parse_script(script_oral_Bit_information.txt)` retourne 0 slides → bascule en **mode lite** avec une bulle compacte teintée orange : « ℹ Mode lite : *Le script source `script_oral_Bit_information.txt` n'a pas de headers SLIDE N. 1 page PDF = 1 slide synthétique.* [📝 Régénérer via Claude Code] ».
7. Clic « 📝 Régénérer » → modal CC avec radio kind + prompt aligné COURS/CLAUDE.md, bouton 📋 Copier.

### Tests

Pas de nouveau test dans cette passe (fixes ciblés UX/CSS/coerce). **399 tests OK** (inchangé).

### Audit cross-matière PSI (livré séparément, 2026-05-12)

Suite à *« Bref après fais ça [prompt audit_matiere_cc] »* : audit complet de PSI/ exécuté **par moi-même** (Compagnon a juste fourni le prompt, j'agis ici en Claude Code). Rapport sauvé dans `COURS/_audit/sessions/2026-05-12_audit_PSI_scripts.md` selon §6 RÈGLE LOGGING. Voir ce fichier pour la liste des orphelins, divergences SCRIPT/PDF, et recommandations.

---

## Phase A.7.2 v15.7.36.3 : Hotfix : boucle modal fallback + faux énoncé pour types libres (2026-05-11)

**User feedback** (suite v15.7.36.2) :
1. *« j'ai beau sélectionné le script et slide eh bien le message "mode guidé : matériau introuvable" après validation réapparait »* : boucle infinie de la modal de fallback même après que l'user ait pointé les bons fichiers.
2. *« faut aussi corriger les incohérences de la doc car ça affiche n'importe quoi »* puis *« genre y'a pas d'énoncé par exemple pour ce cas précis mais ça force à avoir un énoncé »*.

### Bug 1 : Boucle modal après validation

**Cause** : le wrapper try/except global de `/api/guided/init` (ajouté en v15.7.36.1 pour éviter le 500 HTML) retournait `guided_fallback_required: true` sur **toute** exception. Si `_build_guided_init_lite_response` plantait en interne (par ex `rasterize_if_needed` lève), le frontend recevait le flag et ré-ouvrait la modal alors que l'user venait juste de valider ses choix → boucle infinie sans le savoir.

**Fix** : retirer `guided_fallback_required: true` du payload d'exception générique. Le wrapper retourne juste `{error, detail}` 500. Le frontend voit alors juste une erreur normale (« Mode guidé indisponible : … ») sans re-déclencher la modal.

### Bug 2 : Faux énoncé pour types libres

**Cause** : depuis v15.7.33, `find_enonce_pdf` retournait `annale_synthese_CC2.pdf` comme énoncé pour les types libres. Mais l'annale est un Q&A (questions + corrections), pas un énoncé d'exercice séparé. Pour un dossier comme PSI `_revision_CC2/` qui est de la **révision globale** sans fichier d'énoncé strict, ça créait :
- Une fausse section « ÉNONCÉ DE L'EXERCICE » dans le prompt initial du tuteur (contenant l'annale Q&A)
- Une fausse section « CORRIGÉ OFFICIEL » avec le même PDF (doublon)
- Un doublon « Énoncé » + « Corrigé » dans le picker Docs frontend

Le user a noté *« genre y'a pas d'énoncé par exemple pour ce cas précis mais ça force à avoir un énoncé »* : `_build_session_context` raise `FileNotFoundError` si pas d'énoncé pour type non-CM, ce qui forçait à étiqueter l'annale comme énoncé pour éviter le crash.

**Fix** :
- `cours_resolver.find_enonce_pdf` pour type libre : retourne `exos_{theme}.{pdf,md}` si **et seulement si** un fichier `exos_*` existe (cas PSI `exos_TP_Shannon.pdf` pour le thème TP_Shannon). Sinon retourne `None`. **Fallback `annale_synthese` retiré.**
- `app.py._build_session_context` : tolère `enonce=None` pour types libres (`not _is_canonical_type(type_code)`), sans raise. Le tuteur s'appuie alors sur `cm_poly_path = aide_memoire` + `correction_paths = [annale_synthese]` pour avoir tout le matériel.
- `app.py./api/corrections/init` : dédup des paths exposés (`_seen_paths` set). Si annale apparaît dans corrections, plus jamais affichée 2 fois dans le picker Docs.

### Résultat pour PSI `_revision_CC2/Bit_information`

```
ENONCE  : None                              ← plus de faux énoncé
CORRIGES: annale_synthese_CC2.pdf           ← seul item Q&A
POLY    : aide_memoire_CC2.pdf              ← cheat sheet (référence)
SCRIPT  : scripts/script_oral_Bit_information.txt
IMPRIM  : scripts/script_imprimable_Bit_information.pdf
SLIDES  : scripts/slides_Bit_information.pdf
```

Le tuteur reçoit dans le prompt initial :
- **Pas de section ÉNONCÉ** (cohérent avec « pas d'énoncé pour de la révision globale »)
- Section CORRIGÉ OFFICIEL = annale Q&A
- Section POLY DU PROF = aide_memoire (matériau de référence)
- SCRIPT ORAL PERSO = script_oral_*.txt (matériau récité)
- SLIDES PERSO mention

Le picker Docs frontend affiche : « Corrigé : annale_synthese_CC2.pdf », « Script imprimable : … », pas de doublon Énoncé/Corrigé.

### Tests

`test_cours_resolver.py` mis à jour (4 cas adaptés à la nouvelle sémantique) :
- `find_enonce_returns_none_for_free_type_full` (au lieu de `returns_annale_synthese`)
- `find_enonce_none_for_free_type_md_only` (au lieu de `falls_back_to_md`)
- `find_enonce_themed_returns_exos_when_available` (cas heureux avec exos_{theme})
- **Nouveau** `find_enonce_themed_returns_none_when_no_exos` (cas thème sans exos)
- `test_case_insensitive_match` reformulé pour passer par resolve_corrections (puisque find_enonce retourne None)

**399 tests OK** (était 398, +1 net).

### Limites assumées

- Si un futur dossier libre a **vraiment** un fichier d'énoncé (`enonce_*.pdf` au top), il sera détecté via `_FREE_ENONCE_HINTS` actuellement réduit à `("annale_synthese", "enonce", "exos", "sujet")`. **MAIS le nouveau code retourne explicitement `None` pour le cas `full` et n'utilise le hint `exos` qu'en mode thème**. Si tu veux un énoncé strict pour un type libre `full`, il faudra étendre `find_enonce_pdf` pour rechercher `enonce_*` aussi en mode full. Pas ajouté car non observé.

---

## Phase A.7.2 v15.7.36.2 : Hotfixes : 500 sur PDF-comme-script + autostart depuis GUI (2026-05-11)

**User feedback** (suite v15.7.36) :
1. *« Mode guidé : endpoint /api/guided/init absent (HTTP 500). Redémarre le backend... »* alors que le backend était bien redémarré et à jour. Le scan IA avait classé `script_imprimable_Bit_information.pdf` comme **script** (au lieu de `script_oral_Bit_information.txt`) et `script_oral_Bit_information.txt` comme **slides**. `parse_script` essayait alors de `read_text()` sur le `.pdf` binaire → `UnicodeDecodeError` → 500 HTML → le content-type check côté JS affichait le faux message « endpoint absent ».
2. *« et aussi tu dois rajouter un truc pour parcourir uniquement slide ou uniquement script si après la recherche IA y'a que 1/2 de bons »*
3. *« Aussi dans le GUI quand j'appuie sur lancer que ça lance directement et que je n'ai pas à rappuyer sur lancer depuis le nav »*

### Fixes

**1. Validation d'extensions sur /api/guided/init** (`v15.7.36.1`)
- Si `script_path` n'est pas `.md` ou `.txt` → 400 propre avec `guided_fallback_required: true` (modal re-ouvre).
- Si `slides_path` n'est pas `.pdf` → 400 propre.
- **Auto-swap** si `script_path=.pdf` ET `slides_path=.txt|.md` → swap des paths (cas Gemini a inversé).
- **Try/except global** dans `api_guided_init` qui catch les exceptions inattendues et retourne du JSON (au lieu du 500 HTML qui faisait croire au front que l'endpoint n'existait pas).

**2. Renforcement du prompt Gemini Flash** (`v15.7.36.1`)
- Spécification stricte des extensions attendues par champ (`.md`/`.txt` pour script, `.pdf` pour slides).
- Exclusion explicite de `script_imprimable_*.pdf` et `aide_memoire_*.pdf` comme candidats slides (ce sont des imprimables N&B, pas du Beamer).
- Auto-swap côté `_scan_with_ai_internal` si Gemini répond avec inversion + cap confidence à 60 + ajout `[auto-swap]` dans reasoning.
- Validation finale : si après swap les extensions sont encore invalides, cap confidence à 30 + warning dans reasoning.

**3. Boutons « parcourir uniquement X » dans le panneau IA result** (`v15.7.36.1`)
- Quand 1/2 fichier IA est juste, l'user peut :
  - `✓ Garder slides + 🔍 re-parcourir script` (valide les slides IA, ouvre le picker en mode "script")
  - `✓ Garder script + 🔍 re-parcourir slides` (valide le script IA, ouvre le picker en mode "slides")
  - `🔍 Tout re-parcourir manuellement` (reset complet, mode "script" en premier)
- Avant : seul ✓ Utiliser ou 🔍 Tout reparcourir → forçait à reclasser le bon fichier aussi.

**4. Pré-remplissage modal selon `missing_only`** (`v15.7.36.1`)
- `/api/guided/init` renvoie maintenant `missing_only: "script" | "slides"` dans le payload `guided_fallback_required` quand un seul des deux fichiers manque (avec `script_path` du fichier déjà résolu dans l'autre cas).
- `openGuidedFallbackModal` pré-remplit le state avec le fichier déjà OK et ouvre le picker direct sur le mode "script" ou "slides" manquant. L'user parcourt uniquement le manquant.

**5. Autostart depuis GUI Tk** (`v15.7.36.2`)
- `compagnon.py` argparse `--autostart` + propagation `params["autostart"] = "1"` dans `_build_url`.
- `gui.py._launch` ajoute `--autostart` à la commande spawn.
- `gui.py._open_browser` (bouton « 🗂 Ouvrir l'UI navigateur ») reste inchangé → ouvre `http://127.0.0.1:5680/` sans params → comportement normal (user doit cliquer Lancer dans le form).
- Frontend (`app.js`) : `params.get("autostart") === "1"` → submit automatique du form après 350 ms (pour laisser les cascades se remplir). `history.replaceState` retire le param de l'URL pour qu'un F5 ne re-déclenche pas l'autostart.

### Tests

`test_app_guided_fallback.py` étendu de 4 cas (total 25) :
- `script_path=.pdf + slides_path=.pdf` → 400 propre
- `script_path=.md + slides_path=.txt` → 400 propre
- `script_path=.pdf + slides_path=.txt` → auto-swap (pas de 500)
- Exception inattendue dans `find_perso_script_md` → wrapper catch → 500 JSON (pas 500 HTML)

**398 tests OK** (était 394, +4).

### Workflow utilisateur amélioré

1. Click Lancer dans la GUI Tk → spawn `compagnon.py --autostart ...` → ouvre `http://127.0.0.1:5680/?matiere=PSI&type=_revision_CC2&num=Bit_information&exo=full&mode=guidé&autostart=1`.
2. Front pré-remplit les selects (cascades), retire `autostart` de l'URL via `history.replaceState`, attend 350 ms, submit le form automatiquement. La session démarre sans clic supplémentaire.
3. F5 dans le navigateur : URL nettoyée n'a plus `autostart=1` → restore via `/api/current_session` (chemin normal). Pas de double-submit.
4. Si le mode guidé tombe sur un mismatch d'extension après scan IA (Gemini a inversé `.pdf`/`.txt`) → auto-swap silencieux côté backend, le mode lite ou la modal s'ouvre selon le cas.
5. Si le user clique sur « 🔍 Ouvrir l'UI navigateur » de la GUI Tk (bouton secondaire) → comportement original conservé (form vide, user remplit + clique Lancer côté web).

### Limites assumées

- **Autostart au F5** : retiré de l'URL côté front. Si l'user veut re-déclencher un autostart, il doit ré-lancer depuis la GUI Tk. Acceptable.
- **Auto-swap silencieux** : pas de notification visuelle à l'user que le swap a eu lieu. Le `reasoning` mentionne `[auto-swap]` dans la modal IA. Si l'user n'ouvre pas la modal, il ne le saura pas, mais le résultat est correct alors c'est OK.

---

## Phase A.7.2 v15.7.36 : Mode guidé « lite » + prompt Claude Code (2026-05-11)

**User feedback** (suite v15.7.35) :
> *« Mode guidé indisponible : SCRIPT.md sans headers [SLIDE N]. Repli en mode lecture libre. tu peux corriger en live le script/slide et les régénérer en live puis les repush sur discord (tu purges les anciens) et vérifies pour tous les modules de psi en passant s'il y a pas d'autres incohérences (sinon faut que compagnon propose un prompt à dire pour claude code je sais pas si c mieux) »* puis *« le prompt doit etre basé de ce qui y'a dans claude.md hein attention à ne pas dire n'importe quoi. Lis d'abord le claude.md et il peut y avoir d'autres cas où il est bon de générer un prompt pour claude code qd le moteur voit une erreur »*.

### Friction observée

Le user a pointé via la modal v15.7.35 vers `script_oral_Bit_information.txt` + `slides_Bit_information.pdf`. `/api/guided/init` a parse le script avec `parse_script`, qui retourne **0 slides** car le `.txt` est du texte continu sans headers `## [SLIDE N]` Feynman. Le mode guidé retombait alors en 422 sans option de continuer.

### Décision (2 voies)

1. **Mode guidé « lite »** : au lieu de 422 quand `structure.slides` est vide, rasteriser les slides PDF page-par-page et exposer 1 slide synth par page (`title = "Page N/M"`, `oral_excerpt` du début du `.txt` sur la 1ʳᵉ slide seulement). Le tuteur reçoit déjà le texte complet via SCRIPT ORAL PERSO injecté au prompt initial, il peut commenter chaque page individuellement.
2. **Prompt Claude Code** : bouton dans la notice lite qui ouvre une modal proposant un prompt clé-en-main pour une session Claude Code séparée. Le prompt est **strictement aligné sur COURS/CLAUDE.md** (référence explicite §1, §3, §4 D, §6, et `_prompts_claude_ai/SPEC_script_oral_v2.md`). Deux kinds disponibles via radio :
   - **`regen_script_md`** : régénère un SCRIPT_*.md Feynman à partir du .txt + slides PDF
   - **`audit_matiere_cc`** : scanne toute la matière pour orphelins script/slides (read-only, génère un rapport `_audit/sessions/`)

### Livré

**Backend (`app.py`)** :
- `_build_guided_init_lite_response(script_path, slides_pdf)` : helper qui rasterise via `rasterize_if_needed`, construit des slides synth, renvoie `{slides, total, titre_global, lite: true, lite_reason}`. Appelé dans `/api/guided/init` quand `structure.slides` vide au lieu de 422.
- `POST /api/claude_code_prompt` : Body `{kind, matiere?, type_code?, num?, ...}`. 2 kinds supportés `regen_script_md` / `audit_matiere_cc`. Si pas de matiere/type/num explicite → résolus depuis la session active. Retourne `{prompt, kind, matiere, type_code, num}`. Codes 200/400 (kind invalide)/409 (pas de session ET pas d'overrides).
- Helpers `_build_prompt_regen_script_md` + `_build_prompt_audit_matiere_cc` : génèrent des prompts français longs (~80 lignes) explicitement alignés sur COURS/CLAUDE.md :
  - Mention de la séparation Claude Code (exécute) vs Claude AI (interprète) §1
  - Conventions de nommage strictes §3 (`SCRIPT_{MAT}_{TYPE}{n}_ex{e}.md`)
  - Workflow D §4 (SCRIPT.md → run_script_oral.py → .txt + slides .pdf + slides .tex)
  - Référence à `SPEC_script_oral_v2.md` §7 pour le format complet
  - Rappel des **RÈGLES ABSOLUES §6** : PRESERVE.md, jamais de suppression directe (→ `_A_VALIDER/`), atomic writes, idempotence, mise à jour docs méta
  - Rétro-ingénierie assumée explicitement (cette tâche est zone grise §1)
  - **Pas de push Discord automatique** sans validation Gaylord
  - Rapport audit dans `_audit/sessions/` §6 RÈGLE LOGGING

**Frontend (`app.js`)** :
- `renderGuidedLiteNotice(reason)` : bulle système teintée warning avec le `lite_reason` + bouton « 📝 Régénérer proprement via Claude Code ».
- `openClaudeCodePromptModal(defaultKind)` : modal avec radio sélecteur de kind (`regen_script_md` / `audit_matiere_cc`), textarea contenant le prompt généré, boutons « 📋 Copier » (Clipboard API avec fallback execCommand) + « Fermer ». Change de kind → recharge le prompt.

**CSS** : `.guided-lite-notice` (orange warning), `.cc-prompt-card` (modal large 820px), `.cc-prompt-kind-selector` (radios), `.cc-prompt-textarea` (mono 420px hauteur min).

**Tests** : `test_app_guided_fallback.py` étendu de 6 cas (total 21) :
- `/api/claude_code_prompt` no session no overrides → 409
- kind invalide → 400
- regen_script_md utilise le contexte session, prompt contient bien `COURS/CLAUDE.md`, `SPEC_script_oral_v2.md`, `run_script_oral.py`, `PRESERVE.md`, `RÈGLE`, `atomic`, et les paths du contexte
- overrides explicites bypasse la session
- `audit_matiere_cc` retourne un prompt read-only contenant `Audit`, `orphelins`, et la mention « Ne modifie aucun fichier »
- Mode lite : `/api/guided/init` avec parse_script qui retourne 0 slides → 200 OK avec `lite: true`, 3 slides synth, oral_excerpt sur la 1ʳᵉ seulement, titres « Page N/M », `lite_reason` mentionne « Feynman »

**394 tests OK** (était 388, +6).

### Workflow utilisateur

1. Lancement session PSI `_revision_CC2/Bit_information` mode guidé
2. `/api/guided/init` trouve `script_oral_Bit_information.txt` + `slides_Bit_information.pdf` (via overrides modal v15.7.35 OU résolution `_get_free_type_dir`).
3. `parse_script` retourne 0 slides → bascule en mode lite : 3 pages PDF (par exemple) → 3 slides synthétiques `Page 1/3`, `Page 2/3`, `Page 3/3`.
4. Bulle système orange : « ℹ Mode guidé (lite) » avec explication + bouton « 📝 Régénérer proprement via Claude Code ».
5. Click bouton → modal avec textarea. Radio par défaut : `regen_script_md`. L'user voit le prompt aligné COURS/CLAUDE.md, peut basculer sur `audit_matiere_cc` via radio pour générer un rapport d'audit.
6. Click « 📋 Copier » → presse-papier → coller dans une nouvelle session `claude` à la racine COURS.
7. La session Compagnon **continue normalement** en mode lite, sans interruption. Le user peut commenter chaque page PDF avec le tuteur, qui a déjà le texte continu complet.

### Limites assumées

- **Mode lite : pas de découpage oral par slide** : le tuteur reçoit le `.txt` complet via SCRIPT ORAL PERSO. Quand l'user est sur la slide 3, le tuteur n'a pas de section dédiée à commenter. Il s'adapte naturellement (interroge sur le visuel de la slide), mais l'expérience est moins riche qu'un vrai SCRIPT.md Feynman.
- **Régénération via Claude Code = pas en local** : le bouton génère un prompt mais l'user doit lancer une session `claude` séparée (le compagnon ne peut pas exécuter Claude Code en sub-process avec les bons permissions FS). Acceptable : l'user le voulait ainsi.
- **Audit cross-matière `audit_matiere_cc`** : génère un rapport, ne corrige pas. C'est intentionnel (chaque régen passe par `regen_script_md` validé par l'user).
- **Génération du prompt pas paramétrable** depuis le body actuellement (kinds figés). Extensible via ajout de nouveaux kinds dans `KINDS_VALID` + helper `_build_prompt_*`.

---

## Phase A.7.2 v15.7.35 : Modal fallback mode guidé (file picker + scan IA Gemini) (2026-05-11)

**User feedback** :
> *« c'est normal que dans → 2026-05-11_PSI__revision_CC2Bit_information_exfull (engine: gemini_api) ça dit "Système Mode guidé indisponible : SCRIPT_*.md introuvable. Repli en mode lecture libre." alors que le script (et le diapo aussi) se trouve dans […]/PSI/_revision_CC2/scripts. J'ai pas envie que ce soit hardcodé, je sais pas si c'est une bonne idée que si le nav web trouve pas le script et/ou diapo y'a le choix de parcourir dans le dossier de la matière et aussi tu en profites pour rendre la recherche plus intelligente (quitte à utiliser le llm qui consommera des tokens pour le faire et après c'est persistant) »*

### Friction observée

Le mode guidé requiert un `SCRIPT_*.md` au format **Beamer-Feynman strict** avec headers `## [SLIDE N]` parsés par `parse_script` slide-par-slide. PSI `_revision_CC2/scripts/` contient des `script_oral_*.txt` (texte continu sans headers) + `slides_*.pdf` : pas le format Feynman. Donc `find_perso_script_md` retourne `None` et le front affiche `« Mode guidé indisponible : SCRIPT_*.md introuvable. Repli en mode lecture libre. »` sans aucune option de continuer en guidé sur du matériau ad hoc.

### Décision

3 voies de récupération exposées à l'utilisateur via une **modal qui s'ouvre quand le mode guidé échoue** :
1. **🔍 Parcourir manuellement** : file picker hiérarchique sous COURS_ROOT pour pointer script + slides
2. **🤖 Chercher avec IA** : Gemini Flash 2.5 scan le dossier, suggère les meilleurs candidats, résultat persisté dans `{dossier}/_compagnon_scan.json` invalidé sur mtime du dossier
3. **↩ Repli en mode colle** : abandonne le guidé, continue en mode colle libre

Le scan IA est en **deuxième intention** (sur clic explicite) pour éviter de brûler des tokens à chaque session. Le cache mtime-based permet de re-utiliser le résultat tant que le dossier ne change pas. Le bouton « 🔄 Relancer (ignore cache) » permet de refaire le scan si l'user trouve le résultat faux.

### Livré

**Backend (`app.py`)** :
- `POST /api/browse_folder` : Body `{path}` (relatif à COURS_ROOT). Retourne `{cwd, parent_path, entries: [{name, path_rel, is_dir, size?, kind?}]}`. Sécurité anti-traversal via `_is_under_cours_root` (path résolu doit être strictement sous COURS_ROOT). Heuristique `_classify_file` détecte 9 kinds : `script_md`, `script_txt`, `script_imprimable`, `slides_pdf`, `annale`, `aide_memoire`, `pdf`, `md`, `txt`, `other`. Filtre les fichiers techniques (`.bak`, `.tmp`, `.pyc`, dotfiles). Codes 200 / 400 (traversal) / 404 (dossier inexistant).
- `POST /api/scan_with_ai` : Body `{folder_path, force_refresh?}`. Cache `{dossier}/_compagnon_scan.json` valide tant que `cache_mtime >= max(folder_mtime, sub_folder_mtimes)`. Sinon (ou `force_refresh=true`), nouveau scan via `_scan_with_ai_internal` :
  - Walk récursif 2 niveaux sur le dossier, collecte fichiers PDF/MD/TXT avec leur kind + taille
  - Prompt Gemini Flash 2.5 (engine forcé) : « voici la liste, identifie script_oral + slides + script_imprimable. Confidence 0-100 + reasoning. »
  - Parse JSON strict, strip fences markdown éventuels (Gemini les ajoute parfois)
  - Normalise les chemins retournés en relatifs à COURS_ROOT (sécurité supplémentaire)
  - Persist le résultat atomic write
  - Fail-soft : Gemini fail ou JSON cassé → retour dégradé `{script_oral_path: None, ..., error: "..."}`, code 200 (le front affiche le reasoning d'erreur)
- `/api/guided/init` étendu :
  - Accepte query params `?script_path=...&slides_path=...` (overrides). Si fournis et valides, prend le pas sur la résolution canonique.
  - Quand SCRIPT_*.md ou slides_*.pdf introuvable, retourne 404 enrichi avec `guided_fallback_required: true, matiere, type_code, num, folder_path` pour signaler au front d'ouvrir la modal.

**Frontend (`app.js`)** :
- `initGuidedPanel(startIndex, overrides?)` détecte `guided_fallback_required` et appelle `openGuidedFallbackModal(data, startIndex)`.
- Modal `#guided-fallback-modal` avec 3 panneaux (alternatifs) :
  - **Panneau actions principales** : 3 boutons « 🔍 Parcourir » / « 🤖 IA » / « ↩ Colle »
  - **Panneau picker** : header (target « 🎯 Choisis le SCRIPT » ou « SLIDES » + cwd) + liste hiérarchique avec bouton « ⬆ remonter » + selections en bas
  - **Panneau résultat IA** : header avec confidence badge (rouge/orange/vert selon 0-40 / 40-70 / 70+), reasoning, 2 paths suggérés, 3 boutons d'action (✓ Utiliser / 🔄 Relancer / 🔍 Picker manuel)
- `gfbLoadFolder(pathRel)` : navigation interactive, classifie les fichiers par kind avec icônes (📁 dir, 🖼 slides_pdf, 📝 script_md/txt, 🖨 script_imprimable, 📑 annale, 📋 aide_memoire, 📄 autre PDF).
- `gfbSelectFile(entry)` : sélection séquentielle (script → puis slides), `gfbRenderSelections` affiche l'état avec boutons ✕ pour clear.
- `gfbRunAiScan(force)` : POST `/api/scan_with_ai`, affiche le résultat. Bouton « ✓ Utiliser » bascule vers le panneau picker avec les paths pré-remplis (modifiables).
- `gfbLaunchGuided` : ferme la modal et relance `initGuidedPanel(startIndex, {script_path, slides_path})` qui appelle `/api/guided/init` avec les overrides.

**CSS (`style.css`)** : ~250 lignes pour la modal (overlay, card, picker hiérarchique, result IA avec confidence badges colorés).

**Tests** : `test_app_guided_fallback.py` (15 cas) :
- `/api/browse_folder` : root + subdir, classification kinds, path traversal refusé, nonexistent 404, leading slash normalize
- `/api/scan_with_ai` : folder_path requis, traversal refusé, nonexistent 404, appel Gemini mocké + persist cache, cache hit au 2ᵉ appel, force_refresh bypass cache, cache invalidé sur folder mtime bump
- `/api/guided/init` : 409 sans session, 404 + `guided_fallback_required: true` quand SCRIPT manque

**388 tests OK** (était 373, +15).

### Workflow utilisateur (cas PSI `_revision_CC2/`)

1. Lancement session avec type=`_revision_CC2`, num=`Bit_information`, mode=guidé
2. `/api/guided/init` cherche SCRIPT_*.md → introuvable → 404 `guided_fallback_required: true`
3. Modal s'ouvre. L'user a 3 choix :
   - **A. Parcourir** : navigation dans `PSI/_revision_CC2/scripts/`, choisit `script_oral_Bit_information.txt` puis `slides_Bit_information.pdf`, clic ▶ Lancer
   - **B. IA** : Gemini Flash scan, propose `scripts/script_oral_Bit_information.txt` + `scripts/slides_Bit_information.pdf` avec confidence ~85, clic ✓ Utiliser puis ▶ Lancer. Persisté pour les sessions suivantes.
   - **C. Colle** : ferme la modal, continue en mode colle.
4. Si script/slides choisis : `initGuidedPanel(0, {script_path, slides_path})` relance `/api/guided/init?script_path=...&slides_path=...` qui résout les overrides. Si `parse_script` du fichier choisi retourne 0 slides (ex : `script_oral_*.txt` sans headers `## [SLIDE N]`) → 422 toujours. Limite assumée : l'user doit pointer un vrai SCRIPT.md Feynman ou créer un.

### Fix UX inclus v15.7.35.1 (même commit)

User feedback immédiat après livraison v15.7.35 : *« par exemple pour ça […] ça propose un mauvais fichier et un bon fichier et du coup je suis obligé de parcourir mais pour les deux dont le bon alors qu'il faudrait cibler que le mauvais qu'on veut »*. Le panneau picker affichait un message « Sélections IA appliquées » à la place de la liste de fichiers, masquant la possibilité de parcourir un remplaçant. Fix :
- **Bouton ✎ Modifier** par sélection (à côté du ✕ Clear) : recharge le picker dans le dossier du fichier actuel, force le pickerMode sur ce slot.
- **Slot actif mis en évidence** : la sélection ciblée par le prochain clic dans la liste a une bordure gauche teintée accent + marker `← cible du picker`. L'user voit où va atterrir son clic.
- **Liste plus cachée après ✓ Utiliser** : le panneau picker s'ouvre avec la liste chargée dans le dossier du script suggéré, pickerMode = "slides" par défaut (le cas le plus fréquent d'erreur IA en multi-thèmes).

### Limites connues

- **`script_oral_*.txt` sans headers SLIDE N** : même si l'user le pointe via le picker, `parse_script` retourne 0 slides → 422. La modal v15.7.35 ne convertit PAS automatiquement un `.txt` en SCRIPT.md Feynman. Pour un dossier PSI `_revision_CC2/` qui n'a que du `.txt`, l'user doit soit créer manuellement un SCRIPT.md avec headers, soit basculer en mode colle (option 3 de la modal). Phase ultérieure : mode guidé « lite » qui rasterise les slides PDF page-par-page sans script segmenté.
- **Cache scan IA** : invalidé sur mtime du dossier ET d'un sous-dossier de niveau 1. Si l'user modifie un fichier dans `scripts/scripts/` (niveau 2), le cache reste valide. Acceptable : pas de cas usage observé.
- **Coût Gemini Flash par scan** : ~$0.0001 par appel (input ~500 tokens, output ~150). Avec cache, 1 scan par dossier par session de modif. Marginal.

---

## Phase A.7.2 v15.7.34 : Fix layout GUI Tk en fenêtre taille native (2026-05-11)

**User feedback** :
> *« juste dans lancer une session y'a des trucs mal agencés niveau css quand la fenêtre est normale (pas agrandie au max) mais la fenêtre de taille de base. Genre les input de droite sont coupés et le texte de guidé aussi. »*

### Friction observée

Sur la GUI Tk en taille de fenêtre native (avant que l'user redimensionne) :
- Le label du radio « Guidé » faisait 55 caractères (`"Guidé (slide-par-slide + tuteur Read FS + suggestions)"`) et débordait du LabelFrame Lancer.
- Les comboboxes Type et Exo (column 3 du grid) étaient coupés à droite car les columns n'avaient pas de `weight` configuré → le grid utilisait juste la largeur minimum du contenu.
- Phase v15.7.32 puis v15.7.33 ont aggravé en ajoutant `_revision_CC2` (16 chars) comme valeur Type et des thèmes longs comme `Bit_information`/`TP_Shannon` comme valeur Num : ces strings plus larges saturaient les comboboxes en taille native.

### Livré

- **`gui.py`** :
  - `outer.grid_columnconfigure(0, minsize=420)` → `minsize=500` pour la colonne 0 (Lancer une session). La colonne 1 (Quota) garde 420 car pas de débordement.
  - `f.grid_columnconfigure(1, weight=1, minsize=120)` et `(3, weight=1, minsize=160)` sur le LabelFrame Lancer pour propager la largeur disponible aux columns de comboboxes. Sans `weight`, le grid Tk colle au contenu minimum.
  - `sticky="w"` → `sticky="ew"` sur les comboboxes Matière/Type/Num/Exo/Année, ce qui leur permet de s'étirer dans la column avec poids.
  - `self.type_combo` largeur 10 → 18 caractères (pour caser `_revision_CC2` sans troncature visible avant ouverture du dropdown).
  - `self.num_combo` largeur 10 → 14 caractères (pour caser `Bit_information`).
  - Radio « Guidé » : label raccourci `"Guidé (slide-par-slide + tuteur Read FS + suggestions)"` → `"Guidé (slide-par-slide)"`. La description complète est déménagée vers une `ttk.Label` grise discrète **sur sa propre ligne** sous les radios mode, avec `wraplength=480` (multi-ligne si encore étroit) : « *Colle = interrogation pure ; Guidé = tuteur Read FS + suggestions de correction* ».

### Tests

Pas de test fonctionnel ajouté : c'est purement du layout Tk visuel. Syntax check `python -c "ast.parse(...)"` + suite complète (**373 tests OK**, aucune régression).

### Limites assumées

Si l'user a une résolution très basse (<1024×768) ou un thème système qui force des polices XL, la fenêtre peut toujours être à l'étroit. Solution dans ce cas : redimensionner manuellement (les `weight=1` propagent l'espace gagné). Pas de mode responsive complet : c'est une GUI Tk personnelle, pas une UI multi-device.

---

## Phase A.7.2 v15.7.33 : Détection des thèmes + mapping correct pour types libres (2026-05-11)

**User feedback** (suite v15.7.32) :
> *« tu es sûr que ce que tu dis là c'est cohérent […] tu as exploré ces fichiers ? »* puis *« je doute que juste avoir full ce soit cohérent par rapport à tout ce qu'il y a »* puis *« ok GO A »* (l'approche A des 3 proposées).

### Friction observée (vérification réelle)

J'avais mappé heuristiquement par **nom de fichier** sans regarder les contenus en v15.7.32. Vérification :

- **`aide_memoire_CC2.pdf`** est un **cheat sheet / poly de révision** (synthèse par concepts : Bit info, Hamming, Shannon, RAID, USB), **pas un énoncé d'exercice**. Étiqueté à tort comme énoncé.
- **`annale_synthese_CC2.pdf`** est une **annale de 24 questions Q&A avec corrections**. Format examen blanc : sert à la fois d'énoncé ET de corrigé.
- **`scripts/script_oral_*.txt`** : **4 fichiers par thème** (`Bit_information`, `RAID`, `TP_Shannon`, `USB`). Le scanner v15.7.32 ne prenait que le 1ᵉʳ : les 3 autres rataient.
- **`scripts/script_imprimable_*.pdf`** et **`scripts/slides_*.pdf`** : pareil, 4 versions par thème, scanner ne ramassait qu'une.
- **`pitch_oral_30s.pdf`** : pitch oral 30 s, **pas des slides** (les vraies slides sont `scripts/slides_*.pdf`). Confondu en v15.7.32.
- **`exos_TP_Shannon.pdf`** : exos spécifiques au TP Shannon, **jamais détecté** en v15.7.32.

### Approche retenue (A : sous-numéros par thème)

Pour un dossier libre qui agrège plusieurs thèmes (cas PSI `_revision_CC2/`), le combobox Num expose désormais :
- `full` (matériaux globaux : annale Q&A + cheat sheet)
- + un sous-numéro par **thème détecté** dans `scripts/script_oral_*.{txt,md}` ou `slides_*.pdf` ou `script_imprimable_*.pdf`

Pour PSI `_revision_CC2/` → Num = `["full", "Bit_information", "RAID", "TP_Shannon", "USB"]`.
Pour PSI `_revision_CC1/` (que des .md globaux, pas de scripts par thème) → Num = `["full"]`.

### Nouveau mapping correct

| Champ SessionContext | Mapping v15.7.32 (faux) | Mapping v15.7.33 (correct) |
|---|---|---|
| `enonce_path` | `aide_memoire_CC{N}.pdf` | `annale_synthese_CC{N}.{pdf,md}` (Q&A examen blanc). Si num=thème + `exos_{theme}.{pdf,md}` présent → ce fichier prioritaire. |
| `correction_paths` | `annale_synthese_CC{N}` | Même PDF Q&A (l'annale contient les corrections : c'est sa nature de synthèse Q&A). |
| `cm_poly_path` *(nouveau auto-résolu)* | *(non auto-résolu)* | `aide_memoire_CC{N}.{pdf,md}` (cheat sheet = poly de référence). Section « POLY DU PROF » du prompt. |
| `script_oral_path` | 1ᵉʳ `script_oral_*` | `scripts/script_oral_{num}.{txt,md}` (filtré par thème si num != full). |
| `script_imprimable_path` | 1ᵉʳ `script_imprimable_*` | `scripts/script_imprimable_{num}.pdf` (filtré). |
| `slides_pdf_path` | `pitch_oral_30s.pdf` | `scripts/slides_{num}.pdf` (filtré). `pitch_oral` retiré de la liste des hints slides. |

### Livré

- **`cours_resolver.py`** :
  - Constante `_FREE_ENONCE_HINTS = ("annale_synthese", "enonce", "exos", "sujet")` : `aide_memoire` retiré.
  - Nouvelle constante `_FREE_POLY_HINTS = ("aide_memoire", "poly", "cheat_sheet", "synthese")`.
  - `_FREE_SLIDES_HINTS = ("slides",)` : `pitch` retiré.
  - Nouveau helper `_detect_themes_in_free_dir(folder)` : scan `folder/scripts/` et `folder/scripts_oraux/` pour patterns `{prefix}_{theme}.{ext}` où `prefix ∈ {script_oral, slides, script_imprimable}`. Extrait les thèmes uniques.
  - Nouveau helper `_match_free_pdf_themed(folder, hints, theme, exts)` : variante qui filtre par thème (nom doit contenir hint **et** thème).
  - Nouveau helper public `find_free_poly(cours_root, matiere, type_code)` : retourne `aide_memoire_*.{pdf,md}` pour les types libres. Mappé vers `cm_poly_path`.
  - `_find_free_script` étendu avec param `theme` : si fourni et != `"full"`, le fichier doit contenir `_{theme}.` ou `_{theme}_` dans son nom.
  - `list_nums_for_type` pour type libre : retourne `["full"] + themes` (thèmes détectés via `_detect_themes_in_free_dir`).
  - `find_enonce_pdf` pour type libre + num=thème : essaye `exos_{theme}` au top (priorité), fallback `annale_synthese` global.
  - `find_perso_script_oral`, `find_perso_script_imprimable`, `find_perso_slides_pdf` : reçoivent `num` comme thème et filtrent.

- **`app.py`** : `_build_session_context` appelle `find_free_poly(...)` pour auto-résoudre `cm_poly_path` quand le type est libre. Le prompt initial reçoit alors une section « POLY DU PROF » distincte de l'énoncé.

- **Tests** : 4 nouveaux + 7 mis à jour dans `TestFreeTypeBrowse` :
  - `list_nums` retourne `["full", "Bit"]` (thème détecté depuis `script_oral_Bit.txt`)
  - `find_enonce` retourne `annale_synthese`, pas `aide_memoire` (régression check)
  - `find_free_poly` retourne `aide_memoire` (nouveau)
  - `find_perso_script_oral` filtre par thème (`num="Bit"` ramène `script_oral_Bit.txt`, `num="RAID"` ramène `script_oral_RAID.txt`)
  - `find_enonce_pdf` priorise `exos_{theme}` au top quand applicable
  - `_detect_themes_in_free_dir` extrait correctement les thèmes
  - Casse insensible préservée
  - Type canonique TD inaffecté

**373 tests OK** (était 369, +4).

### Workflow utilisateur

1. GUI ou web → matière `PSI` → type `_revision_CC2` → Num = liste `[full, Bit_information, RAID, TP_Shannon, USB]`.
2. Choix `TP_Shannon` → session lancée avec :
   - **énoncé** = `exos_TP_Shannon.md` (exos spécifiques du thème, prioritaire)
   - **corrigé** = `annale_synthese_CC2.pdf` (annale globale, contient le thème)
   - **poly CM** = `aide_memoire_CC2.pdf` (cheat sheet de référence)
   - **script perso** = `scripts/script_oral_TP_Shannon.txt`
   - **slides** = `scripts/slides_TP_Shannon.pdf`
   - **imprimable** = `scripts/script_imprimable_TP_Shannon.pdf`
3. Choix `full` → tuteur reçoit tous les matériaux globaux (annale + cheat sheet + 1er script disponible).

Le tuteur en mode colle peut désormais interroger l'étudiant **précisément sur le thème** Shannon ou USB sans charger tout le contexte des autres thèmes (économie de tokens + focus pédagogique).

### Limites connues

- Le `num` = nom du thème est **case-sensitive** côté backend (le filtrage `_find_free_script` est lower mais la value transmise doit refléter le nom du fichier). Si l'user tape `tp_shannon` au lieu de `TP_Shannon`, ça matche quand même via lower. OK.
- L'**énoncé** d'un thème reste l'annale globale `annale_synthese_CC2.pdf` (qui couvre tous les thèmes) sauf si un `exos_{theme}.{pdf,md}` spécifique existe au top du dossier. Le tuteur reçoit donc tout le PDF Q&A mais sait via le contexte (Num = thème) qu'il doit se focaliser sur les questions de ce thème. Si on voulait extraire la section du thème dans le PDF, faudrait un parser PDF par section, ce qui est surdimensionné pour cette phase.
- Pour `num=full`, le `script_oral` retourné est le 1ᵉʳ disponible (alphabétique). Conséquence : le tuteur reçoit le script `Bit_information` même si l'user voulait une révision globale. Acceptable car `full` est censé être une révision globale ; en pratique l'user fera un choix de thème.

---

## Phase A.7.2 v15.7.32 : Types libres dans le scanner d'arborescence (2026-05-11)

**User feedback** :
> *« Dans le gui de compagnon de révision, les regex de lancer une session pour la matière PSI semble mal appliqué. Pour le type CC eh bien je n'en vois aucun. Pour les CM je vois des nums mais je sais pas à quoi correspond ces nums. […] Les cours de PSI se trouvent ici […]. En ft ce que je suis censé réviser c'est […]/PSI/_revision_CC2 mais y'a un truc qui semble ne pas bien matcher (et au passage même si ça me sert à rien actuel faut ça matche `_revision_CC1` aussi) »* puis *« fin faut trouver une solution et qui pourra s'appliquer aussi pour les autres années à venir »* puis *« quand j'aurai de nouvelle matière un peu spécifique comme ça »* puis *« faut aussi un truc plus modulable genre carrément que ça explore l'arbo »*.

### Friction observée

Le scanner d'arborescence (`cours_resolver.list_types_for_matiere` + helpers) suit une convention de nommage stricte basée sur les types canoniques **TD/TP/CC/CM/Quiz/Examen**. Quand une matière dévie de cette convention, comme PSI avec ses dossiers `_revision_CC1/` et `_revision_CC2/` au top (matériel de révision globale agrégé : aide-mémoire + annale + scripts), le scanner ne les voit pas (préfixe `_` exclu par convention). Résultat : impossible de lancer une session sur ce matériel depuis la GUI/web. PSI/CC/ n'a en plus aucun fichier suivant la convention `enonce_CC{N}_*.pdf` (juste des PDFs « hints »), donc le combobox CC apparaît vide.

### Décision

Plutôt que de hardcoder une convention `_revision_CC*` ou un pseudo-type `RévCC` (approche initialement envisagée puis abandonnée car non-extensible), **scanner générique** : tout sous-dossier de la matière qui contient au moins 1 fichier pédagogique (`.pdf`, `.md` ou `.txt` sur 2 niveaux de profondeur) et qui n'est pas un dossier technique (blacklist `_EXCLUDED_TOP_DIRS`) apparaît dans le combobox Type. Le resolver scan ensuite ce dossier **heuristiquement** pour trouver énoncé/corrigé/script. Marche pour PSI maintenant, futurs CC, autres matières spécifiques à venir, sans hardcode.

### Livré

- **`cours_resolver.py`** :
  - Helper `_is_canonical_type(type_code)` distingue TD/TP/CC/CM/Quiz/Examen des types libres.
  - Constante `_EXCLUDED_TOP_DIRS` : dossiers techniques à toujours exclure du scan (`_moodle`, `_archives`, `_inbox_dl`, `_contextes_reprise`, `_A_TRIER`, `_audit`, `_publish_queue`, `_prompts_claude_ai/code`, `_perso`, `_scripts`, `_INBOX`, `_A_VALIDER`, `_temp_latex`, `_archived`, `_lectures`, `scripts_oraux`).
  - Helper `_has_material_recursive(folder, max_depth=2)` : True si au moins 1 `.pdf`/`.md`/`.txt` (étendu pour détecter `_revision_CC1/` qui n'a que des markdown).
  - Helper `_get_free_type_dir(cours_root, matiere, type_code)` : retourne le path `{MAT}/{type_code}/` si existe ET non-canonique. Tolère casse insensible (`_REVISION_CC2` matche `_revision_CC2`).
  - Constantes heuristiques par ordre de priorité :
    - `_FREE_ENONCE_HINTS = ("enonce", "aide_memoire", "sujet", "poly", "pitch_oral")` : testées dans cet ordre, `aide_memoire` l'emporte sur `pitch_oral`.
    - `_FREE_CORRIGE_HINTS = ("correction", "annale_synthese", "corrige", "corrigé")`
    - `_FREE_IMPRIMABLE_HINTS = ("script_imprimable", "_recopie", "a4_recopie")` : variantes PSI.
    - `_FREE_SLIDES_HINTS = ("slides", "pitch")`.
  - `_match_free_pdf(folder, hints, exts=(".pdf",))` étend aux `.md`/`.txt` et priorise les hints séquentiellement. Préfère le `.pdf` sur le `.md` si les deux existent pour un même hint (tri par ext_priority).
  - `_scan_free_corrections(folder)` : retourne tous les fichiers matchant `_FREE_CORRIGE_HINTS`. PDFs prioritaires, `.md` en fallback (uniquement si stem pas déjà capturé par un PDF).
  - `_find_free_script(folder, exts)` : scan `folder/scripts/` puis `folder/scripts_oraux/`, préfère `script_oral_*.{ext}`.
  - `list_types_for_matiere` réécrite : canoniques d'abord (tri alpha), puis libres (tri alpha) : l'ordre rend le combobox lisible.
  - `list_nums_for_type` : pour type libre, retourne `["full"]` si le dossier existe, sinon `[]`.
  - `list_exos_for_num` : pour type libre, retourne `["full"]`.
  - `list_annees_for_cc` : nouvelle signature avec `type_code` optionnel, retourne `[]` proprement pour les types libres (au lieu de scanner le path CC inexistant).
  - `find_enonce_pdf`, `resolve_corrections`, `find_perso_script_oral`, `find_perso_script_imprimable`, `find_perso_slides_pdf` : early-return via `_get_free_type_dir` quand applicable, sinon dispatch vers la logique canonique historique (zéro régression).

- **`prompt_builder.py`** : `_extract_pdf_text` étendu pour accepter `.md`/`.txt` (lecture directe, pas via pypdf). Cas `_revision_CC1/aide_memoire_CC1.md` qui n'a pas encore de version PDF.

- **Tests** : 13 nouveaux cas dans `test_cours_resolver.py` (classe `TestFreeTypeBrowse`) :
  - `list_types` inclut les dossiers libres avec matériel (PSI : `_revision_CC1`, `_revision_CC2`, `TP_recherche_docu`)
  - `list_types` exclut les dossiers techniques (`_moodle`, dossiers vides)
  - Canoniques triés avant libres
  - `list_nums` retourne `["full"]` pour type libre existant, `[]` pour inexistant
  - `list_exos` retourne `["full"]` pour type libre
  - `list_annees` retourne `[]` proprement pour type libre via le nouveau param `type_code`
  - `find_enonce` priorise `aide_memoire` sur `pitch_oral` (régression check)
  - `find_enonce` fallback `.md` quand pas de PDF
  - `resolve_corrections` trouve `annale_synthese`, fallback `.md`
  - `find_script_oral` scan le sous-dossier `scripts/`
  - Casse insensible (`_REVISION_CC2` matche `_revision_CC2`)
  - Type canonique TD continue de résoudre via convention historique (zéro régression).

**369 tests OK** (était 355, +14).

### Côté GUI / web

Pas de modification nécessaire côté `gui.py` ni `app.js` : les combobox lisent dynamiquement depuis `list_types_for_matiere` et `list_nums_for_type`. L'ajout des types libres au scanner backend fait apparaître automatiquement `_revision_CC1`, `_revision_CC2`, `TP_recherche_docu` dans le combobox Type pour PSI au prochain restart de la GUI (ou rescan via le bouton 🔄). L'endpoint `/api/cours_options` côté web relaie aussi sans modification.

Le combobox Num affichera `full` pour les types libres (logique : pas de notion de numéro). Le combobox Année désactivé. Le combobox Exo affichera `full` aussi. Le user clique Lancer et la session démarre avec :
- énoncé = aide_memoire_CC{N}.pdf (ou .md si pas de PDF)
- corrigé = annale_synthese_CC{N}.pdf
- script = scripts/script_oral_*.txt
- imprimable = aide_memoire_CC{N}_*recopie*.pdf
- slides = pitch_oral_30s.pdf

### Limites assumées

- **Affichage `_revision_CC2`** dans le combobox : le préfixe `_` reste visible. Pas idéal esthétiquement mais ça reflète exactement le nom du dossier sur disque, pas de risque d'ambiguïté. Si le user veut un wording plus clean, il peut renommer le dossier (sans préfixe `_`), le scanner le détecterait toujours.
- **Pas de découpage par exercice** : un type libre = un dossier = un seul matériel agrégé (`full`). Cohérent avec l'usage « révision globale du CC ».
- **Heuristiques de hints fixes** : si une matière future utilise des conventions de nommage très différentes (ex : `synthese.pdf` au lieu de `aide_memoire.pdf`), elle ne sera pas détectée comme énoncé. Ajouter le hint dans la constante correspondante quand le cas se présente.

---

## Phase A.7.2 v15.7.31 : Phase débrief post-séance + audit rétro WP + mini-exos + export Anki (2026-05-11)

**User feedback** :
> *« j'ai terminé mon CC EN1 et ça a terminé la session. Déjà un truc qui m'intrigue c'est que ça dit 0 point faible alors qu'au départ si je galérais sur des trucs. Mais en plus ben c'est dommage que ça coupe la session, ça peut au moins faire un résumé de tout ce qui a été fait et analyser mon profil etc faire des trucs […] et me laisser continuer encore à poser des questions ou je sais pas proposer des trucs pour travailler les points faibles ou refaire un bref […]. »*

### Friction observée

Session EN1 CC2 du 2026-05-10 : 83 tours de dialogue, `weak_points: []`. Le tuteur (Gemini 2.5 Pro) n'a **jamais** émis `<<<WEAK_POINT>>>` malgré §5 du prompt. Test connu : la balise live n'est pas obéie de façon fiable par Gemini en sessions longues (Opus est correct). De plus, la séance se ferme brutalement sur `<<<END_SESSION>>>` : pas de bilan, pas de Q&R post-séance, pas d'aide pour travailler ce qui a été galéré.

### Décision

Plutôt que de durcir §5 du prompt (instruction qu'on espère obéie en live = fragile), **audit rétrospectif côté Python**. Gemini Flash 2.5 scanne le transcript complet à la fin et produit un JSON structuré `{summary, concepts_covered, exercises_handled, suggestions, weak_points_retro}`. Bonus : on en profite pour ajouter une vraie **phase débrief** entre la fin de séance et la fermeture définitive.

### Livré (A + B + C en 1 passe)

**A : Récap auto + audit rétro WP** :
- Helper `_generate_session_recap(transcript)` (app.py) : 1 appel Gemini Flash forcé (latence 3-8s vs Opus 15-30s, coût négligeable, cohérence cross-engine). Prompt JSON strict avec validation post-parse : score 0-4, fields requis, fail-soft si JSON cassé (fallback dégradé `{summary: raw_text, ...empty}`). Strip défensif des fences ```json``` que Gemini ajoute parfois.
- Endpoint `POST /api/session_recap` : génère + persiste `recap` + `weak_points_retro` + `phase="debrief"` + `recap_at` (atomic write). Idempotent : si déjà en debrief/closed, retourne le cache. Injecte `[PHASE DÉBRIEF ENGAGÉE]` dans le `_history` du tuteur. Codes 200/409.
- Carte récap frontend `.session-recap-card` (CSS dédié, teinte accent bleue) : résumé Markdown, concepts couverts (liste), exercices traités (liste), points faibles rétro (chacun encadré avec couleur selon score 0→4 : err/warn/student), suggestions, 3 boutons d'action (Export Anki / Continuer débrief / Fermer définitivement).

**B : Phase débrief continue** :
- Champ session JSON `phase ∈ {active, debrief, closed}` (additif, default `active`, pas de bump schéma).
- Endpoint `POST /api/session_close` : vraie finalize (set `phase=closed` + `final_closed_at` + `session_state.finalize()`).
- Prompt v0.6 → **v0.7** :
  - **§1.7** « Phase débrief » : ratio §2.1 relâché (peut détailler 4-6 phrases), indices §2.4 levés (répond directement), rigueur §2.3 sur le vocabulaire conservée (sinon c'est un chatbot), vouvoiement §4.9 conservé, pas de retour colle sauf demande explicite, pas de nouvel `<<<WEAK_POINT>>>` en débrief.
  - **§1.7bis** : marker `[MINI-EXO : concept=..., what_failed=..., score=..., context=...]` déclenche un exo court (3-5 questions progressives), une question à la fois, posture colle re-activée localement, fin sobre + bilan.
  - **§4.13** : règle absolue « pas de résistance à la bascule en phase débrief » (clone §4.11/§4.12). Interdit « voulez-vous vraiment terminer ? », « on n'a pas fini l'ex 3 ».
- Modification `finishSession()` côté frontend : par défaut déclenche `triggerSessionRecap()` au lieu de fermer brutalement. Fallback `"force_close"` pour le chemin direct (cas d'erreur).
- Restauration : `restoreActiveSessionIfAny` détecte `phase=debrief` et ré-affiche la carte récap (le user ferme son onglet et revient).

**C : Mini-exos sur WP + export Anki** :
- Endpoint `POST /api/mini_exo` : Body `{wp_index}` (résolution via `weak_points_retro[idx]`) OU `{concept, what_failed, score?, exercise_context?}` direct. Injecte le marker `[MINI-EXO : ...]` dans `_history` + set `retry_pending=True` côté state pour que le prochain `/api/stream_response` streame sans `pending_user_text` à fournir.
- Frontend : bouton 🎯 Mini-exo dans chaque carte WP de la récap → `triggerMiniExo(idx, wp)` → POST + `streamResponse()`. Bulle système « 🎯 Mini-exo demandé : … » dans le fil.
- Endpoint `GET /api/export_anki` : retourne `.txt` tab-separated `front\tback\ttags` importable Anki natif (Fichier → Importer → délimiteur tab). Format : `{concept} : {context}\t{what_failed}. Score : {score}/4.\tcompagnon_revision {MAT} score_{N}`. Filename dynamique `compagnon_{MAT}_{TYPE}{NUM}_anki.txt`.
- Bouton 📥 Export Anki dans la carte récap (`disabled` si pas de WP rétro).

### Tests

`test_app_post_session.py` (19 cas) :
- `/api/session_recap` : 4 cas (no session 409, happy path + persist set_meta, idempotent cache si debrief, fallback dégradé si Gemini fail)
- `/api/session_close` : 3 cas (no session, finalize, combinaison live + retro WP count)
- `/api/mini_exo` : 5 cas (no session, index out of range, index valid + marker + retry_pending, direct concept, required missing 400)
- `/api/export_anki` : 3 cas (no session, empty WP, tab-separated format + filename)
- Doctrine v0.7 : 4 cas (§1.7 présent + ratio relâché, §1.7bis 3-5 questions, §4.13 no resistance + interdit, rigueur vocabulaire conservée)

**355 tests OK** (était 336, +19).

### Limites connues

- **Audit rétro non-incrémental** : chaque appel à `/api/session_recap` regénère depuis le transcript complet (~5s Gemini Flash). Si user clique Terminer plusieurs fois → cache idempotent évite le retravail, mais une nouvelle session après mini-exos enchainés voudrait peut-être un audit étendu. Pas critique pour Phase v15.7.31.
- **Marker `[MINI-EXO : ...]` parsing côté tuteur** : repose sur l'obéissance LLM. En cas de tuteur récalcitrant (typique Gemini en session longue), le mini-exo peut sortir mal formé. Pas de fallback automatique côté Python.
- **Format `.apkg`** : pas implémenté (nécessiterait `genanki`). Le `.txt` tab-separated couvre 95 % du cas (import Anki natif zéro friction). `.apkg` éventuellement Phase C post-CC3.
- **Plus de heartbeat lifecycle distinct** entre phase débrief et active : le `last_alive` continue de battre tant que la session n'est pas fermée. Voulu (le user peut revenir des heures après).

### Décision prompt v0.7 : §5 NON durci

J'ai choisi de **NE PAS** durcir §5 (WEAK_POINT) dans v0.7. Raison : l'audit rétro côté Python rend la fiabilité de la balise live moins critique. Durcir §5 sur Gemini 2.5 Pro ne change pas grand chose (les sessions longues continuent d'ignorer), alors que l'audit rétro fonctionne sur tous les engines (sa propre instance Gemini Flash). Si Phase v15.7.32 montre que c'est encore problématique en débrief, on durcira à ce moment-là.

---

## Phase A.7.2 v15.7.30 : Ancrage corrigé paramétrable (strict / consultatif / aucun) (2026-05-11)

**User feedback** :
> *« j'avais un doute sur le corrigé et en parallèle j'ai demandé à claude ai sonnet 4.6 de faire le corriger et il me dit que le corrigé fourni dans compagnon est faux et du coup compagnon tourne en boucle dessus. […] Finalement vaut-il pas mieux retirer les corriger comme source de vérité ou alors avoir la possibilité de selectionné ou non le corrigé pour que ce genre d'erreur n'arrive pas ? »* (2026-05-10, session EN1 CC2 exfull en cours, replay)

### Friction observée

Phase A.5 (2026-05-05) a ajouté §1.4 « ancrage sur le corrigé officiel » comme **règle inviolable** parce que le tuteur divergeait des corrigés prof. C'était la bonne décision quand le corrigé est juste. Mais le cas inverse (corrigé prof erroné) n'avait pas de soupape de sécurité : le tuteur **tournait en boucle** en répétant tour après tour « le corrigé attend X » sans pouvoir s'émanciper, alors que l'étudiant produisait pourtant un raisonnement structuré et cohérent qui le contredisait. Vérifié en parallèle sur Claude.ai Sonnet 4.6 qui confirme que le corrigé est faux. Le tuteur Compagnon ne sait pas se remettre en question dans la session courante : c'est la règle §1.4 qui le bloque.

### Choix d'architecture

Plutôt que de relâcher §1.4 globalement (régression vers la friction Phase A.5), **paramétrage en 3 modes** au pattern jumeau de `colle_format` v15.7.4 :

| Mode | Comportement | Cas d'usage |
|---|---|---|
| **📘 Strict** *(défaut)* | Corrigé inviolable, comportement v0.5 | 1ᵉʳ tour TD, validation conformité prof |
| **📖 Consultatif** | Corrigé visible mais cité comme point de vue parmi d'autres ; voies alternatives cohérentes validées | 2ᵉ tour TD, exploration, **quand on suspecte que le corrigé est faux** |
| **🚫 Sans corrigé** | Bloc CORRIGÉ OFFICIEL **carrément pas injecté** dans le contexte du tuteur | Révision blanche sans biais conformité |

5 arbitrages décidés sans demander (le user a dit « oui code ») :
1. **3 modes** plutôt que 2 (`consultatif` = utile pour 2ᵉ tour TD)
2. **Local-only** par défaut, pas d'auto-publication Discord
3. **100 % LLM** pour le déclenchement (pas de compteur Python qui sous/sur-détecte)
4. **`aucun` skippe vraiment** l'injection plutôt qu'un header « non-prescriptif »
5. **Bascule à chaud** ne re-injecte pas le corrigé (limite assumée, redémarrage pour récupérer)

### Livré

- **`PROMPT_SYSTEME_COMPAGNON.md` v0.5 → v0.6** : §1.4 réécrit en 3 sous-sections détaillées (5 conséquences concrètes par mode) + §4.6 amendé pour distinguer « pas d'invention » selon le mode + nouvelle règle absolue §4.12 « pas de résistance aux bascules d'ancrage » (clone §4.11 pour le format) avec interdiction explicite de « le corrigé est pourtant la référence ».
- **`prompt_builder.py`** : nouveau paramètre `corrige_anchor: str = "strict"` à `build_initial_context_message`, ligne `[ANCRAGE CORRIGÉ : ...]` injectée après `[FORMAT COLLE : ...]` (uniquement mode colle), skip du bloc CORRIGÉ OFFICIEL si mode `aucun`, helper `_normalize_corrige_anchor` avec aliases (`sans_corrigé`/`sans corrige` → `aucun`).
- **`session_state.py`** : champ additif `corrige_anchor` dans `_build_initial_data` (default `"strict"`, pas de bump schéma).
- **`app.py`** : helper `_apply_corrige_anchor_change()`, endpoint `POST /api/set_corrige_anchor`, slash-commands `/strict` `/consultatif` `/aucun` `/sans_corrigé` (regex `_SLASH_CORRIGE_ANCHOR_RE` avec tolérance accents/espace/point final), lecture body dans `/api/start_session` et `/api/resume_session`, propagation à `build_initial_context_message`, retour dans `/api/current_session` + `/api/start_session` + `/api/resume_session`.
- **`runtime_settings.py`** : `DEFAULT_LAST_SELECTION["corrige_anchor"] = "strict"` (additif, merge avec defaults).
- **`compagnon.py`** : argument `--corrige-anchor` propagé en URL.
- **`gui.py`** : radio 3-states sous Format colle (`📘 Strict (défaut)` / `📖 Consultatif` / `🚫 Sans corrigé`), `_refresh_corrige_anchor_visibility` joint à `_refresh_colle_format_visibility` (même condition `mode==colle`), `corrige_anchor` ajouté à l'auto-save `last_selection` et propagé dans le CLI au clic Lancer.
- **`app.js`** : `applyCorrigeAnchorChips()`, `setCorrigeAnchor()`, `appendAnchorMarker()` (teinté mauve pour distinguer du format-marker orange), bandeau `#corrige-anchor-chips` avec 3 chips, `SLASH_CORRIGE_ANCHOR_RE` côté front, intégration `restoreActiveSessionIfAny` + `doStartSession` + `resumeSession` + `viewerRefreshTranscript` + `applyViewerMode`, parsing URL param `corrige_anchor`, toggle visibilité select dans le form joint au mode.
- **`index.html`** : select `corrige_anchor` dans le form, bandeau `#corrige-anchor-chips` sous celui du format colle.
- **`style.css`** : `.corrige-anchor-chip` (teinte mauve `rgba(190,130,220)`) + `.anchor-marker`.
- **Tests** : `test_app_corrige_anchor.py` (18 cas : endpoint + slash + doctrine v0.6) + `test_prompt_builder.py` étendu de 7 cas (3 modes happy path + skip block `aucun` + helper normalize + fallback + régression strict) + `test_runtime_settings.py` étendu de 4 cas (default strict + roundtrip + aucun persisté + legacy fallback). **336 tests OK** (était 304).

### Limite connue assumée

La bascule en cours de séance ne re-injecte **pas** le bloc CORRIGÉ OFFICIEL dans le contexte. Si tu démarres en `aucun`, le corrigé reste absent même après un `/strict`. Le tuteur change juste de posture pédagogique. Pour avoir le corrigé disponible après une bascule depuis `aucun`, redémarrer la session. Documenté dans le prompt §1.4 et le helper `_apply_corrige_anchor_change`.

### Décision sur la Phase v15.7.31 (Protocole de doute + tag `<<<DOUBT_CORRIGÉ>>>`)

L'archi a aussi sketché un mécanisme de **détection autonome** par le LLM des contradictions cohérentes répétées (2-3 tours) avec génération d'un `.md` d'audit clé-en-main pour Claude Code (qui peut ensuite éditer `TACHE_*.md` + relancer `run_correction.py` côté COURS). **Reporté** à v15.7.31 pour valider d'abord v15.7.30 en session réelle. Décision « code par bouts » CLAUDE.md §6.1.

---

## Phase A.7.2 v15.7.28 : Notes : cleanup KaTeX direct (2026-05-10)

**User feedback** :
> *« Pourquoi faut un truc source et pas juste correctement bien l'afficher ? c'est pas à cause du `<pre></pre>` que ça casse ? »*

Réponse : non, le `<pre>` n'y est pour rien, le bruit est **dans le text** au moment du `getSelection().toString()` :

- **Doublons KaTeX** : MathML invisible (chars Unicode mathématiques `𝑌 𝑖 𝐸 𝑆 𝐸 𝐿`) + couche visuelle (`Y i E S E L`) capturés tous les deux.
- **Retours à la ligne parasites** entre chaque span inline-block KaTeX.
- **Zero-width spaces** (`​`, `​`) intercalés pour le rendu mathématique.

### Approche v15.7.28 (plus simple que v15.7.26)

Helper `_cleanupKatexSelection()` appliqué **avant la sauvegarde** + **au render** (idempotent → couvre aussi les anciennes notes legacy avec junk Unicode déjà persisté, sans migration JSON).

**Regex** :
1. Retire chars Mathematical Alphanumeric Symbols : `[\u{1D400}-\u{1D7FF}]/gu`
2. Retire invisibles : ZWSP, ZWNJ, ZWJ, FUNCTION APPLICATION, INVISIBLE TIMES, INVISIBLE SEPARATOR, INVISIBLE PLUS, BOM
3. Collapse whitespace multiples (`\s+` → ` `)
4. Trim final

### Test sur le sample du user

```
IN  : "La règle du DEMUX12 est : la sortie \n𝑌\n𝑖\nY \ni\n​\n  vaut \n𝐸\nE
       si \n𝑆\n𝐸\n𝐿\n=\n𝑖\nSEL=i, et 0 sinon."

OUT : "La règle du DEMUX12 est : la sortie Y i vaut E si = SEL=i, et 0 sinon."
```

Lisible, copiable, citable. **Tradeoff assumé** : pas de KaTeX rendu (`Y_i` devient `Y i`), mais propre.

### Suppressions

- Bouton 📖 Source ↔ 📝 Sélection (et toute la logique 2 modes de v15.7.26).
- CSS `.note-text-raw` / `.note-text-rendered` (devenus inutiles).
- Plus d'envoi `raw_text` côté frontend : le backend l'accepte toujours mais ignore (rétrocompat passive, pas de bump schema).

### Conservé

- Highlight persistant `<mark.saved-note-mark>` au save (v15.7.26) : fonctionne toujours.
- Cleanup `<mark>` au delete de la note via `parentNode.insertBefore` + `normalize()`.

### Fichiers touchés

- `_scripts/web/static/app.js` : helper `_cleanupKatexSelection()` + applied au save + applied au render
- `_scripts/web/static/style.css` : suppression des styles 2 modes
- `README.md` : section « Cleanup KaTeX automatique » dans le bloc Notes
- `CHANGELOG.md` : cette entrée
- `CLAUDE.md` : entrée brève Phase v15.7.28

307/307 tests OK inchangés.

---

## Phase A.7.2 v15.7.27 : Cache-bust dynamique sur les assets (2026-05-10, hotfix)

**Bug observé** : v15.7.26 livrait le code `raw_text` côté frontend, mais le user a sauvé 4 nouvelles notes après le push avec `raw_text=null` ET `message_id=null`. Diagnostic en lisant `_sessions/2026-05-10_EN1_CC2_exfull.json` : son browser cachait l'ancien `app.js` v15.7.25 (sans le code v15.7.26).

### Fix

`@app.context_processor` Flask qui expose `static_v(filename)` → `?v=<mtime>` aux templates. `index.html` versionné dynamiquement :

```html
<link rel="stylesheet" href="/static/style.css{{ static_v('style.css') }}">
<script src="/static/app.js{{ static_v('app.js') }}"></script>
```

Le browser revalide quand le fichier change réellement (mtime auto-géré par git checkout), pas de bump manuel.

### Bug introduit + fix immédiat

Première version cassait l'interface : `index()` utilisait `send_from_directory` (= fichier statique brut, pas d'interpolation Jinja). Le browser recevait l'URL littérale `/static/style.css{{ static_v('style.css') }}` → 404 → CSS perdu.

**Fix** : `render_template("index.html")` + import `render_template` depuis `flask`. `mobile.html` garde `send_from_directory` (pas de balise Jinja dedans, asset self-contained).

Vérification après fix : la page rendue contient maintenant `/static/style.css?v=1778423147` et `/static/app.js?v=1778423121` au lieu des balises littérales.

### Workaround pour la session du user

Ctrl+F5 (hard reload) pour la fois courante. Après ce push : plus jamais ce piège, pour aucun deploy futur.

307/307 tests OK inchangés.

---

## Phase A.7.2 v15.7.26 : Notes : raw_text source + highlight persistant (2026-05-10)

**Bug observé** : sauvegarder une sélection contenant du LaTeX (formule rendue par KaTeX) ou du markdown gras/italique donne un affichage cassé dans le panneau 🔖 Notes. Exemple concret depuis la session EN1 CC2 :

```
Sélection visuelle : « La règle du DEMUX12 est : la sortie Yi vaut E si SEL=i, et 0 sinon. »
selection.toString() :
  "La règle du DEMUX12 est : la sortie \n𝑌\n𝑖\nY \ni\n​\n  vaut \n𝐸\nE si \n𝑆\n𝐸\n𝐿\n=\n𝑖\nSEL=i, et 0 sinon."
```

Les chars Unicode mathématiques (`𝑌`, `𝐸`, `𝐿`) + ZWSP (`​`) + retours à la ligne intercalés sont ce que `getSelection().toString()` capture du DOM KaTeX rendu. Inutilisable pour ré-afficher proprement.

**Demande secondaire** (reformulée par Gstar : *« je pensais que tu avais dis qu'après selection et save ça soit surligné j'aimais bien ça, surligne donc »*) : highlight visuel persistant de la phrase sauvegardée dans la bulle source, pas seulement un flash temporaire au scroll-back.

### Livré

#### 1. `raw_text` capturé au save

- Frontend (`_handleSelectionAction`) : envoie aussi `raw_text: info.bubbleEl.dataset.rawText` (le source markdown brut de la bulle complète, déjà stocké au render initial du turn).
- Backend (`POST /api/saved_selections`) : champ optionnel `raw_text`, capé silencieusement à 10 000 chars, persisté dans `saved_selections[i].raw_text`.
- Schéma additif compatible : pas de bump de `schema_version` (le champ vaut `null` pour les notes pré-v15.7.26).

#### 2. Panneau Notes : affichage 2 modes

- **Mode brut** (par défaut, `<pre class="note-text-raw">`) : affiche `selection.toString()` tel quel, dans une boîte mono lisible. L'user voit fidèlement ce qu'il a sélectionné (chars KaTeX inclus, mais lisibles en mono).
- **Mode rendu** (toggle bouton `📖 Source`) : affiche `renderMarkdown(raw_text) + renderMathIn()` du source complet de la bulle. KaTeX et markdown corrects.
- Bouton `📖 Source` ↔ `📝 Sélection` switch les deux. Bouton absent si `raw_text === null` (anciennes notes).

#### 3. Highlight persistant

- Au save : tente `range.surroundContents(<mark class="saved-note-mark" data-sel-id="...">)`.
- CSS : fond jaune doux `rgba(255, 235, 80, 0.32)` + soulignement pointillé jaune.
- Au delete de la note : retire les `<mark>` du DOM via `parentNode.insertBefore` + `normalize()`.
- Best-effort : si la sélection traverse plusieurs nœuds (cas typique sur du KaTeX multi-spans), `surroundContents` lève `DOMException` → swallow + log debug. La note est sauvée, juste sans highlight visuel.

### Limitations connues (à voir si bloquant)

- Le highlight persiste tant que la bulle est dans le DOM, mais ne survit pas à un reload complet de la page (la liste des selection_ids n'est pas re-appliquée au render initial du transcript). Si demandé : ajouter une passe `_reapplySavedHighlightsAfterTranscriptRender` qui re-fait le matching texte.
- `surroundContents` foire silencieusement sur sélections multi-nœuds. Pour un fix robuste : approche `extractContents` + wrap, ou overlay CSS positionné sur les rects.

### Tests

3 nouveaux tests dans `test_app_saved_selections.py` :
- `test_post_with_raw_text` : raw_text accepté + persisté
- `test_post_without_raw_text_default_none` : backward-compat (champ `null` si absent)
- `test_post_raw_text_capped_at_10000` : cap silencieux, pas 400

**307/307 tests OK**.

### Fichiers touchés

- `_scripts/web/app.py` : champ `raw_text` au POST, cap 10 000 chars
- `_scripts/web/static/app.js` :
  - `_handleSelectionAction` envoie `raw_text` + tente `surroundContents` highlight
  - `refreshSavedNotes` : 2 modes d'affichage + bouton toggle + cleanup `<mark>` au delete
- `_scripts/web/static/style.css` : `.note-text-raw`, `.note-text-rendered`, `mark.saved-note-mark`
- `tests/test_app_saved_selections.py` : 3 tests raw_text

---

## Phase A.7.2 v15.7.25 : Fix résumé reprise obsolète + Gemini Flash forcé (2026-05-10)

**Bug observé EN1 CC2 (97 tours)** : Gstar reload la page après une longue session. Le tuteur dit *« Nous étions sur l'exercice 1, mais vous abordez l'exercice 2. »* alors que le dernier message Compagnon avant le reload portait clairement sur l'**exercice 2 (DEMUX14)**, pas l'exo 1. Le résumé de reprise est figé sur un état ancien.

### Cause

`resume_session` (ligne 4480) : `summary = data.get("resume_summary")` puis `if not summary: regen`. Si le cache existe (résumé déjà calculé à un moment précédent), il est utilisé tel quel **sans vérifier s'il est obsolète**. Or des tours sont ajoutés en continu après chaque échange, et le résumé n'est jamais invalidé.

Inspection de la session : `resume_summary_at` cache un résumé qui dit *« Arrêt : exercice 1, question 1.1 forme étendue »*, mais les 60+ tours suivants ont fait passer à l'exo 2 sur le DEMUX14.

### Livré

#### 1. Invalidation du cache obsolète

```python
summary = data.get("resume_summary")
summary_at = data.get("resume_summary_at")
if summary and summary_at and transcript:
    last_msg = transcript[-1]
    last_at = (last_msg.get("at") or "").strip()
    if last_at and last_at > summary_at:
        logger.info("resume_summary obsolète (...) : regen")
        summary = None
```

Comparaison ISO 8601 lexicographique (qui marche pour les timestamps `YYYY-MM-DDTHH:MM:SS+00:00`). Si le dernier message du transcript est postérieur au résumé caché, on régénère. Coût marginal : ~1-2s sur Gemini Flash quand le résumé doit vraiment être refait.

#### 2. Gemini Flash forcé pour le résumé

`_generate_resume_summary` utilisait l'engine courant de la session (typiquement CLI subscription Opus, ou Anthropic API). Sur Opus, un résumé de 97 tours peut prendre **5-10 secondes** : délai désagréable au reload alors que c'est juste un résumé textuel sans raisonnement complexe nécessaire.

**Force désormais `gemini_api` + `gemini-2.5-flash`** (pattern aligné sur `/api/refine_search_query` v15.7.14, `/api/ocr_photo` v15.7.20). Latence ~1-2s, coût négligeable, cohérent quel que soit le moteur de séance.

#### 3. Prompt enrichi

Ajout au user_msg : *« ATTENTION : si l'étudiant a abordé plusieurs exercices (ex 1, puis ex 2), focalise-toi sur le DERNIER en cours, pas le premier. Le tuteur va reprendre à partir du dernier point d'arrêt. »*, ceci pour éviter qu'au lieu de focaliser le résumé sur l'état courant (exo 2), Gemini ne fasse une synthèse globale qui valoriserait le passage par l'exo 1 et perdrait le pointer actuel.

#### 4. Cache obsolète de la session courante invalidé manuellement

Pour que Gstar puisse immédiatement bénéficier du fix sans attendre une nouvelle session : `resume_summary` et `resume_summary_at` mis à `null` dans `_sessions/2026-05-10_EN1_CC2_exfull.json` via opération directe. Au prochain reload, regen complet via Gemini Flash avec le nouveau prompt sur les 97 tours.

### Tests

304 tests OK inchangés (aucun test ne couvre `_generate_resume_summary` directement : feature ajoutée Phase A sans test, à étendre plus tard si besoin).

---

## Phase A.7.2 v15.7.24 : 3 fixes : tone-toolbar grisée après modify + transcription écrase suppression user + crop mobile zones rikiki (2026-05-10)

3 bugs signalés par Gstar en cours de session, fix groupé.

### Bug 1 : Tone-toolbar grisée après « 🎛 Modifier ▾ → preset »

**Symptôme** : après un click sur un preset Modifier (ex « 📖 Avec exemple »), les boutons sous CETTE bulle (🔍 Exo voisin / 📚 Passage CM / 🎬 Vidéo / 🌐 Internet) restent grisés/curseur tournant à vie. Sur les autres bulles ils marchent.

**Cause** (`app.js:483`) : le click handler du preset désactive tous les boutons de la toolbar (`toolbar.querySelectorAll("button").forEach(b => b.disabled = true)`) pour éviter le double-click, mais nulle part les boutons ne sont re-enabled. Les nouvelles bulles Compagnon créées par `streamResponse()` ont leur propre toolbar fonctionnelle, c'est juste celle de la bulle d'origine qui restait coincée.

**Fix** : `await sendMetaInstruction(...)` dans le handler avec un `try/finally` qui re-enable les boutons. Comme `sendMetaInstruction` resolve dès que `streamResponse()` est lancé (= juste après le POST `/api/send_message` retourne), la toolbar est restaurée immédiatement (l'utilisateur peut cliquer 🔍 / 🎬 / etc. pendant que la réponse stream).

### Bug 2 : Transcription Whisper écrase la suppression user pendant le call

**Symptôme** : utilisateur enregistre vocal via 🎤. Pendant que Whisper transcrit (~1-3s), l'utilisateur efface l'input pour reformuler manuellement. Au retour de Whisper, l'ancien texte revient écrasant ce que l'utilisateur voulait effacer.

**Cause** (`app.js:3642`) : `userInputBeforeRecording` est snapshotté au start de l'enregistrement. À la fin de la transcription, `userInput.value = prev + text` où `prev = userInputBeforeRecording`. Si l'utilisateur a touché à l'input entre temps, sa modif est ignorée.

**Fix** : compare `userInput.value.trim()` actuel à `userInputBeforeRecording.trim()`. Si différent → l'utilisateur a modifié → utilise sa version actuelle comme préfixe (qui peut être vide). Sinon → comportement legacy. Effacement total = transcription seule, ajout texte = concaténation correcte.

### Bug 3 : Crop sur mobile : taps accidentels cassent la zone

**Symptôme Gstar** : *« quand à l'extérieur par erreur je clique sur les bords noirs ben ça casse la sélection du recadrage et c'est chiant. Pareil quand c'est au bord noir y'a des moments où la sélection s'écrase, ça fait un petit bout sélectionné. Si tu touches pas le petit bout carré bleu, ça peut casser ma sélection. »*

**Cause** : depuis v15.7.16, j'ai mis `dragMode: "crop"` sur Cropper.js pour permettre de glisser sur l'image et redessiner la zone (handles 5×5 trop petits sur mobile). Mais avec ce mode, **n'importe quel tap sur l'image redessine une zone**. Sur mobile, taps accidentels (intercept doigt, scroll furtif, gros pouce) → mini-zone d'1 pixel → l'utilisateur perd sa sélection en cours.

**Fix** : nouveau helper `_cropperOptionsCommon()` (Compagnon `app.js`) et `_cropperOptsM()` (mobile.html Compagnon + Clipboard_Relay) qui :
- Détecte touch device : `(navigator.maxTouchPoints > 0) || ("ontouchstart" in window)`
- **`dragMode: "move"` sur touch device** (tap dans l'image déplace l'image, NE casse PAS la zone) ; **`"crop"` sur souris desktop** (glisser redessine librement, pas de tap accidentel à la souris)
- **`minCropBoxWidth: 50, minCropBoxHeight: 50`** : filet sécurité, la zone ne peut pas se réduire sous 50×50 px même si Cropper recevait un drag accidentel

Appliqué à 5 init Cropper :
- Compagnon `app.js` × 2 : `openCropModal` (re-crop attachment) + `_openImagePreviewBeforeUpload` (preview before upload)
- Compagnon `mobile.html` × 2 : `openCropModal` + `_openCropPreviewModalM`
- Clipboard_Relay `mobile.html` × 1 : capture+import handler

Tradeoff assumé : sur mobile, redessiner librement la zone n'est plus possible en glissant : il faut soit cliquer ↩ Reset puis ajuster les handles, soit garder la zone en cours et l'ajuster via les handles 18-22px (qui sont assez gros depuis v15.7.16). Compromis acceptable vu la friction du bug actuel.

### Tests

304 tests OK inchangés (3 fixes purement frontend, l'algo reste testable manuellement).

---

## Phase A.7.2 v15.7.23 : Sélection texte → popup contextuel (Save / Citer / Expliquer / Copier) + onglet 🔖 Notes (2026-05-10)

**Demande Gstar** : *« quand on selectionne un texte ou un bout de texte ou un tableau ou un schéma du message du Compagnon, y'ait des trucs qui apparaissent, ce que je veux le plus c'est save la phrase pour une prise de note ou un concept à pas oublier. Dans Docs j'imagine, mais si tu vois meilleur endroit tu me dis. Ça marche aussi sur mes propres messages, et click sur la note → redirige vers le message. »*

### Architecture

#### Nouveau onglet sidebar 🔖 Notes (entre 📚 Docs et 💬 Historique)

Plutôt que squatter l'onglet Docs (qui héberge déjà énoncé/corrigés/script depuis v15.7+), un onglet dédié plus clair. Si vide : message d'aide *« Aucune note. Sélectionne du texte dans une bulle (Compagnon ou toi-même) pour voir les options : 💾 Sauvegarder, 📋 Citer, 🤔 Expliquer, 📝 Copier. »*

#### Mini-popup flottant au-dessus de la sélection

`document.addEventListener("selectionchange", ...)` détecte les sélections (≥ 3 chars) à l'intérieur d'une bulle `.turn.claude` ou `.turn.student` (skip les bulles `system`). Un toolbar `#selection-toolbar` apparaît positionné au-dessus de la sélection (auto-bascule en dessous si en haut du viewport) avec 4 boutons :

| Action | Effet |
|---|---|
| **💾 Save** | POST `/api/saved_selections` → toast feedback + refresh onglet 🔖 Notes |
| **📋 Citer** | Insère `> texte\n\n` dans `userInput` (préfixe Markdown citation) |
| **🤔 Explique** | Insère `Peux-tu m'expliquer : "texte"` dans `userInput` (validation manuelle par Entrée) |
| **📝 Copier** | `navigator.clipboard.writeText(text)` + toast |

Auto-hide après 8s d'inactivité ou perte de sélection. `mousedown` preventDefault pour ne pas perdre la sélection au clic sur le toolbar.

#### Backend : 3 endpoints + persistance

- **POST `/api/saved_selections`** : body `{text, message_id?, role?}` → `{id, text, message_id, role, captured_at}`. Validation : text non vide, ≤ 5000 chars. Role default `"claude"` si manquant ou invalide.
- **GET `/api/saved_selections`** : `{selections: [...], active: bool}`.
- **DELETE `/api/saved_selections/<id>`** : 204 si trouvé, 404 sinon.
- Persistance dans `session_state.data["saved_selections"]` (additif, pas de bump schéma) → conservées en reprise de session.

#### Onglet 🔖 Notes : render

- Liste avec `[role + timestamp][texte][↪ Voir / 🗑]`. Bordure latérale colorée selon role (bleu `claude`, jaune `student`).
- **Click sur le texte ou ↪ Voir** → `_scrollToBubble(message_id)` : trouve la bulle via `.turn[data-msg-id="..."]`, scroll center, ajoute classe `note-highlight` qui anime un fond jaune léger 2.5s. Si la bulle n'existe pas dans le transcript courant (supprimée, autre session) : alerte explicite.
- Refresh automatique au switch sur l'onglet Notes (cf. `setupSidebarTabs`).
- `🔄` bouton de refresh manuel.

### Tests

12 nouveaux dans `test_app_saved_selections.py` : GET no-session / GET liste, POST no-session / text vide / text trop long (5001 chars) / happy path complet / role default claude / role student préservé / appends non-remplace, DELETE no-session / id inconnu (404) / suppression OK (204). **304 tests OK** (était 292).

### Roadmap (à voir si tu veux)

- **Highlight persistant** : la phrase sauvegardée reste teintée jaune léger dans la bulle source pour la repérer au scroll
- **Export Markdown** : bouton dans l'onglet pour copier toutes les notes au format `> citation` pour Anki/Obsidian
- **Tags** : libre par note pour organiser

---

## Phase A.7.2 v15.7.22 : Auto-preview Cropper avant upload (alignement UX Clipboard_Relay) (2026-05-10)

**Demande Gstar** : *« j'aime bien le fait qu'il y ait un aperçu pour rogner directement sans cliquer sur un icon. Il faudrait avoir la même ergonomie pour Compagnon de révision. »*

Avant cette phase, le workflow Compagnon pour cropper une photo était :
1. Photo arrive (📷 mobile, paste, drag-drop, 📎 file picker) → upload direct dans `pending_attachments`
2. Apparaît dans le tray
3. Click ✂ Rogner sur la thumbnail → ouvre modal Cropper → recadre → `POST /api/pending_attachments/<id>/replace`

→ 3 étapes, l'icône ✂ devait être trouvée et cliquée avant chaque crop.

Workflow `Clipboard_Relay v0.1.5` que Gstar préfère :
1. Photo arrive
2. **Modal Cropper s'ouvre AUTOMATIQUEMENT** (preview)
3. Recadrage / rotation / Envoyer tel quel / Annuler → upload du résultat

Aligné avec le mode colle exigeant : force l'utilisateur à recadrer **avant** envoi → moins de bordel autour de la table de vérité que le tuteur reçoit.

### Livré

#### Nouvelle modal pré-preview `#crop-preview-modal` (desktop)

`index.html` : nouvelle modal avec 6 boutons :
- 🗑 Annuler (skip upload)
- ↺ 90° / ↻ 90° (rotation)
- ↩ Reset (réinitialise crop)
- 📤 Envoyer tel quel (upload original sans modif, pour photos déjà clean)
- ✂ Recadrer & ajouter (upload du canvas cropped)

Distincte de `#crop-modal` qui sert au re-crop d'attachment déjà uploadé (Phase v15.7.10).

#### Frontend `app.js` : refactor `uploadAttachmentFile`

```js
async function uploadAttachmentFile(file) {
  if (!file) return null;
  // Phase v15.7.22 : pré-preview Cropper auto pour les images
  if (file.type && file.type.startsWith("image/")) {
    const previewResult = await _openImagePreviewBeforeUpload(file);
    if (previewResult === null) return null;  // user a annulé
    file = previewResult;  // soit cropped, soit l'original (Skip)
  }
  // ... upload comme avant
}
```

- `_openImagePreviewBeforeUpload(file) → Promise<File|null>` : ouvre la modal, attend le choix user, resolve avec le `File` final ou `null` si annulé.
- Tous les canaux d'upload passent par `uploadAttachmentFile` → couvre **automatiquement** : 📎 file picker, paste clipboard, drag-drop, 📷 mobile via `/mobile`.
- Non-images (PDF, Excel, etc.) : upload direct comme avant.

#### Multi-upload séquentiel

`handlePasteEvent` modifié : collecte d'abord tous les files puis `for await uploadAttachmentFile(f)` séquentiel. Sans ça, multi-paste ouvrirait plusieurs modals Cropper en même temps (race condition sur `cropPreviewResolve`).

Drag-drop et file picker `📎` étaient déjà séquentiels via `for f of files: await uploadAttachmentFile(f)`.

#### Page `/mobile` Compagnon : même pattern

`mobile.html` : nouvelle modal `#crop-preview-modal-m` (variante mobile plein écran avec touch handles, comme `#crop-modal` du mobile mais pour le mode preview avant upload). Helper `_openCropPreviewModalM(file) → Promise<File|null>`. `captureInput.change` modifié : si l'image, passe par cette modal AVANT `uploadOne`. Cohérence cross-device : workflow identique desktop / mobile.

### Tradeoffs assumés

- **+** Plus fluide, alignement UX Clipboard_Relay
- **+** Mode colle/photos : force le crop = moins de noise pour le tuteur
- **+** « Envoyer tel quel » accessible en 1 clic dans la modal pour les images déjà clean
- **−** +1 step pour les images déjà parfaites (mitigé par le bouton skip)
- **−** Multi-upload séquentiel : 5 modals successifs si tu drag-drop 5 photos. Cohérent avec le pattern « valider chaque photo », mais peut être lourd. Tu peux toujours skip rapidement chaque modal si pas envie de cropper.

### Tests

Aucun nouveau test (UX pure frontend). 292 tests OK inchangés.

### Note

L'icône ✂ Rogner dans le tray reste opérationnelle : utile pour re-cropper après-coup si tu changes d'avis sur le cadrage initial. Le pré-preview est juste un raccourci pour le cas commun.

---

## Phase A.7.2 v15.7.21 : Bouton ⏹ Annuler la réflexion du Compagnon en cours de stream (2026-05-10)

**Demande Gstar** : *« quand Compagnon réfléchit je dois être capable d'annuler sa réflexion en cours de route et soit qu'il reprenne ou soit rien du coup je supprime son msg pour recharger »*.

Distinct du Stop end-session (qui termine la séance entière) : c'est juste annuler **le tour courant** avec 2 options : reprendre où on en était (garder mon dernier message) ou tout supprimer (« comme si je n'avais rien envoyé »).

### Livré

#### Backend

- **`CompanionSession.cancel_requested: bool`** flag, reseté au démarrage de chaque nouveau stream dans `/api/stream_response`.
- **Nouveau `POST /api/cancel_stream`** : body `{action: "resume"|"delete_last_user"}` → set `cancel_requested = True`. Si `delete_last_user` : retire aussi le dernier message `role=user` du `client._history` ET le dernier message `role=student` du `current_branch_path` du transcript persisté (atomic write via `set_meta`). Retourne `{ok, action_applied, deleted_msg_id?}`.
- **Helper `_remove_last_student_message(session_state)`** : tronque `current_branch_path` à partir du dernier student trouvé, re-dérive le `transcript`, atomic write. L'objet du message reste dans `messages` (l'arbo branches conserve l'historique de toutes les modifs), juste retiré du chemin actif.
- **`_sse_generator` modifié** : `queue.get(timeout=0.5)` au lieu de bloquant + check `st.cancel_requested` à chaque tick. Si flag set → yield `event: cancelled` au front et return immédiat. Le sub-process LLM peut continuer en background quelques secondes : on accepte le coût des tokens consommés (compromis simplicité vs `subprocess.kill()` qui demanderait un check par moteur).

#### Frontend

- **`setStreamingUI(streaming: boolean)`** : pendant un stream, le bouton Send devient **`⏹ Annuler`** (rouge, animation pulse). Mémorise le texte original via `dataset.originalText` pour restaurer à la fin. Désactive aussi 📎 / 📷 / ✨ pendant le stream (pas de sens d'attacher de nouveaux fichiers ou reformuler tant que le tuteur n'a pas fini).
- **`isStreamingActive()`** : vrai si `currentEventSource !== null`.
- **`cancelStream(action)`** : ferme le SSE côté client, set l'UI propre, retire la bulle Compagnon partielle du DOM (et la bulle student si `delete_last_user`), POST `/api/cancel_stream` au backend (best-effort, ne bloque pas l'UI).
- **`openCancelStreamModal()`** : modal créée à la volée en JS pur (pas de HTML pré-existant). 3 options :
  - **↩ Reprendre (garder mon message)** → `cancelStream("resume")`
  - **🗑 Supprimer mon message** → `cancelStream("delete_last_user")`
  - **← Retour (continuer la réflexion)** → ferme la modal sans rien annuler (utile si le user a cliqué par erreur). Click outside = same.
- **`_onSendClickRouter()`** : intercepte le click sur Send (et `Enter` dans le textarea). Si stream actif → ouvre la modal. Sinon → flux d'envoi normal.
- **Listener `event: cancelled`** dans `streamResponse` : reset l'UI proprement quand le serveur a confirmé l'annulation côté backend.

#### CSS

- `#send-btn.cancel-mode` : rouge `var(--err)` + animation `pulse-cancel` 1.4s pour attirer l'œil.
- `#cancel-stream-modal.modal-overlay` : modal lightbox centrée, 3 boutons empilés verticalement (secondary bleu = Reprendre, danger rouge = Supprimer, cancel transparent = Retour). Click outside = back.

### Tests

6 nouveaux dans `test_app_cancel_stream.py` : action invalide → 400, pas de session → 409, action=resume flag set + history/transcript intacts, action=delete_last_user retire du _history client ET du transcript (vérification du `current_branch_path` tronqué + transcript dérivé), pas de student dans le path → ok silencieux, action default (absente) = resume. **292 tests OK** (était 286).

### Note

Si tu cliques ⏹ pendant que le tuteur est encore en pleine génération, l'appel LLM (Anthropic / CLI / Gemini / OpenAI) peut continuer à tourner quelques secondes en background : tes tokens sont consommés quoi qu'il arrive sur le tour. C'est un compromis assumé pour la simplicité (vs ajouter un mécanisme `subprocess.kill()` ou cancel API par moteur). L'important est que tu voies l'arrêt immédiatement côté UI et que tu puisses reprendre proprement.

---

## Phase A.7.2 v15.7.20 : OCR pré-vérifié Gemini Flash 2.5 + LaTeX rendu sur student (2026-05-10)

**Frictions Gstar (2 en 1)** :

1. *« y'a des soucis avec l'ocr parfois du coup je suis passer sur gemini 3.1 flash depuis aistudio.google.com et je lui ai demandé une ocr il a pu bien me le faire »* : la consigne §1.6 v0.5 (forcer le tuteur à exposer son OCR avant jugement) tient sur certains tours mais pas tous. Gemini 2.5 Flash dédié à l'OCR donne des résultats plus fiables que le tuteur principal qui a aussi du raisonnement pédagogique à faire en parallèle.
2. *« quand je poste du latex même si je ne suis pas compagnon, que ça applique le markdown »* : les bulles student affichaient le markdown brut (`$f(x) = x^2$` non rendu). Bug pur, aucune raison pédagogique.

### Décision archi (point 1)

Pré-traitement OCR par un moteur dédié (Gemini Flash 2.5) AVANT envoi au tuteur principal. Pattern identique à v15.7.14/v15.7.15 (refine_search_query forcé Gemini Flash) :
- Latence ~1-2s, coût ~$0.0001-0.0005 par photo (négligeable)
- L'OCR est exposé à 2 destinataires :
  - **Le tuteur** (injecté dans son contexte comme bloc « [OCR pré-traitée par Gemini Flash 2.5 : vérifie qu'elle correspond à ta lecture, sinon dis-le et signale la divergence] »). Le tuteur fait sa propre lecture multimodale ET compare.
  - **L'étudiant** (collapsible `<details>` sous la bulle student avec « 🔍 OCR pré-vérifié par Gemini Flash · type · complétude X% · Y warnings »). Auto-ouvert si warnings ou completeness < 80%. L'étudiant peut contester.
- **Double check par 2 moteurs indépendants** = robustesse réelle. Si les 2 sont d'accord = haute confiance. Si désaccord = signal explicite à l'étudiant.

### Livré

#### Backend

- **Nouveau endpoint `POST /api/ocr_photo`** (244 LOC) : body `{attachment_id, hint?}` → `{ocr_markdown, kind_detected, completeness_pct, warnings, engine: gemini_api, model: gemini-2.5-flash}`. Engine forcé Gemini Flash via `_run_isolated_lookup(engine_override="gemini_api", model_override="gemini-2.5-flash")`. Sortie balisée `<<<OCR>>>{json}<<<END>>>`.
- **`OCR_PHOTO_PROMPT`** : system prompt dédié avec exemples inline (table de vérité 8 lignes colonne S vide → `(vide)` partout, équation manuscrite → LaTeX, calcul incomplet → ligne par ligne avec ratures). Marqueurs explicites `(vide)` / `(illisible)` / `(raturé)`. Détecte le `kind_detected` parmi `{table_de_verite, schema_logique, calcul_pose, equation, dessin, pseudo_code, texte, autre}` et estime `completeness_pct` (cellules / éléments remplis vs total attendu).
- **Helper `_ocr_attachment_internal(att, hint)`** réutilisable pour appeler l'OCR depuis n'importe où en interne. Best-effort : aucune exception remontée (sinon ça bloquerait l'envoi du message au tuteur).
- **Intégration dans `/api/send_message`** : quand mode colle ET `colle_format ∈ {photos, mixte}` ET au moins une image dans `pending_attachments`, lance OCR Gemini Flash pour chaque image AVANT de finaliser `pending_user_text`. Hint = dernière réplique du tuteur (orientation `kind_detected`). Bloc OCR injecté dans le `text` envoyé au tuteur. Réponse 202 enrichie de `ocr_blocks: [...]` pour le frontend.

#### Frontend

- **`_appendOcrCollapsibleBlock(turnContainer, blk)`** : ajoute un `<details class="ocr-collapsible">` sous la bulle student. Auto-ouvert si warnings ou completeness < 80% (attire l'œil sur les cas suspects). Markdown rendu avec KaTeX pour les équations dans l'OCR.
- CSS dédié dans `style.css` : bloc teinté bleu accent, summary cliquable avec triangle natif, warnings teintés orange si présents, body monospace pour tables avec scroll horizontal mobile, hint italique « Si cet OCR ne correspond pas à ce que tu as écrit, signale-le au Compagnon dans ton prochain message ».

#### Bonus point 2 : `renderMathIn` étendu aux bulles student

3 spots fixés :
- `sendUserMessage` (ligne ~1870) : `renderMathIn(t)` après `renderMarkdown(displayText)` pour les nouvelles bulles student.
- `rerenderDialogueFromTranscript` (ligne ~2596) : retiré la condition `if (role === "claude")` autour de `renderMathIn`. Gardé pour `linkifyPageRefs` et `appendToneToolbar` (uniquement pertinent claude).
- Édition in-place (ligne ~2736) : retiré la condition `if (role === "claude")` autour de `renderMathIn`.

Conséquence : `$x^2 + 1$` posté par l'étudiant rend KaTeX comme dans les bulles Compagnon.

### Tests

8 nouveaux dans `test_app_ocr_photo.py` : attachment_id manquant → 400, pas de session → 409, attachment inconnu → 404, attachment non-image → 400, happy path retourne ocr_markdown + kind + completeness + warnings, **engine Gemini + model Flash forcés peu importe la pref user**, ocr_markdown vide → 502, warnings cappés à 10. **286 tests OK** (était 278).

### Notes

- L'endpoint `/api/ocr_photo` est public (pas d'usage frontend pour l'instant en standalone, l'OCR est lancé automatiquement par `/api/send_message`). Réservé pour un éventuel bouton 🔍 « Re-OCR » dans le tray ou une UI manuelle future.
- L'intégration dans `send_message` ne cassera AUCUNE session legacy : si Gemini échoue ou pas de clé `GEMINI_API_KEY`, le bloc OCR est juste absent du message envoyé au tuteur (qui voit toujours l'image en multimodal natif depuis v15.7.18). Mode dégradé gracieux.

---

## Phase A.7.2 v15.7.19 : Protocole OCR obligatoire dans §1.6 « Quand la photo arrive » (2026-05-10)

**Friction observée par Gstar EN1 CC2 (tour 15→17)** : photo de table de vérité étendue à 8 lignes envoyée, la colonne S était **entièrement vide** (Gstar venait juste de poser le squelette). Le tuteur a répondu :

> *« Vérification ligne par ligne de votre photo :
> - SEL=0, E0=0, E1=0 → S=0 ✓
> - SEL=0, E0=0, E1=1 → S=0 ✓ (E1 ignoré)
> - …
> - SEL=1, E0=1, E1=1 → S=1 ✓
>
> **Table correcte.** »*

Hallucination classique des LLM multimodaux face à un objet structuré partiellement rempli : le tuteur a reconnu visuellement le tableau « table de vérité MUX21 », **a complété mentalement les cellules vides** avec les valeurs attendues, et a déclaré la table correcte. Au tour 16, Gstar lui fait remarquer : *« Mais comment peux-tu me dire que c'est correct alors que je n'ai rien rempli dans la colonne S ? »*, et le tuteur avoue (tour 17) *« Vous avez raison, je me suis trompé. La colonne S est vide sur votre photo, je l'ai remplie mentalement au lieu de la lire. **Faute professionnelle**. »*

C'est exactement l'opposé du mode colle (rigueur, refus du flou, validation strictement basée sur ce que produit l'étudiant). Si Gstar n'avait pas relevé, il serait parti convaincu d'avoir bon le jour J.

### Décision archi : protocole OCR obligatoire dans le prompt

Pas de tool OCR séparé (le LLM multimodal fait déjà l'OCR mentalement). Solution : **le forcer à exposer son OCR** avant tout jugement, dans la même réponse, pour que l'étudiant puisse vérifier que la lecture est correcte.

### Livré

`PROMPT_SYSTEME_COMPAGNON.md` v0.4 → **v0.5** : §1.6 sous-paragraphe « Quand la photo arrive » réécrit en **protocole 2-étapes** :

**Étape 1 : OCR explicite affiché à l'étudiant** : la réponse doit commencer par un bloc `📸 Ce que je lis dans votre photo :` qui reproduit case par case / ligne par ligne ce qui est effectivement visible. Format adapté selon le type d'objet :
- Table de vérité : tableau Markdown avec **toutes les cases**, marqueurs `(vide)` / `(illisible)` pour cases incomplètes
- Schéma logique : énumération des composants visibles + connexions
- Calcul posé : reproduction ligne par ligne (avec ratures, hésitations)
- Dessin / graphe : axes, courbes visibles, annotations
- Pseudo-code : reproduction lignes telles qu'écrites

**Étape 2 : Jugement** : seulement après l'OCR, sous le bloc `Vérification :`. La validation s'appuie strictement sur ce qui a été lu, pas sur ce qui est attendu.

**4 garde-fous** :
1. **≥30 % de cases vides** sur objet supposé complet → refus de juger : *« Photo trop incomplète pour valider. Complétez et renvoyez. »*
2. **Case ambiguë** (raturée, floue, photo coupée) → demande de clarification avant jugement.
3. **N'INFÉREZ JAMAIS** une valeur depuis ce qui est attendu : *« si vous validez une case vide « parce qu'elle aurait dû être 1 », vous le ratez à son CC »*.
4. Photo hors-sujet → dire directement, pas d'OCR détaillé inutile.

**Exemple de réponse correcte** inclus dans le prompt (cas EN1 CC2 colonne S vide) pour ancrer le format attendu.

### Bénéfices observables

- **Transparence** : l'étudiant voit en clair ce que le tuteur a lu. Si l'OCR est faux (genre « j'ai lu (vide) alors que j'ai écrit 1 »), il peut corriger immédiatement plutôt que recevoir un jugement basé sur une lecture erronée.
- **Anti-hallucination** : forcer la verbalisation case par case empêche la complétion automatique mentale. Le LLM ne peut plus dire « table correcte » sans avoir explicitement listé les valeurs lues.
- **Pédagogie préservée** : le mode colle reste exigeant, c'est l'étudiant qui doit produire la bonne réponse.

### Tests

1 nouveau test de doctrine `test_protocole_ocr_photo_v15_7_19` dans `test_app_colle_format.py` qui assert que le prompt contient `📸 Ce que je lis dans votre photo`, `N'INFÉREZ JAMAIS`, `(vide)`, et `30 %`. Casse si quelqu'un assouplit le protocole lors d'un futur refactor. **278 tests OK** (était 277).

---

## Phase A.7.2 v15.7.18 : Multimodal natif (base64) pour Anthropic API + Gemini + OpenAI-compat (2026-05-10)

**Friction signalée par Gstar** : v15.7.17 a fixé le cas `cli_subscription` (en autorisant `Read`), mais le bug subsisterait sur les autres engines (`api_anthropic`, `gemini_api`, `deepseek_api`, `groq_api`). Réponse : « Ben ça risque d'arriver donc fais le. ».

### Cause générale

Tous les engines reçoivent l'historique sous forme `{role: user, content: "Ma photo : ![photo](EN1/CC/photos/x.jpg)"}` (string brut). Aucun ne savait extraire l'image et la passer en multimodal natif. Conséquence : le LLM voyait juste une URL/path en texte, sans pouvoir voir l'image.

### Architecture livrée

#### 1 helper module-level + 3 transformations spécifiques

**`_extract_inline_images(text, cours_root)`** : Parse les `![alt](path)` du texte avec regex `/!\[([^\]]*)\]\(([^)]+)\)/`. Pour chaque match :
- Résout le path (absolu, sinon relatif à `cours_root`)
- Vérifie l'extension dans `_IMAGE_MEDIA_TYPES = {.jpg/.jpeg → image/jpeg, .png → image/png, .gif, .webp, .heic}`
- Vérifie la taille ≤ `_MAX_IMAGE_BYTES = 5 MB` (cap raisonnable photo téléphone HD)
- Lit les bytes, encode en base64
- Remplace dans le texte par un placeholder `[image: <alt>]` (aide le LLM à savoir où l'image se rattache dans le flux)
- Skip silencieux + log warning si fichier manquant / extension non supportée / taille excessive

Retourne `(text_without_images, images: list[dict])`.

**3 helpers de transformation par moteur** :

| Helper | Format de sortie |
|---|---|
| `_messages_to_anthropic_multimodal(history, cours_root)` | `{role: user, content: [{type:text}, {type:image, source:{type:base64, media_type, data}}]}` |
| `_messages_to_openai_multimodal(history, cours_root)` | `{role: user, content: [{type:text}, {type:image_url, image_url:{url:"data:image/jpeg;base64,..."}}]}` |
| `_messages_to_gemini_parts(history, cours_root)` | `{role: user|model, parts: [{text}, {inline_data:{mime_type, data: bytes}}]}` (assistant → model translation) |

Chaque helper passe les messages text-only inchangés, et ne mute pas `_history` (transformation à la volée au moment du call API).

#### Intégration dans les 3 méthodes `_stream_via_*`

- `_stream_via_api` (Anthropic) : `messages_for_api = _messages_to_anthropic_multimodal(self._history, self._cours_root)` au lieu de `messages = self._history`.
- `_stream_via_gemini` : `gemini_contents = _messages_to_gemini_parts(...)` au lieu de la conversion ad-hoc précédente.
- `_stream_via_openai_compatible` : `messages.extend(_messages_to_openai_multimodal(...))` au lieu de `messages.extend(self._history)`.
- `_stream_via_cli` (CLI subscription) : **PAS modifié** : utilise déjà le tool `Read` autorisé en v15.7.17.

### Notes par engine

- **Anthropic API** : multimodal natif depuis Claude 3 (toutes les versions actuelles). Le tuteur voit la photo et la commente directement.
- **Gemini API** : multimodal natif depuis Gemini 1.5+. `inline_data` accepte les bytes bruts (pas base64). On décode au moment de la transformation.
- **DeepSeek-V3** (`deepseek-chat`) : **text-only**, ignore silencieusement les blocs `image_url` envoyés. Pas une erreur, juste pas de vision. Si tu veux Gemini comme fallback automatique pour les sessions avec photos, c'est une feature future à demander.
- **Groq llama-3.3-70b-versatile** (défaut) : **text-only** aussi. Les variantes vision de Groq (`llama-vision-*`, `llava-*`) liraient les images si tu changes le modèle via env `GROQ_MODEL`.

### Tests

13 nouveaux dans `test_claude_client_multimodal.py` :
- `_extract_inline_images` (7 cas) : pas d'image, single, fichier manquant, extension non supportée, image > 5 MB, multiples images dans 1 texte, path absolu
- `_messages_to_anthropic_multimodal` (3 cas) : text-only inchangé, transformation user, assistant non transformé
- `_messages_to_openai_multimodal` (1 cas) : format data URI correct
- `_messages_to_gemini_parts` (2 cas) : translation assistant → model, inline_data avec bytes bruts

**277 tests OK** (était 264, +13).

Pas de tests d'intégration multimodal (mocker anthropic/google.genai/openai serait fragile pour le ratio bénéfice/coût). Validation manuelle requise : envoie une photo en mode colle sur chaque engine que tu veux tester.

---

## Phase A.7.2 v15.7.17 : Mode colle : autoriser `Read` scopé à COURS_ROOT (pour les photos attachées) (2026-05-10)

**Friction signalée par Gstar pendant son CC2 EN1** : envoi d'une photo de table de vérité depuis le mobile, le tuteur répond *« J'examine votre photo. Je n'arrive pas à ouvrir votre photo (permission de lecture refusée sur le fichier). Autorisez l'accès au dossier `photos/` ou renvoyez la photo, je ne peux pas valider à l'aveugle. »*

### Cause racine

Le user est sur engine `cli_subscription` (Claude CLI via subprocess). Le mode `colle` lance `claude --print` **sans `--allowedTools`** (par design originel : pas d'accès filesystem pour respecter la posture « pas de fouinage »). Quand le backend injecte `![photo](EN1/CC/...path.jpg)` dans le user message, la CLI Claude essaie d'utiliser le tool `Read` pour voir l'image en multimodal, mais elle n'a pas le tool → permission refusée propagée au tuteur, qui le rapporte à l'étudiant. Bug fonctionnel depuis Phase A (jamais testé en colle + photo avant aujourd'hui).

### Décision archi

Compromis : autoriser **`Read` UNIQUEMENT** (pas Grep/Glob qui permettraient l'exploration libre) en mode colle quand `cours_root` est défini. Le tuteur peut désormais lire les fichiers **EXPLICITEMENT cités** par l'étudiant (image attachée via 📷/📎, PDF en pièce jointe), mais ne peut **pas** fouiller l'arbo des cours librement. Alignement pédagogique préservé : pas de spoiler de corrigé, pas de divagation hors-énoncé.

### Livré

- `claude_client.py` `_stream_via_cli_subprocess()` : ajout d'une branche `elif self._mode == MODE_COLLE and self._cours_root is not None: cmd += ["--allowedTools", "Read"]; cwd = str(self._cours_root)`. Comparé à `MODE_GUIDE` qui ouvre `GUIDE_ALLOWED_TOOLS = "Read,Grep,Glob"`.
- `cwd` posé à `cours_root` même en mode colle pour que les paths relatifs (`EN1/CC/2025-26/CC2/photos/...`) résolvent.
- 264 tests OK inchangés (aucun test ne reposait sur l'absence de `--allowedTools` en mode colle).

### Note sur les autres engines

Ce fix concerne **uniquement `cli_subscription`** (le seul engine actuel testé sur les photos en colle). Pour `api_anthropic`, `gemini_api`, `deepseek_api`, etc., il faudrait passer les images en multimodal natif (`{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "..."}}` pour Anthropic) au lieu d'injecter le markdown texte. **Pas implémenté** : sera nécessaire si Gstar bascule sur API en cours de séance avec photos. Si ce cas arrive, signal explicite et fix v15.7.18.

---

## Phase A.7.2 v15.7.16 : Modal crop : boutons rotation 90° + dragMode crop + handles tactiles (2026-05-10)

**Frictions signalées par Gstar (2 en 1)** :

1. *« parfois je prends ma photo de manière horizontale au lieu de vertical sans le faire exprès, faut une option pour pouvoir retourner la photo »*
2. *« le glissement à la main sur mobile ne fonctionne pas tjr je sais pas si ça vient de mon téléphone mais j'ai un peu du mal pour recadrer, je suis obligé de m'y reprendre plusieurs fois pour enfin pouvoir select le bon et rogner l'image »*

### Causes

1. **Pas de bouton rotation** dans le modal crop (j'avais activé `checkOrientation: true` qui respecte l'EXIF, mais l'EXIF est faux quand le téléphone est tenu de travers : le capteur n'a pas eu le temps de calibrer l'orientation). Pas de fix manuel possible avant ce patch.
2. **`dragMode: "move"`** dans la config Cropper.js (mon choix v15.7.10) : ce mode déplace l'IMAGE quand on glisse, et force à utiliser les handles (5×5 px par défaut) pour redessiner la zone de recadrage. Sur mobile, des handles 5×5 sont **impossibles à attraper au doigt** sans plusieurs tentatives. Erreur de design v15.7.10.

### Livré

#### Boutons rotation 90° (desktop + mobile)

- **Desktop** (`index.html` modal `#crop-modal`) : 2 boutons `↺ 90°` et `↻ 90°` insérés dans `.crop-actions` entre Annuler et Reset.
- **Mobile** (`mobile.html` modal `#crop-modal`) : nouvelle rangée dédiée `.crop-rotate-row-m` au-dessus des actions principales, 2 boutons touch-friendly (48px de haut). Évite de surcharger la rangée Annuler/Reset/Recadrer déjà étroite.
- `app.js` + script `mobile.html` : event listeners → `cropperInstance.rotate(-90)` ou `cropperInstance.rotate(90)`. API native Cropper.js, rien d'inventé.

#### `dragMode: "crop"` au lieu de `"move"`

`Cropper.js` propose 3 modes de glisser sur l'image : `crop` (redessine la zone, défaut Cropper.js), `move` (déplace l'image dans le viewport), `none`. v15.7.10 utilisait `"move"` qui forçait les handles → mauvais sur mobile. v15.7.16 passe à `"crop"` partout (desktop ET mobile).

#### Handles tactiles plus larges

CSS override dans `style.css` (desktop) et `mobile.html` (page mobile) :
- `.cropper-point` : 5×5 → **18×18** (sides) et **22×22** (corners).
- Marges ajustées en conséquence (`-9px` / `-11px`) pour rester centrés sur les bords.
- Couleur `var(--accent)` pour les rendre visibles sur fonds variés.
- Lignes de la box (`.cropper-line`) re-teintées en accent bleu pour mieux délimiter visuellement.
- Conditional via `@media (max-width: 900px), (pointer: coarse)` côté desktop pour ne PAS gonfler les handles sur grand écran avec souris (ils restent 5×5 là, comme avant).

### Pas de nouveaux tests

Pure UI/UX : impossible à valider via tests Python (pas de DOM). 264 tests OK inchangés. Validation manuelle requise : prendre une photo de travers depuis `/mobile`, ouvrir crop, vérifier que les 2 boutons rotation marchent, et que glisser sur l'image redessine la zone.

---

## Phase A.7.2 v15.7.15 : Refine 2-étapes : infer concept → compose query (sans hardcode du niveau) (2026-05-10)

**Friction signalée par Gstar** : analyse honnête des queries v15.7.14 sur EN1 CC2. Les queries (« COMP S[1:0] A[2:0] table de vérité logique combinatoire exemple résolu » pour YouTube ; « composant COMP S[1:0] A[2:0] table de vérité exercice corrigé » pour web) étaient mieux que la phrase brute, mais sub-optimales : Gemini Flash **copiait-collait les identifiants techniques** (`COMP`, `S[1:0]`, `A[2:0]`) au lieu d'**inférer le concept général** que ces identifiants représentent. Or :
- `COMP` est propre à l'énoncé du cours, aucun YouTuber pédagogique francophone n'utilise ce nom : il faut deviner que c'est probablement un **comparateur** ou un **codeur**
- `S[1:0]` / `A[2:0]` est de la notation VHDL/Verilog brute. Les vidéos pédagogiques disent « 3 bits », « 2 sorties », pas `[N:M]`

Quand j'ai proposé 3 options pour fixer (light = durcir le prompt, medium = ajouter contexte matière hardcodé, heavy = 2 refines successifs), Gstar a choisi **C explicitement**, en précisant : « je ne vais pas toujours être en L1 ISTIC, même si je pense que le bot peut être intelligent et voir que le td qu'on traite n'est pas L1 mais on sait jamais ». Refus du hardcode niveau, préférence pour l'inférence.

### Livré

#### Workflow 2-étapes dans `/api/refine_search_query`

**Étape 1, `INFER_CONCEPT_PROMPT` (Gemini Flash, ~1.5s)** : analyse la demande pédagogique brute pour inférer :
- `concept` : nom standard du composant ou de la notion (« comparateur logique 3 bits » au lieu de « COMP »)
- `concept_alternatives` : 0-2 autres concepts plausibles si ambigu (ex. `COMP` peut être comparateur OU codeur prioritaire)
- `level` : niveau pédagogique inféré (lycée / L1 / L2 / prépa / BTS / master / inconnu) : **PAS hardcodé**, le LLM devine depuis les indices contextuels (vocabulaire, complexité, type de notation)
- `key_specs` : specs techniques traduites en français (« 3 entrées 2 sorties » au lieu de `S[1:0] A[2:0]`)
- `domain` : domaine large (« logique combinatoire », « analyse réelle », etc.)

Output balisé `<<<CONCEPT>>>{json}<<<END>>>`.

**Étape 2, `REFINE_SEARCH_QUERY_PROMPT` v2 (Gemini Flash, ~1.5s)** : compose la query depuis le concept analysé. Plus précis qu'avant parce qu'il travaille sur du concept clean, pas sur du jargon brut :
- Utilise le `concept` français standard (pas l'identifiant brut)
- Inclut les `key_specs` en français (« 3 bits », « 2 sorties »), JAMAIS la notation `[N:M]`
- Calibre le vocabulaire selon le `level` (« exercice » pour lycée, « démonstration » pour prépa, neutre si inconnu)
- Les alternatives explorent les `concept_alternatives` ou varient l'angle (cours / exercice / vidéo / fiche)

Output balisé `<<<REFINED>>>{json}<<<END>>>`.

#### Pourquoi 2 appels au lieu d'un

Le LLM ne mélange plus les responsabilités (analyse vs reformulation). Chaque étape a un prompt court et focalisé → meilleure qualité. La tâche d'inférence du concept (« COMP = comparateur ou codeur ? ») est **explicite et auditable**, pas masquée dans une chaîne de pensée.

**Coût** : 2× ~$0.0001 = $0.0002 par recherche (négligeable). **Latence** : ~3s vs ~1.5s. La bulle « ✨ Reformulation… » côté front reste visible un peu plus longtemps.

#### Pourquoi pas de hardcode du niveau pédagogique

Discussion explicite avec Gstar : il fait L1 maintenant, mais la trajectoire est L1 → L2 → L3 → master/recherche, et probablement plusieurs phases de retours en formation continue. Hardcoder « tu es L1 ISTIC » dans le prompt aurait été pratique pendant 6 mois puis devenu une dette technique trompeuse. Le LLM infère le niveau depuis les indices à chaque appel, donc naturellement adaptable.

#### API publique inchangée

Le frontend ne voit aucune différence. La réponse 200 expose en bonus 2 nouveaux champs `concept` et `level` (pour debug / affichage éventuel futur du genre « reformulé via concept : comparateur 3 bits, niveau inféré : L1 »). Pas de changement de signature côté JS.

#### Tests

10 cas dans `test_app_refine_search_query.py` (était 8) :
- Helper `_make_fake_client_pair(concept_response, refined_response)` qui produit 2 fake clients consécutifs via `side_effect`.
- Cas updated : happy path retourne query + alts + concept + level ; engine Gemini + model Flash forcés sur **les 2 calls** ; exclude propagé à l'étape 2 uniquement (pas l'étape 1).
- 2 nouveaux cas : `test_empty_concept_in_step1_returns_502` (stoppe net si étape 1 vide, retourne `step: "infer_concept"`), `test_concept_data_propagated_to_step2_prompt` (vérifie que `concept` / `level` / `key_specs` / `domain` sont bien injectés dans le sys_prompt de l'étape 2).
- **264 tests OK** (était 262).

---

## Phase A.7.2 v15.7.14 : Reformulation LLM des queries de recherche par Gemini Flash (2026-05-10)

**Friction signalée par Gstar (suite v15.7.13)** : « ok mais faut aussi que le moteur fasse un travail pour reformuler la demande pour que ce soit une vraie requête et pas juste une reprise bête et méchante de la phrase du tuteur ».

L'heuristique JS de v15.7.13 extrayait bien la phrase technique du tuteur, mais c'était toujours une **phrase pédagogique** (« analysez le composant COMP pour déterminer S[1:0]… ») et pas une **requête de recherche** (« comparateur COMP S[1:0] A[2:0] table de vérité logique combinatoire »). Les algos de Google/YouTube préfèrent les mots-clés au langage naturel.

### Livré

#### Backend : Nouveau endpoint `POST /api/refine_search_query`

- Body : `{description, target: "web"|"youtube", exclude?: [...]}`
- **Engine forcé : `gemini_api` + model `gemini-2.5-flash`** (raison : voir README §Choix de Gemini Flash). Override du `model_override` ajouté à `_run_isolated_lookup` pour ce cas précis.
- System prompt `REFINE_SEARCH_QUERY_PROMPT` : transforme la demande pédagogique → query 4-10 mots avec jargon technique préservé. Exemples inline pour ancrer le format.
- Output : `<<<REFINED>>>{"query": "...", "alternatives": ["...", "..."]}<<<END>>>` (1 query principale + 2-3 alternatives).
- `exclude` : queries déjà proposées (utilisé par le bouton 🔄 Reformuler côté front).
- Cap description à 3000 chars (anti tokens runaway).
- Codes 400 (description vide), 429 (quota Gemini), 502 (SDK error / réponse vide).

#### Backend : Intégration dans `/api/web_search_exo` et `/api/find_youtube_video`

Les deux endpoints acceptent `body.refined_query` (str optionnel). Si présent, ajouté au `sys_prompt` comme bloc « QUERY DE RECHERCHE OPTIMISÉE » qui guide le LLM principal vers les bons mots-clés. Sans ça, le LLM bricolait sa propre query depuis la description verbeuse → off-topic ou hallucinations (cas EN1 CC2 : 1 vidéo morte sur 1 + 2 liens web morts sur 3).

#### Frontend : Pré-remplissage 2 temps + bouton 🔄 Reformuler

- Nouveau helper `_refineSearchQuery(description, target, exclude)` qui POST `/api/refine_search_query`. Renvoie `{query, alternatives}` ou null si erreur.
- `performWebSearchExo()` et `performFindYoutube()` lancent **d'abord** le refine (~1-2s avec Flash, bulle « ✨ Reformulation… »), puis lancent la recherche en passant `refined_query` au backend. Le `refinedData` est ensuite propagé au render-bulle.
- `_appendDirectSearchInput(wrapper, description, target, refinedData?)` :
  - Si `refinedData` fourni : pré-remplit le champ avec `refinedData.query`, ajoute marker ✨ visible.
  - Si non fourni (cas legacy) : pré-remplit avec heuristique JS instantanée (v15.7.13), puis fait un refine async en background pour upgrader (le marker ✨ apparaît quand la query LLM arrive). Si l'utilisateur a déjà touché à l'input, on ne remplace pas.
- **Nouveau bouton 🔄 Reformuler** à côté de l'input : re-call `/api/refine_search_query` avec `exclude=[query courante, ...alternatives déjà essayées]` pour obtenir un autre angle. Si plus rien de neuf, alerte explicite.
- L'utilisateur peut toujours **éditer manuellement** l'input à tout moment.

#### Tests

- Nouveau `test_app_refine_search_query.py` (8 cas) : description vide → 400, happy path retourne query + alts, target youtube vs web, target invalide → fallback web, **engine Gemini + model Flash forcés peu importe la pref user**, exclude propagé au sys_prompt, query vide → 502, alternatives cappées à 3.
- **262 tests OK** (était 254, +8).

### Choix de Gemini Flash (documenté README + ici)

Trois raisons :
1. **Latence** : ~0.5-1.5s vs ~3-5s pour Opus / Pro. Important parce que le user attend avant de voir le champ « Édite la query » se remplir.
2. **Coût négligeable** : ~200 tokens in / 50 tokens out par refine. Sur Gemini API c'est ~$0.0001 par recherche, vs ~$0.005-0.015 sur Opus.
3. **Cohérence d'expérience** : que l'user soit sur Opus / Sonnet / DeepSeek / CLI subscription, le refine reste rapide. Sinon l'utilisateur sur Opus verrait un délai désagréable juste pour transformer une phrase en mots-clés (tâche triviale qui ne profite pas du raisonnement Opus).

Tradeoff assumé : nécessite une clé `GEMINI_API_KEY` dans l'env. Si absente, l'endpoint retourne 502 et le frontend tombe en fallback heuristique JS (v15.7.13).

---

## Phase A.7.2 v15.7.13 : Query de recherche : extrait uniquement la portion tuteur + heuristique densité technique (2026-05-10)

**Friction signalée par Gstar (suite v15.7.12)** : le strip du markdown image était bien en place, mais le champ « Édite la query » affichait quand même « Là c'est mieux ? » (la dernière phrase student du tour précédent). Évident maintenant : `_extractSimpleSearchQuery` prenait simplement la dernière phrase de la description complète, sans distinguer si elle venait du tuteur ou de l'étudiant.

Or pour une recherche externe (YouTube / Google), **seul le bloc tuteur compte** : c'est lui qui contient le vocabulaire technique (`COMP`, `S[1:0]`, `A[2:0]`, table de vérité). Le « Là c'est mieux ? » du student est inutile, voire nuisible : il déclenche des hallucinations (le LLM ne comprend pas de quoi on parle, invente des videoIds bidons → 1 vidéo morte sur 1 + 2 liens web morts sur 3).

### Livré

`_extractSimpleSearchQuery(description)` réécrite avec 3 améliorations :

1. **Extraction du bloc tuteur uniquement** : split sur les marqueurs `Le tuteur vient de me dire / demander :` (début) et `Ma dernière intervention était :` (fin du bloc tuteur). Le bloc student et les blocs `Je bloque pour répondre…` / `PRÉCISION DE L'ÉTUDIANT :` / `trouve-moi dans mes cours…` sont retirés. Si aucun marker trouvé (texte raw passé directement), fallback au comportement v15.7.12.

2. **Heuristique densité technique** : score chaque phrase par regex `/\[[0-9]+(?::[0-9]+)?\]|\b[A-Z]{2,}\b|\b[A-Z][a-z]*[0-9]+\b/g` qui détecte les notations `[N:M]` (registres / bus), les mots tout en MAJUSCULES (COMP, MUX, SEL, CC), et les identifiants alphanumériques (MUX21, A2, E0). Préfère les phrases avec score > 0, parmi elles la dernière (la plus récente). Sinon fallback sur la dernière phrase de longueur raisonnable. Conséquence : sur EN1 CC2 « Question 1.3 : analysez le composant COMP pour déterminer S[1:0] en fonction de A[2:0]. » (score 3) bat « Établissez la table de vérité… » (score 0) et « Correct. » (score 0).

3. **Strip du préfixe « Question N.N : »** qui prend de la place sans aider la recherche : `pick.replace(/^Question\s+\d+(?:[.,]\d+)?\s*:\s*/i, "")`.

4. **Limite passée de 80 → 100 chars** pour laisser passer les phrases techniques moyennes sans tronquer.

Résultat sur l'exemple de Gstar : la query passe de **« Là c'est mieux ? »** (16 chars, conversationnel inutile) à **« analysez le composant COMP pour déterminer S[1:0] en fonction de A[2:0] »** (71 chars, techniquement spécifique). YouTube/Google peuvent désormais matcher des contenus pertinents.

254 tests OK (purement frontend, pas de nouveau test Python : la fonction est trop spécifique JS pour avoir un test mock raisonnable côté backend).

---

## Phase A.7.2 v15.7.12 : Strip des markdowns d'images dans le contexte des recherches (2026-05-10)

**Friction signalée par Gstar pendant son CC2 EN1 (en cours)** : il envoie une photo de sa table de vérité, le tuteur la commente. Plus tard il clique 🎬 Vidéo (ou 🌐 Internet) sur la bulle Compagnon → la recherche YouTube/Web part avec **le markdown brut de l'image en query** : `![17784034108725046446798751189514.jpg](EN1/CC/2025-26/CC2/photos/17784034108725046446798751189514.jpg)`. Le champ « Édite la query » de la bulle de recherche affiche aussi cette URL au lieu du texte de la question, et la query passée au LLM est polluée. Résultat : « 1 vidéo morte (probable hallucination) » et 2 liens web morts sur 3.

Cause : `_getLastStudentTextBefore()` lit `prev.dataset.rawText` (markdown source persisté pour l'édition de bulle) qui contient `![alt](path)` quand une photo est attachée. Idem `getLastTutorTurnText()` (utilisé par le rewrite contextuel v15.7.1, même latence). `_extractSimpleSearchQuery()` ensuite garde l'URL parce qu'aucune phrase concrète ne la dépasse en taille.

### Livré

- Nouveau helper `_stripAttachmentMarkdown(text)` qui retire :
  - Les images Markdown : regex `/!\[[^\]]*\]\([^)]*\)/g`
  - Les mentions texte de pièce jointe : regex `/\[Pièce jointe\s*:[^\]]*\]/g`
  - Cleanup des `\n\n\n` cascadés et espaces avant retour à la ligne laissés par le strip.
- Appliqué à 3 points d'entrée :
  1. **`_buildContextualExoDescription`** (claudeText + studentText AVANT troncature à 800/400 chars). Sinon les premiers chars d'une bulle qui commence par une grosse URL d'image étaient juste l'URL.
  2. **`getLastTutorTurnText`** (rewrite contextualisé v15.7.1) : même problème côté Améliorer ✨.
  3. **`_extractSimpleSearchQuery`** en défense en profondeur (au cas où la fonction est appelée avec du brut depuis un autre call-site futur).
- 254 tests OK (purement frontend, pas de nouveau test Python).

### Bénéfice

Les boutons 🔍 Exo voisin / 📚 Passage CM / 🎬 Vidéo / 🌐 Internet partent désormais avec **le vrai contexte de la question** (texte du tuteur + dernière intervention de l'étudiant), sans pollution par l'URL des photos attachées. Le champ « Édite la query » est aussi propre.

---

## Phase A.7.2 v15.7.11 : Style cohérent du bouton 📷 + repositionnement popover ✨ (2026-05-10)

**Friction signalée par Gstar** : « le bouton photo à côté de joindre un fichier est moche, le style n'est pas le même que ceux des autres ».

Cause : `#photo-btn` ajouté en v15.7.10 sans entrée dans la règle CSS commune `#mic-btn, #media-btn, #rewrite-btn, #find-exo-btn { width: 38px; height: 38px; border-radius: 50%; ... }`. Du coup il rendait avec le style natif du `<button>` (rectangulaire, fond gris système). Bug de copie/coller.

Bonus : le popover `✨ Améliorer` était positionné en `left: 96px` calculé pour la disposition mic + media + rewrite. Avec le nouveau bouton 📷 inséré entre mic et media, il s'affichait décalé de 46px à gauche par rapport au bouton ✨.

### Livré

- Ajout de `#photo-btn` à toutes les règles communes des boutons ronds : style général (`width/height/border-radius/background/font-size`), hover, et `:disabled`. Désormais cohérent visuellement avec 🎤, 📎, ✨.
- `#rewrite-popover { left: 142px }` (était 96px) : recalculé pour les 4 boutons mic + photo + media + rewrite. Commentaire CSS mis à jour avec le calcul détaillé.
- 254 tests OK (purement CSS, pas de nouveau test).

---

## Phase A.7.2 v15.7.10 : Bouton 📷 dédié + crop Cropper.js (desktop & /mobile) (2026-05-10)

**Friction signalée par Gstar** : « Quand j'envoie une photo que ce soit sur mobile ou depuis le navigateur (d'ailleurs il faut aussi un bouton photo sur le navigateur à côté de joindre un fichier et détecter quand on est sur navigateur qu'on peut passer sur mobile et puis ça ouvre l'onglet distant et ça scintille dessus comme c'est pour le moteur). Eh bien il faut avoir la possibilité de rogner la partie pour avant l'envoi. »

Trois manques :
1. **Pas de bouton 📷 dédié** : seul le 📎 fichier générique existait, qui acceptait tous types. Pas de signal UX qu'une photo est attendue.
2. **Pas de redirection desktop → mobile** : sur PC, cliquer 📎 et pointer un fichier image = pas le bon flow pour révision papier (le cahier n'est pas devant le laptop).
3. **Pas de crop** : toute la photo partait au tuteur multimodal, avec le bordel autour de la table de vérité (cahier, table, mug, etc.). Surcoût tokens + bruit pour le tuteur.

### Livré

#### Bouton 📷 Photo (navigateur) : Volet 1
- `index.html` : bouton `📷` entre 🎤 et 📎, avec `<input type="file" accept="image/*" capture="environment">` caché.
- `app.js` `openPhotoFlow()` :
  - **Mobile** détecté via `(navigator.maxTouchPoints > 0 || 'ontouchstart' in window) && window.innerWidth < 900` → click input file → ouvre la caméra arrière native (Android/iOS).
  - **Desktop** → bascule sur l'onglet sidebar `🔗 Distant` (click programmatique sur `[data-tab="mobile"]`) + `flashRemoteTab()` qui scroll + 3 pulses oranges sur la pane (pattern emprunté à `flashEngineSwitcher` v15.6.4) + bannière hint orange au-dessus du tray (auto-dismiss 7s) : *« Scanne le QR ou ouvre l'URL Tailscale sur ton téléphone pour prendre une photo »*.
- Bouton désactivé hors session (cohérent avec mic/media), enabled au start_session, disabled au finishSession.

#### Crop Cropper.js (desktop & mobile) : Volet 2
- **Cropper.js v1.6.2** vendoré dans `_scripts/web/static/vendor/cropperjs/` (~37 KB JS + 4 KB CSS, MIT). Pas de CDN runtime.
- **Bouton ✂ Rogner** dans chaque thumbnail du tray, **uniquement pour les images** (pas les PDF/Excel). À côté de 🗑.
- **Modal de crop** lightbox : image affichée, handles glissables (Cropper.js `viewMode: 1, autoCropArea: 1, dragMode: "move", checkOrientation: true` pour respecter EXIF). Boutons « ↩ Annuler / ↻ Reset / ✂ Recadrer & remplacer ». Échap ferme.
- Au click `✂ Recadrer & remplacer` : `getCroppedCanvas({maxWidth: 2000, maxHeight: 2000})` → `canvas.toBlob` JPEG 0.92 → POST multipart vers nouveau endpoint **`/api/pending_attachments/<id>/replace`**.
- Backend `_apply_crop` : trouve l'attachment par id (404 si introuvable), refuse si `is_image=False` (400 « image only »), écrit le nouveau fichier dans le **même dossier** avec suffixe `_cropped_vN` pour éviter overwrite, mute l'entry en place (rel_path, filename, mime, size_bytes, uploaded_at, `cropped: true`). **L'ancien fichier reste sur disque** (cohérent avec le pattern DELETE qui ne touche que la queue). Garde-fou anti-cumul de suffixes : si stem contient déjà `_cropped_v`, on repart du préfixe original (pas de `_cropped_v1_cropped_v1`).
- **Page mobile `/mobile`** : même UX adaptée, modal plein écran avec touch handles confortables, mêmes boutons `[↩ Annuler] [↻ Reset] [✂ Recadrer]` en footer sticky.

#### Tests
- Nouveau `test_app_attachment_replace.py` (6 cas) : 409 sans session, 404 id inconnu, 400 attachment non-image, 400 file manquant, 200 happy path (nouveau fichier écrit + entry mutée + ancien préservé), garde anti-cumul de suffixes `_cropped_v1_cropped_v1`.
- **254 tests OK** (était 248, +6).

### UX résultante

**Desktop** : click 📷 → bascule onglet Distant + flash → tu sors ton téléphone, scannes le QR / ouvres l'URL → prends la photo via la page `/mobile` → la photo arrive dans le tray PC en ~1-2 s (polling) → click ✂ sur la thumbnail → crop → Envoyer.

**Mobile (page /mobile)** : click 📷 (gros bouton « Prendre une photo ») → app caméra système → la photo apparaît dans la liste → click ✂ → modal plein écran → crop → la photo envoyée arrive sur le PC à jour automatiquement.

---

## Phase A.7.2 v15.7.9 : Robustesse : retire la bulle student orpheline si send_message échoue (2026-05-10)

**Friction observée** : après un Ctrl+F5 mais SANS redémarrer le backend Python, le user envoie une photo seule. Le front nouveau (v15.7.8) accepte, mais le backend ancien refuse 400 « text vide » → alerte. Sauf que la bulle student avec la photo a déjà été ajoutée au DOM **avant** le fetch (ligne `t = appendTurn("student", "")` puis `t.innerHTML = renderMarkdown(displayText)`). Conséquences :
- Bulle student orpheline visible dans le fil
- Tentative de suppression échoue avec « index hors plage : 2 (transcript a 1 entrées) » parce que la bulle est dans le DOM mais pas dans le transcript backend
- Recovery : stop + relance, lui supprime tout côté DOM. La photo reste dans `pending_attachments` côté backend (queue persistante) et part au 1ᵉʳ envoi suivant.

### Livré

Helper `_removeOrphanStudentBubble()` dans `sendUserMessage` qui retire la bulle student du DOM quand le fetch `/api/send_message` échoue (status non-OK, non-202) ou lève une exception réseau. Best-effort : try/catch silencieux. 248 tests OK (purement frontend).

### Note importante (cause racine ≠ ce fix)

La cause racine du « text vide » 400 venait du **backend Python pas relancé** après v15.7.8. Pour appliquer une modif d'`app.py`, il faut **tuer et relancer le process Python** (kill `pythonw.exe gui.py` et/ou `python compagnon.py` puis relancer). Un Ctrl+F5 sur la page web ne recharge que le JS/CSS, pas le code serveur. Ce fix v15.7.9 traite seulement la conséquence visuelle (bulle orpheline) : la conséquence fonctionnelle (la photo n'arrive pas au tuteur) est résolue par le redémarrage backend.

---

## Phase A.7.2 v15.7.8 : Envoi photo seule (sans texte) (2026-05-10)

**Friction signalée par Gstar** : « je ne peux pas envoyer de photo sans texte, parfois je n'aurai juste envie d'envoyer qu'une photo ».

Cause : double garde « text vide → return » côté front (`sendUserMessage`) et côté back (`/api/send_message` → 400). Le pattern attendu pour la dictée (« il faut bien dire quelque chose ») bloquait l'usage légitime « voilà ma table de vérité, à toi de juger » sans commentaire.

### Livré

- **Frontend** `sendUserMessage` : check `if (!text && !hasAttachments) return` au lieu de `if (!text) return`. `hasAttachments` lit `attachmentsTray.children.length > 0` (le tray est tenu à jour par polling, fiable sans nouveau fetch). Si text vide, pas de séparateur `"\n\n"` en tête de `displayText` (sinon la bulle student commençait par 2 retours à la ligne avant l'image).
- **Backend** `/api/send_message` : refus 400 « text vide » uniquement si **aussi** aucune `pending_attachment`. Symmétrie avec le front. Construction du `text` final : pas de séparateur `"\n\n"` quand text vide.
- Slash-commands `/oral|/photos|/mixte` ne matchent plus quand text est vide (guard `text ? SLASH_COLLE_FORMAT_RE.exec(text) : null`).
- 248 tests OK (pas de nouveau test : la fonctionnalité photo seule est manuelle, l'infra existante de send_message + pending_attachments est déjà testée).

### UX résultante

Click 📎 → upload photo (ou paste depuis presse-papier, ou drag&drop, ou page mobile `/mobile`) → la photo apparaît dans le tray → click Envoyer **sans rien taper** → bulle student affichée avec juste l'image, le tuteur reçoit `[image attachée]` et la commente.

---

## Phase A.7.2 v15.7.7 : Sync GUI Tk → web sur le select Format colle (2026-05-10)

**Friction signalée par Gstar** : « j'ai lancé en format photo depuis le GUI et au lancement le select dans le web est resté sur mixte, faut corriger cette incohérence ».

Cause : `compagnon.py` propageait bien `--colle-format` à l'URL via `params["colle_format"] = args.colle_format` (v15.7.4), mais le code d'init du frontend (`initFormOptions` dans `app.js`) lisait `matiere`/`type`/`num`/`exo`/`annee`/`mode` depuis `URLSearchParams` et **oubliait `colle_format`**. Le select web restait sur sa valeur par défaut HTML (`mixte`).

### Livré

- `app.js` `initFormOptions` : lit `params.get("colle_format")`, normalise lowercase, valide ∈ {oral, photos, mixte}, applique au select.
- **Bonus cohérence** avec la GUI Tk : toggle de visibilité du select Format colle selon `mode` (masqué + disabled en `guidé`, puisque le backend ignore le paramètre dans ce mode). Listener `change` sur le select `mode` + appel initial.
- 248 tests OK (pas de nouveau test, fix purement frontend).

---

## Phase A.7.2 v15.7.6 : Robustesse GUI Tk : visibilité radio Format colle + auto-save sur change (2026-05-10)

**Friction signalée par Gstar** : « dans le GUI je dois aussi pouvoir choisir les modes quand je prends colle » + « et qu'à la sélection ça reste persistant au redémarrage ».

Trois bugs / manques résiduels de v15.7.4 dans `gui.py` :

1. **Pas d'appel initial à `_refresh_colle_format_visibility()`** après création des widgets. Conséquence : si l'utilisateur ferme la GUI en mode `guidé`, au boot suivant le radio « Format colle » restait visible alors qu'il aurait dû être masqué (jusqu'au 1ᵉʳ changement de mode). Pas critique mais incohérent.
2. **Le label « Format colle » à gauche n'était pas masqué** quand le frame des radios l'était : il restait visible à côté d'un espace vide en mode `guidé`.
3. **`self.colle_format` absent de la liste auto-save** dans `_wire_traces` (qui couvre `mode`, `enable_audio`, `skip_quota`). Conséquence : un changement de radio Format colle n'était persisté qu'au clic Lancer. Si l'utilisateur basculait Oral → Photos puis fermait la GUI sans lancer, le choix était perdu.

### Livré

- `_refresh_colle_format_visibility()` masque/affiche le **label ET le frame** ensemble.
- Référence `self.colle_format_label` gardée pour pouvoir l'adresser.
- **Appel initial** de `_refresh_colle_format_visibility()` à la création (juste après le `trace_add` sur `self.mode`), pour respecter le mode restauré depuis `last_selection`.
- `self.colle_format` ajouté à la liste auto-save → `_save_selection_silent` appelé à chaque changement (cohérent avec le pattern du reste du formulaire).
- 248 tests OK (pas de nouveau test : c'est de la robustesse UI, pas de logique).

### Note

Pour que ces fixes prennent effet, **il faut redémarrer la GUI Tk** (kill `pythonw.exe gui.py` puis relancer via `start_gui.vbs`). Une GUI lancée avant le commit continuera à tourner avec l'ancien code.

---

## Phase A.7.2 v15.7.5 : Neutralisation des références d'UI dans §1.6 (2026-05-10)

**Friction signalée par Gstar immédiatement après v15.7.4** : en format `photos`, le tuteur a généré « Tracez-la sur papier. Photographiez via l'icône 📎 quand c'est prêt. », wording correct sur le fond mais qui **prescrit** l'icône 📎 desktop alors qu'il y a aussi la page mobile `/mobile` (accessible via QR depuis l'onglet Distant) pour upload direct depuis l'appareil photo. Pour Gstar lui-même au téléphone c'est déjà déroutant (« je devrais utiliser 📎 ? Ça marche depuis le mobile ? »), et **incompatible avec une future ouverture publique** du Compagnon où d'autres voies d'upload pourraient exister selon les setups utilisateur.

Cause : §1.6 v0.3 incluait des exemples explicites « Photographiez via 📎 » et « Photo via 📎 conseillée ». Le LLM les a (à juste titre) repris.

### Livré

`PROMPT_SYSTEME_COMPAGNON.md` v0.3 → **v0.4** :

- **Exemples §1.6 réécrits** sans citer d'icône ni de canal précis :
  - « Photographiez via 📎 » → « Envoyez-moi la photo »
  - « Photo via 📎 conseillée » → « Envoyez-moi une photo si possible »
  - Tous les exemples format `photos` et `mixte` neutralisés.
- **Nouveau sous-§1.6** « Règle de wording : neutralité sur le canal d'upload » qui formalise la consigne :
  > Quand vous demandez ou proposez une photo, dites simplement « envoyez-moi une photo » […]. **N'imposez aucun canal précis** : ne mentionnez ni l'icône 📎, ni la page mobile `/mobile`, ni le QR code, ni aucun bouton spécifique de l'interface. L'étudiant a plusieurs voies d'upload selon son setup et il choisit la sienne. Vous formulez **la demande pédagogique**, pas la procédure UI.
- **Test de doctrine** `test_neutralite_canal_upload_v15_7_5` ajouté à `test_app_colle_format.py` : assert que la règle de neutralité est bien présente dans le prompt : casse si quelqu'un ré-introduit du wording prescriptif lors d'un futur refactor. **248 tests OK** (était 247).

### Pourquoi cette règle compte au-delà de Gstar

Le projet a une trajectoire « vitrine publique été 2026 » documentée en mémoire : si le Compagnon est partagé (démo, portfolio, voire utilisateurs externes), chaque utilisateur peut avoir un setup différent : desktop avec 📎, mobile avec /mobile via QR, ou demain une intégration Discord, un bot Telegram, un client custom. Le tuteur qui prescrit une icône précise rend ces voies invisibles ou contradictoires. Mieux vaut qu'il formule la demande pédagogique brute et laisse la couche UI gérer l'expression concrète.

---

## Phase A.7.2 v15.7.4 : Format colle paramétrable + bascule à chaud (2026-05-10)

**Friction observée EN1 CC2 (multiplexeur)** : sur certaines questions à objet structuré (table de vérité, schéma logique, équation posée), le tuteur en mode colle se contentait d'attendre une dictée vocale nécessairement bancale OU sautait silencieusement la question parce qu'il sentait que ça calait. Pas de proposition de photo, pas de bascule sur vérification orale partielle. Du coup l'étudiant se retrouvait à passer à la question suivante sans avoir vraiment construit la table.

Le user a explicitement demandé un mécanisme de paramétrage qui lui laisse **la main libre au moment** sur le format de la séance, avec bascule possible **en cours** : « si je veux qu'on fasse une séance où j'envoie les photos de mon cahier, ou une séance où c'est plus que de l'oral, ou par défaut le mixte des deux, c'est à moi de choisir le mode ». Et un peu plus tard : « en pleine conv je pourrais changer le mode si j'en ai envie, ça marque en message système et le tuteur s'adapte ».

### Décision archi

3 voies de bascule (redondantes pour rester pratique selon le contexte) :

1. **Paramètre initial au lancement** : radio « Format colle » dans la GUI Tk (visible si mode=colle), select dans le formulaire web. Persisté dans `runtime_settings.last_selection.colle_format` (champ additif, pas de bump schéma) pour restauration au boot. CLI : flag `--colle-format oral|photos|mixte`.
2. **Chips UI** dans le bandeau au-dessus du dialogue : `🎙 Oral` / `📸 Photos` / `🔀 Mixte`. Visibles seulement en mode colle. Click = bascule immédiate, chip actif highlighté. Pour quand tu vois le clavier.
3. **Slash-commands** dans le textarea : `/oral`, `/photos` (ou `/photo`), `/mixte` détectées en début de message → backend applique, n'envoie PAS au tuteur. Tolérance casse insensible et point final pour la dictée vocale (« slash photos point »). Pour quand tu dictes au mic.

### Comportement attendu côté tuteur

`PROMPT_SYSTEME_COMPAGNON.md` bumpé v0.2 → **v0.3** :

- **Nouveau §1.6** « Format colle paramétré » avec **3 sous-paragraphes** selon le bloc `[FORMAT COLLE : <oral|photos|mixte>]` injecté en tête du contexte initial :
  - **Format `oral`** : pas de photo mentionnée, vérification orale partielle si l'étudiant cale sur un objet structuré.
  - **Format `photos`** : le tuteur **attend** la photo avant de juger une question structurée et la propose en première intention.
  - **Format `mixte`** (défaut) : décision au cas par cas, propose la photo sur table de vérité / schéma / équation posée / dessin / pseudo-code long, mais reste sur l'oral pour les définitions / théorèmes / raisonnements.
- **Garde-fou général** : *« Ne sautez jamais silencieusement une question parce que la dictée vous paraît bancale. »* Soit photo, soit vérification orale partielle, jamais le silence (qui faisait passer un blocage pour acquis).
- **Nouvelle règle absolue §4.11** : *« Pas de résistance aux bascules de format colle. »* Quand le tuteur reçoit `[FORMAT BASCULÉ → oral|photos|mixte]` synthétique, il acquitte d'**un seul fragment** (« Format photos. ») et adapte. **Interdit absolu** : « êtes-vous sûr ? », « pourquoi ? », « finissons d'abord cet exercice », « est-ce vraiment nécessaire ? ». L'étudiant a la main, le tuteur applique.

### Détails techniques

- **Backend** :
  - `prompt_builder.py` : `build_initial_context_message()` accepte `mode` et `colle_format`. Si `mode == "colle"`, injecte `[FORMAT COLLE : <fmt>]` après l'en-tête de séance. En mode guidé, omis (le tuteur a déjà accès aux PDF via Read/Grep). Helper `_normalize_colle_format` (casse insensible, fallback `mixte`).
  - `session_state.py` : champ `colle_format` (défaut `"mixte"`) dans le JSON de session. Additif, pas de bump schéma.
  - `app.py` : `/api/start_session` lit `body.colle_format`, persiste dans `data["colle_format"]`, passe au builder. `/api/current_session` retourne le format pour la restauration front. Nouveau **endpoint `/api/set_colle_format`** : Body `{format}`, persiste + injecte `[FORMAT BASCULÉ → ...]` dans le `_history` du client. Détection slash-command dans `/api/send_message` (regex `^/(oral|photos?|mixte)\.?\s*$`, casse insensible) → 202 `{ok, slash_command:true, colle_format}` sans poste user.
  - `compagnon.py` : flag CLI `--colle-format`.
- **Frontend** :
  - `index.html` : select `colle_format` dans le formulaire de lancement, bandeau `#colle-format-chips` au-dessus du dialogue.
  - `style.css` : style des 3 chips (rounded, bordure highlight si actif) + marker `.format-marker` teinté orange (distinct du `.doc-marker` bleu).
  - `app.js` : state global `activeColleFormat`, helpers `applyColleFormatChips(fmt)` / `appendFormatMarker(fmt)` / `setColleFormat(fmt, opts)`. Sync au start_session, restauration via `/api/current_session`, mode viewer désactive les chips (visible mais pas cliquable). Détection slash-command côté front aussi (intercepte AVANT POST send_message → marker tout de suite, vide l'input). Reset au `finishSession`.
- **GUI Tk** : 3 boutons radio « Format colle » sous le radio mode (toggle visibilité géré par `_refresh_colle_format_visibility` via `trace_add` sur le mode). Persisté via `update_last_selection(colle_format=...)`.

### Tests

- `test_prompt_builder.py` (+6 cas) : default `mixte`, override `oral`/`photos`, fallback sur valeur invalide, **omission en mode `guidé`**, helper `_normalize_colle_format`.
- `test_app_colle_format.py` (nouveau, 13 cas) : endpoint `/api/set_colle_format` (409 sans session, 400 invalide, 200 happy + persist + marker, tolérance singulier `photo`/`photos`, casse insensible) + détection slash-command dans `/api/send_message` (`/oral`, `/photos.` dictation, `/MIXTE` casse, slash + texte après = pas intercepté, texte normal = flow inchangé) + **3 tests de doctrine** sur `PROMPT_SYSTEME_COMPAGNON.md` (§1.6 présent avec les 3 formats, règle 11 présente avec « êtes-vous sûr », garde-fou « jamais silencieusement »).
- **247 tests OK** (était 228, +19).

### Itérations à prévoir si le tuteur résiste en runtime

Comportement émergent du LLM : malgré la règle §4.11 dure, certains modèles (DeepSeek surtout) résistent parfois aux contraintes négatives. À monitorer en session réelle. Si le tuteur se met à demander « êtes-vous sûr ? » ou ralentit la bascule, on durcit le wording du prompt système en v15.7.5 (ex : exemple explicite, ou marker plus impératif type `[FORMAT_SWITCH_NO_DISCUSS]`).

---

## Phase A.7.2 v15.7.3 : Auto-abort du rewrite ✨ Améliorer à l'envoi du message (2026-05-10)

**Friction observée** : Gstar clique ✨ Améliorer puis, sans attendre les ~1-3 s du rewrite, envoie son message brut directement (Entrée). Le rewrite continue en arrière-plan et, ~1 s plus tard, **écrase `userInput.value` avec la version améliorée du message qu'il vient d'envoyer brut** → l'input se retrouve pollué d'un texte « fantôme » qui correspond à un message déjà parti.

Cause : `sendUserMessage()` annulait déjà la transcription Whisper en vol (`cancelPendingTranscribe()`) mais pas le rewrite (l'AbortController `rewriteInFlightAbort` existait depuis v15.5 mais n'était abort que par un nouveau rewrite, pas par un envoi).

### Livré

- **`sendUserMessage()`** appelle désormais `rewriteInFlightAbort?.abort()` + reset à `null` à côté de `cancelPendingTranscribe()` (3 lignes ajoutées). Le `finally` de `performRewrite()` s'occupe de remettre l'UI propre (bouton `✨`, `readOnly = false`), pas besoin de dupliquer.
- Pas de test JS (la fix est triviale et l'infra de tests Python ne couvre pas le DOM). Validation manuelle requise : lancer rewrite, envoyer immédiatement, vérifier que l'input reste vide après.
- Pas de changement de schéma ni d'API → pas d'update ARCHITECTURE.md.

---

## Phase A.7.2 v15.7.2 : Durcissement « Corriger fautes » : interdiction stricte de toucher aux faux départs (2026-05-10)

**Friction observée immédiatement après v15.7.1** (test EN1 CC2 multiplexeur, dictée WebSpeech) : le rewriter a fait du très bon boulot sur les fautes pures et sur l'alignement vocabulaire technique grâce au contexte tuteur. Mais il a aussi **supprimé le faux départ** `« et non c'est la »` qui ouvrait la phrase de Gstar. C'était inintelligible donc défendable, mais sort strictement du périmètre annoncé de « Corriger fautes » (qui doit cibler **uniquement** orthographe / grammaire / ponctuation, comme « Plus concis » est l'intent dédié au nettoyage des hésitations).

Décision (validée par Gstar) : durcir le prompt pour que `fix_typos` ne touche **strictement qu'aux fautes**, quitte à laisser un texte « moche » ou décousu. Si l'utilisateur veut nettoyer, il a explicitement « Plus concis » ou « Reformuler » à disposition : choisir « Corriger fautes » est un signal qu'il veut garder le grain brut de sa dictée.

### Livré

- **`REWRITE_INTENTS["fix_typos"]`** : ajout d'un paragraphe « INTERDICTIONS ABSOLUES » qui liste explicitement ce qu'il ne faut PAS supprimer : faux départs (« et non c'est », « enfin je veux dire », « ah non »), hésitations (« euh », « ben », « bah », « du coup », « voilà »), mots-béquilles, répétitions. Justification incluse dans le prompt lui-même : *« Si l'utilisateur voulait nettoyer ces tics oraux, il aurait choisi « Plus concis » ou « Reformuler » ; en choisissant « Corriger fautes » il signale qu'il veut garder le grain brut de sa dictée et juste les accents/accords. Respecte ce choix. »*
- **Test de doctrine** (`test_fix_typos_prompt_forbids_removing_false_starts`) : assert que `REWRITE_INTENTS["fix_typos"]` mentionne explicitement « faux départ », « hésitation », et un mot normatif fort (« interdiction » ou « interdit »). Léger, mais casse si quelqu'un assouplit la consigne par inadvertance lors d'un futur refactor. **228 tests OK** (était 227).
- Pas de changement frontend ni backend autre que le prompt : c'est uniquement de la doctrine.

### Note d'usage (cf. README)

Garder en réflexe : **Reformuler** = défaut sur dictée vocale (le rewriter aligne vocabulaire et nettoie un peu) ; **Corriger fautes** = quand on a déjà tapé proprement et on veut juste les accents/accords sans toucher à rien d'autre.

---

## Phase A.7.2 v15.7.1 : Rewrite contextualisé par le dernier tour Compagnon (2026-05-10)

**Friction concrète sur EN1 CC2 (multiplexeur)** : le tuteur explique que la sortie `S` recopie l'une des deux **entrées** `E0` ou `E1` selon `SEL`, et demande « Reprenez : si SEL vaut 0, laquelle des deux entrées est recopiée sur la sortie S ? ». Gstar dicte au mic : *« Si celle vaut 0, bah si celle vaut 0, eh bien il n'y aura que la sortie E1 qui sera recopiée, étant donné que sa valeur est un, je crois. »*

Le brouillon a deux problèmes d'ordres différents :
- **Forme** : `« celle »` est un pronom orphelin (référent = `SEL` mais le rewriter ne peut pas le deviner sans contexte) ; `« la sortie E1 »` est faux côté terminologie (E1 est une **entrée**, le tuteur vient de le rappeler).
- **Fond** : si SEL=0, c'est E0 (pas E1) qui est recopiée, erreur de raisonnement.

Avant cette phase : `/api/rewrite` était stateless. « Corriger fautes » et « Reformuler » n'avaient aucun moyen de résoudre `« celle »` ni de corriger `« la sortie E1 »` → résultat aléatoire selon le LLM. Et la tentation de corriger le fond aurait été pire (perdre l'intérêt pédagogique du mode colle, où l'étudiant doit *trouver* son erreur).

### Livré

- **Backend `/api/rewrite`** : nouveau champ `context_tutor` (str optionnel) dans le body. Capé à `REWRITE_MAX_CONTEXT_CHARS = 2000` chars (un tour Compagnon typique fait 200-800 chars). Truncation par le **début** : on garde la fin du tour, où la question reformulée du prompt COMPAGNON §3 (« Reprenez : … ? ») se trouve typiquement. Si présent, préfixé dans le `user_msg` envoyé au modèle :
  ```
  [Contexte : dernier message du tuteur]
  <texte capé>
  [/Contexte]

  Consigne : <REWRITE_INTENTS[intent]>
  ---
  Texte à transformer :
  <brouillon>
  ```
- **`REWRITE_SYSTEM_PROMPT`** : ajout d'un paragraphe explicite : *« Si un bloc [Contexte : dernier message du tuteur] est fourni, il sert UNIQUEMENT à : (1) lever les ambiguïtés de pronoms (« celle », « il », « ça » → le terme exact), (2) aligner le vocabulaire technique sur celui du tuteur. Tu n'as PAS le droit d'ajouter, corriger ou supprimer un raisonnement, un fait ou une conclusion du brouillon, même si le contexte du tuteur les contredit : l'étudiant doit trouver son erreur de fond lui-même. »* Garde-fou explicite contre la dérive « je corrige le fond pendant que j'y suis ».
- **Frontend `app.js`** : helper `getLastTutorTurnText()` lit la dernière bulle `.turn.claude` du dialogue, prend `dataset.rawText` (markdown source persisté pour l'édition de bulle, plus propre que `textContent` qui inclurait les marqueurs visuels). Fallback `textContent` si absent. Retourne `""` si pas de bulle Compagnon → backend bascule en mode legacy. `performRewrite(intent)` ajoute `context_tutor` au body uniquement si non vide.
- **Réponse 200 enrichie** : nouveau champ `context_chars` (int), longueur du contexte effectivement injecté après truncation, `0` si absent. Utile pour debug/futur télémétrie sans avoir à dumper le user_msg complet.
- **Tests** : 4 nouveaux cas dans `test_app_rewrite.py` : (1) sans `context_tutor` = comportement legacy (pas de bloc `[Contexte]` dans le user_msg, `context_chars: 0`) ; (2) avec contexte = bloc préfixé correctement, brouillon préservé en queue ; (3) contexte > cap = truncation par le début, queue préservée ; (4) `context_tutor: "   \n   "` (whitespace) = traité comme absent. **227 tests OK** (était 223).

### Pourquoi cette UX

Aucun LLM grand public (ChatGPT/Claude.ai/Gemini) n'expose ce « rewrite avant envoi avec contexte conversationnel » en standard. Pour la révision orale en mode colle où l'étudiant dicte au mic, c'est exactement ce qui manque pour que les 4 intents (Reformuler / Concis / Développer / Corriger fautes) ne fassent pas du bruit aléatoire.

### Coût

- ~+500-1500 tokens in par rewrite (cap 2000 chars ≈ ~500 tokens FR).
- Sur Pro Max : invisible (compté à la session, pas au token).
- Sur API anthropic Sonnet : ~+$0.005-0.015 par rewrite (vs ~$0.005 avant). Toujours négligeable comparé au stream principal.

---

## Phase Z.9.3 → Z.9.7 : Itérations anti-hallucination + UX recherche externe (2026-05-09, nuit)

5 incréments en suivant Z.9.2, après que Gstar ait identifié plusieurs frictions concrètes en runtime sur EN1 CC2 ex full :
- Z.9.2 affichait `Recherche échouée : balise_absente` quand Gemini répondait en texte libre sans suivre le format `<<<TAG>>>{json}<<<END>>>`.
- Tous les 4 videoIds YouTube proposés étaient hallucinés → bulle vide sans recours.
- Le HEAD check laissait passer des faux positifs (DNS fail = `s-prep.fr` retourné comme alive).
- Le bouton « 🔍 Chercher directement sur YouTube » passait toute la description structurée (incluant *« Le tuteur vient de me dire / demander : … Je bloque pour répondre »*) comme query : moche et inefficace pour l'algo natif YouTube.
- Pas de fallback manuel sur les bulles de **résultats** web/youtube quand les liens proposés ne plaisaient pas (juste sur les bulles d'erreur).
- Pas de bouton 🌐 Internet dans la tone-toolbar : il fallait passer par 🔍 Exo voisin pour y accéder.
- Tone-toolbar à 10 boutons après l'ajout de 🌐 Z.9.6 : visuellement dense.

### Z.9.3 : Fallback extraction quand le LLM ignore le format

- Helper `_fallback_extract_youtube(raw)` : regex sur les videoIds présents dans le texte brut (`(?:v=|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})`), oembed pour récupérer titre/channel, extrait du contexte (~250 chars autour de l'URL) en `why`. Retourne `{results: [...]}` ou None.
- Helper `_fallback_extract_web(raw)` : regex sur URLs HTTP non-YouTube + heuristique titre (slug + domaine) + contexte ~200 chars.
- `_run_isolated_lookup` accepte `fallback_kind: "youtube" | "web" | None`. Si la balise est absente, log warning + tente le fallback. Si le fallback retourne quelque chose, on continue normalement (le filtrage oembed/HEAD est appliqué après comme prévu). Plus de 502 cryptique pour le user.

### Z.9.4 : DNS check durci + bouton « 🔍 Chercher directement »

- `_verify_external_url` durci sur `urllib.error.URLError` avec `socket.gaierror` détecté (DNS fail = domaine inexistant = mort). Fix le faux positif `s-prep.fr` (domaine inexistant retournait `True` avant car notre code était tolérant sur toutes les exceptions).
- `_renderSearchFailedBubble(emoji, reason, description, target)` : bulle d'erreur enrichie avec un lien direct vers Google (`target=web`) ou YouTube (`target=youtube`) avec la query pré-remplie. L'algo natif est beaucoup plus fiable que les hallucinations LLM.
- Endpoints `/api/web_search_exo` et `/api/find_youtube_video` acceptent `body.force_engine` pour forcer Anthropic ou Gemini (utile si l'utilisateur veut tester le `web_search_20250305` natif d'Anthropic, plus fiable que Search Grounding Gemini).
- Limite connue assumée : `eeinap.com` type **soft-404 retournant 200** reste un faux positif car le serveur répond vraiment HTTP 200 même sur les pages inventées. Pas détectable par HEAD sans heuristique de contenu (lourd, faux positifs sur les sites légitimes en JS).

### Z.9.5 : Query éditable + « Chercher directement » sur les bulles de résultats

- `_extractSimpleSearchQuery(description)` (frontend) : heuristique qui retire les blocs préambule/postambule (« Le tuteur vient de me dire », « Je bloque pour répondre », « PRÉCISION DE L'ÉTUDIANT : », « trouve-moi dans mes cours »…), découpe en phrases, choisit la dernière concrète, limite à 80 chars sans couper un mot.
- `_appendDirectSearchInput(wrapper, description, target)` : helper réutilisable qui ajoute « `<input>` éditable + bouton 🔍 Chercher sur Google/YouTube » dans n'importe quelle bulle. Initial query pré-remplie par l'heuristique, l'utilisateur ajuste s'il veut. Entrée valide depuis l'input. Cible Google ou YouTube selon contexte.
- `_renderSearchFailedBubble` simplifié : utilise le helper.
- `_renderWebResultsBubble` et `_renderYoutubeResultsBubble` : ajoutent la query éditable + bouton « Chercher directement » en plus du bouton « Autre ressource/vidéo ». Plan B garanti même quand le LLM trouve quelque chose qui ne plaît pas.
- CSS `.found-search-query / .found-search-input / .found-exo-direct-search-btn` : input flexible avec focus accent bleu, bouton chip cohérent avec la palette web.

### Z.9.6 : Bouton 🌐 Internet dans la tone-toolbar

- 4ᵉ bouton après 🔍 Exo voisin / 📚 Passage CM / 🎬 Vidéo dans la `tone-toolbar` sous chaque bulle Compagnon. Visible en mode colle uniquement.
- Click → utilise le contexte de la bulle Compagnon parente + dernier student précédent (comme les 3 autres) → lance `performWebSearchExo`. Pas besoin de cliquer 🔍 Exo voisin d'abord pour avoir accès à la recherche web.

### Z.9.7 : Popover « 🎛 Modifier ▾ » pour grouper les 6 reformulations

- La tone-toolbar passait de 10 boutons. User a validé **option 2** (popover pour les reformulations, accès direct conservé pour les recherches).
- Bouton `🎛 Modifier ▾` à la place des 6 boutons individuels de `TONE_PRESETS`. Click → toggle popover `.tone-modify-popover`.
- Popover (style identique à `#rewrite-popover` du textarea) : 6 actions stylées en grille 2-cols (icon + label + hint avec instruction). Hover `#2a2a2a`.
- Click sur une action → ferme popover + désactive tous les boutons de la toolbar (anti double-click) + envoie le meta-instruction.
- Click outside → ferme via `_onClickOutsideToneModify`. Handler global auto-removed quand plus aucun popover ouvert (pas de listener zombie).
- Plusieurs bulles Compagnon = plusieurs popovers possibles, mais ouvrir un nouveau ferme les autres pour limiter le bruit visuel.
- **Tone-toolbar passe de 10 boutons → 5 visibles** (1 grouped + 4 direct). Reformulations à 2 clics au lieu de 1, mais usage moins fréquent que les recherches → trade-off favorable.

### Tests

- 223 tests Python OK pour chaque commit (refacto + nouveaux endpoints + frontend).
- Validation manuelle par Gstar en runtime : (a) bulle d'erreur YouTube affiche désormais un lien direct vers une recherche YouTube manuelle. (b) `s-prep.fr` est désormais filtré comme mort. (c) Query proposée dans l'input éditable est nette ("multiplexeur MUX21 fonction" au lieu de la phrase structurée bruitée). (d) Click sur 🎛 Modifier ouvre le popover ; click outside le ferme.

### Pas livré (consciemment)

- Pas de retry automatique cross-engine après hallucination (l'utilisateur garde le contrôle, peut basculer manuellement via `flashEngineSwitcher`). Le bouton « 🔍 Chercher directement » est le plan B universel : gratuit, fiable, 1 clic.
- Pas d'extraction de mots-clés via mini-LLM (économie d'un appel par clic). L'heuristique JS suffit pour 80 % des cas, l'utilisateur édite le 20 % restant.
- Pas d'option « épingler le popover » (le user peut fermer puis re-ouvrir). Si demandé, on ajoutera un mode pinned-open.

---

## Phase Z.9.2 : Anti-hallucination URLs + retrait bouton 🔍 footer + bouton « ✏ Affiner » (2026-05-09, nuit)

**Frictions immédiatement remontées** après le déploiement de Z.9 :

1. **URLs YouTube hallucinées** : *« les liens sont mort ces vidéos existent vraiment ? ou tu as halluciné ? »*. Sur 2/2 vidéos retournées, deux `videoId` inventés (`sU14hGU1xIs`, `7X5bB_N-L0M`) plausibles mais inexistants. Confirmé : Gemini sans grounding effectif fabrique des IDs YouTube valides en format mais inexistants en base.
2. **URLs web hallucinées de la même façon** : 2 sur 3 morts (`eeinap.com/...mux-2-1.html`, `f2school.com/post/269/...`). Gemini hallucine aussi les URLs profondes des sites éducatifs même connus.
3. **Bouton 🔍 footer redondant** : *« Je trouve mtn que le bouton trouver un exo voisin ne sert plus à rien il est devenu trop spécifique »*. Le bouton contextuel + les 5 boutons « Pas satisfait ? » couvrent tous les cas. Le footer devient bruit visuel.
4. **Manque de contrôle fin** : *« ou alors dans exo voisin quand on clique dessus avoir un champ pour taper aussi pour spécifier la demande »*. Pas moyen d'enrichir le contexte automatique avec une précision manuelle.

**Livré.**

### Vérification anti-hallucination des URLs (Z.9.1)

- **`_verify_youtube_url(url)`** : extrait le `videoId` via regex (`v=` / `youtu.be/` / `/embed/` / `/shorts/`, 11 chars `[a-zA-Z0-9_-]`), hit l'**endpoint oembed officiel** `https://www.youtube.com/oembed?url=…&format=json`. 200 = vidéo live, 401/404 = supprimée ou ID inventé. Autres codes (rate limit, géo) = on garde par défaut (faux positif moins grave que faux négatif).
- **`_verify_external_url(url)`** : HEAD avec timeout 5 s. Si HEAD non supporté (405), fallback GET. 4xx = mort. 5xx + erreurs réseau = on garde.
- **`_filter_dead_urls(results, verify_fn)`** : ThreadPoolExecutor 4 workers, vérifie tous en parallèle (~1-2 s pour 1-3 URLs au lieu de séquentiel). Retourne `(alive, dead_count)`.
- Branchement dans `/api/web_search_exo` (avec `_verify_external_url`) et `/api/find_youtube_video` (avec `_verify_youtube_url`). Réponse enrichie de `dead_urls_filtered: int`. Si TOUS les résultats étaient morts → `found: false` avec une `reason` explicite : *« Toutes les URLs (N) renvoyées étaient mortes, probable hallucination du modèle. Réessaie ou bascule sur Claude API qui groundé mieux. »*

### Durcissement des system prompts (Z.9.1)

- **`YOUTUBE_PROMPT`** : section « RÈGLE INVIOLABLE : pas d'hallucination d'URLs » en tête. Interdit explicitement d'inventer un videoId depuis la connaissance interne. Demande au modèle d'utiliser le tool `web_search` / `google_search` AVANT de proposer une URL et de copier l'URL EXACTEMENT comme elle apparaît dans les résultats du tool. Si pas d'accès au tool → `{"results":[]}` honnête.
- **`WEB_SEARCH_EXO_PROMPT`** : même règle ajoutée. Explique que les URLs profondes (`/exercices/calcul-binaire-3.html`) ne sont pas prévisibles, donc inventables.

### Frontend : warning visuel quand des URLs sont mortes (Z.9.1)

- `_renderWebResultsBubble(results, description, deadCount)` et `_renderYoutubeResultsBubble(...)` acceptent désormais un `deadCount`. Si `> 0`, ligne d'avertissement `⚠ N lien(s) supprimé(s) car morts (probable hallucination du modèle)` en orange juste sous le header.
- `performWebSearchExo` / `performFindYoutube` propagent `data.dead_urls_filtered`.
- Si `found: false` avec une `reason` explicite, affichage du message backend tel quel (l'utilisateur sait qu'il faut essayer autrement).

### Suppression du bouton 🔍 footer + bouton « ✏ Affiner » (Z.9.2)

- `<button id="find-exo-btn">🔍</button>` retiré de `templates/index.html`. Code JS gardait déjà des `if (findExoBtn)` partout, donc no-op.
- Nouveau 4ᵉ bouton `✏ Affiner` dans la barre « Pas satisfait ? » de la bulle exo voisin. Click → `window.prompt` qui demande une précision libre (« plus axé table de vérité », « cas industriel concret », etc.). La précision est ajoutée en post-scriptum à la description contextuelle existante (`PRÉCISION DE L'ÉTUDIANT : …`) et la recherche est relancée.
- Helper `_refineAndRelaunch(baseDescription)` factorisé pour clarté.

### Docs

- README section "Trouve un exercice voisin" : 3 entrées → 2 entrées (suppression footer). 5 boutons « Pas satisfait » → 6 (ajout `✏ Affiner`).
- CHANGELOG entrée Z.9.2 (cette section).

### Tests
- 223 tests Python OK.
- Validation manuelle attendue : (a) bouton 🔍 footer absent. (b) Lance recherche YouTube → si vidéos hallucinées par Gemini, warning ⚠ visible et résultats filtrés. (c) Cliquer ✏ Affiner → prompt pour précision → nouvelle recherche enrichie. (d) Si toutes les URLs sont mortes, message FR clair plutôt que liste de liens 404.

### Pas livré (consciemment)
- Pas d'option « ré-essayer avec un autre moteur » dans le bouton si Gemini hallucine : l'utilisateur peut basculer manuellement (sélecteur en haut). Pourra être ajouté si l'hallucination Gemini se confirme comme systématique.
- Pas de cache des URLs vérifiées : chaque appel re-vérifie. Coût négligeable (1-2 s pour 3 URLs).
- Pas de blacklist de domaines connus pour halluciner (eeinap.com, f2school.com semblent fréquents). Si ça revient, on listera dans le system prompt « jamais ces domaines ».

---

## Phase Z.9 : Suite d'outils contextuels « pas satisfait, autre chose ? » (2026-05-09, fin de soirée)

**Friction agrégée.** Après le bouton 🔍 contextuel de Z.8.6, le user identifie que la bulle exo voisin actuelle n'a qu'une réponse possible : si l'exo trouvé ne convient pas (trop dur / trop simple / mauvais angle / rien dans les cours), il faut une porte de sortie. Cinq angles à couvrir en bloc :
- **B1** : variantes de difficulté du même besoin (📉 plus simple, 📈 plus dur, 🔄 autre angle).
- **B2** : ne pas retomber sur un exo déjà proposé dans la session.
- **A1** : recherche internet sur sites éducatifs FR quand local insuffisant.
- **C2** : pointer le passage du CM qui définit le concept (alternative à l'exo).
- **C3** : trouver une vidéo YouTube éducative FR.

Citations user : *« si ça ne trouve pas d'exo voisin dans mes cours ou alors si l'exo voisin nous satisfait pas il peut y avoir des boutons supplémentaires pour demander à faire une recherche sur internet ? et tu vois d'autres trucs ? »* + *« j'aime bien tes recommandations et applique aussi B2 et C3 tu as trouvé de très bonnes idées je veux tout »* + *« pareil pour vidéo faut un truc qui pointe vers autre vidéo si ça me plaît pas »*.

### Backend : 4 endpoints + 1 helper transverse

- **`_run_isolated_lookup(sys_prompt, user_msg, open_tag, close_tag, …)`** : factorisation du pattern partagé « ClaudeClient jetable + parse balise → dict ». Retourne `(payload, engine, error_response_or_None)`. Caller propage `error_response` si non-None. Utilisé par les 4 endpoints lookup ci-dessous + `/api/find_similar_exo`.
- **`POST /api/find_similar_exo`** (extension Z.8.4) :
  - Nouveaux params : `difficulty: easier|harder|different|null` et `exclude: [{matiere, type, num, exo}]` (cap 20). Le system prompt est étendu en fin avec les consignes de difficulté et la liste des exos à éviter.
  - Frontend mémorise `foundExoHistory` à chaque réponse `found=true` et le passe en `exclude` au prochain appel, ce qui évite le retombe sur le même exo.
- **`POST /api/find_cm_passage`** (nouveau, C2) :
  - Body `{description}`. Mode `MODE_GUIDE` avec `cours_root=COURS/{matiere}/`. System prompt `FIND_CM_PASSAGE_PROMPT_TEMPLATE` qui interdit le corrigé en cours et exige sortie balisée `<<<CM_FOUND>>>{filename, label, page, extract, why, …}<<<END>>>`.
  - Backend résout le `pdf_path` via `(matiere_dir / "CM").rglob(filename)` après le parse.
- **`POST /api/web_search_exo`** (nouveau, A1) :
  - Body `{description, exclude_urls}`. Engines supportés : `api_anthropic` et `gemini_api`. Sur les autres → 400 `engine_unsupported` avec liste des moteurs supportés (le frontend gère via `flashEngineSwitcher()`).
  - System prompt `WEB_SEARCH_EXO_PROMPT` qui contraint les sites éducatifs FR (Bibmath, Exo7, Wikiversité, Khan Academy FR, fiches-bac, kartable, etc.) et exclut les sites de devoirs corrigés.
  - Sortie balisée `<<<WEB_FOUND>>>{results: [{title, url, source, why, kind}]}<<<END>>>`.
- **`POST /api/find_youtube_video`** (nouveau, C3) : symétrique, prompt qui privilégie les chaînes Yvan Monka, JeChercheUneOrange, Heu?reka, Science Étonnante, etc. Sortie `<<<YT_FOUND>>>{results: [{title, url, channel, why}]}<<<END>>>`.

### Backend : recherche web native dans `claude_client.py`

- Nouveau flag `_enable_web_search` + setter `set_enable_web_search(bool)` sur `ClaudeClient`.
- **API Anthropic (`_stream_via_api`)** : ajoute un tool `{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}` dans `api_kwargs["tools"]` quand le flag est ON. Cohabite avec les tools natifs existants (concat).
- **Gemini (`_stream_via_gemini`)** : ajoute `tools=[Tool(google_search=GoogleSearch())]` dans `GenerateContentConfig`. Fallback warning si SDK trop ancien : le LLM répond depuis sa connaissance interne (dégradé mais utilisable).
- DeepSeek/Groq/CLI ne supportent pas → no-op silencieux. Les endpoints web/yt rejettent avec 400 `engine_unsupported` AVANT d'appeler le client, donc pas de surprise runtime.

### Frontend : boutons contextuels et bulles dédiées

- **Tone-toolbar** sous chaque bulle Compagnon (en colle uniquement) : `🔍 Exo voisin` + nouveaux `📚 Passage CM` + `🎬 Vidéo`. Tous prennent le contexte de la bulle parente + dernier student précédent via `_buildContextualExoDescription`.
- **Bulle exo voisin** (`renderFoundExoBubble`) : nouvelle ligne « Pas satisfait ? » avec 5 boutons :
  - `📉 Plus simple` / `📈 Plus dur` / `🔄 Autre angle` → re-call `/api/find_similar_exo` avec `difficulty` + `exclude=foundExoHistory`.
  - `🌐 Sur internet` → `performWebSearchExo(description)`.
  - `🎬 Vidéo YouTube` → `performFindYoutube(description)`.
- **Bulle « rien trouvé »** (`_renderEmptyExoBubble`) : 3 boutons de redémarrage `🌐 Sur internet` / `🎬 Vidéo YouTube` / `📚 Passage du CM`. Évite l'impasse "rien trouvé en local, fin du jeu".
- **Bulle web** (`_renderWebResultsBubble`) : liste des liens externes formatés (titre + source + kind + why), bouton `🌐 Autre ressource` qui re-call avec `exclude_urls=seenWebUrls` pour éviter les doublons.
- **Bulle vidéo** (`_renderYoutubeResultsBubble`) : liste des vidéos avec channel + why, bouton `🎬 Autre vidéo` symétrique.
- **Bulle CM** (`_renderCmPassageBubble`) : label du document + page + extrait copié du poly + bouton `📄 Ouvrir le PDF` qui ouvre dans nouvel onglet.

### Frontend : mémoires de session (Phase Z.9 B2 généralisé)

Trois listes globales reset à `initCorrectionsPanel` :
- `foundExoHistory: [{matiere, type, num, exo}]` : exos voisins déjà proposés.
- `seenWebUrls: [string]` : URLs externes déjà vues.
- `seenYoutubeUrls: [string]` : vidéos YouTube déjà vues.

Chaque appel API correspondant passe la liste appropriée en `exclude` / `exclude_urls`. Le LLM intègre la consigne « ces refs ont déjà été suggérées, propose-en de DIFFÉRENTES ». Si vraiment rien d'autre, retourne `{none: true}` avec une raison claire (« tu as déjà vu les bons candidats »).

### CSS : bulles colorées par type

- `.found-exo-bubble` (orange) : exo voisin (existant Z.8.4).
- `.found-web-bubble` (bleu `rgba(98, 168, 255, …)`) : ressources internet.
- `.found-video-bubble` (rouge `rgba(231, 76, 60, …)`) : vidéo YouTube.
- `.found-cm-bubble` (vert `rgba(46, 204, 113, …)`) : passage CM.
- `.found-exo-alts` : barre d'actions « pas satisfait » avec border-top dashed teintée.
- `.found-web-list` / `.found-web-item` : cards pour chaque résultat web/yt.

### Tests / validation

- 223 tests Python OK (factorisation + nouveaux endpoints, pas de régression backend).
- Validation manuelle prévue par Gstar : (a) cliquer 🔍 → bulle exo voisin avec 5 boutons « pas satisfait ». (b) Re-cliquer 🔄 → exo différent (pas le même grâce à `exclude`). (c) Bouton 🌐 sur engine non supporté → confirm + flash sélecteur. (d) Bascule sur Gemini, re-cliquer 🌐 → 2-3 liens externes affichés avec why. (e) Bouton 🎬 → 1-3 vidéos avec channel. (f) Bouton 📚 sous bulle Compagnon → page + extrait du CM + bouton ouvrir PDF.

### Pas livré (consciemment)

- Pas de tests automatisés sur les 3 nouveaux endpoints : mock du tool web_search d'Anthropic et du Search Grounding de Gemini est complexe et pas critique en Phase A (ce sont des wrappers). Validation runtime par Gstar.
- Pas de cache des résultats web/yt : chaque clic re-déclenche un appel. Invocations rares (1-3 par session de blocage), donc pas un enjeu.
- Pas de filtrage de domaines au niveau Python : on s'appuie sur la consigne du system prompt. Si dérive observée, un postprocess pourra blacklister certains domaines (Stack Overflow, sites de copies gratuites).

---

## Phase Z.8.6 : Bouton 🔍 contextuel sous chaque bulle tuteur + cleanup conflit emoji (2026-05-09, soirée)

**Friction.** Le bouton 💡 livré en Z.8.4 demandait à l'étudiant de décrire son blocage via `window.prompt` à chaque clic. Or sur le cas concret EN1 CC2 (le tuteur en colle vient de poser *« Définissez, avec vos mots, la fonction d'un multiplexeur MUX21. »*), l'étudiant ne sait justement pas comment formuler son blocage : il a besoin d'un exo voisin **sur exactement ce que le tuteur lui demande**. Demander de re-décrire est redondant et frictionneux. Citation utilisateur : *« moi je sais pas comment définir mes propres mots, bon ben je clique sur le bouton et après ben à toi de voir ce qui se fera, je te laisse champ libre, ça doit juste être bien quoi anticipe les choses ».*

Aussi : conflit visuel sur l'emoji 💡, utilisé par le bouton footer Z.8.4 ET par le preset "Avec exemple" de la `tone-toolbar` sous chaque bulle Compagnon. Deux sens différents pour le même icône au même endroit.

**Livré.**

### Bouton 🔍 contextuel dans la `tone-toolbar`
- `appendToneToolbar(parentTurn)` enrichi avec un 7ᵉ bouton « 🔍 Exo voisin » placé après les 6 presets de reformulation, **visible en mode colle uniquement** (`activeMode === "colle"`). En guidé, le tuteur a déjà accès FS, donc bouton inutile.
- Click → récupère le texte de la bulle Compagnon parente (`parentTurn.dataset.rawText` ou `textContent`) + le dernier message student rendu **avant** cette bulle (helper `_getLastStudentTextBefore`). Construit une description structurée via `_buildContextualExoDescription` :
  ```
  Le tuteur vient de me dire / demander :
  
  <texte tuteur>
  
  Ma dernière intervention était :
  
  <dernier student>
  
  Je bloque pour répondre, trouve-moi dans mes cours un exercice voisin du même type pour m'entraîner avant de revenir à celui-ci.
  ```
- Borne 800 chars sur le texte tuteur, 400 sur le student → évite d'envoyer des dumps massifs. Suffisant pour le contexte d'un blocage.
- Bouton désactivé pendant l'appel (sur ce bouton précis, pas tous), s'auto-réactive au `.finally`.

### Refacto `performFindSimilarExo(opts)`
- Avant : prend toujours le contrôle du bouton footer + `window.prompt` obligatoire.
- Après : accepte `opts.description` optionnel.
  - Si fourni (cas 🔍 toolbar) → utilise direct, skip le prompt.
  - Sinon (cas 🔍 footer ou appel direct) → prompt manuel comme avant.
- Le state visuel du `findExoBtn` (footer) est **conditionnel** : si le bouton est absent ou hidden (mode guidé), on saute, la bulle "🔍 Recherche…" suffit comme indicateur. Garde-fous `if (findExoBtn)` partout.

### Cleanup conflit emoji 💡
- `TONE_PRESETS["Avec exemple"]` : emoji `💡` → `📖` (livre, sémantique pédagogique cohérente avec l'action « illustrer avec un exemple concret »).
- Bouton footer `#find-exo-btn` : emoji `💡` → `🔍` (loupe, cohérent avec le 🔍 de la toolbar). Title actualisé.
- `findExoBtn.textContent = "🔍"` au reset (au lieu de `"💡"`).
- Résultat : `🔍` partout pour « Trouve un exo voisin » (toolbar + footer), `📖` pour « Avec exemple » (preset reformulation). Plus aucune ambiguïté.

### Docs
- README.md section « Bouton 🔍 Trouve un exercice voisin » réécrite pour expliquer les **deux entrées** (contextuel sous chaque bulle vs manuel dans le footer) avec leurs use cases respectifs.

### Tests
- 223 tests Python OK (changements purement frontend).
- Validation manuelle prévue par Gstar : (a) en colle, le 🔍 apparaît sous chaque bulle tuteur. (b) clic → bulle "🔍 Recherche…" → bulle résultat avec énoncé. (c) en guidé, ni 🔍 footer ni 🔍 toolbar n'apparaissent. (d) le 💡 résiduel pour "Avec exemple" est bien remplacé par 📖 partout.

### Pas livré (consciemment)
- Pas de prise en compte de plusieurs bulles précédentes (juste la bulle parente + 1 student précédent). Si l'échange courant porte sur un long aller-retour autour du même point, on prend la fin, suffisant en pratique. Si dérive observée, on étendra à 2-3 derniers tours.
- Pas de bouton 🔍 sur les bulles `student` ou `system` : uniquement sur les bulles Compagnon (où la `tone-toolbar` est attachée).

---

## Phase Z.8.4 : Bouton 💡 « Trouve un exo équivalent » + fix SHOW_DOC multi-corrigés (2026-05-09, soirée)

Deux frictions traitées en une passe.

### Friction 1 : bug SHOW_DOC sur sessions multi-corrigés

L'utilisateur en mode guidé sur TD8 EN1 (5 exercices, donc 5 fichiers `correction_TD8_EN1_ex<N>.pdf`) constate :

> « le tuteur a tenté d'afficher la page 10 du corrigé de l'exercice 3, mais le système a ouvert une page du corrigé de l'exercice 1 à la place »

**Cause.** Le payload SHOW_DOC ne contenait que `{kind, page}`. Le handler côté front faisait `correctionsList.findIndex(c => c.kind === kind)` qui retourne **toujours le 1ᵉʳ corrigé du kind** dans l'ordre du listing, indépendamment de l'exo ciblé. Idem pour `linkifyPageRefs` : la regex capturait `page X du corrigé` mais pas le `de l'exercice N` qui pouvait suivre, donc tous les liens cliquables du tuteur pointaient vers le 1ᵉʳ corrigé.

**Fix.**

- **Backend** `_build_document_entry` : nouveau champ `exo` extrait du filename via regex `_ex([\w.]+?)(?:_\d{4}-\d{2})?\.pdf`. Patterns supportés : `ex3`, `ex3.5` (sous-question), `ex3_2024-25` (CC daté). Retourne `None` si pas de pattern (énoncé global, script imprimable).
- **Backend** `_extract_exo_from_filename(name)` : helper isolé, testable.
- **Frontend** SHOW_DOC handler : payload accepte désormais `exo` optionnel. `_findDocIdx(kind, exoStr)` matche d'abord `(kind === target && exo === target)`, fallback sur 1ᵉʳ du kind avec warning console.
- **Frontend** `jumpToCorrigePage(pageN, kind, opts={})` : `opts.idx` (priorité 1, déjà résolu par caller), `opts.exo` (priorité 2, résolu via `_findDocIdx`), sinon 1ᵉʳ du kind.
- **Frontend** `linkifyPageRefs` : regex étendue `(?:\s+(?:de\s+)?(?:l['']?)?(?:exercice|exo|ex)\.?\s*(\d+(?:\.\d+)?))?` pour capturer optionnellement le numéro d'exo après le kind. Le 3ᵉ groupe est passé à `jumpToCorrigePage`. Title et dataset.exo enrichis.
- **Prompt** `PROMPT_SYSTEME_GUIDE.md` §2.11 : format de la balise enrichi avec champ `exo`. Section dédiée explique que ce champ est **obligatoire** quand plusieurs corrigés existent (1 par exercice) : sans lui, le 1ᵉʳ corrigé est ouvert et c'est faux dans la majorité des cas. Exemples mis à jour.

Effet : « voir page 10 du corrigé de l'exercice 3 » dans une bulle tuteur ouvre maintenant le bon corrigé. Pour SHOW_DOC, le tuteur émet `{"kind":"correction","page":10,"exo":"3"}` et l'UI route correctement.

### Friction 2 : exo équivalent en mode colle (Option A)

Cas d'usage : étudiant en colle sur un CC, bloqué sur un exo. Veut un **exemple voisin** dans son arbo `COURS/` pour s'entraîner SANS être spoilé par le corrigé du CC en cours. Le mode colle pur n'a pas accès FS, le mode guidé a tout y compris le corrigé en cours → spoil garanti.

**Solution livrée.** Un appel Claude **jetable** isolé de la conv principale, déclenché par un bouton 💡 dédié.

- **Backend** `POST /api/find_similar_exo` :
  - Input : `{description}` (description du blocage). Le contexte (matière, type, num, exo) est lu depuis la session active.
  - Construit `FIND_EXO_SYSTEM_PROMPT_TEMPLATE` qui :
    1. Précise le contexte de la session.
    2. **Interdit explicitement de Read le corrigé en cours** (`correction_{type}{num}*.pdf`).
    3. Exige : énoncé brut + 1 phrase sur la similarité, **pas de solution**.
    4. Format de sortie balisé `<<<EXO_FOUND>>>{json}<<<END>>>` pour parsing déterministe.
  - Lance `ClaudeClient` jetable en `MODE_GUIDE` avec `cours_root=matiere_dir` (scope FS limité à `COURS/{matiere}/` : pas de fuite vers d'autres matières ou perso).
  - User message minimal : « Lance la recherche. ».
  - Parse la balise, retourne `{found, exo: {matiere, type, num, exo, label, why, enonce}, engine}` ou `{found: false, reason}`.
  - Codes : 400 (description vide), 409 (pas de session), 429 (quota), 502 (claude_error / json_invalide / balise_absente).

- **Frontend** :
  - Bouton `<button id="find-exo-btn">💡</button>` ajouté dans le footer du dialogue, à côté de ✨ Améliorer. Visible UNIQUEMENT en mode colle (`refreshFindExoBtnState` synchro avec `activeMode`). Caché en guidé (où le tuteur peut déjà fouiller naturellement).
  - Click → `window.prompt` pour décrire le blocage → POST → bulle "🔍 Recherche…" temporaire → remplacée par le résultat.
  - `renderFoundExoBubble(exo)` : bulle système typée `.found-exo-bubble` avec :
    - Label "💡 Exercice voisin (hors session)" + timestamp
    - `.found-exo-label` : matière + type + num + exo
    - `.found-exo-why` : phrase courte sur la similarité (rendue via `renderMarkdown`)
    - `.found-exo-enonce` : énoncé brut dans un encadré dédié (rendu markdown)
    - `.found-exo-hint` : avertissement « Le tuteur de la colle ne voit pas cet exo. Quand tu reviens, dis-le-lui pour qu'il sache que tu as fait le détour. »
    - Boutons 📋 (copier énoncé) et 🗑 (masquer)
  - CSS : bordure jaune-orange `rgba(255, 167, 38, 0.55)` pour distinguer visuellement de la conv principale.
  - Gestion 429 réutilise `formatQuotaErrorFr()` du Phase v15.6.4 : message FR clair et bouton bascule moteur si quota épuisé.

**Pourquoi pas en mode guidé.** En guidé, le tuteur a déjà Read/Grep/Glob et peut fouiller naturellement à la demande. Le bouton 💡 serait redondant et risquerait de doubler des appels.

**Coût.** ~2-5k tokens input (system prompt + listing FS via Glob/Read), ~500-1500 tokens output. Sur quota Pro Max invisible. Sur API ~$0.01-0.03 par recherche. Volume estimé : 1-5 par session.

### Tests
- 223 tests Python OK (refacto purement endpoints + frontend).
- Sandbox node : 8 cas markdown listes/HR de Phase Z.8.1 préservés.
- Validation manuelle prévue par Gstar : (a) bouton 💡 visible en colle, caché en guidé. (b) clic prompt + bulle résultat. (c) re-clic même session = nouvelle recherche. (d) test SHOW_DOC `{exo:"3", page:10}` ouvre bien le 3ᵉ corrigé.

### Pas livré (consciemment)
- Pas de mémorisation des exos voisins déjà proposés au sein de la session : chaque clic 💡 redemande à zéro. Pas grave, l'utilisateur fait rarement plus de 2-3 recherches par session.
- Pas de re-injection automatique de la recherche dans la conv principale du tuteur. C'est volontaire (isolation forte). L'utilisateur le mentionne au tuteur quand il revient.
- Pas de garde-fou backend qui filtre les `correction_*` du dossier en cours dans les Read autorisés : on s'appuie sur le prompt système pour la discipline. Les modèles SOTA respectent cette consigne en pratique. Si dérive observée, on durcira via un wrapper Read côté CLI.

---

## Phase Z.8 : Suppression du mode `lecture`, absorbé par `guidé` (2026-05-09, soirée)

**Friction.** Verbalisée par Gstar : *« Dans compagnon révision le mode lecture ne sert à rien étant donné que le mode guidé est une version plus complète. Supprime le partout et documente cette suppression. »*

Le mode `lecture` (Phase A.7-light, livré 2026-05-05) avait été pensé comme tuteur libre avec accès FS Read/Grep + suggestions de correction `<<<SUGGESTED_EDIT>>>`. Le mode `guidé` (Phase A.7.2 v5, livré 2026-05-07) avait été conçu **comme une variante UI de lecture** : mêmes capacités tuteur (le code partageait `PROMPT_SYSTEME_LECTURE.md`, `LECTURE_ALLOWED_TOOLS`, `MODE_LECTURE` était listé dans la branche `guidé`) avec en plus une UI slide-par-slide.

En pratique, après quelques semaines d'usage, `guidé` est devenu strictement supérieur à `lecture` :
- Sur les TD/TP/CC qui ont script + slides → on prend `guidé` (UI structurée).
- Sur les TD/TP/CC qui n'ont QUE le script (pas de slides) → on aurait pris `lecture`, mais en pratique on prenait quand même `guidé` qui dégrade gracieusement vers de la lecture libre dans ce cas (la nav slide est juste désactivée).
- Sur les CM bruts à explorer sans slides → on aurait dit « lecture », mais aucune session de Gstar ne s'est faite dans ce cas en pratique.

Donc `lecture` n'apportait aucune valeur unique. Maintenir 3 modes alors que 2 suffisent ajoutait du bruit dans la doc, dans la GUI (radio à 3 boutons), dans les tests, et dans le prompt (qui devait dire « ce qui s'applique en mode lecture *et* en mode guidé »).

**Livré.**

### Suppression du mode `lecture` partout dans le code
- **`_scripts/dialogue/claude_client.py`** :
  - Constante `MODE_LECTURE = "lecture"` retirée.
  - `LECTURE_ALLOWED_TOOLS` renommée `GUIDE_ALLOWED_TOOLS`.
  - Validation `mode in (MODE_COLLE, MODE_LECTURE, MODE_GUIDE)` simplifiée en `(MODE_COLLE, MODE_GUIDE)`.
  - Branche CLI `if self._mode in (MODE_LECTURE, MODE_GUIDE)` simplifiée en `if self._mode == MODE_GUIDE`.
- **`config.py`** : `PROMPT_SYSTEME_LECTURE_PATH` renommée `PROMPT_SYSTEME_GUIDE_PATH`.
- **`_prompts/PROMPT_SYSTEME_LECTURE.md`** renommé via `git mv` en `_prompts/PROMPT_SYSTEME_GUIDE.md` pour préserver l'historique git. Header du fichier mis à jour : titre « Mode guidé », version 1.6, branchement actualisé. Les mentions internes « mode lecture » → « mode guidé » (env. 8 occurrences). Le contenu pédagogique du prompt n'a PAS bougé : c'est exactement le même tuteur, juste rebadgé.
- **`_scripts/web/app.py`** :
  - Imports `MODE_LECTURE`, `PROMPT_SYSTEME_LECTURE_PATH` retirés / renommés.
  - 2 sites de check du mode (`/api/start_session`, `/api/resume_session`) simplifiés.
  - Choix du prompt : `PROMPT_SYSTEME_GUIDE_PATH if mode == MODE_GUIDE else PROMPT_SYSTEME_PATH`.
- **`compagnon.py`** (CLI) : argparse `choices=("colle", "lecture", "guidé")` → `("colle", "guidé")`. Aide actualisée.
- **`gui.py`** : radio « Lecture » supprimée. Fallback du radio « Guidé » quand matériaux indisponibles : avant `self.mode.set("lecture")`, maintenant `self.mode.set("colle")`.
- **`_scripts/dialogue/parser.py`** : commentaires « Phase A.7 lecture », « lecture/guidé » → « mode guidé ».
- **`_scripts/dialogue/output_filters.py`** : header doc `mode lecture/guidé` → `mode guidé`.
- **`_scripts/web/static/app.js`** : `let activeMode  // "colle" | "lecture" | "guidé"` → `// "colle" | "guidé"`.
- **`_scripts/web/templates/index.html`** : `<option value="lecture">Lecture</option>` retiré du select. Title du select reformulé.

### Archivage
- `_prompts_claude_ai/LECTURE.md` → `_prompts_claude_ai/_archived/LECTURE_2026-05-09.md` (via `git mv`).
- `_prompts_claude_cowork/LECTURE.md` → `_prompts_claude_cowork/_archived/LECTURE_2026-05-09.md`.
- `README.md` de chaque dossier mis à jour : section « Mode d'emploi » et « Quand utiliser quoi » réécrites pour 2 prompts au lieu de 3, avec note explicite de la suppression Phase Z.8 et pointeur vers `_archived/`.

### Tests adaptés
- `tests/test_runtime_settings.py` : 4 occurrences `"mode": "lecture"` → `"mode": "guidé"` dans les fixtures de roundtrip.
- `tests/test_switch_engine.py` : `fake_client._mode = "lecture"` → `"guidé"`, `kwargs["mode"]` assert idem.
- `tests/test_tool_calling.py` : `mode="lecture"` → `mode="guidé"` dans le setup ClaudeClient.
- `tests/eval_prompt.md` : titre de section « Mode lecture/guidé » → « Mode guidé ».
- 223 tests OK après refonte (pas de régression).

### Docs synchronisées
- **`README.md`** : header "Phase A.7-light" garde la mention historique avec note Phase Z.8 explicite. Section « Mode colle vs Mode lecture vs Mode guidé » → « Mode colle vs Mode guidé », sous-sections fusionnées (l'ex « Mode lecture » devient le corps de « Mode guidé »). Tableau quota tours, latence, références prompt système, etc. tous actualisés.
- **`CLAUDE.md`** : §1.4 listing des prompts (lecture → guidé v1.6), §2 arborescence, §11 pointers utiles. Mention Phase Z.8 dans le fichier prompt.
- **`ARCHITECTURE.md`** : §1, §3, §4.1 (signature `mode`), §6 (commandes CLI), §8 (endpoints), §9 (dialogue) : toutes les mentions « mode lecture » devenues « mode guidé », sauf le récap historique des phases qui garde la trace de A.7-light Mode lecture (cf. `tests/test_app_apply_edit.py` qui reste valide pour le mode guidé).
- **`tests/eval_prompt.md`** : actualisé.

### Pas livré (consciemment)
- Pas de migration des fichiers `_sessions/*.json` historiques qui auraient `"mode": "lecture"` en clé. Si l'utilisateur reprend une vieille session en mode `lecture`, le backend rejette avec erreur 400 « mode invalide ». Acceptable : Phase A.7.2 v15 introduit déjà la modal « session existante détectée » qui propose de démarrer une nouvelle session. À voir si Gstar a des sessions actives en mode `lecture` au moment du déploiement, sinon migration manuelle simple par sed/jq.
- Pas de retour en arrière des sections historiques du CHANGELOG (Phase A.7-light, A.7.1, A.7.2 v8-v14) qui mentionnent « mode lecture ». Ces sections décrivent l'historique fidèle, on ne réécrit pas le passé.

---

## Phase A.7.2 v15.6.5 : Panneau Quota multi-moteurs (DeepSeek balance live + tiers Groq/Gemini/Anthropic) (2026-05-09)

**Friction.** Au moment où Gstar se prend une 402 DeepSeek puis une 413 Groq en plein TD7 (cf. v15.6.4), il demande : « j'peux pas voir le quota de mes autres trucs afficher dans quota ? et un truc en live ? ». Le panneau Quota n'affichait que Pro Max : aucune visibilité sur le solde DeepSeek, l'état Groq/Gemini, ou si une clé API était même configurée. Le user devait deviner ou aller sur les consoles externes.

**Livré.**

### Backend : `/api/quota` étendue avec un bloc `engines`
- Snapshot Pro Max retourné comme avant (compatibilité front), plus un nouveau bloc `engines` :
  - **DeepSeek** : appel `GET https://api.deepseek.com/user/balance` avec `Bearer DEEPSEEK_API_KEY`. Retourne `total_balance` / `granted_balance` / `topped_up_balance` en USD parsés depuis la string JSON. Endpoint officiel et stable. Timeout 5 s, tolérant aux 401 (clé invalide) et erreurs réseau (`{error}` retourné, autres moteurs continuent).
  - **Groq / Gemini / API Anthropic** : pas d'endpoint balance public chez ces providers, donc on retourne juste `key_present` (présence de la var d'env) + les limites du free tier hardcodées depuis la doc :
    - Groq → 30 RPM, 12 000 TPM, 14 400 RPD (free tier).
    - Gemini → 60 RPM, 1500 RPD.
    - API Anthropic → tier "Pay-as-you-go" sans limite chiffrée.
- Helper `_collect_engines_status()` avec **cache 30 s** (`_engines_status_cache_ts`), aligné sur le polling frontend pour qu'1 hit DeepSeek/30 s suffise.
- Helper `_safe_float()` pour convertir les balances DeepSeek (renvoyées en string) en float Python.

### Frontend : section « 🔌 Autres moteurs » sous Pro Max
- `renderQuota` désormais composé de deux blocs : `🤖 Claude Pro Max` (existant) puis `🔌 Autres moteurs` (nouveau) via `renderEnginesStatus(d.engines)`.
- DeepSeek : affichage avec barre colorée (verte si > 0.5 $, orange < 0.5 $, rouge si épuisé) + détail textuel `2.13 USD restants (gratuit 5.00 + rechargé 0.00)`. Lien ⚙ cliquable vers `https://platform.deepseek.com/billing`. Si clé absente → `Pas de clé API configurée`. Si erreur API → `❌ HTTP 401` + lien.
- Groq/Gemini/API Anthropic : ligne compacte (grid 4 colonnes : icon · label · status · detail) avec icon emoji thématique (⚡/✨/🧠), label, statut (✓ ou tiret), et détail type `Free Tier · 30 RPM · 12 000 TPM · 14 400 RPD`.
- CSS dédié : `.quota-section-title` (en-têtes), `.engine-row` / `.engine-row-bar` (compact ou avec barre), `.engine-billing-link` (lien ⚙ accent), `.engine-broken-hint` (rouge italique).
- `escapeHtml()` appliqué sur les valeurs interpolées (label, detail) pour éviter une injection si un provider renvoyait du HTML dans son message d'erreur.

### Polling 30 s (au lieu de 60 s)
- `QUOTA_POLL_MS` raccourci à 30 000 ms pour la « sensation live » sur le solde DeepSeek qui peut baisser à chaque rewrite/stream.
- Cache backend 30 s aligné dessus → en pratique 1 hit `/user/balance` par 30 s, indépendamment du nombre d'utilisateurs ou d'onglets ouverts.

### Tests
- 223 OK (tests Python : la nouvelle route est testable mais en mode mock pas urgent en Phase A).

**Pas livré (consciemment).**
- Pas de balance pour Groq/Gemini/Anthropic : ces providers n'exposent pas d'endpoint public. Si Groq sort une API balance dans le futur, on l'ajoutera.
- Pas de tracker historique des consommations (« t'as utilisé 1.27 $ de DeepSeek aujourd'hui »). Le panneau est un snapshot, pas une time-series. À voir Phase B si utile.
- Pas d'auto-refresh post-rewrite (forcer un fetch après chaque appel API consommateur). Le polling 30 s suffit, et le cache backend bloquerait l'invalidation immédiate de toute façon.
- Pas de tests automatisés du nouveau bloc `engines` côté backend : la mock de `urllib.request.urlopen` est fastidieuse en stdlib pure (pas de pytest-httpx). Validation manuelle par Gstar en session.

---

## Phase A.7.2 v15.6.4 : Erreurs moteur explicites en français + bascule guidée (pas d'auto-fallback) (2026-05-09)

**Frictions** : pendant TD7 ex2 sur l'additionneur MUX (mode guidé) :

1. **DeepSeek 402 « Insufficient Balance »** : la clé API était à zéro. Le rewrite ✨ et le stream principal balançaient un dump SDK brut en anglais : `Rewrite échoué : DeepSeek erreur : Error code: 402 - {'error': {'message': 'Insufficient Balance', 'type': 'unknown_error', ...}}`. Pas de proposition d'action, message cryptique pour un étudiant.
2. **Groq 413 « Request too large for model »** : bascule en désespoir vers Groq Llama 3.3 70B free tier qui limite à 12 000 TPM, mais la session avec script + corrigés + transcript faisait 55 882 tokens. Erreur SDK encore brute.
3. **Pas d'auto-fallback voulu** : le user a dit explicitement : « Ben faut juste me dire qu'il y a plus de solde et me proposer de changer de moteur pas que ça repasse automatiquement sinon je vais pas savoir. » Le choix de moteur est une décision consciente (préserver Pro Max pour le stream principal, par exemple) : switcher dans son dos défait la stratégie.

**Livré.**

### Backend : mapping erreur → quota dans `_stream_via_openai_compatible`
- Avant : seul `RateLimitError` (429) était mappé sur `ClaudeQuotaExhaustedError`. Les autres erreurs (402, 413, context_length_exceeded) tombaient dans `ClaudeClientError` générique → 502 cryptique côté frontend.
- Après : détection sur la string de l'erreur SDK des motifs « moteur HS pour cette requête » → tous mappés sur `ClaudeQuotaExhaustedError` :
  - `402` / `insufficient balance` / `payment required` (DeepSeek sans solde).
  - `413` / `request too large` / `tokens per minute` (Groq TPM dépassé).
  - `context_length_exceeded` / `context length` (DeepSeek 64k, Gemini 1M atteint sur sessions très longues).
  - `rate_limit_exceeded` (générique).
- Bénéficie aux deux endpoints : `/api/rewrite` renvoie 429 (au lieu de 502) → confirm front avec proposal de bascule. `/api/stream_response` déclenche le card `quota_midflow` existant (au lieu d'un event `error` brut) → list des fallbacks dispo.
- Le détail brut de l'erreur SDK reste dans le message (la string « Limit 12000, Requested 55882 » est précieuse pour comprendre).

### Frontend : `formatQuotaErrorFr(engine, detail)` : 5 cas explicites en FR
- Helper centralisé dans `app.js`, réutilisé par le rewrite confirm + le stream SSE error event.
- Cas couverts (regex sur `detail.toLowerCase()`) :
  - 💳 **Solde insuffisant** (DeepSeek 402) : *« n'a plus de solde sur ta clé API. Recharge sur platform.deepseek.com/billing ou bascule. »*
  - 📏 **Requête trop grosse / TPM** (Groq 13) : extraction du motif `Limit X, Requested Y` pour formater *« ta requête fait 55 882 tokens, mais Groq n'accepte que 12 000 tokens/minute »*. Suggestion : *« Bascule sur Claude CLI (1M tokens), Gemini 2.5 Pro (1M), ou API Anthropic (200k). »*
  - 📦 **Contexte session trop long** : idem.
  - ⏱ **Rate limit RPM/RPD** : *« attends 1-5 min ou bascule. »*
  - 🚫 **Quota Anthropic** : *« le reset Pro Max est visible dans le panneau Quota. »*
- Chaque entrée retourne `{title, cause, suggestion}` qu'on assemble dans un `confirm()` (rewrite) ou un `appendTurn("system", ...)` (stream).

### Frontend : `flashEngineSwitcher()` + CSS `.flash-attention`
- Quand l'utilisateur clique « Oui » sur le confirm de bascule, on appelle `flashEngineSwitcher()` qui :
  1. Scroll vers `#engine-switcher` (en haut, dans la barre).
  2. Anim 3 pulses orange (`@keyframes flash-attention-pulse` : 0.6 s × 3 = 1.8 s) avec outline + box-shadow + background dégradé.
  3. Focus le `<select>` pour que le user n'ait qu'à appuyer ↑/↓ pour changer.

### Stream SSE error event : détection fine
- Avant : `appendTurn("system", "[Erreur stream] " + (info || "connexion perdue"))` brut.
- Après : si `info` matche le motif quota (regex sur 402/413/insufficient/too.large/tokens per minute/context.length/rate.limit), on formate via `formatQuotaErrorFr()` pour afficher `{title}\n{cause}\n{suggestion}\n\nDétail technique: ...`. Sinon on garde le fallback générique.

### Tests
- 223 OK (refacto + nouveau code, pas de test dédié au formatter FR : c'est purement frontend, sans test JS dans le projet).

**Pas livré (consciemment).**
- Pas d'auto-fallback dans `/api/rewrite`. Le user reste maître. (Une version draft avec fallback chain `[primary, cli_subscription]` existait dans une révision intermédiaire, retirée sur demande explicite.)
- Pas de modal stylé pour le confirm : le `window.confirm()` natif suffit pour le moment, et son comportement bloquant est approprié (l'utilisateur doit décider avant de retourner à son flow).

---

## Phase A.7.2 v15.6.3 : Bouton ✨ activé après abort mic (preview WebSpeech) (2026-05-09)

**Friction.** Le user dicte au mic, arrête (re-click 🎤 → `abortRecordingAndTranscribe` depuis v15.6.2), l'input contient la preview WebSpeech (ex: 80 caractères), MAIS le bouton ✨ Améliorer reste désactivé. Or il devrait s'activer (seuil 8 chars).

**Cause.** La preview WebSpeech remplit `userInput.value` **programmatiquement** (`userInput.value = liveTranscriptFinal + interim` dans le handler `recognition.onresult`). Or l'event DOM `input` ne se déclenche QUE pour les modifs au clavier, pas pour les assignations JS. Donc mon listener `userInput.addEventListener("input", refreshRewriteBtnState)` ne se déclenchait jamais pendant la dictée.

Et depuis v15.6.2, le re-clic 🎤 n'appelle plus `onRecordingStopped` (qui faisait déjà `refreshRewriteBtnState()` en v15.6) mais `abortRecordingAndTranscribe()` qui n'avait pas ce reflexe.

**Livré.** Appel explicite à `refreshRewriteBtnState()` en fin de `abortRecordingAndTranscribe()`. Le bouton ✨ se met à jour dès que le mic est arrêté.

**Pas livré (consciemment).** Pas de refresh sur chaque update de preview WebSpeech (chaque appel à `recognition.onresult`) : ce serait du gâchis (60 fois par seconde sur certaines phrases) et pas utile (on ne clique pas ✨ pendant qu'on parle).

---

## Phase A.7.2 v15.7 : Marker de position cliquable dans le dialogue + restoration mémoire centralisée (2026-05-09)

**Frictions** signalées en session :

1. **Repère temporel** quand on parcourt les documents : « si je tourne 8 pages dans le corrigé puis je pose une question, j'aimerais retrouver dans la conv où j'étais à ce moment ». Pas de marqueur visuel dans le stream pour matérialiser ce que l'étudiant regardait.
2. **Bug mémoire de page entre docs** : page 5 du script → switch sur l'énoncé via le picker → finit l'énoncé → revient sur le script → ça redémarre à page 1 au lieu de page 5. La mémoire `corrigePageMemory` existait déjà mais la lookup était dans le handler du picker, pas dans `showCorrige`. Une refacto antérieure ou un edge case (filename vide ?) cassait silencieusement la résolution.

**Livré.**

### Marker de position cliquable
- Helper `maybeAppendDocPositionMarker(idx, pageIdx)` debouncé à `DOC_MARKER_DEBOUNCE_MS = 1500` ms : on attend une pause de navigation avant de poser le marker, pour ne pas flooder le stream à chaque pression de flèche.
- Dédup via `lastDocMarkerKey = "idx:pageIdx"` du dernier marker posé : si l'utilisateur revient à la même position après un détour, pas de doublon.
- Marker = `<div class="doc-marker">` cliquable inline (pas une bulle complète comme student/claude). Texte type `📄 Page 5/8 du corrigé « Toutes les corrections »` avec hint `↩ retour` à droite. Click → `showCorrige(idx, pageIdx, /*notify=*/false)` (pas de re-pose) + activation auto de l'onglet Docs s'il avait été quitté.
- Reset à l'init de session (`initCorrectionsPanel`) : nouveau timeout, nouvelle dédup.
- Pas de POST silencieux à Claude. Le marker est purement local frontend : il sert juste de repère visuel pour l'étudiant.

### Mémoire de page centralisée dans `showCorrige`
- `showCorrige(idx, pageIdx, notify=true)` : si `pageIdx` est `null`/`undefined`, on consulte `corrigePageMemory.get(item.filename)` et on l'utilise. Sinon (valeur explicite), on respecte l'override.
- Picker `change` simplifié : `showCorrige(idx)` (sans 2e arg) : la mémoire est consultée à l'intérieur. Source unique de vérité pour la restauration.
- Effet : page 5 du script → bascule via picker sur énoncé → retour sur script via picker = page 5 (pas page 1).
- Flèches ←/→ inchangées : continuent à passer `pageIdx` explicite (next-page +1 sur le doc courant, ou doc suivant page 0 / doc précédent dernière page sur débordement). Sémantique linéaire prévisible préservée.
- Click sur un marker : passe `pageIdx` explicite + `notify=false` → pas affecté par la mémoire (c'est un retour intentionnel à une position précise).
- Refs cliquables `page X du corrigé` dans les bulles : passent aussi explicite.

### CSS : `.doc-marker`
- Inline-flex compact avec icône, texte, et hint à droite (`margin-left: auto`).
- Fond bleu très léger (`rgba(126, 182, 255, 0.05)`) + barre verticale gauche (border-left `0.45` opacity), couleur dimmed.
- Hover : fond plus marqué (`0.12`) + texte clair. Cursor pointer. Transition 0.15 s.
- `width: fit-content` pour que ça ne prenne pas toute la largeur, ce qui garde l'aspect "étiquette" qui s'insère discrètement entre les bulles de dialogue.

### Tests
- 223 OK (full suite Python : la refacto est purement frontend).
- Validation manuelle prévue par Gstar en session : (a) tourner 5 pages d'un doc → un marker apparaît après ~1.5 s ; (b) cliquer le marker → retour à cette position ; (c) switcher entre 3 docs via le picker → chaque retour repart à la page d'où on était parti.

**Pas livré (consciemment).**
- Pas de persistance backend de `corrigePageMemory` ni des markers. Si l'utilisateur fait Ctrl+F5, la mémoire des pages mémorisées et les markers du dialogue disparaissent (le transcript replay côté backend ne contient pas les markers : ils sont locaux). Acceptable Phase A.
- Pas de marker pour la nav guidée (mode `guidé` avec `<<<NEXT_SLIDE>>>`) : celle-là a déjà ses propres markers d'arrivée slide en `appendTurn("system", ...)`.
- Pas de bouton "supprimer ce marker" dans l'UI. Si le stream devient trop dense en markers, l'utilisateur peut juste les ignorer ou utiliser ✏ sur les bulles voisines pour scroller.

---

## Phase A.7.2 v15.6.2 : Re-click 🎤 = annuler (plus de Whisper canonique) + markdown blockquote/headings (2026-05-09)

**Frictions** signalées tout de suite après le déploiement de v15.6 :

1. **Re-click sur 🎤 finalisait via Whisper** (~1-3 s d'attente) et écrasait l'input avec la version canonique. Le user veut juste annuler le mic : la preview WebSpeech actuelle suffit, et si elle est bruitée le bouton ✨ Améliorer la nettoie en 1 click. Le pass Whisper sur ⏹ devenait redondant avec ✨, et coûtait du temps d'attente.
2. **Bug rendu markdown** : les blockquotes (`> ligne`) restaient affichés avec les `>` bruts au lieu d'être stylés. Idem pour les titres ATX (`#`, `##`, ..., `######`) qui affichaient les hashes littéralement. Le moteur `renderMarkdown` (`app.js:104`) couvrait images, code, gras/italique, listes et tables GFM, mais pas ces deux primitives pourtant courantes.

**Livré.**

### Sémantique mic unifiée : re-click = abort
- Le toggle micBtn appelle désormais `abortRecordingAndTranscribe()` (au lieu de `stopRecording()`) sur le re-click. Plus de `POST /api/transcribe`, plus d'attente Whisper, plus d'écrasement.
- `finishSession()` aligné sur la même fonction quand le mic est actif au moment où on termine la séance.
- Tooltip mic pendant l'enregistrement : « Cliquer pour annuler le mic (garde la preview dans l'input). Entrée envoie directement ce qui est dans l'input. »
- Placeholder textarea simplifié : « 🎤 Parlez… Entrée pour envoyer, ⏹ pour annuler le mic ».
- `stopRecording()` reste définie (orpheline désormais) : pas supprimée pour ne pas casser un usage qu'on aurait raté ; sera retirée si confirmée non-utilisée.

### `renderMarkdown` : ajout blockquotes + titres ATX
- **Titres `# H1` à `###### H6`** : regex `(?:^|\n)(#{1,6})\s+([^\n]+)` au début de ligne (espace requis après les `#` selon CommonMark). Inséré après gras/italique pour permettre `# **mot** important` → `<h1>` avec gras à l'intérieur.
- **Blockquotes `> ligne`** : regex `(?:^|\n)((?:&gt;\s?[^\n]*(?:\n|$))+)` qui groupe les lignes consécutives en un seul `<blockquote>` avec `<br>` entre. Important : `escapeHtml` transforme `>` en `&gt;` AVANT mes regexes, donc je matche `&gt;` (pas `>`), sinon double-échappement.
- Lookbehind/lookahead du pass `\n → <br>` étendu à `h1-h6` et `blockquote` pour ne pas insérer de `<br>` parasites autour des nouveaux blocs.
- Cleanup final `<p>\s*<\/p>` retiré pour éviter les paragraphes vides créés par les `\n\n` qui encadrent les blocs.
- CSS dédié dans `style.css` : 6 niveaux de titre avec hiérarchie typographique (H1 le plus gros, H6 en uppercase petit gris), blockquote avec barre verticale + fond légèrement teinté + italique.
- **Cas négatifs préservés** : `le #5 est important` (inline, pas début de ligne) reste tel quel ; `5 > 3` (espacé, pas de début de ligne) reste tel quel après échappement HTML.

### Tests manuels
6 cas validés en sandbox node :
| Input | Output attendu | OK |
|---|---|---|
| `> BCD0 = BN0\n> BCD5 = 0` | `<blockquote>BCD0 = BN0<br>BCD5 = 0</blockquote>` | ✅ |
| `# Titre\n\nParagraphe.` | `<h1>Titre</h1><p>Paragraphe.</p>` | ✅ |
| `## H2\n\n### H3` | `<h2>H2</h2><h3>H3</h3>` | ✅ |
| `# Hello\n\n> cite\n> suite` | `<h1>...</h1><blockquote>cite<br>suite</blockquote>` | ✅ |
| `le #5 est important` | `le #5 est important` (intact) | ✅ |
| `5 > 3 est vrai` | `5 &gt; 3 est vrai` (intact, pas de blockquote) | ✅ |

223 tests Python OK (pas de régression sur le backend).

**Pas livré (consciemment).**
- Pas de blockquotes imbriquées (`>>` `>>>`). Cas rare ; les corrigés universitaires n'en utilisent pas.
- Pas de tests JS automatisés pour `renderMarkdown` : pas de tooling JS dans le projet (vanilla, pas de Jest/Vitest). Validation manuelle via node + sandbox eval.
- Pas de support des Setext headings (`Titre\n===` ou `Titre\n---`). Format ATX (`#`) couvre tout ce que les LLM produisent en pratique.

---

## Phase A.7.2 v15.6 : Bug mic actif après envoi + bouton ✨ Améliorer le brouillon (2026-05-09)

**Friction.** Deux problèmes signalés sur la même session de dictée :

1. **Bug état mic après envoi.** Tu cliques 🎤, tu parles, tu vois la preview WebSpeech remplir l'input, tu appuies Entrée pour envoyer. Le message part bien, mais le mic continue d'enregistrer en arrière-plan (icône toujours rouge pulsée, indicator « Enregistrement… » qui continue de monter). Si tu re-cliques 🎤 pour ré-enregistrer un autre message, tu pars dans la branche `stopRecording()` au lieu de `startRecording()` → la transcription Whisper du premier enregistrement non-terminé revient écraser ton input courant. Comportement erratique et incompréhensible pour un nouvel utilisateur.
2. **Manque d'options « rewrite avant envoi ».** Quand tu dictes au micro, la transcription brute est pleine d'« euh / donc / voilà / faux départs » qui consomment des tokens et restent dans l'historique de la conversation. Aucun LLM grand public (ChatGPT, Claude.ai, Gemini, Mistral) n'expose en standard un bouton « reformule mon brouillon avant envoi ». Pourtant c'est une fonctionnalité naturelle quand on dicte beaucoup.

**Cause technique.** `app.js:sendUserMessage()` appelait `cancelPendingTranscribe()` (qui annule le `fetch /api/transcribe` en vol) mais **ne stoppait jamais le `MediaRecorder`** ni le `liveRecognition` WebSpeech ni le `micStream`. Donc à l'envoi, le mic continuait, l'indicator restait actif, et le re-clic du bouton trouvait `isRecording === true`.

**Livré.**

### Fix bug : auto-stop du mic à l'envoi (`app.js`)
- Nouvelle fonction `abortRecordingAndTranscribe()` qui :
  - Détache le listener `stop` du `MediaRecorder` AVANT de l'arrêter pour bypasser `onRecordingStopped` qui aurait posté à `/api/transcribe`.
  - Stoppe `liveRecognition` (WebSpeech) et libère `micStream` (`getTracks().forEach(stop)`).
  - Reset l'UI : icône `🎤`, classes `recording`/`transcribing` retirées, timer `recordTimerHandle` clearé, placeholder du textarea remis au défaut, `recordIndicator` désactivé.
  - **Recolle le préfixe** : si l'utilisateur avait tapé du texte AVANT de cliquer 🎤 (préservé dans `userInputBeforeRecording`), on le préfixe à la preview WebSpeech actuelle. Sinon ce texte serait perdu.
- `sendUserMessage()` appelle `abortRecordingAndTranscribe()` en première ligne si `isRecording === true`.
- Tooltip mis à jour sur le bouton mic pendant l'enregistrement : « ⏹ Arrêter et finaliser Whisper (texte propre, à relire), ou Entrée / Envoyer pour envoyer direct sans relecture ». Et placeholder du textarea : « 🎤 Parlez… ⏹ pour relire le texte propre, ou Entrée pour envoyer direct ».

**Pas de toggle nécessaire.** Les deux modes coexistent naturellement par UI :
- **Envoi direct** : `🎤` → parler → `Entrée` (ou Envoyer). Le mic s'arrête, on envoie ce qui est dans l'input (preview WebSpeech sur Chrome/Edge, ou texte tapé). Légèrement plus de tokens (~5-15% à cause des hésitations), mais Claude/Gemini gèrent sans souci.
- **Avec relecture** : `🎤` → parler → `⏹` → attendre Whisper canonique (~1-3 s) → éditer → `Entrée`. Plus propre, économe en tokens. Recommandé pour les longs messages.

### Bouton ✨ Améliorer + popover (`templates/index.html` + `static/style.css` + `static/app.js`)
- Bouton `#rewrite-btn` rond `38×38` ajouté entre `📎` et le textarea. Visuellement aligné avec `#mic-btn` et `#media-btn` (mêmes styles partagés). Disabled tant que `userInput.value.trim().length < 8` ou que la session n'est pas active.
- Popover `#rewrite-popover` (position absolute au-dessus du bouton, `z-index 50`) avec 4 actions :
  - 📝 **Reformuler** : plus clair et naturel, sens identique
  - ✂️ **Plus concis** : supprime hésitations et redondances
  - 📖 **Développer** : explicite les nuances implicites
  - ✅ **Corriger fautes** : orthographe, grammaire, ponctuation uniquement
  - ↩ **Annuler le dernier rewrite** : affiché seulement si `lastRewriteOriginal !== null`
- Click outside le popover → close (`document.addEventListener("click", _onClickOutsideRewritePopover)` ré-attaché à chaque ouverture, removed à chaque fermeture pour éviter les leaks).
- Pendant la requête : bouton passe en `⏳ busy` pulsé orange (classe `.busy`), `userInput.readOnly = true` pour bloquer les modifs concurrentes.
- Au retour 200 : `userInput.value` remplacé par `data.rewritten`, banner discret `#rewrite-banner` au-dessus du footer affiché 8 s avec lien `↩ Annuler` qui restaure `lastRewriteOriginal`.
- AbortController `rewriteInFlightAbort` annule un rewrite précédent encore en vol si l'utilisateur clique sur une autre action.

### Endpoint `POST /api/rewrite` (`web/app.py`)
- 4 intents acceptés (`reformulate`, `concise`, `expand`, `fix_typos`), chacun avec un mini-prompt explicite côté backend (constante `REWRITE_INTENTS`). System prompt isolé `REWRITE_SYSTEM_PROMPT` qui force « UNIQUEMENT le texte transformé, sans préambule, sans guillemets autour, sans markdown ».
- Cap d'entrée `REWRITE_MAX_INPUT_CHARS = 8000` (au-delà, l'utilisateur doit segmenter, ce qui évite qu'un copier-coller massif ne déclenche un rewrite monstrueux).
- Réutilise le moteur courant lu via `_read_engine_pref()` (CLI subscription / API Anthropic / Gemini / DeepSeek / Groq) : bascule automatique si l'utilisateur change le moteur dans la barre du haut.
- Construit un `ClaudeClient` jetable en mode `MODE_COLLE` (pas d'accès FS pour un rewrite), un seul tour, retourne `{rewritten, intent, engine}`. Codes : 400 (text vide / intent invalide / texte trop long), 429 (quota épuisé), 502 (erreur SDK / réponse vide).
- Strip des guillemets enveloppants éventuels (`"…"`, `'…'`, `«…»`) que le modèle peut ajouter malgré la consigne.
- **Coût** : ~300-1500 tokens in/out par appel selon longueur. Sur quota Pro Max, invisible (compté à la session). Sur API Anthropic ~$0.005 par rewrite avec Sonnet.

### Tests (`tests/test_app_rewrite.py`)
- 11 cas : text vide, whitespace seul, intent invalide, texte trop long, succès reformulate, strip guillemets simples / français, quota épuisé → 429, erreur SDK → 502, réponse vide → 502, et un loop sur les 4 intents acceptés.
- `ClaudeClient` mocké via `MagicMock` qui simule l'append + le stream_response (mute `_history` au lieu d'appeler Claude réseau).
- Total suite : **223 OK** (212 + 11).

**Pas livré (consciemment).**
- Pas de streaming pour `/api/rewrite` : c'est one-shot bloquant. Pour 300-1500 tokens, l'utilisateur attend ~1-3 s, le `⏳ busy` pulsé suffit comme feedback visuel. Si jamais ça devient gênant, on streamera plus tard.
- Pas de cache des rewrites (texte identique → même appel). En pratique l'utilisateur reformule rarement le même texte deux fois.
- Pas d'historique des rewrites au-delà du dernier (un seul `lastRewriteOriginal`). Suffisant pour l'undo immédiat ; si l'utilisateur lance 3 rewrites consécutifs, seul le dernier est annulable.
- Pas de raccourci clavier dédié (style `Ctrl+Shift+R` pour reformuler). À voir si l'usage le demande.

---

## Phase A.7.2 v15.5 : Toggle 3-states Funnel/serve + panneau Distant état live (2026-05-09)

**Friction.** Le bouton toggle Funnel de v15.3 traitait deux états (ON/OFF) mais en pratique Tailscale a 3 états distincts :
- `public` : Funnel ON, accessible depuis Internet
- `tailnet` : `tailscale serve` actif sans Funnel, accessible uniquement depuis le tailnet (toi + invités via ACL/share)
- `off` : aucune config, Compagnon pas exposé du tout au-delà de localhost

**Et surtout** : `tailscale funnel --https=443 off` **vire aussi la config serve**. Si tu coupes Funnel pour passer en privé tailnet (typique : un invité est partagé sur ta machine, tu veux qu'il continue d'accéder mais sans exposer publiquement), tu perds l'accès tailnet HTTPS aussi. Il faut re-créer `tailscale serve --bg --https=443 http://127.0.0.1:5680` après. Le bouton de v15.3 ne le faisait pas, résultat l'invité se retrouvait coupé.

**Livré.**

### GUI Tk : toggle 3-states
- `_funnel_status_parse()` retourne `(state, url)` avec `state ∈ {"public", "tailnet", "off"}` (au lieu d'un bool).
- `_apply_funnel_status_ui()` :
  - `public` → bouton « 🌐 Public, passer en privé », label rouge « ⚠ exposé Internet : <url> ».
  - `tailnet` → bouton « 🔒 Privé tailnet, passer en public », label vert « tailnet only : <url> ».
  - `off` → bouton « ⚪ Coupé, activer privé tailnet », label gris.
- `_toggle_funnel()` cycle : public → tailnet (off funnel + re-serve), tailnet → public (funnel on), off → tailnet (juste serve). Le passage public→tailnet exécute **2 commandes** consécutives pour ne pas perdre l'accès tailnet.

### Backend : `/api/connection_info` étendu
- Détecte l'état live via `subprocess.run(["tailscale", "funnel", "status"])` (timeout 3s, fail-soft).
- Retourne `tailscale_funnel_state` (`"public"|"tailnet"|"off"`) + `tailscale_funnel_live_url` (URL extraite de la sortie tailscale, plus à jour que celle du JSON).
- Retourne aussi `viewer_enabled` pour que le front sache si le mode viewer est configuré (informationnel).

### Frontend : panneau « 🔗 Distant »
- Ligne Funnel rendue selon l'état :
  - `public` : 🌐 « Tailscale Funnel : exposé sur Internet », URL cliquable.
  - `tailnet` : 🔒 « Tailscale serve : privé (tailnet uniquement) », URL cliquable.
  - `off` mais URL configurée : ⚪ « coupé (config présente mais inactive) », URL non-cliquable (désync probable).
  - `off` et pas configuré : ⚪ « non configuré », pointe vers la doc.
- **Refresh auto toutes les 30 s** via `setInterval(refreshConnectionInfo, 30_000)` : l'utilisateur voit le changement d'état quand il toggle depuis la GUI Tk sans avoir à F5.

### Documentation
- `_remote_access/SETUP_TAILSCALE_FUNNEL.md` : section « Couper Funnel mais garder l'accès tailnet (ami partagé) » qui documente le piège `funnel off` → `serve` perdu et la séquence correcte (off + re-serve). Section « Couper TOUT » et « Re-activer le mode public » séparées pour clarifier le 3-state.

### Tests
- 212 OK (full suite).

**Pas livré (consciemment).**
- Pas de bouton « hard reset » dans la GUI (équivalent `tailscale serve reset` + `tailscale funnel off`). Si l'utilisateur veut couper TOUT (off-off), il passe par la CLI (rare en pratique).
- Pas de notification cross-process quand l'état change (GUI Tk ne notifie pas le panneau web instantanément). Le polling 30s suffit pour le use case.

---

## Phase A.7.2 v15.4 : Mode viewer (lecture seule) pour partager une session sans risque (2026-05-09)

**Pourquoi.** Un proche a fait remarquer que partager l'URL Tailscale Funnel + creds Basic Auth donne accès complet : peut lire toutes les sessions passées (transcripts, points faibles, photos), peut consommer le quota Pro Max en envoyant des messages, peut éditer/supprimer des messages. Trop ouvert pour partager à un pote curieux qui veut juste voir l'outil tourner.

**Solution livrée.** Une 2ᵉ paire de credentials `viewer_user` / `viewer_pass` dans `_secrets/remote_access.json`. Quand quelqu'un se connecte avec ces creds, il atterrit en **mode lecture seule** : voit l'UI en live, peut naviguer dans les corrigés/script, peut consulter les sessions passées, mais **ne peut absolument rien modifier ni consommer de quota**. Le owner garde ses creds privées et y accède normalement.

### Backend
- **`_check_credentials(auth, basic)`** : helper qui compare aux 2 paires possibles. Retourne `"owner"`, `"viewer"`, ou None. Constant-time via `hmac.compare_digest`.
- **`_enforce_basic_auth` étendu** : stocke le rôle dans `flask.g.role`. Default `"owner"` (localhost / auth désactivée). Si `viewer` détecté, vérifie via `_viewer_can_access(method, path)` que l'endpoint est dans la whitelist GET → sinon **403** (avec payload JSON détaillant pourquoi).
- **Whitelist viewer** :
  - GET `/`, `/mobile`, `/robots.txt`, `/static/*`
  - GET `/api/role`, `/api/quota`, `/api/connection_info`
  - GET `/api/current_session`, `/api/sessions`, `/api/sessions/<id>`
  - GET `/api/cours_options`, `/api/cours_file`
  - GET `/api/corrections/init`, `/api/guided/init`
  - GET `/api/pending_attachments`, `/api/engines`
- **Tout le reste est bloqué pour viewer** : POST/PATCH/DELETE bien sûr, mais aussi GET `/api/stream_response` (consomme quota) et POST `/api/transcribe` (utilise Whisper GPU). Bloqué côté serveur, pas seulement caché côté front : la sécurité ne dépend pas du JS.
- **Nouvel endpoint `GET /api/role`** : permet au front de savoir s'il est en owner ou viewer pour adapter l'UI.

### Frontend
- **Au boot** : `detectUserRole()` fetch `/api/role`, store dans `userRole`. Si `viewer`, appelle `applyViewerMode()`.
- **`applyViewerMode()`** :
  - Banner 🔒 jaune en haut du `#dialogue` : "Mode partagé (lecture seule) : vous voyez la session en direct, vous ne pouvez pas modifier ni envoyer de message."
  - Cache via `style.display = "none"` : le form Lancer, l'input footer (textarea/send/mic/media), bouton Terminer la séance, record-indicator, engine switcher.
  - CSS injecté pour cacher : `.turn-actions`, `.tone-toolbar`, `.turn-edit-area`, `.turn-branch-nav`, `#guided-nav`, `#guided-remind-nav-btn`, `#corrige-nav`, `#corrige-picker`, `.suggested-edit .se-actions`, `#attachments-tray`.
- **Polling `/api/current_session` toutes les 5 s** : le viewer voit en live ce que tape le owner. Sync aussi `guided_index` pour que le panneau slides suive ce que regarde le owner. `initCorrectionsPanel()` lazy au 1ᵉʳ tick.
- **`streamResponse()` et fetch des endpoints d'écriture ne sont jamais appelés** côté viewer (c'est le `applyViewerMode` qui cache les triggers + le polling remplace le streaming).

### Configuration
- `_secrets/remote_access.json` : nouveaux champs `viewer_user` / `viewer_pass` dans le bloc `basic_auth`. Vides → pas de viewer activé. Le fichier `.example` documenté.

### Cas couverts
- **Owner se connecte à distance** : popup → entre `gstar` + sa pass owner → mode owner full.
- **Un invité se connecte** : popup → entre `invite` + viewer pass → mode viewer.
- **Random qui devine l'URL et tape n'importe quoi** : 401 → relance popup. 10 essais en 5 min → IP locked 15 min (rate-limit existant de v15.3).
- **Un invité tente d'envoyer un message** : front lui cache le bouton, mais s'il forge la requête, backend retourne 403 avec `{"error": "lecture seule : endpoint non autorisé pour les viewers"}`. Sécurité backend, pas client.

**Pas livré (consciemment).**
- Pas de multi-viewer (1 seul `viewer_user`/`viewer_pass`). Si tu veux plus tard donner accès à 2-3 personnes différentes avec des passes uniques par personne, on étendra le schéma `viewers: [{user, pass}, ...]`. Pour 1 ami c'est overkill.
- Pas d'expiration automatique des creds viewer. Si tu veux retirer l'accès à quelqu'un, change la `viewer_pass` dans le JSON et relance Flask : l'ancienne pass devient invalide. Manuel mais simple.
- Pas de log audit explicite (qui a vu quoi quand). Les logs Flask standard tracent les requêtes 200/403/401 avec IP, suffisant pour un usage perso.

---

## Phase A.7.2 v15.3 : Cascading selects web form + sécu hardening (2026-05-09)

**Frictions.**
1. Form web header en `<input>` libre → typos AN1/EN1 → erreur backend confuse « énoncé introuvable ». La GUI Tk avait des comboboxes cascading depuis A.6.1, le web pas.
2. Un proche a noté avec raison : URL Tailscale Funnel publique avec juste auth Basic = surface d'attaque pour drive-by bots, brute-force possible si pas de rate-limit.

**Livré.**

### Cascading selects (web form)
- Endpoint `GET /api/cours_options?matiere=&type=&num=&annee=` → recycle `list_matieres`/`list_types_for_matiere`/`list_nums_for_type`/`list_annees_for_cc`/`list_exos_for_num` du `cours_resolver`. Renvoie `{matieres, types, nums, annees, exos}` selon le contexte fourni.
- Form HTML : 5 `<select>` (matière/type/num/annee CC/exo) + select Mode + bouton 🔄 Rescan. Champ `enonce_path` retiré (auto-résolution suffit, override toujours possible via CLI `compagnon.py --enonce-path` ou query param).
- JS cascade : `cascadeFromMatiere` → `cascadeFromType` → `cascadeFromNum` → `cascadeFromAnnee` (CC) → exos. Garde-fou `cascadeMuted` anti-récursion. Auto-select sur 1 seule année CC. Restauration depuis query params au boot (compagnon.py CLI).
- CSS : selects stylés cohérent avec les inputs précédents.

### Sécu : Rate-limit + lockout sur Basic Auth
- Constantes : 10 échecs en 5 min → IP locked 15 min. In-memory (dict + `threading.Lock`), pas persistant : restart Flask reset, mais l'attaquant a perdu son temps.
- `_record_auth_failure(ip)` purge les vieux échecs hors window puis ajoute le nouveau ; déclenche lockout au seuil. `_check_lockout(ip)` retourne le temps restant ou None. `_reset_auth_state(ip)` purge après succès (l'humain qui mistype 2 fois puis trouve ne doit pas être pénalisé plus tard).
- Middleware `_enforce_basic_auth` : lockout vérifié avant l'auth (économie CPU + ne révèle pas si on s'approche du bon password). 429 + `Retry-After` header. Échec d'auth fournie → enregistré ; 401 sans header Authorization → pas enregistré (premier hit normal).

### Sécu : robots.txt + meta noindex
- `GET /robots.txt` retourne `User-agent: *\nDisallow: /\n` (text/plain).
- `<meta name="robots" content="noindex, nofollow, noarchive">` + `<meta name="referrer" content="no-referrer">` dans `index.html` et `mobile.html`.
- Stoppe l'indexation Google/Bing/etc. Ne stoppe pas les bots de scraping ciblés (eux ignorent robots.txt) mais filtre 90 % du drive-by.

### Sécu : Bouton toggle Funnel dans la GUI Tk
- Nouveau bouton dans le launch frame : `🔗 Accès distant : 🟢 ON, couper` ou `⚪ OFF, activer` selon état. Label de status à côté qui affiche l'URL publique quand ON.
- Click → subprocess `tailscale funnel --bg --https=443 http://127.0.0.1:5680` (activer) ou `tailscale funnel --https=443 off` (couper). Run en thread daemon pour ne pas bloquer la mainloop Tk.
- Refresh auto toutes les 30 s via `tailscale funnel status`. 1ʳᵉ check 800 ms après ouverture GUI. CREATE_NO_WINDOW sur Windows pour éviter le flash console.
- Permet de couper Funnel quand on est à la maison (surface d'attaque = zéro), n'activer que quand on part à la fac. C'est la mesure sécu la plus impactante des trois : un attaquant ne peut pas brute-forcer une URL qui n'existe pas.

### Tests
- 212 OK (full suite, pas de régression).

**Pas livré (consciemment).**
- Pas de skip-auth pour les IPs Tailscale tailnet (`100.64.0.0/10`). Pour l'instant tout invité tailnet doit aussi entrer le user/pass : c'est belt-and-braces (Tailscale auth + Basic Auth). Si ça gêne en pratique, on peut ajouter un toggle dans `remote_access.json` pour skipper l'auth sur tailnet IPs.
- Pas de webhook / log alerté quand un lockout se déclenche. Les warnings Flask suffisent pour l'instant (loggés dans la console GUI Tk).
- Pas de captcha. Overkill pour ce volume d'utilisation.

---

## Phase A.7.2 v15.2 : Accès distant (Tailscale Funnel + Cloudflare Tunnel) + Auth Basic (2026-05-08, nuit)

**Pourquoi.** À la fac et sur les PCs où on ne peut pas installer Tailscale, on n'a aucun moyen d'accéder à Compagnon qui tourne à la maison. Solution actuelle (`/mobile` via Tailscale tailnet) ne marche que si le client distant a Tailscale installé, ce qui n'est pas le cas sur les ordinateurs publics. TeamViewer écarté (encode tout l'écran, dépendant de l'upload home en permanence, latence et qualité dégradées). On veut une URL HTTPS publique permanente, accessible depuis n'importe quel navigateur, sécurisée.

**Décision archi.** Deux tunnels supportés en parallèle, choix selon contexte :

1. **Tailscale Funnel** : voie immédiate sans domaine. URL `https://compagnon-<host>.tail<orgid>.ts.net` stable, free tier 1000 GB/mois. Setup ~5 min (`tailscale serve` + `tailscale funnel`). Pas d'auth couche tunnel native → **Auth Basic Compagnon obligatoire**.
2. **Cloudflare Tunnel** : voie long terme avec domaine perso. URL `https://compagnon.<ton-domaine>.fr`, bandwidth illimité, **Cloudflare Access** ajoute une couche d'auth Google avant le tunnel. Setup ~30 min (cloudflared + DNS + Access). **Même brique que pour le portfolio** (`gaylord.fr` futur) : un `cloudflared` peut servir N sous-domaines.

**Livré.**

### Backend
- **`_secrets/remote_access.json`** (gitignored) : config centrale, schema_version 1 :
  ```json
  {
    "schema_version": 1,
    "basic_auth": {"enabled": true, "user": "...", "pass": "..."},
    "public_urls": {
      "tailscale_funnel": "https://...",
      "cloudflare_tunnel": "https://..."
    }
  }
  ```
- **Middleware Flask `_enforce_basic_auth`** (`@app.before_request`) : vérifie HTTP Basic Auth quand `enabled=true`. **Skip pour 127.0.0.1/::1** (GUI Tk locale, navigateur même PC, cloudflared/tailscaled qui forwarde depuis localhost). `hmac.compare_digest` pour comparaison constant-time. 401 + `WWW-Authenticate: Basic realm="Compagnon de revision"` sinon.
- **`/api/connection_info` étendu** : retourne désormais `cloudflare_tunnel`, `tailscale_funnel`, `basic_auth_enabled` (en plus des LAN/Tailscale tailnet existants). `_load_remote_access_cfg()` helper centralisé.
- **Constantes `config.py`** : `REMOTE_ACCESS_PATH`, `SCHEMA_VERSION_REMOTE_ACCESS`.

### Frontend
- **Onglet renommé `🔗 Distant`** (vs `📱 Mobile`). Pane h2 = `Accès distant`.
- **Panneau Distant, 4 lignes** : WiFi LAN, Tailscale tailnet, Tailscale Funnel public, Cloudflare Tunnel public. Chaque ligne soit URL cliquable+copiable (configurée), soit message « non configuré → voir _remote_access/SETUP_*.md » (placeholder).
- **Banner 🔐 auth** quand `basic_auth_enabled` : informe l'utilisateur qu'un popup user/pass apparaîtra sur les URLs publiques.
- **Footer hint** : ajout de `/mobile` à n'importe quelle URL pour la page photo téléphone (séparation des préoccupations : panneau Distant = voies de connexion, page /mobile = use case spécifique photo).

### Documentation
- **`_remote_access/README.md`** : overview des 4 voies, table comparative, décision rapide, lien avec le portfolio futur, bottleneck connexion home expliqué (vs TeamViewer).
- **`_remote_access/SETUP_TAILSCALE_FUNNEL.md`** : pas-à-pas 5 étapes (HTTPS tailnet, activer Funnel, démarrer, auth Basic, tester). Persistance après reboot, désinstallation.
- **`_remote_access/SETUP_CLOUDFLARE.md`** : pas-à-pas 9 étapes (install cloudflared, login, créer tunnel, config.yml, DNS record, démarrage manuel, service Windows, Cloudflare Access avec Google OAuth, référencement côté Compagnon). Section « Étendre à d'autres projets » avec config exemple multi-sous-domaines pour le portfolio.
- **`_remote_access/cloudflared.yml.example`** : template de config avec placeholders documentés (timeouts SSE adaptés, ingress catch-all 404).
- **`_remote_access/remote_access.json.example`** : template `_secrets/remote_access.json`.
- **README.md** : refonte complète de la section anciennement « Connexion depuis le téléphone » → « Accès distant », couvrant les 4 canaux + auth Basic + bottleneck + lien portfolio. Section `/mobile` séparée (use case photo).

**Pas livré (consciemment).**

- Pas d'auto-setup `cloudflared` ou Funnel depuis la GUI : trop dépendant du contexte (compte Cloudflare, domaine acheté, Tailscale config). Setup manuel via les docs `_remote_access/SETUP_*.md`. Une fois fait, c'est persistant (service Windows pour cloudflared, persist Tailscale via `--bg`).
- Pas de webhook de notification quand un client distant se connecte. Ajoutable via Cloudflare Access logs si besoin.
- Pas de rate limiting Flask au-delà de l'auth Basic. Cloudflare a un rate limit côté tunnel ; Tailscale Funnel a un quota bande passante. Suffisant en pratique pour un usage perso.
- Pas de `cloudflared.yml` versionné dans le repo (juste `.example`) : la vraie config contient un tunnel ID privé.

---

## Phase A.7.2 v15.1 : Panneau Docs (énoncé/corrigé/script) + SHOW_DOC + mémoire pages + fix layout (2026-05-08, soir)

**Friction.** Suite immédiate de v15 :
1. Le label « Corrigés & script » faisait déborder l'onglet Mobile à droite (mobile coupé visuellement).
2. Switch corrigé→script→corrigé via le picker : la 2ᵉ visite revenait page 1 au lieu de la dernière page lue.
3. L'énoncé manquait au panneau alors qu'il sert tout autant que le corrigé pour s'orienter.
4. Demande : permettre au tuteur (en mode lecture/guidé avec auto-nav opt-in) de **prendre le contrôle** du panneau pour pointer une page précise, pas juste citer dans le texte.

**Livré.**

- **Onglet renommé `📚 Docs`** : concis, neutre, fait la place pour énoncé en plus du corrigé/script. Le pane garde un titre descriptif `<h2>Documents (énoncé · corrigé · script)</h2>`.
- **CSS sidebar tabs** : `flex: 1 1 0; min-width: 0;` au lieu de `flex: 1 1 auto`. Padding réduit `10px 4px`. Distribution équitable avec ellipsis propre quand un nom dépasse, plus de débordement.
- **Énoncé inclus** dans `/api/corrections/init` via `find_enonce_pdf` (helper existant) : `kind: "enonce"`, label `"Énoncé"`. Toujours en 1ʳᵉ position dans le picker (lecture séquentielle naturelle énoncé → corrigé → script). Ajouté aussi à `_kickoff_corrige_prerasterize` pour pré-rasterisation au boot.
- **Mémoire dernière page par doc** : `corrigePageMemory: Map<filename, pageIdx>`. Avant chaque `showCorrige(idx, ...)`, on save la page courante du doc qu'on quitte. À la sélection picker, `corrigePageMemory.get(filename) ?? 0`. Switch corrigé→script→corrigé revient sur la page lue précédemment.
- **Tag `<<<SHOW_DOC>>>{"kind":"...","page":N}<<<END>>>`** :
  - Parser : nouveau `INSIDE_SHOW_DOC` state + `_try_parse_show_doc()` qui valide kind ∈ {`enonce`, `correction`, `script`} (avec aliases FR `corrigé`/`énoncé`) et page ≥ 1. Émet `ParserEventType.SHOW_DOC`.
  - SSE : `event: show_doc\ndata: {kind, page}` côté `app.py`.
  - Front : handler ouvre le tab Docs, sélectionne le 1ᵉʳ doc du bon kind via `jumpToCorrigePage`, ajoute une bulle système `🤖 Le tuteur affiche la page X/Y du <kind> « <label> »` pour traçabilité. Délai 800 ms pour laisser lire la fin de la phrase qui justifie le saut.
  - Prompt LECTURE v1.5 : §2.11 explique quand l'utiliser (passage cadré dans énoncé/corrigé/script, contexte visuel d'un schéma) et quand NON (à chaque réplique = intrusif, fuir une question, étudiant déjà sur la page). **Gated par auto-advance** (même flag opt-in que `<<<NEXT_SLIDE>>>`).
- **Linkify étendu aux énoncés** : la regex `linkifyPageRefs` accepte maintenant `du corrig[ée] | du script | de l'énonc[ée]` : clic → `jumpToCorrigePage(page, kind)` qui s'aligne sur le bon doc.
- Prompts v0.3 / v1.5 mis à jour (§1.5 mentionne énoncé en plus du corrigé/script).

**Pas livré (consciemment).**
- Pas de cooldown anti-cascade sur SHOW_DOC (vs slide nav qui a `slideTransitionLocked`). Volontaire : le tuteur n'a pas de raison d'émettre plusieurs SHOW_DOC d'affilée. Si ça arrive en pratique, on durcit le prompt avant d'ajouter du code.
- Pas de SHOW_DOC ciblé au 2ᵉ corrigé quand plusieurs corrigés existent. Pour l'instant `kind: "correction"` retombe sur le 1ᵉʳ corrigé. Si ça gêne, on étendra le schéma JSON avec `filename` ou `index`.

---

## Phase A.7.2 v15 : Panneau « Corrigés & script » + alerte session existante + JIT reading state (2026-05-08)

**Pourquoi.** Trois frictions remontées au cours d'une session de révision :
1. Le mode guidé affichait les slides du SCRIPT mais pas les corrigés officiels, pourtant pendant une colle/lecture, garder un œil sur le PDF du prof est utile (ancrage corrigé §1.4). L'étudiant devait l'ouvrir manuellement dans Acrobat à côté.
2. En revenant le lendemain sur un exo déjà commencé, on cliquait Lancer sans réaliser qu'une session existait déjà → écrasement silencieux.
3. L'onglet par défaut « Historique » saturait l'attention au démarrage alors que le panneau Quota est ce qu'on veut voir le plus souvent.

**Ce qui a été livré.**

### Backend
- **`/api/corrections/init`** (nouveau) : retourne la liste de tous les **documents lisibles** pour la session active : corrigés officiels (`resolve_corrections(matiere, type, num, exo, annee)`) **+** script imprimable (`find_perso_script_imprimable`, helper neuf dans `cours_resolver.py`). Chaque entrée contient `kind` (`"correction" | "script"`), `label`, `filename`, `pdf_path`, `total_pages`, et `pages: [{n, png_url}]`. **Ré-résolution à chaque appel** : fonctionne donc sur reprise de session (où `SessionState.load` reconstruit un `SessionContext` minimal sans `correction_paths`).
- **Rasterisation isolée par PDF** : `slides_rasterize.rasterize_pdf(pdf, out_dir, prefix)` paramétrique. Wrapper compat `rasterize_if_needed` conservé. Helper `rasterize_correction(pdf)` met les PNGs dans `<dossier>/.pngs_<stem>/page-N.png` (sous-dossier caché par PDF : pas de collision quand plusieurs corrections cohabitent dans `corrections/`).
- **Pré-rasterisation au boot** : `_kickoff_corrige_prerasterize(ctx)` lance un thread daemon à `start_session` et `resume_session` qui rasterise tout en arrière-plan. 1ʳᵉ ouverture du panneau = instantanée au lieu de 2-5 s par PDF.
- **Just-in-time reading state** : `/api/send_message` accepte un champ `reading_state: {kind, label, filename, page, total}`. Si présent, prefixe une ligne `[Contexte lecture actuelle : l'étudiant consulte la page X/Y du <kind> « <label> » (<filename>)]` au texte avant stockage comme `pending_user_text`. Pas de spam d'historique sur chaque navigation : l'annotation n'apparaît que sur les messages réellement envoyés.
- **Helper `_label_for_correction_pdf`** : génère « Exercice 3 », « Toutes les corrections », « CC2 : corrigé global » selon le pattern de fichier.

### Frontend
- **Onglet « 📄 Corrigés & script »** dans la sidebar (visible dans tous les modes : colle, lecture, guidé). Image de la page courante, picker dropdown si plusieurs documents, prev/next/jump, lightbox au clic. Inactif tant qu'aucune session.
- **Default tab Quota** au lieu d'Historique (ordre des onglets : Quota → Corrigés & script → Historique → Mobile).
- **Modal de conflit au lancement** : avant `POST /api/start_session`, le front fetch `/api/sessions` et filtre sur `(matiere, type, num, exo, annee)`. Si un match (la plus récente), affiche `#start-conflict-modal` avec 3 boutons :
  - ✅ **Reprendre la session existante** → `resumeSession(sid)` (replay/résumé selon ancienneté).
  - 🔄 **Démarrer une nouvelle (l'ancienne sera supprimée)** → `DELETE /api/sessions/<id>` puis `doStartSession(body)`.
  - ↩ **Annuler** : ferme la modal, formulaire reste éditable.
- **Bouton 📋 Copier** sur les bulles student/claude (à côté de ✏ et 🗑). `navigator.clipboard.writeText` du `dataset.rawText` avec fallback `execCommand`. Feedback visuel ✓ vert 1.2 s.
- **Reading state JIT côté front** : `currentReadingState` mis à jour à chaque `showCorrige` (sans API call). `getReadingStateForSend()` ne renvoie le state que si l'onglet « Corrigés & script » est actif (sinon → null, l'étudiant ne lit pas). Inclus dans le body de `/api/send_message` et `sendMetaInstruction`.
- **Raccourcis clavier ←/→** : quand l'onglet Corrigés est actif, navigue les pages. En mode guidé, le tab Corrigés actif prend la priorité sur la nav slide (cohérence visuelle : la flèche actionne ce qui est sous les yeux). Skip si focus dans textarea/input/select/contenteditable.
- **Refs « page N du corrigé/script » cliquables** : `linkifyPageRefs(rootEl)` post-stream et au rerender (transcript replay). Walker DOM sur les text nodes (skip code/pre/katex/déjà-linkifiés). Regex `(?:p\.?|page)\s*(\d+)\s+du\s+(corrig[ée]|script|correction|concat)`. Match → `<a class="corrige-pageref">` avec `data-page` + `data-kind`. Click → switch tab + `showCorrige(idx, page-1)` sur le 1ᵉʳ doc du bon kind.

### Prompts système (concertation explicite : Gstar a autorisé l'édition)
- **`PROMPT_SYSTEME_COMPAGNON.md` v0.3** : nouveau §1.5 « Annotation `[Contexte lecture actuelle : ...]` » expliquant le canal et comment l'utiliser (intégrer silencieusement, ne pas accuser réception, ne pas dicter ce que l'étudiant a sous les yeux).
- **`PROMPT_SYSTEME_LECTURE.md` v1.5** : §1.5 jumeau, plus invitation à utiliser les références « page N du corrigé » dans les réponses (rendues cliquables côté UI).

### Tests
- 212 tests OK (full suite, pas de régression). Pas de nouveau test ciblé sur le panneau corrigé : Phase A reste en couverture pragmatique (cf. CLAUDE.md §6.1).

**Pas livré (consciemment).**
- Pas d'auto-jump quand le tuteur dit « voir page X » : on garde la main sur le clic (moins intrusif, plus contrôlable).
- Pas de tracking de quels passages ont été lus (anti-cheat « tu n'as pas lu la page 3 ») : trop intrusif et peu fiable (un coup d'œil ≠ une lecture comprise).
- Pas de bookmark / annotation côté corrigé : reporté à plus tard si le besoin émerge.

---

## Phase A.7.2 v7.3 : Bascule à chaud cross-engine sans perte d'historique (2026-05-06)

**Pourquoi.** v7.2 livrait un popup au boot (« Quota Anthropic atteint, basculer ? ») mais si le quota saute **en plein flow** (au tour N alors que les N-1 précédents ont marché), le user voyait juste `[Erreur stream] quota_exhausted...` et devait Stop + Lancer en perdant l'historique.

**Ce qui a été livré.**

- **Backend** :
  - Nouvel event SSE `quota_midflow` émis par `_run_claude_streaming` quand `ClaudeQuotaExhaustedError` est levée. Payload : `{message, available: [{engine, label}, ...]}` listant les providers de fallback dont la clé API est définie (filtrés via `_list_available_fallbacks(exclude=current_engine)`).
  - `CompanionSession.retry_pending: bool` : flag posé par `/api/switch_engine` pour signaler à `/api/stream_response` de stream depuis l'historique transféré sans toucher (pas de re-append du user message, pas de consommation de pending).
  - `/api/switch_engine` (nouveau) : POST `{engine: "..."}`. Valide via `SUPPORTED_ENGINES`, snapshot de `_system_prompt`/`_model`/`_max_tokens`/`_mode`/`_cours_root` du client courant, construit un nouveau `ClaudeClient`, **transfère `_history` directement** (le format `[{role, content}]` est universel, `_stream_via_openai_compatible` et `_stream_via_gemini` convertissent à la volée), remplace `st.client`, met `retry_pending=True`, persiste `engine_pref.json` (fail-soft : si OSError on continue, la mémoire est ce qui compte).
  - `_persist_engine_pref` helper standalone (cohérent avec gui.py `_save_engine_pref`, atomic .tmp + os.replace).

- **Frontend** :
  - Listener `quota_midflow` sur l'EventSource → `renderQuotaMidflowCard(payload)` qui affiche un card rouge dans le chat avec un bouton par provider dispo (label humain : « Gemini 2.5 Pro », « DeepSeek V3 / R1 », « Groq + Llama 3.3 70B »).
  - `switchEngineAndRetry(provider, card)` : POST `/api/switch_engine`, désactive les boutons, met à jour le badge `sessionInfo`, puis appelle `streamResponse()` qui re-déclenche un GET SSE → backend détecte `retry_pending=True` et stream depuis l'historique.
  - Cas pas-de-clé : le card affiche un sous-bloc explicatif demandant de configurer au moins une clé puis Stop+Lancer (le subprocess est mort, pas de continuation possible sans clé).
  - CSS `.quota-midflow-card` (border rouge + pulse, boutons accent, états success/error).

- **Tests** (`tests/test_switch_engine.py`, 6 tests) :
  - 409 sans session active.
  - 400 sur engine inconnu (avec `supported` dans la réponse).
  - Bascule réussie : `ClaudeClient` instancié avec les bons args, historique de 3 messages transféré, `st.client` remplacé, `retry_pending=True`, `_persist_engine_pref` appelé.
  - Persistance fail-soft : si `OSError` sur l'écriture du JSON, la bascule en mémoire réussit quand même.
  - `_list_available_fallbacks(exclude=...)` filtre correctement.
  - `_list_available_fallbacks()` sans clé retourne `[]`.

- **Total : 140 tests OK** (full suite).

**Pas livré (consciemment).**

- Pas de retry automatique (sans confirmation user). Volontaire : on veut que l'utilisateur sache qu'il bascule de modèle, vu les différences de qualité (Claude > Gemini > DeepSeek > Groq sur le suivi du prompt).
- Pas de bascule retour automatique vers Claude quand le quota se libère. Manuel via panneau Moteur.
- Pas de tracking des bascules cross-engine dans `session_state.json`. Le JSON garde le `engine` initial. Acceptable pour l'instant (la stat post-session « combien de tours sur Gemini ? » n'a pas d'usage immédiat).

---

## Phase A.7.2 v7.2 : DeepSeek + Groq comme 4ᵉ et 5ᵉ providers (2026-05-06)

**Pourquoi.** Gemini résout le cas « lecture longue », mais pas tout. Pour
le **debug code Idris** ou les **démos math/info qui coincent**, DeepSeek
R1 (modèle de raisonnement, chaîne de pensée explicite) est plus tranchant
que Gemini généraliste. Et quand DeepSeek free tier est saturé (ils coupent
parfois en cas de surcharge), Groq + Llama 3.3 70B est un backup ultra-stable
(14 400 RPD, jamais hit en pratique).

**Décision design.** DeepSeek et Groq exposent tous deux une API
**OpenAI-compatible** (chat.completions standard). On factorise leur impl
streaming dans une seule méthode `_stream_via_openai_compatible(cfg)` qui
prend la config provider en argument (base_url, api_key_env, default_model,
provider_name, signup_url, model_prefix). Évite la duplication. Au-dessus
de ces 2, on resterait dans le pattern strategy ; à 6+ providers, abstraire.

**Ce qui a été livré.**

- `claude_client.py` :
  - Constantes `ENGINE_DEEPSEEK = "deepseek_api"` et `ENGINE_GROQ = "groq_api"`,
    ajoutées à `SUPPORTED_ENGINES` (5 au total).
  - Dict `_OPENAI_COMPATIBLE_PROVIDERS` mappe chaque engine à sa cfg.
  - Méthode `_stream_via_openai_compatible(on_event, cfg)` :
    SDK `openai` >= 1.30 avec `base_url` custom, format `messages` standard
    (system prompt en 1ᵉʳ message role=system, puis `_history` tel quel),
    `stream_options.include_usage=True` pour récupérer prompt_tokens /
    completion_tokens du dernier chunk.
  - Mapping erreurs : `RateLimitError` → ClaudeQuotaExhaustedError,
    `APIConnectionError`/`APITimeoutError` → ClaudeNetworkError, autre
    `APIError` → ClaudeClientError.

- `compagnon.py` : skip quota Anthropic si engine actif n'est pas
  `cli_subscription` ou `api_anthropic` (était : skip uniquement si Gemini).

- `gui.py` :
  - 2 nouvelles radios « DeepSeek V3 / R1 » et « Groq + Llama 3.3 70B »
    dans le panneau Moteur. Aide mise à jour pour mentionner les 3 envs.
  - **Bascule auto étendue** : `_FALLBACK_PROVIDERS` tuple ordonné
    (Gemini, DeepSeek, Groq). `_show_gemini_fallback_dialog` propose le
    1ᵉʳ provider dont la clé est définie. Si plusieurs clés présentes,
    les autres sont mentionnées dans le message du popup comme
    alternatives accessibles via le panneau Moteur. Si aucune clé,
    warning avec les 3 liens d'inscription. Le nom de la méthode reste
    `_show_gemini_fallback_dialog` (legacy) malgré qu'elle gère 3
    providers, sera renommée en v8 si on en ajoute encore.

- `requirements.txt` : ajout `openai>=1.30`.

- Tests :
  - `test_provider_routing.py` (nouveau, 9 tests) :
    `SUPPORTED_ENGINES` complet, format de `_OPENAI_COMPATIBLE_PROVIDERS`,
    dispatch deepseek/groq/gemini/api vers leur impl, message d'erreur
    explicite quand clé absente (mentionne env et URL d'inscription).
  - `test_gemini_fallback.py` (étendu à 11 tests) : couvre maintenant
    DeepSeek-only, Groq-only, priorité Gemini si toutes les clés présentes,
    skip si engine déjà non-Anthropic.
  - **Total : 20 tests OK**.

- `README.md` : tableau comparatif étendu (5 lignes), section « Quand
  utiliser quel moteur » avec recommandations par cas d'usage,
  configuration des 3 clés, hiérarchie de fallback documentée, limites
  assumées rectifiées (factorisation OpenAI-compatible, pas de tools
  côté providers non-Anthropic).

**Pas livré (consciemment).**

- Pas d'auto-fallback à chaud (en plein flow). Si quota saute en milieu
  de séance, Stop + Lancer pour re-déclencher le check qui propose la
  bascule.
- Pas de re-tune des prompts par modèle.
- Pas de quota tracker DeepSeek/Groq côté GUI (panneau Quota reste
  Anthropic-only). Voir limites côté provider directement.

---

## Phase A.7.2 v7.1 : Bascule auto Gemini sur quota Anthropic + correction limites free tier (2026-05-06)

**Correction de doc.** v7 annonçait « free tier généreux ~50 RPM, 1500 req/jour », c'était l'ancien tier Flash 1.5. Gemini 2.5 Pro free tier (2026) = ~5 RPM, ~250 k TPM, ~100 RPD. Pour l'usage Compagnon (~20 tours par session, jamais plus de 1 RPM en pratique), la contrainte réelle = **cap journalier à ~5 sessions de révision**. Plus généreux que Pro Max sur la durée mais PAS illimité. README et tableau comparatif rectifiés, note explicite ajoutée.

**Bascule auto vers Gemini quand quota Anthropic atteint.** Quand `compagnon.py` refuse le démarrage et imprime « Impossible de demarrer : Quota 5h a 87% », la GUI détecte le pattern dans le log et popup : « Basculer sur Gemini 2.5 Pro pour cette séance ? ». « Oui » → maj `engine_pref.json`, relance immédiate avec les mêmes args. « Non » → situation inchangée.

Pré-requis : `GEMINI_API_KEY` détectée. Sinon popup explique comment la créer (`$env:GEMINI_API_KEY = "AIza..."` ou `setx`).

Implémentation (`gui.py`) : `_last_launch_args` sauvegardé au launch, `_gemini_fallback_proposed` garde-fou anti double-popup, `_maybe_propose_gemini_fallback(line)` dans la pump du log, `_show_gemini_fallback_dialog()` + `_relaunch_with_saved_args()`.

---

## Phase A.7.2 v7 : Engine Gemini en alternative pour sessions longues (2026-05-06)

**Pourquoi maintenant.** Conso tokens de Claude CLI subscription = ~18-22
tours par fenêtre 5h (cf. v6.5). Pour les sessions de lecture de 1h30+
sur les CMs, on hit systématiquement le quota. Gemini 2.5 Pro a un free
tier généreux (50 RPM, 1500/jour) et un contexte 1M qui absorbe un CM
complet sans capping.

**Décision design.** L'utilisateur avait reçu un plan d'orchestration
multi-providers de Gemini : Provider Factory abstraite + 4-5 providers
(Claude/Gemini/GPT/DeepSeek/Mistral) + reprise cross-provider. Refusé
comme sur-ingénierie (cf. discussion conv) : on ajoute UN seul provider
en strategy-pattern minimal, sans Factory. Si on en rajoute un 3e dans
6 mois, on abstraira à ce moment-là (3 = la limite avant que le pattern
strategy devienne pénible).

**Ce qui a été livré.**

- `claude_client.py` :
  - Nouvelle constante `ENGINE_GEMINI = "gemini_api"` + `SUPPORTED_ENGINES`
    tuple (centralise la liste pour gui.py et app.py).
  - `_stream_via_gemini()` : utilise `google.genai` (SDK unifié 2025+),
    convertit l'historique Anthropic-style → Gemini-style
    (`role: assistant` → `role: model`, `content: str` → `parts:[{text}]`),
    passe le system_prompt via `GenerateContentConfig.system_instruction`,
    streame via `generate_content_stream`. Mapping erreurs sur les 3
    exceptions standard du module (quota / réseau / autre).
  - `DEFAULT_GEMINI_MODEL = "gemini-2.5-pro"`, surchargeable via env
    `GEMINI_MODEL`.
- `compagnon.py` : skip `can_start_session()` (quota Anthropic) si engine
  actif est Gemini : le rate limiting Gemini est tracké côté Google.
- `app.py` : accepte `gemini_api` dans `_read_engine_pref` via
  `SUPPORTED_ENGINES`.
- `gui.py` : 3ᵉ radio « Gemini 2.5 Pro » dans le panneau Moteur.
  Description rappelle la limite (pas d'accès FS) et le besoin de
  `$env:GEMINI_API_KEY`.
- `requirements.txt` créé (n'existait pas pour Compagnon, partagé avec
  BotGSTAR jusqu'ici, n'incluait pas anthropic / faster-whisper /
  google-genai). Liste explicite des deps Phase A.7.2.

- `README.md` : nouvelle section **Moteurs supportés (Phase A.7.2 v7)**
  avec tableau comparatif des 3 backends (forces/limites/coût), guide
  « quand utiliser quoi », instructions setup clé Gemini
  (`$env:GEMINI_API_KEY` ou `_secrets/.env`), et limites assumées
  (pas de Factory, pas de tools côté Gemini, pas de fallback auto, prompt
  unique non re-tuné).

**Pas livré (consciemment).**

- Pas de Provider Factory abstraite (overkill pour 3 engines).
- Pas de fallback auto cross-engine (manuel via GUI radio + restart).
- Pas de re-tune des prompts système par modèle (one-prompt-fits-all,
  on observera la dérive en usage réel).
- Pas de mapping des tools `Read`/`Grep` Claude vers le tool use Gemini
  (les sessions lecture/guidé sous Gemini n'ont pas accès FS, acceptable
  pour de la lecture libre).
- Pas de quota tracker Gemini séparé (count tokens reste utile mais on
  ne block pas la session sur seuil).

---

## Phase A.7.2 v6.5 : Doc consommation tokens dans README (2026-05-06)

**Pourquoi.** L'utilisateur a hit le seuil session 5h à 87 % après quelques
tours seulement, surpris par la conso. Pas de bug : le Compagnon est gros
mangeur par construction (CLI subscription replay le contexte complet à
chaque tour, pas de cache prompt). Mais ce n'était documenté nulle part.

**Ce qui a été ajouté dans README.md** (sous-section « Conso tokens »
dans § Limites assumées) :

- Décomposition des tokens par tour : prompt système (3 300) + transcription
  CM (5 200) + TACHE/script perso (7 800) + corrigés cumulés (20 000) +
  points faibles (500) + historique (+200-500/tour) = **~37 000 tokens
  input par tour**.
- Estimation Pro Max Opus 4.7 : **~18-22 tours par fenêtre 5 h** avant
  blocage à 85 %, soit **~1 séance de 1 h-1 h 30**. Hebdo : ~3-4 séances.
- Conseils pour étirer : baisser `correction_total_chars` de 80k à 20k
  (+50-70 % de tours), basculer en mode colle (contexte ÷2.5), passer en
  API pay-as-you-go, terminer proprement les séances.
- Note sur le seuil session 85 % par défaut (modifiable via auto-save dans
  le panneau Quota).

Pas de changement de code : uniquement docs.

---

## Phase A.7.2 v6.4 : Lightbox slides + posture lecture moins muette (2026-05-06)

**Lightbox sur clic slide guidée.** Le PNG dans la sidebar fait ~220 px
de haut, illisible pour les diagrammes denses (schémas Beamer avec
plusieurs nœuds, code Idris en colonnes). Cliquer la slide ouvre désormais
une lightbox plein écran : `<div id="lightbox">` + `<img id="lightbox-img">`,
visible jusqu'à 96 vw × 92 vh. Fermeture : clic n'importe où sur l'overlay
ou touche Échap. Cursor `zoom-in` sur la sidebar pour que l'utilisateur
voie que c'est cliquable.

**Refonte de la posture « lecture sans question »** dans
`_prompts/PROMPT_SYSTEME_LECTURE.md §2.1`. Avant : « répondez `(attente)`
ou `…` ». Problème observé en prod : l'étudiant lit à voix haute, le
Compagnon répond littéralement « (attente) » → message vide, casse le
rythme, on dirait que c'est cassé.

Maintenant interdit explicitement de répondre `(attente)`, `…`, `OK`,
`je vous écoute`. À la place, choisir UNE des 4 options selon le passage :

1. **Accusé bref + nuance qui ajoute** (~70 %) : « Bon début, "récursion
   structurelle" = celle qui décompose selon le constructeur, vu CM5 §3. »
2. **Question Feynman de vérification** (~20 %) : « Reformulez "récursion
   structurelle" sans le script, juste avec vos mots. »
3. **Flag d'un point glissé trop vite** (~10 %) : « Vous avez dit "tout
   se transpose presque" : le "presque" est important, on y revient ? »
4. **Encouragement** (rare) : « Continuez, c'est clair. »

Avec ratio cible explicite pour éviter l'effet « question Feynman à
chaque passage » qui serait insupportable.

---

## Phase A.7.2 v6.3 : Indicateur de réflexion + suppression boutons 💾 (2026-05-06)

**Ce qui a été livré.**

- **Boutons 💾 Sauvegarder supprimés** des panneaux Seuils et Caps contexte.
  Avec l'auto-save 500 ms (v6.2), ils étaient redondants. Le bouton
  « 🔄 Recharger depuis disque » des seuils est conservé pour les cas où
  l'utilisateur a édité `runtime_settings.json` à la main et veut
  réimporter dans la GUI. Méthodes `_save_thresholds` / `_save_caps`
  supprimées (les variantes `_silent` restent, ce sont elles qui
  écrivent réellement).

- **Indicateur de réflexion sur stream Compagnon** (`thinking-indicator`).
  Entre le clic Lancer/Envoyer et le 1ᵉʳ chunk de réponse Claude, l'écran
  restait silencieux pendant 3-15 s (variable selon engine et taille du
  contexte). Sans feedback, on dirait que c'est planté. Maintenant : une
  bulle « 🤔 Compagnon réfléchit… 0.0 s » est attachée à la bulle Claude
  vide, le timer s'incrémente toutes les 250 ms, et la bulle est retirée
  dès le 1ᵉʳ event `text` (ou `done`/`end`/`error`). CSS pulse + bordure
  bleue cohérente avec le reste du dialogue.

  Couvre les 2 cas d'attente (start_session ET send_message) puisque
  `streamResponse()` est appelé dans les deux flows.

---

## Phase A.7.2 v6.2 : Auto-save seuils quota + caps contexte (2026-05-06)

**Pourquoi maintenant.** L'utilisateur a essayé de monter le seuil session
de 85 % à 95 % en plein blocage de quota, et la session a continué d'être
refusée. Cause : il faut cliquer 💾 Sauvegarder ; les Spinbox n'écrivaient
pas dans `runtime_settings.json` à chaque modif. Inconsistant avec le reste
du formulaire (matière/type/mode/audio/skip_quota auto-persistent dans
`gui_state.json` via `trace_add` silencieux).

**Ce qui a été livré.** `gui.py` : trace_add « write » sur les 2 IntVar
de seuils + chacune des 4 IntVar caps contexte. Les saves se font via
debounce 500 ms (`self.root.after_cancel` + `self.root.after`), sans
debounce, taper « 95 » écrirait transitoirement 9 (puis 95) sur disque,
risquant qu'un démarrage de session entre les deux frappes voie un seuil
ridicule. Méthodes `_schedule_thresholds_save` /
`_schedule_caps_save` réinitialisent le timer à chaque keystroke. Les
exécutants `_save_thresholds_silent` / `_save_caps_silent` sont fail-soft
(corrupt JSON ou valeur hors range : on swallow et le bouton 💾 manuel
reste dispo).

Boutons « 💾 Sauvegarder » conservés en backup (au cas où le debounce
ait avalé une frappe). Labels d'aide mis à jour : « Auto-save 500 ms après
modif, bouton 💾 en backup ».

`README.md` : section GUI clarifiée, explicite l'auto-save des seuils ET
des caps contexte, avec note que les caps prennent effet au **prochain
démarrage de session** (lus à la création du PromptBuilder, pas modifiables
à chaud).

---

## Phase A.7.2 v6.1 : Fix SessionState.context + détection incohérence SCRIPT/PDF (2026-05-06)

**Bugs en prod découverts au 1ᵉʳ test du mode guidé.**

1. **HTTP 500 sur `/api/guided/init` et `/api/upload_photo`**. `SessionState`
   stockait `context` uniquement comme dict sérialisé dans `_data`, sans
   exposer l'objet vivant. Les endpoints qui faisaient
   `st.session_state.context` levaient `AttributeError` → 500.
   Le bug était latent dans `/api/upload_photo` depuis Phase A.7.2 v4
   (jamais déclenché en pratique car l'utilisateur passait par Discord
   inbox au lieu du bouton 📎). Le mode guidé v5 a juste été le 1ᵉʳ
   endpoint à toucher la même path.
   - `session_state.py` : ajout `self._context: SessionContext = context`
     au `__init__`, plus property accesseur. `SessionState.load()`
     reconstitue un SessionContext minimal depuis le JSON
     (matiere/type/num/exo/annee, les Path objets sont perdus mais
     suffisent pour les endpoints lookup).

2. **Filtre `annee` parasite sur les CM**. Le placeholder GUI
   `"2025-26 (CC)"` peut être interprété comme valeur (autocomplete,
   copy-paste). Pour CM/TD/TP, le millésime n'a aucun sens : `_scan_script_dir`
   filtrait sur `_{annee}` dans le nom de fichier et écartait tous les
   scripts. Force `annee=None` sauf pour les CC dans `/api/guided/init`.

**Détection auto incohérence SCRIPT.md ↔ slides_*.pdf.** Demande explicite
de l'étudiant après le 1ᵉʳ test (CM8 avait 14 slides script mais 15 pages
PDF : l'un avait été régénéré sans l'autre).

- L'endpoint `/api/guided/init` compare `nb_slides_script` vs
  `nb_pages_pdf` ; si divergence ou PNG manquant pour une slide, retourne
  un champ `inconsistency: {nb_slides_script, nb_pages_pdf, missing_png_for_slides,
  script_path, slides_pdf_path, regen_command, message}`.
- Front (`app.js`) : `renderInconsistencyBanner()` affiche un card
  warning avec la commande de régen
  (`python _scripts/run_script_oral.py {path}`) + bouton « 📋 Copier la
  commande » via `navigator.clipboard`. CSS `.inconsistency-card` (border
  warn, code block sélectionnable).
- **Pourquoi pas lancer la commande depuis le browser ?** La règle
  `COURS/CLAUDE.md §3` fait du `SCRIPT.md` la source de vérité ; le PDF
  se recompile via `run_script_oral.py` qui dépend de MiKTeX, droits
  système, dossier `_temp_latex/`. Lancer ça depuis Flask (subprocess avec
  shell=True, env LaTeX, CWD COURS) ouvre une RCE en cas de path injection.
  Mieux : on guide l'étudiant à copier-coller dans son terminal où il a
  déjà tout configuré.

**Audit consistance PRG2** au moment de la livraison (CM7, CM8, TD8,
TP7, TP8, TP9) : seul CM8 divergeait. Recompilé via `run_script_oral.py`,
14 slides cohérentes désormais.

---

## Phase A.7.2 v6 : WebSpeech live preview + image broken handler (2026-05-06)

**Pourquoi maintenant.** Sur les dictées de plus de 30 s, le silence visuel
entre « clic ⏹ » et « retour Whisper » est inconfortable : l'étudiant ne
sait pas si l'audio est bien capté, ni s'il a oublié un mot. Et quand
Claude embedde une image qui plante (chemin invalide, hors COURS_ROOT),
l'icône cassée du navigateur ne dit pas pourquoi.

**Live preview WebSpeech (Chrome/Edge).** En parallèle de MediaRecorder
(qui produit le blob webm pour Whisper), on lance l'API `SpeechRecognition`
native (Chrome/Edge). Elle envoie l'audio en streaming au cloud Google et
nous renvoie une transcription quasi-instantanée : qualité ~85-90 % en
français, mauvaise sur le vocab technique (Idris, Marquis, formules), mais
suffisante pour un feedback visuel pendant qu'on parle. Au stop, la
transcription Whisper canonique haute qualité **écrase** la preview.

- `app.js` : `setupLiveRecognition()` + `startLiveRecognition()` +
  `stopLiveRecognition()`. Snapshot `userInputBeforeRecording` avant clic
  🎤 pour préserver ce que l'étudiant avait déjà tapé (la preview écrit
  dans `userInput`, mais le retour Whisper restaure le snapshot et
  concatène la transcription canonique).
- Auto-restart sur `onend` (Chrome auto-stop après ~60 s) tant que
  `isRecording` reste vrai.
- Erreurs `no-speech` et `aborted` ignorées (normales).
- Privacy : Chrome/Edge envoient l'audio chez Google. Acceptable sur
  localhost pour Compagnon perso. Documenté dans le README.
- Firefox/Safari < 14.1 : pas d'API SpeechRecognition → on saute
  silencieusement le live preview, le timer reste comme feedback.

**Handler `onerror` sur images embarquées.** Quand Claude génère
`![alt](path)` et que `/api/cours_file` retourne 404 (chemin tapé
incorrect, fichier absent, hors COURS_ROOT), le navigateur affichait une
icône cassée muette. Maintenant, `<img onerror>` remplace par un placeholder
visible :

> ⚠️ Image introuvable : `PRG2/CM/scripts_oraux/slide-7.png`

Plus normalisation des backslashes Windows (Claude génère parfois
`PRG2\CM\...` qui ne résout pas via le param `path`).

**CSS** : nouvelle classe `.md-img-broken` (bord pointillé rouge,
chemin tenté en `<code>`).

---

## Phase A.7.2 v5 : Mode guidé slide-par-slide (2026-05-06)

**Pourquoi maintenant.** En mode lecture, le tuteur (Claude) attend que
l'étudiant pose une question ou demande quelque chose. Pour réviser un CM
ou une feuille avec slides Beamer, c'est inversé : l'étudiant veut lire
les slides dans l'ordre et que le tuteur intervienne quand utile (pièges,
questions d'ancrage, liens cours). Sans support UI, ce flux était
impossible : l'étudiant devait copier-coller chaque slide dans le chat.

**Ce qui a été livré.**

- `script_parser.py` (nouveau) : parse les `SCRIPT_*.md` (format Feynman v2,
  cf. `COURS/_prompts_claude_ai/SPEC_script_oral_v2.md`) en liste de
  `SlideMeta(n, title, duration_min, oral_text, beamer_source)`. Regex
  `## [SLIDE N] Titre (X min)` non-greedy (titres avec parenthèses OK).
- `slides_rasterize.py` (nouveau) : `rasterize_if_needed(pdf_path, dpi=150)`
  produit `slide-1.png`, ..., `slide-N.png` à côté du PDF via `pdftoppm`
  (MiKTeX). Idempotent (skip si tous les PNGs sont plus récents que le PDF).
- `cours_resolver.py` : nouvelle fonction `find_perso_script_md` (le mode
  guidé exige le `.md` source avec headers `[SLIDE N]`, pas le `.txt`
  extrait).
- `claude_client.py` : ajout de `MODE_GUIDE = "guidé"`. Le mode partage le
  même posture tuteur que `lecture` (Read/Grep scopés à COURS_ROOT).
- `app.py` : nouvel endpoint `GET /api/guided/init` qui retourne
  `{slides: [{n, title, duration_min, png_url, oral_excerpt}, ...], total,
  titre_global}`. La rasterisation est faite à la volée si nécessaire.
  `/api/start_session` accepte désormais `mode in (colle, lecture, guidé)`.
- Front (`templates/index.html`, `static/style.css`, `static/app.js`) :
  - Nouvelle option `Guidé` dans le select Mode.
  - Sidebar panel `#guided-panel` avec image PNG, titre, durée cible,
    boutons ⬅ / 🎯 (jump) / ➡, et compteur N/Total.
  - Raccourcis clavier : Espace ou → pour slide suivante, ← pour précédente
    (override du legacy "espace pulse l'indicator record" quand mode guidé
    actif et focus hors input texte).
  - À chaque changement de slide (sauf init), envoi d'un meta-message
    silencieux à Claude :
    ```
    [Mode guidé] L'étudiant vient d'arriver sur la slide N/Total (« titre »).
    Aperçu : ... Interviens UNIQUEMENT si tu as quelque chose d'utile à
    apporter. Sinon, reste silencieux ou réponds très brièvement.
    ```
    Affiché côté UI sous forme de chip discret `📍 Slide N/Total : titre`
    pour traçabilité. Le tuteur décide d'enchaîner ou rester silencieux,
    posture adaptative voulue par l'étudiant.
- `gui.py` : 3ᵉ radio Mode « Guidé (slide-par-slide) ». Désactivé si
  `find_perso_script_md` OU `find_perso_slides_pdf` retourne `None` pour
  la sélection courante (le mode exige les deux). Bascule auto vers
  `lecture` si l'utilisateur avait `guidé` sélectionné mais la cascade
  retire le matériau.

**Décisions de design.**

- **Slide-par-slide strict, pas de groupes.** L'étudiant a explicitement
  demandé « les groupes c'est de l'over-engineering pour un usage qui
  n'existe pas encore » : on lit dans l'ordre, on relit en arrière si
  besoin, on saute via 🎯 prompt.
- **Mode adaptatif.** Le tuteur reçoit chaque transition de slide comme
  un meta-message non-bloquant. Le prompt l'instruit de rester silencieux
  par défaut et n'intervenir que si pertinent. Évite la sur-interruption
  qui casse la lecture.
- **PNG plutôt que PDF embed.** Plus léger côté navigateur, plus simple
  côté serveur (`/api/cours_file?path=...` sert directement le PNG depuis
  COURS_ROOT, pas de viewer PDF intégré).
- **Prompt système réutilisé.** Mode guidé partage `PROMPT_SYSTEME_LECTURE.md`
  (posture tuteur, accès Read/Grep). Pas de prompt séparé tant que
  l'usage n'a pas révélé un besoin de divergence.

**Pilote.** PRG2 CM7 (15 slides) et CM8 (14 slides) testés bout-en-bout :
parser OK, rasterisation OK, navigation OK.

---

## Phase A.7.2 : Support type=CM dans Lancer une session (2026-05-06)

**Pourquoi maintenant.** Ajout récent de scripts Feynman pour les CMs PRG2
(CM7 ordre supérieur, CM8 arbres binaires) avec leurs slides Beamer et
script imprimable. La GUI ne proposait que `TD/TP/CC/Examen/Quiz`,
rendant impossible de lancer une session de révision sur un CM directement.

**Ce qui a été livré.**

- `cours_resolver.py` : ajout de `CM` à `_BROWSER_KNOWN_TYPES`. Helpers
  `list_nums_for_type` (extraction depuis `SCRIPT_*_CM{N}.md` et
  `slides_*_CM{N}.pdf` du `scripts_oraux/`, plus transcription
  `CM{N}_*.txt` et poly `cm_*_{N}.pdf`), `list_exos_for_num` (CM →
  `["full"]` comme CC), `_candidate_exercise_folders` (CM → `{MAT}/CM/`
  à plat). `find_enonce_pdf` retombe sur le poly `cm_{matiere_lower}_{N}.pdf`
  comme document de référence pour les CM (l'« énoncé » au sens TD/TP
  n'existe pas ici).
- `gui.py` : `TYPES = ("TD", "TP", "CC", "CM", "Examen", "Quiz")`. Le
  combobox `Exo` est désactivé pour CM et CC (un seul exo `full`).
  Nouveaux attributs `btn_open_script` / `btn_open_slides` rendent les
  boutons configurables, et `_refresh_avail_buttons()` les **active /
  désactive en live** selon la dispo réelle du fichier sur disque pour
  la sélection courante. Plus de popup « Introuvable » : l'utilisateur
  voit directement ce qui est disponible.
- `prompt_builder.py` : `SessionContext.enonce_path` devient
  `Optional[Path]` (None pour CM sans poly disponible). La section
  ÉNONCÉ est skip si None ; titre adapté à `POLY DU COURS` pour les CM
  (vs `ÉNONCÉ DE L'EXERCICE` pour TD/TP/CC). Le header de séance dit
  « Cours magistral entier (pas d'exercice ciblé) » au lieu de
  « Exercice ciblé : tout le TD/TP » quand `type=CM`.
- `app.py` : `_build_session_context` ne raise plus `FileNotFoundError`
  pour les CM sans énoncé/poly : `enonce=None` est passé tel quel au
  `SessionContext`.
- `compagnon.py` : help text de `type` mis à jour
  (`TD, TP, CC, CM, Examen, Quiz`).

**Test E2E.** PRG2 CM7 (avec poly `cm_prg2_7.pdf`) et CM8 (sans poly)
donnent tous deux un `SessionContext` valide avec script + slides. Les
8 CMs PRG2 (CM1-CM8) sont listés par `list_nums_for_type`.

**Suite 6 (même journée) : Toolbar de ton + LaTeX live + images du Compagnon.**

Demande utilisateur après premier test session lecture : pouvoir
réajuster le ton des réponses Compagnon en direct (sans toucher au
prompt système) selon l'humeur, et donner au tuteur la possibilité
d'envoyer des images (slides, photos, schémas) avec rendu LaTeX
propre des formules.

**Toolbar de ton** : 6 boutons en chip-style sous chaque réponse
Compagnon (`📝 Plus concis`, `📚 Plus développé`, `💡 Avec exemple`,
`🎯 Plus simple`, `🔬 Plus rigoureux`, `🔄 Reformule`). Chaque click
envoie une meta-instruction texte à Claude (« Reformule la dernière
réponse en plus concis »), affiche un chip discret `🎛️ Plus concis`
dans le dialogue (au lieu d'une bulle student pleine), puis re-stream
la réponse adaptée. Le prompt système reste inchangé : c'est purement
conversationnel.

**Rendu LaTeX live (KaTeX)** : KaTeX 0.16.11 chargée via CDN dans
`index.html` (CSS + JS + auto-render extension). Au `done` event
SSE, `renderMathInElement(currentClaudeTurn)` transforme les
délimiteurs `$...$` (inline), `$$...$$` (display), `\(...\)`,
`\[...\]` en HTML rendu. Déclenchement uniquement à la fin du stream
pour éviter les flicker sur les `$\frac{` partiels. Les deux prompts
système (lecture + colle) gagnent une section §5.5 / §7.5 qui
demande au tuteur de **privilégier LaTeX** pour les formules.

**Images dans réponses Compagnon** : nouvelle route Flask
`/api/cours_file?path=relative/path` qui sert les fichiers de
`COURS/` avec validation anti-traversal (path doit résoudre sous
`COURS_ROOT`). Whitelist d'extensions : png, jpg, jpeg, webp, gif,
svg, pdf. Le renderer JS détecte la syntaxe Markdown `![alt](path)`
et émet un `<img src="/api/cours_file?path=...">` (URL externe
http(s) laissée telle quelle). Les deux prompts système gagnent une
section §5.6 / §7.6 qui décrit les usages : slides du cours, polys,
photos étudiant, URL externe. CSS `.md-img { max-width: 100%; max-height: 480px }`.

**Suite 5 (même journée) : Console parasite, markdown, bouton média.**

- Bug : à chaque message envoyé, une fenêtre console `claude` clignotait
  brièvement à l'écran. Cause : `subprocess.Popen` sans
  `creationflags=CREATE_NO_WINDOW`. Fix : ajout du flag conditionnel
  `os.name == "nt"` dans `_stream_via_cli`. Plus de pop-up.
- Bug : le markdown des réponses Claude (`**gras**`, listes, code, etc.)
  s'affichait littéralement parce que `currentClaudeTurn.textContent +=
  chunk` ne rend que du plain text. Fix : nouveau `renderMarkdown()` JS
  vanilla (~50 LoC, 0 dépendance) appelé à chaque chunk via
  `currentClaudeTurn.innerHTML = renderMarkdown(rawText)`. Couvre
  ` **bold** `, ` *italic* `, ` \`inline code\` `, blocs ```` ``` ````,
  listes ` - / 1. `, paragraphes `\n\n`. Échappement HTML d'abord pour
  éviter les injections. CSS dédié pour `<strong>`, `<em>`, `<code>`,
  `<pre>`, `<ul>`/`<ol>`.
- **Nouveauté : bouton 📎 média** dans la barre de saisie pour joindre
  des photos. Le picker accepte plusieurs images, chacune POSTée sur
  `/api/upload_photo` qui sauvegarde dans :
  - `COURS/{MAT}/{TYPE}/{TYPE}{N}/photos/` pour TD/TP
  - `COURS/{MAT}/CC/{annee}/CC{N}/photos/` pour CC
  - `COURS/{MAT}/CM/photos/` pour CM (à plat, pas de `CM{N}/` subdir)

  Nom canonique cf. CLAUDE.md §3 : `photo_{MAT}_{TYPE}{N}_v{i}.{ext}`,
  `v{i}` incrémenté pour ne jamais écraser. Extensions whitelist :
  `jpg, jpeg, png, webp, heic, gif`. La réponse contient `rel_path`
  pour que l'UI affiche un récap système avec la liste des fichiers
  sauvegardés. L'étudiant peut ensuite mentionner les photos à Claude
  dans le prochain message texte.

**Suite 4 (même journée) : Trois bugs critiques au lancement de session.**

Bug 1 : `cublas64_12.dll is not found or cannot be loaded` au clic micro.
Cause : `transcribe_stream.py` chargeait `faster_whisper.WhisperModel`
en mode CUDA hardcodé sans setup du PATH pour les DLL nvidia (qui sont
dans `site-packages/nvidia/` après pip install). Fix : porte
`_setup_nvidia_dlls()` depuis `COURS/_scripts/transcribe.py` (appelée
**avant** l'import de `faster_whisper`), passe `device=auto`/
`compute_type=auto` par défaut, et ajoute un fallback CPU explicite
(`int8`) si l'init CUDA fail malgré tout (drivers mismatch, etc.).

Bug 2 : `[Erreur stream] connexion perdue` comme premier message
système au démarrage. Cause : `/api/start_session` push le contexte
initial directement dans `client.history` via
`client.append_user_message(initial)`, mais `/api/stream_response`
exigeait `pending_user_text != None` et retournait HTTP 409 sinon.
La 1ʳᵉ stream après start était donc systématiquement rejetée. Fix :
flag `initial_stream_pending: bool = True` sur `CompanionSession`
(consommé en one-shot) qui autorise le pull du stream sans append d'un
nouveau user message.

Bug 3 : `SessionState._build_context_files` crash sur `Path(None)` quand
`enonce_path=None` (CM sans poly). Stack `TypeError` se répercutait en
HTTP 500 (page HTML), JS attendait JSON et explosait sur
`Unexpected token '<', "<!doctype"`. Fix : gate `if enonce_path is not
None` avant relativize (cf. fix dédié plus bas).

**Suite 3 bis : Feedback visuel pendant l'enregistrement micro.**

L'utilisateur ne voyait pas que sa voix était capturée : pas de
transcription live (Phase A est non-streaming) et pas d'indicateur
clair. Fix sur `app.js` :

- Pendant `recording` : placeholder de `userInput` devient
  `🎤 Parlez maintenant…`, indicator pulsé en bas à droite affiche
  `🎤 Enregistrement… M:SS` avec timer live mis à jour toutes les 250 ms.
- Pendant `transcribing` (après stop, attente Whisper) :
  `⏳ Transcription en cours… (Whisper large-v3)`. Le clignotement
  rouge persiste pour signaler le travail en cours.
- Au retour : reset placeholder + indicator.

La transcription live (mots qui s'affichent au fur et à mesure que
l'utilisateur parle, à la ChatGPT/Claude.ai) reste en Phase B :
nécessite une intégration streaming Whisper côté client (Web Speech
API) ou côté serveur (faster-whisper streaming, plus complexe).

**Suite 3 (même journée) : Persistance sélection même quand Lancer grisé.**
Bug rapporté : pour PRG2 CM6 (poly présent mais ni script ni slides),
sélectionner CM ne « tient » pas : au prochain démarrage le formulaire
restaure le type précédent (TD). Cause : `update_last_selection` n'était
appelée que dans `_launch`, donc grisé Lancer = pas de persistance.

Fix : nouveau helper `_save_selection_silent()` appelé à la fin de
`_refresh_avail_buttons()` (donc à chaque cascade). Atomic write JSON,
fail-soft. Plus un `trace_add` direct sur `mode` / `enable_audio` /
`skip_quota` pour persister aussi ces changements (qui ne déclenchent
pas de cascade). Coût : 1 atomic write par changement de sélection,
négligeable.

Le `update_last_selection` du `_launch` est conservé comme safety net.

**Suite 2 (même journée).** `_refresh_avail_buttons()` étend son action au
bouton **`▶  Lancer`** : grisé quand aucun matériau n'est disponible
pour la sélection courante. Critère final (raffiné après retour user
sur PRG2 CM6) :

- TD/TP/CC : énoncé PDF requis (sinon `app.py` raise `FileNotFoundError`).
- CM : script oral OU slides, **pas le poly seul**. Si les boutons
  « Ouvrir script » et « Ouvrir slides » sont tous deux grisés (cas
  CM6 PRG2 : poly présent mais pas de Feynman généré), Lancer doit
  l'être aussi (cohérence visuelle). Le poly est un document de
  référence, pas un matériau de session Feynman.

Étiquette d'aide `launch_hint` rouge à côté du bouton qui dit
explicitement *« Énoncé PDF introuvable »* (TD/TP/CC) ou *« Aucun
script ni slides généré pour ce CM »* (CM). Plus de session lancée qui
crash au démarrage parce que le fichier manque, et plus d'incohérence
entre les boutons « Ouvrir » grisés et un Lancer actif.

---

## Phase A : MVP boucle dialogue texte (2026-05-01)

**Pourquoi maintenant.** Préparation des CC3 mai-juin 2026, 8 semaines pour
réussir à passer en révision active orale. Tentative précédente avec
`RoleplayOverlay` (lecture passive de scripts oraux figés) qui ne m'avait
pas aidé à apprendre : je récitais sans comprendre. Il me fallait un
interlocuteur exigeant, pas un script que je lis.

**Ce qui a été livré.** 15 modules Python (~2300 lignes + 220 front + 560
tests) :

- `compagnon.py` (entry point CLI)
- `_scripts/dialogue/parser.py` (machine à états SSE pour `<<<TTS>>>`,
  `<<<WEAK_POINT>>>`, `<<<END_SESSION>>>`)
- `_scripts/dialogue/session_state.py` (JSON par séance + heartbeat 30s
  pour détecter les sessions interrompues)
- `_scripts/dialogue/prompt_builder.py` (assemblage contexte initial)
- `_scripts/dialogue/claude_client.py` (wrapper CLI subscription / API)
- `_scripts/audio/listener.py` + `transcribe_stream.py` (push-to-talk
  global via `keyboard`, faster-whisper large-v3 GPU)
- `_scripts/quota/quota_check.py` (wrapper sur `Arsenal_Arguments/claude_usage.py`)
- `_scripts/web/app.py` + `templates/index.html` + `static/app.js` (Flask
  + SSE pour le streaming Claude → front)

39 tests unittest verts. Smoke test live OK : Claude lit le PDF
`enonce_CC2_2023-24_EN1.pdf`, pose une question pédagogique ciblée
(MUX21), capture un weak_point, finalise le JSON.

**Lancement** : `python compagnon.py AN1 TD 5 3` dans un terminal
PowerShell. Ouvre le navigateur sur `127.0.0.1:5680`. Une instance Flask
par session, killée à `Ctrl+C`.

**Friction #1 : la clé API Anthropic était épuisée.** Le pipeline
utilisait `--use-claude-code` (CLI subscription Pro Max) en hardcodé, ce
qui forçait à passer par OAuth/keychain. Acceptable pour cette phase
mais bloquant pour les tests d'infra (limites quota partagées avec la
GUI Arsenal qui tournait en parallèle). → corrigé en Phase Y de BotGSTAR
en parallèle, et reporté ici en Phase Y bis : choix CLI/API persistant
dans `_secrets/engine_pref.json`.

**Friction #2 : endpoint `/api/usage` Claude.ai a évolué.** Le scraper
DPAPI qui lit le quota Pro Max plantait sur les nouvelles structures
`null`. Fix appliqué côté `Arsenal_Arguments/claude_usage.py`
(`_safe_float` / `_safe_int` tolérants aux null), bénéficie aussi à
Compagnon qui réutilise le même module.

**Tests manuels prévus** : Tests 1, 5, 6 OK le jour du commit. Tests 2,
3, 4 (push-to-talk en conditions, capture WP via blocage répété,
heartbeat survit à un kill brutal) reportés au reset hebdo Pro Max
suivant pour pas brûler du quota en debug d'infra.

---

## Phase A.5 : Ancrage corrigé officiel + matériel perso (2026-05-05)

**La friction qui a déclenché ce pivot.** Première discussion avec Claude
le matin du 5 mai sur l'utilité de Compagnon vs **Claude Cowork** qui
venait de passer en GA. Question légitime : « ce que je construis
n'est-il pas redondant avec Cowork ? ». Réponse plutôt nuancée (cf.
README §« Pourquoi pas Claude Cowork »), mais en discutant on a pointé
un trou de spec **vraiment problématique** dans la Phase A telle que
livrée.

> Le souci de compagnon_révision de ce que j'ai compris c'est que c'est
> passer sur un seul fichier qu'on lui donne à manger alors que
> j'aimerais qu'il explore l'arbo de cours et vois les corrections etc.
> de fait en plus de l'énoncé car très souvent ben ce que l'IA dit de
> corriger est très aléatoire et s'éloigne des corrigés officiels. (Gstar)

**Diagnostic.** `SessionContext` Phase A n'embarquait que l'énoncé +
transcription CM optionnelle + poly optionnel. **Pas de champ corrigé.**
Donc Claude infère ses « corrections » sans avoir le corrigé prof sous
les yeux et dérive régulièrement. Pas un bug : un trou dans la spec
initiale.

**Le fix.** Pas de pivot d'archi : extension de `SessionContext` et du
`PromptBuilder` :

- Nouveau module `_scripts/dialogue/cours_resolver.py` (~280 lignes,
  standalone, pas de dépendance au Cog Discord BotGSTAR) qui résout les
  chemins canoniques de l'arbo COURS pour énoncé / corrigés / TACHE
  perso / script oral perso / slides. Logique calquée sur
  `BotGSTAR/extensions/cours_pipeline.resolve_correction_pdf` mais
  réécrite proprement avec `pathlib`.
- `SessionContext` étend avec `correction_paths`, `tache_path`,
  `script_oral_path`, `slides_pdf_path`, `annee`.
- 4 nouvelles sections injectées dans le prompt initial :
  `CORRIGÉ OFFICIEL`, `TACHE PERSO`, `SCRIPT ORAL PERSO`, `SLIDES PERSO
  (mention)`. Caps en mots/chars (80k chars cumulés sur les corrigés,
  6k mots sur la TACHE/script) pour ne pas saturer le contexte sur les
  TD à 11 exos en mode `full`.
- `app.py._build_session_context` auto-résout via le resolver si les
  chemins ne sont pas fournis explicitement dans le body. Bonus :
  auto-discovery du CSV `_points_faibles/{MAT}_points_faibles.csv` pour
  injecter l'historique automatiquement.
- `compagnon.py` ajoute `--annee 2025-26` pour les CC multi-millésime.

**Mais surtout, le prompt système v0.2.** Avoir le PDF dans le contexte
ne suffit pas si Claude ne s'oblige pas à le consulter. Donc nouveau
**§1.4 « Ancrage sur le `CORRIGÉ OFFICIEL` »** dans
`PROMPT_SYSTEME_COMPAGNON.md` avec 5 cas explicites :

1. Réponse alignée → validation sobre.
2. Écart corrigé/réponse → signaler explicitement, **citer** le passage
   du corrigé qui fait foi.
3. Voie alternative valable → valider la voie alternative ET demander
   d'énoncer aussi la voie du corrigé.
4. Corrigé ambigu/partiel → le dire au lieu d'inventer.
5. Pas de corrigé chargé (mode dégradé) → annoncer à l'étudiant
   d'entrée que les corrections ne font pas foi.

Règle absolue n°6 reformulée pour interdire toute correction qui
contredit le corrigé officiel.

**Bonus README.** Tableau comparatif **Cowork / Claude.ai / Claude Code
/ Compagnon / Arsenal** ajouté pour clarifier où chaque outil
intervient. Conclusion : Cowork pourrait absorber la plomberie Phase
B/C (rebuild_weak_points, export Anki) si on ne veut pas la coder, mais
le cœur (boucle PTT vocal + colleur exigeant + capture SRS) reste
irremplaçable.

**Tests.** 25 nouveaux tests, 39 → 64 tous verts. Resolver vérifié sur
la vraie arbo : AN1 TD5 ex3, EN1 CC2 2023-24, AN1 TD5 mode `full`
(préfère le `concat_TD5_AN1.pdf` qui vit dans `corrections/`).

---

## Phase A.6 : GUI Tkinter (2026-05-05, soir)

**La friction.** Une fois Phase A.5 commitée, première vraie session
prévue. Question légitime de Gstar :

> Comment je lance une session ?

Réponse : `cd ... && python compagnon.py AN1 TD 5 3 [...]`. Friction
évidente : pour un outil de révision qu'on est censé lancer plusieurs
fois par semaine pendant 8 semaines, le terminal c'est de la friction
inutile, et la moindre faute de frappe sur les arguments fait planter
le démarrage. Demande explicite :

> Crée-moi une interface UI du langage que tu veux pour que je n'aie
> pas à utiliser le terminal et aussi que je puisse moduler les quota
> etc et autres variables.

**Choix techno.** Tkinter, par cohérence avec
`Arsenal_Arguments/summarize_gui.py` qui suit le même pattern (form +
quota live + persistence dans `_secrets/`). Pas de framework web parce
que Compagnon a déjà Flask + SSE pour le runtime applicatif, ajouter
une 2e UI navigateur juste pour le launcher serait incohérent.

**Ce qui a été livré.**

- `gui.py` (~470 lignes) : fenêtre Tk unique, 6 panneaux :
  1. **▶ Lancer une session** : combobox matière/type, entry num/exo/année,
     3 checkboxes (audio, skip-quota, resume), boutons Lancer/Stop.
  2. **📊 Quota Pro Max (live)** : 4 barres de progression
     (session 5h, hebdo 7j, hebdo Sonnet, overage), refresh 60s, et
     **2 spinboxes seuils** (session/hebdo) sauvegardés dans
     `_secrets/runtime_settings.json` et lus dynamiquement par
     `quota_check.can_start_session()` au prochain check.
  3. **🤖 Moteur Claude** : radio CLI subscription / API Anthropic, sauvé
     à la volée dans `_secrets/engine_pref.json`.
  4. **⚙️ Caps contexte (avancé)** : 4 spinboxes pour les caps du prompt
     builder (CM transcription, perso, corrigés cumulés, top N points
     faibles). Sauvegardés dans `runtime_settings.json`.
  5. **📁 Sessions** : liste des derniers JSON `_sessions/`, marqueur ↩
     pour les reprenables, double-clic ouvre une fenêtre preview JSON
     read-only. Boutons d'ouverture des dossiers (`_sessions/`,
     `_points_faibles/`, `_logs/`, `_secrets/`).
  6. **💻 Console** : `ScrolledText` foncé qui tail le stdout/stderr du
     subprocess `compagnon.py`, capé à 400 lignes pour pas exploser la
     mémoire sur les longues sessions.

- `_scripts/runtime_settings.py` : loader/saver atomic write avec
  fallback aux défauts si fichier absent ou corrompu, schéma versionné,
  merge partiel pour compatibilité avant des champs.
- `_scripts/quota/quota_check.py` : `THRESHOLD_5H_BLOCK_SESSION` /
  `THRESHOLD_7D_BLOCK_SESSION` constants supprimées, remplacées par
  `get_session_threshold_pct()` / `get_weekly_threshold_pct()` lues à
  chaque appel. Effet : changer un seuil dans la GUI prend effet
  **immédiatement** sans relance.
- `start_gui.vbs` : lanceur silencieux Windows (pythonw.exe sans
  console parasite), fallback sur les chemins courants `Python312` /
  `Python313` si pythonw n'est pas dans le PATH. Pattern calqué sur
  `Arsenal_Arguments/start_summarize_gui.vbs`.

**Subprocess management.** La GUI lance `python -u compagnon.py ...` via
`subprocess.Popen` avec `CREATE_NEW_PROCESS_GROUP` sur Windows pour
permettre un stop propre via `CTRL_BREAK_EVENT`. Fallback hard-kill via
`taskkill /F /T /PID` après 5 s si le process ne s'arrête pas.
Stdout/stderr captés dans un thread daemon, poussés dans une `queue`
drainée toutes les 150 ms par le main loop Tk → la console se met à
jour fluide sans bloquer l'UI.

**Tests.** 7 nouveaux tests sur `runtime_settings` (defaults, save/load
roundtrip, fallback corrupt, merge partiel, ignored unknown keys), 64 →
71 tous verts. La GUI elle-même n'est pas testée unitairement (Tk c'est
fastidieux), mais le smoke test au lancement + la fonctionnalité critique
(lecture/écriture des settings) sont couverts.

---

## Phase A.6.1 : Comboboxes cascading dans le formulaire (2026-05-05, foulée)

**Friction observée juste après A.6.** Le formulaire de lancement avait
encore des **entries libres** pour `num`, `exo`, `annee`. Donc on pouvait
toujours taper `AN1 TD 99 ex42` et voir le démarrage planter parce que ça
n'existait pas sur disque. Demande explicite de Gstar :

> Dans Lancer une session, il peut pas y avoir un select qui me permet
> de sélectionner réellement les items et pas que j'aie à rentrer les
> valeurs ? Ceux présents dans /COURS et co.

**Le fix.** Les 5 champs (matière, type, num, exo, année) deviennent
des **comboboxes cascading** alimentés depuis l'arbo COURS. Sélectionner
une matière met à jour la liste des types disponibles, qui met à jour
les nums, qui mettent à jour les exos et les années (CC seulement).

- 5 nouveaux helpers dans `cours_resolver.py` :
  - `list_matieres(cours_root)` : sous-dossiers `[A-Z][A-Z0-9]{1,5}` de
    COURS/, ignore `_INBOX`, `z_archive`, etc.
  - `list_types_for_matiere(cours_root, matiere)` : TD/TP/CC/Quiz/Examen
    réellement présents.
  - `list_nums_for_type(cours_root, matiere, type)` : couvre les 3
    layouts : sous-dossiers `{TYPE}{n}/` (TD/TP), CC flat via
    `enonce_CC{n}_{annee}_*.pdf`, CC nesté via `CC/{annee}/CC{n}/`.
    Tri naturel (`"2"` avant `"10"`, et codes textuels comme `SHANNON`
    après les numériques pour PSI).
  - `list_annees_for_cc(cours_root, matiere, num)` : millésimes triés
    desc.
  - `list_exos_for_num(cours_root, matiere, type, num, annee)` : scan
    `corrections/correction_*_ex*_*.pdf` ET `TACHE_*_ex*.md`. Toujours
    préfixé de `"full"`.
- `gui.py` : 4 entries → 4 comboboxes. Cascade via `trace_add('write')`
  sur les `StringVar`, avec garde anti-récursion (`_in_cascade` flag)
  pour que les `.set()` programmatiques internes au cascade ne
  re-déclenchent pas le cascade. Le champ `année` est **désactivé**
  pour TD/TP, **lecture seule** pour CC. Bouton « 🔄 Rescan COURS »
  pour rafraîchir si on ajoute des fichiers pendant que la GUI tourne.
- 15 nouveaux tests (TestCoursResolverBrowser) qui couvrent les 5
  helpers sur 3 layouts (TD numérique, CC flat avec millésimes, CC
  nesté style AN1, PSI textuel SHANNON, racines manquantes). 71 → 86
  tous verts.

**Vérifié sur la vraie arbo** : COURS contient 5 matières détectées
correctement (AN1, EN1, ISE, PRG2, PSI), AN1 TD a 5 nums (1-5), AN1
TD5 propose `full` + 11 exos (1 à 11 dans l'ordre naturel), EN1 CC1
a 3 millésimes (2023-24 / 2024-25 / 2025-26) en ordre desc.

**Pourquoi `state="normal"` (pas `readonly`) sur num/exo/annee.** Si le
user veut lancer sur un cas non-canonique (énoncé hors arbo, exo qu'il
veut tester avant que la correction soit dispo), il peut taper la
valeur à la main. Validation au démarrage via `cours_resolver.find_enonce_pdf`
qui plante proprement si rien trouvé.

---

## Phase A.6.2 : Bouton micro toggle dans le navigateur (2026-05-05, soir tard)

**Friction observée juste après A.6.1.**

> Mais si j'écris en même temps + je dois appuyer sur Espace c'est chiant.
> Il peut pas y avoir un micro qu'au clic ? Ça met en mode enregistrer
> et ça retranscrit mes paroles en texte comme ce qui est fait sur
> claude.ai et co. (Gstar)

Le hotkey global Espace de Phase A avait deux défauts pratiques :

1. **Conflit avec la saisie clavier.** Le hook `keyboard` Python est
   global : il déclenche l'enregistrement même si tu tapes du texte
   dans la zone de saisie où Espace est juste un séparateur de mots.
2. **Inconfortable pour les longues réponses.** Tenir Espace 30
   secondes pendant qu'on raisonne à voix haute, c'est crispant.

**Le fix.** Un **bouton 🎤 toggle** dans la barre de saisie, à la
Claude.ai. Click = démarrer l'enregistrement (rouge pulsant ⏹), click
encore = arrêter et transcrire (orange ⏳ pendant). La transcription
apparaît dans le champ texte, l'utilisateur la corrige si nécessaire
et clique **Envoyer**.

**Implémentation.**

- **Front (`static/app.js`)** : `MediaRecorder` côté navigateur, capture
  WebM/Opus si supporté (fallback laissé au navigateur sinon). Préfère
  `audio/webm;codecs=opus` puis `audio/webm` puis `audio/ogg;codecs=opus`.
  Stream audio libéré (`getTracks().forEach(t => t.stop())`) après chaque
  enregistrement pour que le voyant micro de l'OS s'éteigne. État `recording`
  / `transcribing` reflété par les classes CSS sur le bouton.
- **Back (`web/app.py`)** : nouvel endpoint `POST /api/transcribe` qui
  reçoit le multipart audio, le sauve dans un tempfile, lazy-load
  `WhisperTranscriber` au premier appel (singleton thread-safe via
  double-checked locking), et retourne `{text, duration_seconds}`.
  Suffix du tempfile dérivé du mimetype pour aider pyav/ffmpeg à choisir
  le bon decoder. Cleanup du tempfile dans `finally` même si crash.
- **Concaténation intelligente** : si l'utilisateur a déjà tapé du texte
  dans la zone de saisie au moment où il clique micro, la transcription
  est *ajoutée* au texte existant au lieu de l'écraser. Permet de
  combiner saisie clavier (formule mathématique) + dictée vocale
  (raisonnement) dans le même tour.
- **Pattern « édit avant envoi »** : la transcription remplit le champ,
  ne s'auto-envoie pas. L'utilisateur vérifie/corrige (Whisper se trompe
  parfois sur les noms propres ou la ponctuation), puis clique Envoyer
  ou tape Entrée.

**`--enable-audio` reste comme legacy.** Le hotkey global Espace via
`keyboard` lib est conservé, case **décochée par défaut** dans la GUI,
label clarifié : « ⌨ Hotkey clavier global Espace (legacy, le bouton
🎤 navigateur suffit) ». Personne n'a besoin de le cocher en pratique
mais on garde la porte de sortie pour les workflow hands-on-keyboard.

**Tests.** 6 nouveaux tests `test_app_transcribe.py` qui mockent
`WhisperTranscriber` (pas envie de charger 3 Go de VRAM dans une suite
de tests) : champ audio manquant → 400, filename vide → 400, succès →
texte retourné, échec lazy-load → 500 `whisper_load_failed`, échec
décodage → 500 `transcribe_failed`, strip whitespace OK. 86 → 92 tous
verts.

**Latence pratique attendue.**

- Premier clic après lancement de Flask : ~5-10 s (lazy-load Whisper).
- Clics suivants : ~1-2 s pour 5-10 s de parole (large-v3 sur RTX 2060
  int8_float16 + VAD).
- Click → texte affiché : essentiellement borné par Whisper, plus 200-
  300 ms réseau local.

**Non couvert.** Streaming Whisper temps réel (texte qui s'affiche
mot par mot pendant qu'on parle). Pas urgent, dépend de la latence
ressentie en sessions réelles. Reporté à une éventuelle Phase B.

---

## Phase A.6.3 : Boutons Ouvrir script / Ouvrir slides (2026-05-05, fin de soirée)

**Friction observée.** Discussion sur le workflow de **pré-révision passive**
avant d'attaquer une colle :

> Si je veux apprendre en commençant à lire le script pour comprendre,
> genre vraiment le début de mon apprentissage, tu penses qu'il faut
> mieux coder des select pour les scripts aussi ? Sachant que y'aura
> le diaporama à côté mais bon ça je suis pas sûr que c'est pertinent
> pour toi. (Gstar)

Workflow naturel pour démarrer un TD nouveau : 15-20 min de lecture
passive (script oral préparé + slides en visuel) avant de passer en
mode colle. Aujourd'hui, ouvrir les fichiers nécessitait Explorer →
naviguer dans `COURS/AN1/TD/TD5/scripts_oraux/` → trouver le bon
`script_oral_*.txt` parmi les 6 variantes. Trop de friction pour un
geste qu'on fait avant chaque nouvelle séance.

**Le fix.** Deux boutons dans le panneau « ▶ Lancer une session », à
côté de **🔄 Rescan COURS** :

- **📖 Ouvrir script** : appelle `find_perso_script_oral()` (le resolver
  préfère déjà `script_oral_*.txt` variant `transcription` sur
  `inference`), puis `os.startfile()` → s'ouvre dans VS Code / Notepad++
  / l'app associée au `.md`/`.txt`.
- **📊 Ouvrir slides** : appelle `find_perso_slides_pdf()`, ouvre dans
  Acrobat / Edge / le lecteur PDF par défaut.

Pas trouvé → `messagebox.showinfo` qui rappelle le chemin canonique
attendu (`COURS/{MAT}/{TYPE}/{TYPE}{N}/scripts_oraux/`).

**Pourquoi pas de mode lecture interactif avec Claude.** Tentation de
créer un **« Mode lecture »** (toggle dans la GUI : Claude joue un
tuteur qui te guide dans ton propre script au lieu de te coller dessus,
second prompt système). Repoussé. Justification : avant d'investir 1
journée dans cette feature, vaut mieux faire 2-3 vraies sessions
de colle pour voir si la lecture passive (juste ouvrir le `.md`) suffit
ou si un dialogue accompagné apporte vraiment quelque chose. Si oui,
Phase A.7 candidate.

**Pourquoi le contenu des slides n'est pas envoyé à Claude.** Le prompt
A.5 mentionne juste le chemin du PDF pour mémoire, pas d'extraction
multimodale (les images des slides en input du modèle). Pas urgent
parce que le script_oral capture déjà à 90 % le contenu des slides en
texte, et l'extraction multimodale demanderait soit du PDF→images→
modèle vision (gourmand) soit `pypdf` text-only (pauvre sur les
diagrammes EN1). Reporté Phase B+ s'il y a un vrai besoin observé.

**Implémentation.** ~30 lignes dans `gui.py` (2 boutons + 2 handlers +
1 helper `_open_file_in_default_app` distinct du `_open_path` existant
qui fait `mkdir`). Aucun nouveau test : c'est une glue UI simple, le
resolver est déjà couvert.

---

## Phase A.7-light : Mode lecture (tuteur + accès FS + suggestions validées) (2026-05-05, fin de la journée)

**Friction observée.** Demande explicite après les boutons Ouvrir script /
slides de A.6.3 :

> Pas que quand c'est un script, mais aussi un exo de TD, une correction
> etc. On sait jamais. […] ce que je veux c'est lire le script en même
> temps que je suis en enregistrement vocal et du coup ça m'est arrivé
> beaucoup de fois d'avoir des questions ou des incompréhensions de ce
> que je lis et l'IA va m'aider à comprendre ce que je lis voire corriger
> des incohérences depuis les fichiers /COURS car oui il faut aussi que
> compagnon de révision puisse corriger les choses en direct et accéder
> à mes outils comme ce que ferait Claude Code ou Claude Cowork. (Gstar)

Bref : un **mode tuteur** complémentaire du mode colle, avec accès live
au filesystem `COURS/` pour lever les confusions et corriger les
incohérences entre les fichiers persos et les sources prof.

**Discussion préalable.** J'ai proposé deux versions (Light vs Full)
avec leurs trade-offs (cf. [README §Mode colle vs Mode lecture](README.md)
pour le détail définitif). Choix utilisateur : **Light**, garder la
main sur chaque correction, le pattern « balises validées par
l'utilisateur » reste cohérent avec l'esprit Compagnon (`WEAK_POINT`,
`TTS`, `END_SESSION`).

### Ce qui a été livré

**Nouveau prompt système** `_prompts/PROMPT_SYSTEME_LECTURE.md` (v1.0,
~230 lignes) : tuteur patient, vouvoiement strict comme en colle, posture
« j'attends qu'on me parle, je n'interromps pas la lecture », règles
spécifiques sur quand suggérer une édition (incohérence vs corrigé prof,
erreur factuelle, typo qui change le sens) et quand ne pas (préférences
stylistiques, edits sur fichiers prof).

**Parser étendu** (`parser.py`) :
- Nouvelle balise `<<<SUGGESTED_EDIT>>>{...}<<<END>>>` parsée comme JSON
- Nouvel état `INSIDE_SUGGESTED_EDIT` dans la machine à états
- Nouveau `ParserEventType.SUGGESTED_EDIT`
- Validation light dans `_try_parse_suggested_edit` : champs `file`,
  `before`, `after` requis, `before` non-vide, `before != after`. La
  validation chemin (no traversal, sous COURS_ROOT, extension whitelist,
  unicité du `before`) est faite à l'**application**, pas au parsing.
- Tolérant : malformations loggués en warning, event simplement non émis.

**Client Claude étendu** (`claude_client.py`) :
- Nouveau paramètre `mode` (`"colle"` ou `"lecture"`)
- Nouveau paramètre `cours_root: Path`
- En mode lecture, `claude --print` est lancé avec
  `--allowedTools "Read,Grep,Glob"` et `cwd=cours_root` : Claude voit
  l'arbre `COURS/` comme working dir, peut faire `Read("AN1/CM/CM6.txt")`
  ou `Grep("théorème de Rolle", path="AN1/CM/")`.
- En mode colle, comportement identique à avant (pas de `--allowedTools`,
  pas de `cwd`).

**Backend** (`app.py`) :
- `/api/start_session` accepte `body["mode"]` (défaut "colle"), choisit
  le bon prompt système, instancie `ClaudeClient(mode=..., cours_root=COURS_ROOT)`,
  trace `mode` dans le JSON de session.
- Forward SSE des `SUGGESTED_EDIT` events au front (event `suggested_edit`).
- Nouvel endpoint **`POST /api/apply_edit`** avec sécurités :
  - Chemin relatif obligatoire (rejet `..`, chemin absolu Unix `/`,
    chemin absolu Windows avec `:`)
  - `target.resolve()` puis `relative_to(COURS_ROOT)` : rejette tout
    chemin qui s'évade par symlink ou autre
  - Extension whitelist `.md` et `.txt` uniquement
  - `before` doit apparaître exactement 1 fois dans le fichier (sinon
    422 « ambigu » ou 422 « introuvable »)
  - Backup `.bak` créé avant l'écriture
  - Atomic write `.tmp` + `os.replace`
  - Retourne `{ok, file, backup, delta_chars}` à 200, ou `{error}` à
    400/404/422/500.

**Front** (`app.js`, `index.html`, `style.css`) :
- Listener SSE `suggested_edit` qui appelle `renderSuggestedEdit(payload)`
- Card dans le flux dialogue avec :
  - Nom du fichier en monospace
  - Raison (italic, gris)
  - Diff `before` / `after` côte-à-côte (rouge sur fond rouge léger,
    vert sur fond vert léger, préfixés `−` / `+`)
  - Boutons « ✓ Appliquer » / « ✗ Rejeter »
  - Status après action (« ✓ Appliqué (+12 car., backup SCRIPT.md.bak) »)
- Le `<select>` Mode est ajouté dans le formulaire de démarrage du
  navigateur : le pattern « prefill from URL params » du JS le remplit
  automatiquement quand `compagnon.py --mode lecture` est lancé.

**CLI / GUI** :
- `compagnon.py --mode colle|lecture` (défaut colle), propagé via URL
  params au formulaire navigateur.
- `gui.py` : nouvelle ligne « Mode » avec 2 radio buttons (Colle/Lecture)
  dans le panneau ▶ Lancer, propagé via `--mode` au sous-process.

**Tests** : 17 nouveaux (92 → **109 tous verts**)
- 7 cas SUGGESTED_EDIT dans `test_parser.py` (valid, split chunks, JSON
  invalide, champs manquants, no-op, before vide, reason optionnel)
- 10 cas dans `test_app_apply_edit.py` (happy path + backup, traversal
  rejet, absolu Unix/Windows rejet, .pdf rejet, fichier manquant 404,
  before introuvable 422, before non-unique 422, no-op rejet, champs
  manquants 400)

### Pourquoi PAS la version Full

Tentation : utiliser directement `Edit` / `Write` du CLI Claude Code
(comme Cowork) pour que Claude écrive en direct dans les fichiers, on
git-stashe avant chaque session pour rollback. Plus puissant, ressemble
à l'expérience Cowork.

Choix utilisateur : Light. Raisons :
1. Cohérence avec l'esprit Compagnon (capture structurée par balises, déjà
   éprouvé pour `WEAK_POINT`).
2. Contrôle fin : l'utilisateur valide **chaque** correction, pas de
   surprise.
3. Risque réduit : pas de fichier modifié sans clic explicite. Le Light
   peut être upgradé en Full plus tard si la friction « valider chaque
   edit » devient gênante.

La version Full reste documentée dans le README pour mémoire, avec
estimation ~3 jours de boulot supplémentaires (allowedTools étendu +
git stash auto + GUI de diff post-session pour validation en bulk).

### Latence pratique attendue

- Premier appel Claude en mode lecture : ~3-5 s (CLI démarre, charge
  contexte, peut faire 1-2 `Read` selon la question)
- Appels suivants : 2-4 s en moyenne, jusqu'à 8-10 s s'il fait beaucoup
  de `Grep` pour vérifier une cohérence multi-CM
- Application d'un edit accepté : <100 ms (read + replace + write atomic)

---

## Phase A.7.1 : Persistance de la dernière sélection (2026-05-05, soir tard)

**Friction observée.**

> Dans les select, quand je sélectionne des choses, fais que ça
> enregistre par défaut comme ça à la réouverture je n'aurai pas à
> de nouveau resélectionner. (Gstar)

Pénible de re-sélectionner matière + type + num + exo + mode à chaque
ouverture de la GUI quand on bosse plusieurs sessions par jour sur le
même TD.

**Le fix.** Étend `_secrets/runtime_settings.json` (qui héberge déjà
les seuils quota et les caps contexte) avec un champ `last_selection` :

```json
{
  "last_selection": {
    "matiere": "AN1",
    "type": "TD",
    "num": "5",
    "exo": "3",
    "annee": "",
    "mode": "lecture",
    "enable_audio": false,
    "skip_quota": false
  }
}
```

- **Au boot de la GUI** (`gui._build_form_vars`) : `get_last_selection()`
  alimente les valeurs initiales des `StringVar` / `BooleanVar`. La
  cascade de comboboxes (`_cascade_from_*`) corrige automatiquement si
  la valeur n'existe plus dans l'arbre (ex : TD supprimé entre 2
  sessions).
- **Au clic Lancer** (`gui._launch`, après spawn subprocess réussi) :
  `update_last_selection(...)` sauvegarde la sélection courante. Pas de
  sauvegarde sur chaque change-de-combobox (trop bruyant) : seul un
  Lancer compte comme « commit ».
- `resume_mode` n'est volontairement **pas** persisté : ça ne fait pas
  sens d'avoir `--resume` activé par défaut au boot suivant.

**Bug rencontré + fix.** Les fonctions `load_settings(path=...)` et
`save_settings(data, path=...)` avaient leur path en default-arg
(``= RUNTIME_SETTINGS_PATH``). Or les default-args sont évalués à la
définition, pas à l'appel, donc `patch.object(rs, "RUNTIME_SETTINGS_PATH",
tmp)` n'a **aucun effet** sur `load_settings()` sans argument explicite.
Refactoré pour résoudre `path` au moment de l'appel
(``path = RUNTIME_SETTINGS_PATH if path is None else path``). Permet
aussi à n'importe quel call-site de patch le module-level path pour
des tests d'isolation propres.

**Tests** : 5 nouveaux dans `test_runtime_settings.py` (default empty,
roundtrip complet, partial merge keeps defaults, coerce bool, partial
update via `update_last_selection`). 109 → **114 tous verts**.

---

## Tableau récap

| Phase | Date | Quoi | Pourquoi |
|---|---|---|---|
| A | 2026-05-01 | MVP texte pur, lancement terminal | Démarrer simple, valider la boucle dialogue + capture WP. |
| A.5 | 2026-05-05 (matin) | Corrigé officiel + matériel perso ancrés dans le contexte. Prompt système v0.2 « consulte le corrigé ». | Friction observée : Claude divergeait des corrigés prof car il ne les voyait pas. |
| A.6 | 2026-05-05 (soir) | GUI Tkinter pour lancer + paramétrer quotas. | Friction observée : terminal pour usage régulier = trop de plomberie. |
| A.6.1 | 2026-05-05 (foulée) | Comboboxes cascading dans le formulaire de lancement (matière → type → num → exo + année), peuplés depuis l'arbo COURS. | Friction observée : entries libres permettaient de taper des valeurs invalides → démarrage planté. |
| A.6.2 | 2026-05-05 (soir tard) | Bouton micro toggle dans le navigateur, à la Claude.ai. `--enable-audio` (hotkey Espace) devient legacy. | Friction observée : tenir Espace est crispant et conflite avec la saisie clavier. |
| A.6.3 | 2026-05-05 (fin de soirée) | Boutons « 📖 Ouvrir script » et « 📊 Ouvrir slides » dans le panneau Lancer pour la pré-révision passive. | Friction observée : naviguer dans Explorer pour trouver le script avant chaque colle = trop de plomberie. |
| A.7-light | 2026-05-05 (fin de la journée) | Mode lecture (tuteur), prompt système séparé, accès FS via Read/Grep/Glob scopés à COURS, suggestions de correction validées par l'utilisateur (balise `<<<SUGGESTED_EDIT>>>` + endpoint `/api/apply_edit`). | Demande utilisateur : tuteur qui aide à comprendre + corrige les incohérences entre script perso et corrigés prof. Light pour garder le contrôle fin sur chaque édit. Version Full repoussée. |
| A.7.1 | 2026-05-05 (soir tard) | Persistance de la dernière sélection (matière/type/num/exo/année/mode/audio/skip-quota) dans `_secrets/runtime_settings.json`. Restaurée au boot, sauvée au clic Lancer. | Friction : re-sélectionner les mêmes valeurs à chaque ouverture quand on bosse plusieurs sessions par jour. |

---

## Prochaines phases (rappel : voir `CLAUDE.md` §9)

- **Phase B** : TTS Edge primary + Piper fallback, watcher photos
  brouillon, mode reprise propre, agrégat `_points_faibles/*.csv`. Avec
  Cowork dispo, scope probablement réduit (rebuild + export délégués à
  Cowork au lieu d'être codés).
- **Phase C** : Export Anki .apkg, mini Flask Tailscale-exposed pour
  réception photos depuis téléphone.
- **Phase D** : multi-séances continues, stats progression, intégration
  cog `cours_pipeline.py` BotGSTAR.
