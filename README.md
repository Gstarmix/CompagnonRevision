# Compagnon_Revision

> Outil personnel de révision orale active à la voix.
> Mode colle d'oral, vouvoiement strict, débrief post-séance.
>
> **Phase A** (MVP texte pur, lancement terminal) : livrée 2026-05-01.
> **Phase A.5** (ancrage corrigé officiel + matériel perso) : 2026-05-05.
> **Phase A.6** (GUI Tkinter pour s'affranchir du terminal + paramétrer les quotas) : 2026-05-05.
> **Phase A.6.1** (comboboxes cascading peuplés depuis l'arbo COURS) : 2026-05-05.
> ⚠ Phase v15.7.32 (2026-05-11) : scanner étendu aux **types libres**, soit tout sous-dossier de la matière qui contient au moins un fichier pédagogique (PDF/MD/TXT) apparaît dans le combobox Type, pas seulement TD/TP/CC/CM/Quiz/Examen.
> ⚠ Phase v15.7.33 (2026-05-11) : pour un type libre qui agrège **plusieurs thèmes** (cas PSI `_revision_CC2/` avec 4 kits par thème : Bit_information / RAID / TP_Shannon / USB dans `scripts/`), le combobox Num expose `full` + un sous-numéro par thème détecté. Mapping fichier→rôle revu : `aide_memoire_CC*` est mappé comme **poly CM** (matériau de référence), `annale_synthese_CC*` comme **énoncé** (Q&A examen blanc). Le tuteur peut interroger précisément sur le thème ciblé sans charger tout le contexte des autres.
> ⚠ Phase v15.7.35 (2026-05-11) : quand le **mode guidé** ne trouve pas un SCRIPT_*.md Feynman (cas dossiers ad hoc), une **modal s'ouvre** avec 3 options : 🔍 parcourir manuellement (file picker hiérarchique sous COURS_ROOT, sécurité anti-traversal), 🤖 chercher avec IA (Gemini Flash scan le dossier, suggère script + slides, résultat persisté dans `{dossier}/_compagnon_scan.json` invalidé sur mtime), ↩ repli en mode colle.
> ⚠ Phase v15.7.36 (2026-05-11) : si le script choisi est un `.txt` continu sans headers `## [SLIDE N]` Feynman, le mode guidé bascule en **« lite »** : 1 page PDF = 1 slide synth (`Page N/M`), le tuteur a le texte complet via SCRIPT ORAL PERSO. Une bulle orange propose un bouton « 📝 Régénérer via Claude Code » qui ouvre une modal avec un prompt clé-en-main (aligné sur `COURS/CLAUDE.md`) à copier dans une session Claude Code séparée. 2 kinds : `regen_script_md` (Feynman propre) et `audit_matiere_cc` (rapport read-only des orphelins script/slides de toute la matière).
> **Phase A.6.2** (bouton micro toggle dans le navigateur, à la Claude.ai) : 2026-05-05.
> **Phase A.6.3** (boutons Ouvrir script / Ouvrir slides pour pré-révision passive) : 2026-05-05.
> **Phase A.7-light** (Mode lecture : tuteur avec lecture FS et suggestions de correction validées par l'utilisateur) : 2026-05-05. ⚠ Phase Z.8 (2026-05-09) : mode `lecture` supprimé, absorbé par mode `guidé`.
> **Phase A.7.1** (persistance de la dernière sélection du formulaire de lancement) : 2026-05-05.
> **Phase A.7.2** (type=CM supporté dans Lancer une session + boutons Ouvrir script/slides grisés en live + Lancer grisé sans matériau Feynman + persistance sélection à chaque cascade + Whisper auto CPU/GPU avec fallback + résolution claude CLI + cmdline > 32 KB → tempfile/stdin + console claude masquée + markdown live + bouton 📎 photos auto-rangées par matière + toolbar de ton 6 boutons sous chaque réponse + rendu LaTeX live via KaTeX + images du Compagnon via `/api/cours_file`) : 2026-05-06.
> **Phase A.7.2 v8-v14** (textarea autosize + tables GFM + détection halluc Whisper + auto-advance NEXT_SLIDE + GOTO_SLIDE + sidebar historique + résumé adaptatif + auto-restore Ctrl+F5 + sélecteur moteur synchro GUI Tkinter + suppression/édition/branching messages style ChatGPT + pièces jointes multi-canal mobile/paste/drag&drop + page `/mobile` Tailscale + lightbox images + bouton 🗑 par image + édition avec joindre image + recharger contexte style Gemini + cooldown anti-cascade slide + flag respondingToSlideMeta anti-cascade multi-tour + refonte sidebar grid+onglets + markers transition slide avec distinction user/tuteur 👉/🤖 + countdown reset dans panneau quota + prompt §2.9 reformulé positif anti-récitation + TTS Edge avec player avancé scrub/speed/voix sur chaque bulle) : 2026-05-07.
> **Phase A.7.2 v15** (anti-fragilité prompt en 3 couches : (1) rails déterministes Python `output_filters.py` qui retirent role hijacking inline (incl. **USER:** dans markdown bold) + récitation + balises mal placées avant stockage transcript, capitalize cosmétique post-filtrage, event SSE `final_text` qui remplace la bulle live, auto-injection NEXT_SLIDE quand le tuteur annonce sans balise ; (2) tool calling natif `tool_schemas.py` avec schémas Anthropic/Gemini/OpenAI-compat et tuning prompt par engine ; (3) PoC DSPy `dspy_compiler.py` avec signatures `RespondToSlideMeta` + `RespondToStudentReading`, dataset 8 exemples, metric basée sur les filtres déterministes ; auto-advance opt-in via bouton sidebar « 🤖 Activer/Rappeler nav » + bulle système traçable, suppression d'un marker de transition = retour slide précédente (cohérence UI/state), timer thinking-indicator adaptatif (jaune>30s / orange>60s / rouge>120s), 205 tests unitaires passing) : 2026-05-07.
>
> Pour l'historique narratif des phases (pourquoi chaque pivot, frictions rencontrées, ce qui a été remplacé), voir **[CHANGELOG.md](CHANGELOG.md)**.
>
> Pour le choix entre les 5 moteurs supportés (subtilités prix, free tiers, use cases concrets, pourquoi pas GPT, cas d'étude re-summarize Arsenal), voir **[MOTEURS.md](MOTEURS.md)**.

---

## C'est quoi

Un compagnon de révision qui m'interroge à voix haute sur un exo de TD ou de CC, dans le style d'un colleur de prépa. Push-to-talk → Whisper → Claude → texte affiché. En fin de séance, un débrief résume ce qui a été couvert et propose des mini-exos ciblés.

Projet sœur de BotGSTAR, autonome, réutilise le module quota d'Arsenal_Arguments et le moteur Whisper GPU.

---

## Trois modes pédagogiques : Découverte → Guidé → Colle (Phase A.8)

Le Compagnon expose **trois postures** pédagogiques distinctes, à choisir au lancement (radio dans la GUI Tk + select dans le form web). Progression idéale d'un nouveau cours : **Découverte** (acquisition) → **Guidé** (consolidation) → **Colle** (vérification).

| Mode | Posture | Quand l'utiliser | Source primaire | Outputs spéciaux |
|---|---|---|---|---|
| 🌱 **Découverte** | Tuteur explicateur, **zéro prérequis**, exposition courte → question simple → validation → suite. Max 2 concepts neufs/réplique, pas de barème d'indices. | Démarrer un sujet **jamais (ou peu) suivi en CM**. Si tu réponds « aucune idée » trop souvent en colle ou tu galères à lire le script Feynman parce qu'il manque les bases. | Aide-mémoire + poly CM + connaissances LLM. Corrigé officiel injecté en interne pour calibrer le PDF d'énoncé inventé, **jamais cité** à l'étudiant. | **PDF d'énoncé d'entraînement** généré (cas A, pas de TP cible) OU posture *bottom-up* sur TP existant (cas B, §1.6bis depuis A.8.1) avec micro-leçons + ancrage par l'écrit + connexion fonction par fonction au TP cible. |
| 📖 **Guidé** | Tuteur slide-par-slide sur le script Feynman préparé par l'étudiant. Accès FS `Read,Grep,Glob` pour vérifier la cohérence script ↔ corrigé prof. | Consolider après avoir découvert les bases. L'étudiant a déjà préparé un script et veut le dérouler activement avec un tuteur qui questionne, vérifie, propose des corrections. | Script perso `SCRIPT_*.md` (ou `.txt`/`slides_*.pdf` en mode « lite » fallback) + corrigé officiel. | `<<<NEXT_SLIDE>>>`, `<<<GOTO_SLIDE>>>`, `<<<SHOW_DOC>>>`, `<<<SUGGESTED_EDIT>>>` (diff validé pas-à-pas). |
| 🎯 **Colle** | Colleur d'oral strict, **vouvoiement strict**, interrogation pure. | Vérifier la maîtrise après consolidation. L'étudiant est prêt à se faire interroger sec, à reformuler proprement, à produire un raisonnement complet. | Énoncé + corrigé officiel (ancrage paramétrable strict/consultatif/aucun) + matériel perso en bonus. | `<<<TTS>>>` (vocalisation passages-clés), `<<<END_SESSION>>>` + phase débrief post-séance avec récap Gemini Flash. |

**Pas obligatoire de suivre la progression**. Tu peux directement attaquer en mode Colle si tu maîtrises déjà. Ou rester en Découverte plusieurs sessions sur un sujet difficile avant de basculer en Guidé. Le radio Découverte est désactivé si aucun matériau pédagogique n'est trouvé pour la matière/type (gate identique au bouton Lancer).

**Doctrine** : le mode Découverte n'est **pas** un cours magistral. C'est un cycle court où le tuteur expose, fait vérifier, recadre. Cf. `_prompts/PROMPT_SYSTEME_DECOUVERTE.md` pour la spec pédagogique complète.

**Cas A vs Cas B (Phase A.8.1)** : si tu démarres une session sans cibler un TP précis (révision globale d'un chapitre), le tuteur génère un PDF d'énoncé d'entraînement (cas A). Si tu cibles un TP existant que tu n'as pas les bases pour aborder (cas observé 2026-05-12 : TP Shannon en Python sans connaître Python), le tuteur bascule en **pédagogie bottom-up** : il identifie les prérequis manquants, fait des micro-leçons ancrées (proposition de noter au cahier + photo de validation), puis **reconnecte fonction par fonction** au TP cible. Pas de PDF inventé dans ce cas : le TP existant est ton support, ton cahier est ta trace. La bascule cas A/B est automatique selon le contenu du SessionContext (énoncé / script / slides présents → cas B).

**Sujet libre : apprendre n'importe quoi hors COURS/ (Phase A.8.3)** : si tu veux apprendre un sujet qui n'est pas dans tes cours d'université (Python depuis zéro, japonais, comptabilité personnelle, philosophie, etc.), coche `💡 Sujet libre` dans le form de lancement et décris ton sujet en 1-3 phrases dans la zone qui apparaît. Le Compagnon bascule alors en mode où :

- Aucun matériel COURS n'est attaché (tous les paths d'énoncé/corrigé/script/CM sont vides)
- Le tuteur s'appuie uniquement sur ses connaissances LLM propres
- **Au 1er tour, il pose 2-3 questions de cadrage** dans une seule réponse : niveau actuel / objectif concret / temps dispo / pré-acquis éventuels. Tu réponds en bloc, et il enchaîne vraiment la séance au 2e tour.
- Mode Guidé est **désactivé** (pas de script Feynman ni slides à dérouler). Tu peux choisir Découverte ou Colle.
- En Découverte, checkbox `📄 Générer un PDF d'entraînement` cochée par défaut : le tuteur émet une balise `<<<SAVE_INVENTED_PDF>>>` au 3e ou 4e tour avec 2-4 exos d'entraînement calibrés sur le cadrage que tu lui as donné. Décoche pour une séance purement conversationnelle.
- En Colle, posture interrogation classique mais ancrage corrigé forcé à `aucun` (pas de corrigé officiel à brandir comme autorité).
- Storage : `_sessions/YYYY-MM-DD_LIBRE_<slug>_full_{mode}_{format}_aucun.json` (Phase A.8.6, suffixe mode/format/anchor, voir §7). Le slug est extrait automatiquement de ton texte (« je veux apprendre Python » → `apprendre-python`).

### Workspace (Phase A.9, 2026-05-13)

Une 5ᵉ source possible, parallèle à Sujet libre : **donner cours à partir d'un dossier de ton disque**. Pratique pour comprendre un projet que t'as construit avec une IA avant un entretien, prendre en main un repo qu'on t'a filé, structurer ton CV, ou explorer un dossier de notes de cours hors COURS/.

#### Workflow GUI

1. Dans le launcher, coche **`📁 Workspace (dossier disque arbitraire : codebase, docs, CV…)`**. Les combos COURS se grisent automatiquement (mutex avec Sujet libre), le radio Guidé se désactive (pas de slides à dérouler).
2. Le bloc workspace apparaît avec 4 champs :
   - **Dossier :** Entry + bouton `Parcourir…`. Sélectionne le dossier racine du workspace via la fenêtre de dialogue Windows.
   - **Raccourcis :** Combobox déroulante de tes dossiers fréquents.
     - Bouton `+` : mémorise le dossier actuellement dans le champ « Dossier : » comme raccourci permanent (persisté dans `_secrets/runtime_settings.json` → `workspace_presets`).
     - Bouton `−` : retire le raccourci actuellement sélectionné dans la liste déroulante.
     - Cliquer sur un raccourci dans la liste le copie dans le champ « Dossier : » d'un seul clic, plus besoin de re-naviguer dans l'explorateur.
   - **Focus sous-dossier :** Entry + bouton `Parcourir…` (scopé au workspace). Optionnel : laisse vide pour que le tuteur ait l'arbre depuis la racine, ou clique Parcourir pour choisir un sous-dossier précis (par ex. `_scripts/dialogue/`) que le tuteur regardera en priorité. Le chemin relatif est calculé automatiquement.
   - **Excludes additionnels :** Entry comma-separated pour exclure tes propres patterns en plus des défauts (`_uploads, *.log` → ajouts aux exclusions de base `.git/`, `node_modules/`, `__pycache__/`, `_secrets/`, etc.).
3. Clique **`▶ Lancer`**. Le launcher passe `--workspace-root` + `--workspace-focus` + `--workspace-exclude` à `compagnon.py`, qui propage à l'URL puis au backend Flask. Le navigateur s'ouvre sur la séance.

#### Ce que reçoit le tuteur au démarrage

- **Marker `[WORKSPACE_TYPE : code|doc|mixed]`** : heuristique automatique sur les extensions des 500 premiers fichiers. Code-heavy (>60% `.py`/`.js`/`.cs`/`.rs`/etc.) → `code`. Doc-heavy (<40% code parmi les fichiers à extension reconnue) → `doc`. Sinon → `mixed`. Le prompt `_prompts/PROMPT_SYSTEME_WORKSPACE.md` ajuste la posture selon ce marker.
- **Marker `[WORKSPACE_FOCUS : <subdir>]`** si tu as rempli le sous-dossier de focus.
- **Résumé auto du workspace (≤ 50 k chars)** :
  - Arbre depth 3 (cap 20% du budget chars) avec les excludes appliqués.
  - Lecture intégrale des fichiers-pivots détectés : `README.md`, `CLAUDE.md`, `AGENTS.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, `pyproject.toml`, `package.json`, `Cargo.toml`, `Dockerfile`, `.github/copilot-instructions.md`, etc. (cap 8 k bytes par fichier).
- **Outils FS pour explorer pendant la séance** : `Read`, `Grep`, `Glob` scopés au workspace. Le tuteur peut donc piocher dans le code au-delà du résumé pour ancrer ses explications. **Phase A.12** : ces outils fonctionnent désormais sur **les 5 moteurs** : nativement via la CLI Claude Code (`cli_subscription`), et via une vraie boucle de function-calling sur les 4 moteurs API (`gemini_api`, `api_anthropic`, `deepseek_api`, `groq_api`). Avant, sur un moteur API le tuteur n'avait aucun canal d'outil et **hallucinait le contenu des fichiers** (cf. CHANGELOG Phase A.12). `Read` gère le texte, le code et les PDF/images (ingérés directement par Gemini et Claude ; DeepSeek/Groq étant text-only, un PDF y renvoie un message honnête). Chaque appel d'outil affiche une **puce animée « 🔍 Lecture de `fichier` »** dans le fil : tu vois le tuteur consulter le dossier en direct, comme dans Claude Code, au lieu d'un bloc de texte opaque (Phase A.12).

#### Les 3 postures (sélectionnées par le tuteur au 1ᵉʳ tour selon ton cadrage)

Au 1ᵉʳ tour, le tuteur ouvre par une présentation brève (3-5 phrases) de ce qu'il comprend du dossier, puis pose 2-3 questions pour cadrer :
1. Tu veux **découvrir** le dossier, **être interrogé** dessus, ou **approfondir un point précis** ?
2. Quel est ton niveau actuel (tu l'as écrit toi-même avec une IA / c'est de l'IA brute à comprendre / c'est un repo tiers) ?
3. Combien de temps, et y a-t-il un livrable derrière (entretien, présentation, refacto) ?

Selon ta réponse, il bascule en :
- **`explain`** : tour guidé des modules/sections avec citations chemin:ligne. Adapté `code` et `mixed`.
- **`quiz`** : quizz progressif (le tuteur te demande ce que fait tel fichier sans te le montrer, signale et fait reformuler sur erreur, comme en mode colle classique). Adapté tous types.
- **`deep-dive`** : lecture méthodique d'une zone précise avec décomposition en sous-questions, remontée systématique au niveau global. Adapté `code` et `mixed`.

Bascule possible à tout moment via « passe en quiz », « explique-moi plutôt », etc.

#### Format pédagogique (oral / photos / mixte)

Le radio « Format » du launcher (et le `<select>` du header en cours de séance) pilote la **stratégie support papier vs écran** par posture (cf. `_prompts/PROMPT_SYSTEME_WORKSPACE.md` §2.8 v1.3) :

- **🎙 `oral`** : pas de photo demandée. Le tuteur s'appuie uniquement sur la conversation tapée/dictée + `Read` sur le code. Adapté transports, écran seul, sans cahier.
- **📸 `photos`** : le tuteur **exige systématiquement** une photo dès qu'il s'agit d'un contenu structuré (schéma d'archi, table de bench, croquis d'API, calcul de complexité, pseudo-code, séquence asynchrone). Pas d'acceptation d'une réponse purement verbale sur ces points. Cas-type : entretien à préparer → tu dessines l'archi sur papier, tu envoies la photo, le tuteur corrige.
- **🔀 `mixte` (défaut)** : décision au cas par cas : photo demandée sur les objets structurés (schéma, calcul lourd), verbal accepté sur les questions courtes ou conceptuelles. Sortie de secours autorisée (« tu peux esquisser à l'oral si pas de papier »).

Bascule à chaud possible via les chips ou slash-cmds `/oral`, `/photos`, `/mixte` : le tuteur adopte la nouvelle stratégie au prochain tour sans résister.

#### PDF d'exos d'entraînement (option, partagée avec sujet libre)

La case **`📄 Générer un PDF d'exos d'entraînement`** apparaît aussi en workspace (default cochée, comme en sujet libre). Quand elle est cochée, le tuteur peut émettre la balise `<<<SAVE_INVENTED_PDF>>>` une fois dans la séance pour générer une fiche papier imprimable (`_generated/<session_id>_enonce.pdf`).

Selon la posture sélectionnée au cadrage, le contenu du PDF varie :
- **`explain`** → fiche d'audit (5 modules-clés + ce qu'il faut savoir dire dessus en entretien).
- **`quiz`** → 10 questions probables d'entretien sur le codebase, avec corrigé en page 2.
- **`deep-dive`** → mini-glossaire des concepts traversés avec citations `chemin:ligne`.

Cas concret : « j'ai un entretien bientôt pour présenter mes logiciels » → coche la case + lance en workspace sur ton dossier projet, demande au tuteur en posture quiz de te générer une fiche de 10 questions d'entretien probables. Tu l'imprimes et tu révises offline.

Décocher = pas de PDF généré (séance purement conversationnelle). Pratique si tu veux juste explorer/discuter sans support papier.

#### Garde-fous (cf. `_prompts/PROMPT_SYSTEME_WORKSPACE.md` §4)

- **Lecture seule** : pas d'`Edit`/`Write`/`Bash`. Le tuteur ne modifie jamais un fichier de ton workspace (même pas via la balise `<<<SUGGESTED_EDIT>>>` du mode guidé). Si tu veux un patch, il te l'explique en texte, à toi de l'appliquer.
- **Pas de fuite de secrets** : `.env`, `_secrets/`, `*.key`, `*.pem`, fichiers nommés `*secret*`/`*password*`/`*token*` ne sont jamais restitués même si accidentellement lus.
- **Pas d'hallucination** : si le résumé n'a pas couvert un aspect, le tuteur fait un `Read` avant de répondre au lieu de « je crois que ça fait X ».
- **Pas de jugement de qualité non sollicité** : pas de « beau code », pas de « cette archi est nulle ». Sauf si tu demandes explicitement une revue.
- **Vouvoiement strict** comme dans les autres modes.

#### Storage et nommage

- session_id : `YYYY-MM-DD_WORKSPACE_<slug>_full_workspace_mixte_aucun.json` (slug = basename normalisé du dossier, par ex. `compagnon-revision`, `cv`, `arsenal-arguments`).
- Les champs `colle_format` (`mixte`) et `corrige_anchor` (`aucun`) sont des placeholders en mode workspace : ils n'ont pas de sémantique, mais gardent le format du session_id homogène avec les autres modes.

**Format pédagogique en Découverte (Phase A.8.2)** : trois postures distinctes selon le contexte matériel de l'étudiant, paramétrées par le même `Format` (oral / photos / mixte) que celui du mode colle, mais avec une **sémantique différente** :

| | 🎙 Oral | 📸 Photos | 🔀 Mixte (défaut) |
|---|---|---|---|
| **Cahier** | Jamais demandé | Systématique sur défs / syntaxes / formules / exemples | Au cas par cas |
| **Photos** | Jamais | Validation régulière | Sur passages clés |
| **OCR Flash 2.5** | Inactif | Actif | Actif quand photo |
| **Reformulation orale** | Centrale (« redites avec vos mots ») | Optionnelle (l'écrit ancre) | Adaptée |
| **Mémoire visée** | Court terme + répétition orale | Long terme via cahier | Mixte |
| **Cas idéal** | Transport / écran seul / smartphone | Boulot calme avec papier sous la main | Défaut adaptatif |

Le tuteur bascule sa posture selon le marker `[FORMAT PÉDAGOGIQUE : ...]` injecté en début de séance. En `photos`, il applique le pattern de **dictée structurée** (titre + définition + exemple à recopier au cahier + photo de validation + OCR + corrections ponctuelles), méthode validée par observation 2026-05-12. En `oral`, il privilégie analogies mémorables et reformulations. En `mixte`, il décide selon la nature du contenu enseigné. Bascule en cours de séance via slash-commands `/oral`, `/photos`, `/mixte` ou via le select Format de l'UI (chips).

---

## ~~Archives .md des séances~~ : supprimée Phase A.10.11 (2026-05-14)

> Feature retirée. Friction d'origine : *« honnêtement archive .md sert à quoi ? car y'a déjà le JSON au pire ? »*. Vrai : le JSON de session était déjà l'unique source de vérité, le live-archive `.md` ajoutait juste de l'I/O disque à chaque tour pour un usage qui n'existait pas en pratique. L'UI web permet déjà de relire toutes les sessions via l'onglet 💬 Historique.
>
> **Remplacé Phase A.10.13b** par un bouton **📄 Récap** dans le footer sidebar qui génère un ZIP (PDF + MD) à la demande, disponible à tout moment (cf. section suivante).

## 📄 Bouton Récap : export PDF + MD on-demand (Phase A.10.13b)

Bouton **📄 Récap** dans le footer sidebar (à côté de « Terminer la séance »). Click → télécharge un ZIP avec deux fichiers :
- **`{session_id}.pdf`** : PDF lisible rendu via reportlab (transcript role-balisé + frontmatter + métadonnées + consignes épinglées + récap de séance phase débrief si dispo)
- **`{session_id}.md`** : version Markdown léger avec le même contenu (frontmatter YAML + sections balisées)

Disponible **à tout moment** pendant la séance, pas seulement à la fin. Utile avant un examen pour relire ta séance offline, pour audit, ou pour le futur portfolio public.

## 📒 Carte cahier : artefact « feuille de cours » coloriée (Phase A.10.19)

**Vraie différenciation vs ChatGPT/Claude/Gemini web** : aucun LLM grand public ne rend les moments « notez ceci sur votre cahier » comme un artefact visuel. Le Compagnon, oui : en modes Découverte et Workspace, quand le tuteur dit « prenez votre cahier », il émet une **carte cahier** structurée. Côté front : fond crème papier, lignes Seyès discrètes, marge rouge stylo à gauche, contenu coloré selon une doctrine pédagogique stricte. L'étudiant **recopie exactement ce qu'il voit** (couleurs incluses) et photographie pour validation OCR. Boucle pédagogique close.

> **Phase A.12** : `PROMPT_SYSTEME_DECOUVERTE.md` v1.7 renforce le *quand* émettre une carte : friction « cartes trop rares / en fin de séance seulement ». Le prompt fixe désormais des déclencheurs explicites (toute définition, syntaxe, formule, méthode, exemple canonique, distinction) et une cadence cible de **1 carte par notion-clef, 5 à 12 par exercice** en formats `photos`/`mixte`. La carte arrive *au moment* où la notion est expliquée, jamais reportée à un récap groupé. Le **mode Workspace** dispose lui aussi des cartes cahier depuis Phase A.12 (`PROMPT_SYSTEME_WORKSPACE.md` v1.6, §2.9), utile pour réviser un dossier de projet/TP avant une soutenance.

### Doctrine couleurs

Basée sur l'audit du cahier réel de Gstar (2026-05-15, 4 photos analysées) : **Bic 4-couleurs** (bleu/rouge/vert/noir) + 4 surligneurs (jaune/vert/rose/violet).

**Stylos (le tuteur DOIT varier, anti tout-bleu)** :

| Balise | Couleur | Sémantique | Fréquence par carte |
|---|---|---|---|
| (défaut) | 🔵 Bleu | Prose courante, narration | ~60% du texte |
| `{rouge}…{/rouge}` | 🔴 Rouge | Concept-clé / résultat à retenir, nom de type/fonction critique | 1-3 mots |
| `{vert}…{/vert}` | 🟢 Vert | Exemple concret, valeur numérique, application, **code fenced** (auto) | 0-3 |
| (auto sur `$…$` / `$$…$$`) | ⚫ Noir | **Formules mathématiques (LaTeX)** : rendu KaTeX | Auto, sur toute formule |

**Surligneurs PONCTUELS** :

| Balise | Couleur | Sémantique | Fréquence par carte |
|---|---|---|---|
| (auto, titre de carte) | 🟣 Violet | **Titre de la carte cahier** (toujours, Phase A.12.6) | 1, automatique |
| (auto, sous-titres) | 🟢 Vert | Sous-titres du corps : titres `##` / `###` + lignes-label (« Méthode : », « Définition : »…) | Auto |
| `{hl-jaune}…{/hl-jaune}` | 🟡 Jaune | Formule vitale à mémoriser par cœur | 0-1 |
| `{hl-rose}…{/hl-rose}` | 🩷 Rose | Piège, erreur classique, « attention » | 0-1 |

### Anti-sapin-de-Noël (règle absolue)

- **Max 2 surligneurs ponctuels par carte** (jaune + rose). Violet du titre et vert root hl ne comptent pas.
- **Max 3 mots en couleur stylo non-bleue** par carte.
- **Aucune balise couleur DANS un bloc fenced** (le code fenced est rendu en vert automatiquement, les formules LaTeX en noir).
- Si rien ne mérite d'être colorié → ne coloriez rien. Le bleu défaut est lisible et propre.

### Syntaxe complète

```
<<<CAHIER titre="N. Nom de la section">>>
Markdown classique (gras, listes, code, KaTeX `$...$`) + balises couleur optionnelles.
{rouge}concept central{/rouge} dans la prose.
{hl-jaune}formule vitale{/hl-jaune} si applicable.
<<<END>>>
```

Parser : extraction pré-markdown-it, render via le helper `_renderCahierBlock` (cf. `_scripts/web/static/app.js` Phase A.10.19). CSS : `.cahier-card` avec dégradé lignes Seyès, marge stylo rouge, palette couleurs spécifiée. Raccourci `==texte==` → surligneur jaune par défaut (extension non-CommonMark).

### Auto-coloriage intelligent (Phase A.10.20 → A.10.26)

Le rendu cahier applique automatiquement le coloriage **sémantique** des inline-code sans que le tuteur ait à wrapper explicitement. L'idée : le tuteur LLM ne sera pas systématiquement discipliné pour choisir `{rouge}` vs `{vert}`, donc on infère côté frontend.

**Inline `` `code` ``, heuristique sémantique (A.10.26)** :

- 🔴 **Rouge (nom / concept)** par défaut : `charToBase`, `BinTree`, `Maybe`, `List Base`, `String`. Mots/symboles techniques à reconnaître.
- 🟢 **Vert (valeur / exemple)** si contient guillemets `"..."`, brackets `[...]`/`{...}`, tuple `(...)`, ou est purement numérique. Ex : `"ATGC"`, `[A, T, G, C]`, `(us, vs)`, `42`, `(0, x)`.

**Blocs fenced ``` ``` ```** :
- Tout le contenu en 🟢 vert stylo, fond vert pâle (= code à recopier, exemple écrit).
- Commentaires (`-- ...` Idris/Haskell, `# ...` Python/Shell, `// ...` C/Java/JS) auto en 🔴 rouge italique.

**Overrides explicites par le tuteur** : `{rouge}foo{/rouge}`, `{vert}bar{/vert}`, `{hl-jaune}formule{/hl-jaune}` etc., pour les cas où l'heuristique se trompe (ex : `Just A` est une valeur mais ne match aucune regex automatique → tuteur peut wrap explicitement).

**Pourquoi cette approche** : Gemini Pro (engine principal de Découverte) suit la voie de moindre résistance : si on attend qu'il choisisse `{rouge}` vs `{vert}` manuellement à chaque inline-code, il oublie. L'heuristique côté frontend garantit un coloriage cohérent indépendamment de la discipline du tuteur. Trade-off : quelques edge cases mal classés que l'override peut corriger.

**Markdown stripped** : `**gras**` et `*italique*` ne s'affichent pas dans une carte cahier (sur papier tu n'as pas le gras). Le tuteur met de la couleur via les balises s'il veut mettre en évidence.

### 🎨 Onglet « Couleurs » : remapper rétroactivement TOUT + appliquer-à-sélection (Phase A.10.21 → A.10.23)

**Unifié depuis A.10.22** : un seul onglet 🎨 Couleurs gère les 2 cas via 2 zones distinctes par swatch :

- **Click sur l'input hex à droite** d'un rôle (ex: rouge) → **remap global rétroactif** instantané (CSS variable, toutes cards rerendent, aucun message touché).
- **Click sur le swatch (« Aa » coloré) à gauche** d'un rôle, quand la bannière `🎯 Sélection active` est visible → **applique à la sélection** (édit du message côté serveur via PATCH `/api/messages/<i>`).

Pour activer la bannière : sélectionne un mot dans une carte cahier crème → un bouton « 🎨 Colorier » apparaît dans la mini-toolbar → click → l'onglet Couleurs s'ouvre, swatches deviennent cliquables avec hover scale.

Position dans la sidebar (depuis A.10.23) : entre 📌 Consignes et 💬 Historique, pas tout à la fin.

**Depuis A.10.27** : 9ᵉ ligne dans le panneau = **surligneur 💾 Notes save** (orange par défaut). Cette couleur n'apparaît PAS dans les cartes cahier : elle marque les sélections sauvegardées via 💾 Save **n'importe où dans le dialogue** (pas seulement dans une carte cahier). Changée de jaune→orange pour éviter la confusion avec le surligneur jaune cahier (formule vitale).



Si la doctrine ne te convient pas (ex : tu trouves le rouge trop sombre, tu veux le bleu plus saturé, tu préfères du orange pour les pièges au lieu du rose), l'**onglet 🎨 Couleurs** dans la sidebar te laisse remapper chaque rôle :

- 4 stylos (bleu / rouge / vert / noir) avec color picker hex
- 4 surligneurs (jaune / vert / rose / violet) avec color picker hex
- Bouton **↺ Reset** aux valeurs par défaut

Mécanique : **CSS variables** (`--cahier-c-rouge`, `--cahier-hl-jaune` etc.). Changer la variable dans `document.documentElement.style` répercute INSTANTANÉMENT sur toutes les `.cahier-c-rouge` / `.cahier-hl-jaune` existantes, passées et futures : **rétroactif sans toucher au texte des messages**. Préférences persistées dans `localStorage` (per-device).

### 🎨 Color picker : éditer UN mot précis (édition au scalpel)

Quand une carte cahier ne te plaît pas (un mot devrait être en rouge mais le tuteur ne l'a pas mis), tu peux :

1. **Sélectionner** le texte concerné DANS la carte cahier (mini-toolbar apparaît au-dessus).
2. Cliquer un bouton couleur : 🔵 / 🔴 / 🟢 / ⚫ stylos, 🟡 / 🟩 / 🩷 / 🟣 surligneurs, ⌫ clear.
3. Le texte source est édité côté serveur (PATCH `/api/messages/<i>` silencieux), la card se re-rend instantanément.

Permet d'éditer la couleur sans passer par ✏ Modifier de la bulle entière.

### Doctrine prompt (Mode Découverte)

Documentée dans `_prompts/PROMPT_SYSTEME_DECOUVERTE.md` §1.6quater. Le tuteur est instruit explicitement :
- Quand utiliser la balise (formats `photos`/`mixte` au moment « prenez votre cahier »)
- La sémantique des 4 couleurs stylo + 4 surligneurs
- L'anti-sapin-de-Noël (limites chiffrées par carte)
- 3 exemples concrets (définition+exemple, formule mathématique, code à recopier)

### Différenciation portfolio

C'est exactement le genre d'artefact UI qui se screenshote bien pour l'expo publique été 2026 (cf. §« Présentation publique »). Le pattern *« le LLM montre exactement comment écrire dans le cahier, l'étudiant photographie pour validation »* n'existe nulle part ailleurs.

---

## 📑 Sommaire dynamique dans Docs (Phase A.10.13c)

Au-dessus des PDFs officiels dans l'onglet 📚 Docs, un **« Sommaire de la séance »** se construit automatiquement à partir des sections / exercices / questions que le tuteur introduit dans ses réponses :
- **Sections** (`## H2`) et **sous-sections** (`### H3`) du markdown
- **Patterns explicites** : `**Exercice N**`, `**Question N**`, `**Étape N**`, `**Chapitre N**`, `**Partie N**`
- **Listes numérotées de questions** (mode colle uniquement)

Pour chaque entrée :
- **Click sur le titre** → scroll vers la bulle source dans le fil
- **Double-click** → édition inline du titre (Enter valide, Esc annule)
- **✓ / ⏸** → activer / désactiver l'entrée (reste dans la liste mais grisée)
- **🗑** → suppression définitive
- **Couleur de la bordure gauche** indique le kind (jaune = section, vert = subsection, bleu = exercice, rose = question)

Refresh après chaque réponse du tuteur (extracteur regex post-stream backend) + manuel via 🔄.

## ❓ Questions à choix cliquables (Phase A.12.4)

Quand le tuteur pose une question fermée (le cadrage d'une séance, « on continue comment ? », etc.), il n'écrit plus les options en prose : il émet une balise `<<<CHOICES>>>` que le front rend comme un **bloc interactif**, façon interface Claude.ai :

- la question + des **boutons d'options cliquables** ;
- **sélection multiple** quand c'est pertinent (le tuteur choisit) ;
- **toujours un champ libre « ✍️ Autre / précise ta réponse… »** pour écrire une réponse hors options ;
- un bouton **Envoyer** qui transmet ta sélection (+ ton texte libre) comme réponse. Le bloc se grise une fois répondu.

En modes **workspace** et **découverte**, le cadrage du 1ᵉʳ tour propose ainsi explicitement **« 📚 Faites-moi cours dessus »** parmi les options : le Compagnon offre de te faire cours, tu n'as pas à le deviner.

## 🏷 Photos auto-renommées par OCR Gemini (Phase A.10.13d)

Quand tu envoies une photo en mode colle/découverte (format `photos` ou `mixte`), le backend fait :
1. **OCR Gemini Flash 2.5** sur l'image (kind détecté + ocr_markdown + completeness%)
2. **Génère un slug** depuis les 2-3 premiers mots-clés significatifs de l'OCR (stopwords FR filtrés)
3. **Renomme le fichier** : `YYYY-MM-DD_HHMM_<kind>_<slug>_vN.ext`
   - Ex : `2026-05-14_1042_table_de_verite_AND_v1.jpg`
   - Ex : `2026-05-14_1055_pseudo_code_leaf2_v1.jpg`
4. **Met à jour** le markdown du transcript + `session_photos[]`

Skip silencieux si l'OCR est de qualité médiocre (kind="?" ou completeness < 50%) : le nom original est conservé pour ne pas pourrir avec un slug aléatoire.

**Hover** sur une vignette dans l'onglet 📸 Photos → tooltip natif avec le nom formaté joli : `"Table De Verite AND · 14/05 10:42"`.

**Rattrapage rétroactif** : `python _scripts/rename_old_photos.py` (dry-run par défaut, `--apply` pour exécuter, `--limit N`, `--session-id X`). Backup auto, appel Gemini direct. Coût ~$0.0001/image.

---

## Ce qui différencie Compagnon des LLM web (claude.ai, ChatGPT, Cowork)

Pas un wrapper. Plusieurs briques **n'existent pas** dans une conversation web standard et coûteraient un copier-coller fastidieux à chaque session :

### 1. Mode guidé piloté slide-par-slide avec auto-advance

Le tuteur **décide lui-même** de passer à la slide suivante en émettant `<<<NEXT_SLIDE>>>` à la fin de sa réplique quand il juge la slide acquise (étudiant a réagi, pas de point flou en suspens). Le front intercepte la balise, retire de l'affichage, et déclenche le passage avec 1,5 s de délai (le temps de lire la fin du message).

Pas de clic « slide suivante » entre chaque échange : le rythme est piloté par le tuteur, l'étudiant reste dans le flow de lecture. Sur claude.ai ou Cowork il faudrait soit te demander à chaque fois de coller la slide suivante manuellement, soit lui donner un signal verbal (« passe »), ce qui casse la fluidité.

Cf. `_prompts/PROMPT_SYSTEME_GUIDE.md` §2.9 pour les conditions d'émission de la balise (cumulatives) et la cadence cible (~8-10 émissions sur 12 slides, pas systématique, sinon le tuteur valide en aveugle).

### 2. Débrief post-séance structuré

En fin de séance, un appel Gemini Flash audite le transcript complet et produit un récap structuré : résumé, concepts couverts, exercices traités, suggestions de révision concrètes. La carte récap s'affiche dans le fil ; chaque concept porte un bouton 🎯 qui déclenche un mini-exo ciblé (3-5 questions) sans quitter la séance.

Sur claude.ai, tu relirais la conversation à la main : pas de récap structuré, pas de mini-exo en un clic.

### 3. Suggestions de correction du script perso avec validation pas-à-pas

En mode guidé, quand le tuteur détecte une incohérence entre le script perso et le corrigé prof, il émet `<<<SUGGESTED_EDIT>>>{"file", "before", "after", "reason"}<<<END>>>`. Le front affiche un panneau diff avec boutons Appliquer/Rejeter. Le backend re-valide à l'application (chemin sous `COURS_ROOT`, no traversal, whitelist `.md`/`.txt`, before unique) et écrit avec backup `.bak` + atomic write.

Sur Cowork avec `Edit` activé, c'est du diff direct sans pas-à-pas : plus rapide mais sans la validation chirurgicale au moment où l'humain est dans le contexte du raisonnement.

### 4. Ancrage corrigé officiel inviolable

Le prompt système §1.4 fait du `CORRIGÉ OFFICIEL` chargé en contexte la **source de vérité** pour juger les réponses étudiantes. Le tuteur ne peut pas asséner « c'est faux » sans citer le passage du corrigé qui fait foi. En mode dégradé (corrigé absent), il l'annonce explicitement à l'ouverture.

Sur un LLM web sans cette discipline injectée, tu vois régulièrement le modèle improviser des corrections plausibles qui contredisent ce qu'attend le prof : tu apprends une mauvaise version.

### 5. Quota Pro Max live + multi-moteurs + countdown reset + erreurs FR

Le panneau latéral affiche en direct deux sections (Phase v15.6.5) :

- **🤖 Claude Pro Max** : barres `session 5h`, `hebdo 7j`, `hebdo Sonnet`, `overage` avec **chacun son countdown de reset** (ex: `↻ 2h15`, `↻ 4j 12h`, hover pour la date absolue).
- **🔌 Autres moteurs** : balance DeepSeek live (via `GET /user/balance` officiel, barre verte / orange / rouge selon `total_balance` USD avec lien ⚙ vers la console billing) ; Groq / Gemini / API Anthropic en ligne compacte avec `✓ Free Tier · 30 RPM · 12 000 TPM · 14 400 RPD` (les chiffres viennent de la doc des providers, hardcodés faute d'API balance publique côté Groq/Gemini).

Polling raccourci à 30 s (au lieu de 60 s) pour la sensation live. Cache backend 30 s aligné dessus pour ne pas spammer DeepSeek.

Si le quota saute en plein flow, le backend pousse un event `quota_midflow` listant les providers de fallback dispo. Et depuis v15.6.4, les erreurs DeepSeek 402 « Insufficient Balance » / Groq 413 « Request too large » / context_length_exceeded / rate limits sont **traduites en français** dans un confirm avec cause + suggestion d'action concrète (recharger la clé, basculer vers un moteur 1M context, etc.). Le sélecteur de moteur en haut clignote 3 fois en orange pour t'indiquer où aller (`flashEngineSwitcher()`). **Pas d'auto-fallback** : tu restes maître du choix.

Sur claude.ai, quand le quota saute tu es mis dehors avec une popup et tu dois recommencer la conversation ailleurs.

### 6. Détection répétitions Whisper + auto-resize textarea + rendu Markdown via markdown-it (Phase A.10.16)

Petits détails UX cumulés qui rendent la dictée vocale + le rendu des explications denses confortables sur une session de 45-60 min : banner « Whisper a halluciné » avec bouton Nettoyer, textarea qui grandit avec le contenu façon LLM SOTA, rendu Markdown CommonMark + GFM (tables, listes imbriquées, blockquotes contenant des listes, fenced code, etc.).

**Migration markdown-it (Phase A.10.16, 2026-05-15)** : `renderMarkdown` a longtemps été 240+ lignes de regex hardcoded (gras, italique, listes, blockquotes, tables, etc.). Chaque nouveau pattern Gemini/Claude révélait des bugs composés (notamment listes à puce dans blockquotes, fix A.10.15d). Migration vers [markdown-it v14](https://github.com/markdown-it/markdown-it) via CDN (`https://cdn.jsdelivr.net/npm/markdown-it@14/dist/markdown-it.min.js`, ~100 KB) :

- **CommonMark + GFM out of the box** : tables, fenced code, listes imbriquées, blockquotes composés, paragraph breaks, autolinks désactivés (on a déjà `linkifyPageRefs` qui fait mieux pour les refs « page 3 du corrigé »).
- **Streaming-tolérant** : un `**` non fermé pendant un chunk SSE produit du texte littéral, pas d'exception. Le re-render au chunk suivant resync.
- **Custom renderers préservés via les hooks markdown-it** :
  - `renderer.rules.image` : route les paths vers `/api/upload_file` (préfixe `_uploads/`, séances post-A.10.2), `/api/cours_file` (relatif à `COURS_ROOT`) ou URL externe directe ; ajoute tooltip joli `_prettifyPhotoFilename` au hover (« Pseudo Code Leaf2 · 14/05 10:42 ») ; `onerror` injecte un placeholder visible avec le path tenté ; wrap dans `<span class="md-img-wrap" data-md=...>` avec bouton 🗑 pour retirer l'image du texte source du message.
  - `renderer.rules.table_open` : injecte la classe `md-table` pour préserver le CSS existant.
- **Post-process séparés** (inchangés) : `linkifyPageRefs(rootEl)` walk les text nodes du DOM rendu pour transformer « page 3 du corrigé » en liens cliquables ; KaTeX auto-render traite `$...$` `$$...$$` sur l'event SSE `done`.
- **Lazy-init** : `app.js` n'a pas `defer` mais `markdown-it.min.js` si, donc `window.markdownit` n'est pas garanti dispo au parse de `app.js`. Le module résout au premier appel à `renderMarkdown` puis cache l'instance. Fallback `<p>${escapeHtml(text)}</p>` si la lib n'est pas (encore) chargée, aucun crash possible.

### 7. Persistance reprenable des sessions + sidebar historique

Toutes les sessions sont persistées dans `_sessions/{session}.json` (transcript, mode, slide guidée courante, contexte fichiers, récap de débrief). Format depuis Phase A.8.6 : `YYYY-MM-DD_{MAT}_{TYPE}{N}_ex{n}_{mode}_{format}_{anchor}.json` : le suffixe `_{mode}_{format}_{anchor}` (par ex. `_colle_mixte_strict`, `_decouverte_oral_aucun`, `_guide_mixte_consultatif`) permet à plusieurs versions du même exo de cohabiter selon la posture choisie (relancer le même exo en mode différent n'écrase plus l'ancien transcript). Le panneau **Historique** dans la sidebar liste toutes les sessions passées avec :
- Click pour reprise : le tuteur reprend la conversation au point d'arrêt
- ✏️ Renommer une session (champ `label` libre, ≤120 chars)
- 🗑️ Supprimer une session
- Indicateur visuel `⚠ interrompue` si la session a été coupée brutalement
- Chips visuelles `mode · format · anchor` dans la ligne meta pour distinguer rapidement les variations d'un même exo

**Reprise = replay quasi-systématique (Phase A.8.6)** :
- Tant que la session a `< 300 tours` (cas courant), **replay complet** du transcript dans l'historique du tuteur. Il retrouve toutes les notes prises, points abordés, où on s'est arrêté.
- Au-delà (cas extrême jamais rencontré), bascule sur un résumé Gemini Flash ≤120 mots caché dans le JSON (`resume_summary` + `resume_summary_at`). Le tag `[résumé]` apparaît alors dans `sessionInfo` à la reprise.

Avant Phase A.8.6 le résumé se déclenchait dès 6 h d'inactivité + 10 tours, ce qui faisait perdre le contexte fin (notes, points abordés) au moindre passage de nuit. Le coût en tokens d'un replay quasi-systématique a été validé explicitement.

**Auto-restore au Ctrl+F5** : le backend garde la session active in-memory ; au boot du front, `GET /api/current_session` permet de restaurer le dialogue (transcript + mode + slide guidée à l'index courant) sans perdre la progression. Sur claude.ai, l'historique de conversation existe mais sans la structure (matière, exo, phase) ni la reprise propre via résumé adaptatif.

**Suppression, édition et branching de messages** (style Gemini AI Studio + ChatGPT) : boutons ✏ et 🗑 visibles au hover sur chaque bulle (toi ou Compagnon).
- 🗑 → `DELETE /api/messages/<index>` retire l'entrée du transcript ET du `_history` du `ClaudeClient`. Au prochain message, le tuteur n'a plus le souvenir de l'échange supprimé.
- ✏ → la bulle devient un textarea pré-rempli avec **deux boutons de save** :
  - **Modifier** → `PATCH /api/messages/<index>` édition in-place (l'ancien contenu est perdu). Le tuteur reçoit une **note système préfixée** dans son `_history` (« ce message a été édité » / « cette réponse a été éditée manuellement »), ce qui lui permet de garder la cohérence si tu trolles ou corriges ta formulation. Petit `(modifié)` à côté du label.
  - **+ Branche** → `PATCH ?as_branch=true` crée une **nouvelle branche** dans le graphe de messages : l'original reste accessible, le `current_branch_path` bascule sur la nouvelle version. Sous chaque message qui a plusieurs versions s'affichent des flèches **‹ N/M ›** pour switcher (POST `/api/messages/<id>/switch` reconstruit le `_history` selon la branche choisie).

**Modèle de données arborescent** : chaque message a un `id` + `parent_id` (None pour racine). `current_branch_path` est la liste ordonnée des ids du chemin actif. `transcript` est dérivé de ce chemin pour rétrocompat. Migration douce des sessions legacy (modèle plat) au load. Toutes les branches sont conservées dans le JSON, utile pour explorer pédagogiquement deux façons de poser la même question et comparer les réponses du tuteur.

### 8. Sidebar à onglets + markers de transition slide visibles

Refonte de la sidebar en **grid layout 4-rows** (Phase A.7.2 v11) pour résoudre l'écrasement quand on accumule beaucoup de panneaux :
- **Row 1** : `#guided-panel` (slide preview + counter + nav prev/jump/next), toujours visible en haut, ne scrolle pas
- **Row 2** : **rail vertical** à 44 px (Phase A.10.4, refonte VSCode-style). Onglets `📊 Quota / 📚 Docs / 🔖 Notes / 📸 Photos / 📌 Consignes / 💬 Historique / 🔗 Distant / 🎓 Astuces`. Tooltip natif au hover, label dans le `<h2>` du pane actif. Le rail scale linéairement à 15-20 onglets sans souci d'espace (versus les 3 tentatives échouées en horizontal A.10.1 → A.10.3).
- **Row 3** : contenu de l'onglet actif (`.sb-pane[data-pane=...]`), scrollable, prend tout l'espace disponible
- **Row 4** : `#sidebar-footer` avec `record-indicator` + bouton « Terminer la séance » : sticky en bas

L'historique a maintenant tout l'espace qu'il faut pour lister les sessions sans être écrasé par les autres panneaux.

**Onglet « 📚 Docs »** (Phase A.7.2 v15+), disponible dans **tous les modes** (colle/lecture/guidé), pas juste guidé :
- Affiche page-par-page **trois sources** : l'**énoncé** (`find_enonce_pdf`), les **corrigés** officiels (`resolve_corrections`), le **script imprimable** (`script_imprimable_*.pdf` issu de `run_script_oral.py`).
- Picker dropdown si plusieurs documents (« Énoncé : Énoncé, 2 pages », « Corrigé : Toutes les corrections, 5 pages », « Script : Script imprimable, 12 pages »). **Mémoire de page par doc** (Phase v15.7, refacto centralisée dans `showCorrige`) : page 5 du script → switch vers énoncé → finir → retour script = page 5, pas page 1. Marche pour tous les couples de docs.
- **Marker de position cliquable** (Phase v15.7) : quand tu tournes les pages du panneau Docs, un marker `📄 Page X/Y du <kind> « <label> »` apparaît dans le stream après une pause de navigation (debounce 1.5 s, dédup pour ne pas spammer). Click sur le marker → retour à cette position dans le panneau. Sert de repère temporel pour retrouver « qu'est-ce que je regardais quand j'ai posé telle question ». Local frontend, pas envoyé à Claude.
- Boutons ⬅/🎯/➡ pour navigation, click image → lightbox plein écran.
- **Raccourcis ←/→** quand l'onglet est actif (priorité sur la nav slide en mode guidé : la flèche actionne ce qui est sous les yeux).
- **Pré-rasterisation au boot** : `_kickoff_corrige_prerasterize` lance un thread daemon à `start_session`/`resume_session`. 1ʳᵉ ouverture du panneau = instantanée.
- **Just-in-time reading state** : quand tu envoies un message au tuteur ET que cet onglet est actif, le backend prefixe une ligne `[Contexte lecture actuelle : l'étudiant consulte la page X/Y du <kind> « <label> »]` au texte. Le tuteur sait ce que tu as sous les yeux sans qu'on lui balance une note à chaque flip de page (canal de tracking propre, zéro pollution d'historique).
- **Refs `page N du corrigé/script/énoncé` cliquables** dans les bulles tuteur : regex post-stream → liens qui ouvrent l'onglet et sautent à la bonne page.
- **Tuteur prend le contrôle** (Phase v15.1) : en mode guidé avec auto-advance opt-in, le tuteur peut émettre `<<<SHOW_DOC>>>{"kind":"enonce|correction|script","page":N}<<<END>>>` pour pointer une page précise. Le panneau s'ouvre, saute à la page, et une bulle système `🤖 Le tuteur affiche la page X/Y du <kind>` apparaît pour traçabilité. Sans le flag opt-in, le tuteur se contente de citer la page dans le texte (rendu cliquable côté UI).

**Modal « session existante détectée »** (Phase A.7.2 v15) : au clic Lancer, si une session pour `(matiere, type, num, exo, annee)` existe déjà : trois choix → ✅ Reprendre / 🔄 Démarrer une nouvelle (l'ancienne sera supprimée) / ↩ Annuler. Évite l'écrasement silencieux quand tu reviens sur un exo le lendemain.

**Bouton 📋 Copier** sur les bulles student/claude, à côté de ✏ et 🗑. Copie le texte brut du message dans le presse-papier (avec fallback `execCommand` pour les contextes non-secure). Feedback visuel ✓ vert 1.2 s.

**Markers de transition slide avec distinction user/tuteur** : chaque changement de slide inscrit dans la conversation une bulle discrète, **différenciée selon qui a fait l'action** :

- **Toi** (clic ⬅/➡/🎯) → 👉 *« L'étudiant est passé à la slide 3/12 : Karnaugh sortie a »* (bulle verte)
- **Tuteur** (`<<<NEXT_SLIDE>>>` / `<<<GOTO_SLIDE>>>`) → 🤖 *« Le tuteur a fait avancer à la slide 4/12 : De Morgan »* (bulle bleu clair)

Détecté côté front via le préfixe `[Mode guidé]` + reconnaissance « Le tuteur » → classes `.turn.marker.marker-user` ou `.marker-tutor`. Rendu compact (italic, icône à gauche, fond pâle, pas d'avatar role). **Visible des deux côtés** : étudiant + tuteur, les deux ont le contexte de la transition **et** savent qui l'a déclenchée. Le tuteur s'en sert pour ajuster sa réaction : si le user a cliqué manuellement sans lire, le tuteur ne commente pas le contenu (l'étudiant n'a peut-être pas eu le temps de lire). Persisté dans le transcript backend → restauré au F5 ou à la reprise de session.

**Garde-fou anti-cascade** : cooldown front 5s après chaque transition auto + règle inviolable dans `_prompts/PROMPT_SYSTEME_GUIDE.md` §2.9 qui interdit au tuteur d'émettre une transition en réponse au meta-message d'arrivée. Évite que plusieurs slides défilent sans que l'étudiant ait le temps de lire.

**Garde-fou anti-anticipation** : le meta d'arrivée envoyé au tuteur dit explicitement *« L'étudiant vient juste d'arriver sur la slide N/M. Il N'A PAS ENCORE LU le contenu, il commence sa lecture maintenant. »* (sans injection du `oral_excerpt`, qui faisait croire au tuteur que l'étudiant avait déjà récité). Le prompt §2.9 interdit explicitement (1) de commenter le contenu d'une slide qui vient d'apparaître, (2) d'émettre une balise transition, (3) d'annoncer la slide N+1. Deux options légitimes seulement : « Allez-y, lisez. » ou 1 phrase d'accroche utile sur un piège classique.

**Suppression d'un marker = retour slide précédente** : sur chaque marker de transition, un bouton 🗑 apparaît au hover. Click → confirmation « Supprimer cette transition et revenir à la slide précédente ? » → backend détecte le marker via préfixe `[Mode guidé]`, parse le numéro de slide via regex, recule `guided_index` à la slide indiquée par le marker antérieur (ou 0 si aucun). Le panneau guidé recule visuellement en synchro. **Cohérence garantie** : pas d'état orphelin où le transcript dit « passé à slide 2 » mais le panneau montre la 5.

**Auto-navigation opt-in via bouton sidebar** : le tuteur ne fait **pas** avancer la slide de lui-même par défaut (mode prévisible le plus stable). Si tu veux le mode auto, click **« 🤖 Activer auto-nav »** dans le panneau guidé sidebar : un message synthétique `[Note système : auto-advance activé]` est injecté dans le `_history` du tuteur, qui peut alors émettre `<<<NEXT_SLIDE>>>`. Si en cours il oublie d'émettre la balise plusieurs tours d'affilée, le bouton bascule en **« 🤖 Rappeler nav au tuteur »** pour réinjecter le rappel. Une bulle système traçable apparaît dans la conv à chaque activation/rappel.

**Timer adaptatif du « Compagnon réfléchit »** : couleur change selon la durée d'attente (neutre 0-30s, jaune 30-60s « anormalement long », orange 60-120s « peut-être bloqué », rouge pulsé 120s+ « probablement bloqué, Stop+Lancer »). Visuellement explicite quand la latence Claude est anormale.

### 9. Pièces jointes multi-canal : page mobile, paste, drag & drop, crop

Cinq sources convergent vers la même file d'attente backend (`pending_attachments`) :
- **Page mobile `/mobile`** : prend le téléphone, ouvre `http://<PC-tailscale-ip>:5680/mobile`, bookmark sur l'écran d'accueil. Bouton 📷 ouvre la caméra système (multi-shoot supporté). Chaque photo est uploadée direct sur le PC, visible dans le bandeau du dialogue desktop en moins de 2s. Tu prends la photo, tu reposes le téléphone, tu retournes au PC, tu écris/dictes ton commentaire, tu envoies, tout en un.
- **Paste clipboard (Ctrl+V)** : si tu Ctrl+C une image dans n'importe quelle app et Ctrl+V dans le navigateur du Compagnon, l'image part directement dans la queue.
- **Drag & drop** : tu drops un fichier (image, PDF, Excel, .csv, .docx, .pptx, .txt…) n'importe où sur la fenêtre, un overlay « 📎 Déposez le fichier pour le joindre » apparaît, et le fichier est uploadé.
- **Bouton 📎** : file picker générique (tous types).
- **Bouton 📷 Photo** *(Phase v15.7.10)* : à côté de 📎, dédié aux photos. Comportement adaptatif :
  - Sur **mobile** (touch + viewport < 900px) → ouvre directement la caméra arrière native via `<input capture="environment">`.
  - Sur **desktop** → bascule sur l'onglet sidebar `🔗 Distant` et le **scintille** (3 pulses oranges, comme `flashEngineSwitcher`), avec une bannière hint orange au-dessus du tray : *« Scanne le QR ou ouvre l'URL Tailscale sur ton téléphone pour prendre une photo »*. Pas de webcam desktop : en révision papier, le cahier n'est pas devant le laptop.

**Bandeau d'attachements** au-dessus du champ d'input : thumbnails des images, icônes pour les autres (📕 PDF, 📊 Excel/CSV, 📽 PowerPoint, etc.) avec nom + taille. ✂ Rogner (images uniquement) et 🗑 Retirer sur chaque. Au clic Envoyer, les paths sont injectés dans le message :
- Images → markdown `![nom](path)` rendu inline + vu par le tuteur multimodal
- PDF/Excel/autres → mention `[Pièce jointe : nom, chemin]` que le tuteur peut Read en mode guidé pour examiner le contenu

Tu peux aussi **envoyer une photo seule** sans rien taper *(Phase v15.7.8)* : la bulle student affichera juste l'image, et le tuteur la commentera directement.

#### ✂ Rogner avant envoi (Phase v15.7.10)

Bouton ✂ dans chaque thumbnail image du tray (et dans chaque entrée image de `/mobile`) → ouvre une **modal Cropper.js** (v1.6.2 vendoré localement, MIT, ~37 KB JS + 4 KB CSS). Tu **glisses sur l'image** pour redessiner la zone (Phase v15.7.16, `dragMode: "crop"`), ou tu attrapes les handles aux coins/bords pour ajuster (handles 18-22 px sur mobile/touch, vs 5×5 par défaut Cropper). 2 boutons **`↺ 90°` / `↻ 90°`** pour pivoter (utile quand tu prends une photo de travers et que l'EXIF est faux). Click `✂ Recadrer & remplacer` → la photo est cropped (max 2000×2000, JPEG 0.92), uploadée via `POST /api/pending_attachments/<id>/replace`, l'entry est mutée en place avec un nouveau `rel_path` suffixe `_cropped_vN`. L'ancien fichier est préservé sur disque (audit / undo manuel).

**Pourquoi** : la photo brute contient souvent table+mug+bordel autour de la table de vérité utile → bruit pour le tuteur multimodal et tokens gaspillés. Crop = la photo ne contient que ce qui sert à la correction. Sur `/mobile`, modal plein écran touch-first.

Polling 2s côté desktop pour rester en sync avec ce qui arrive du téléphone. Depuis la Phase A.10.2 (2026-05-14), tout est sauvegardé dans `Compagnon_Revision/_uploads/{session_id}/{photos|attachments}/` (un dossier par session), avec versioning automatique `_vN` (et `_cropped_vN` pour les versions recadrées) pour ne jamais écraser. Les **anciennes sessions** (pré-A.10.2) gardent leurs photos sous `COURS/{MAT}/{TYPE}/{TYPE}{N}/photos/` (la galerie les retrouve via le backfill A.10.1 qui scanne le transcript). Friction d'origine : les sessions Sujet libre / Workspace n'ont rien à voir avec COURS/, c'était incohérent d'y stocker leurs photos.

#### OCR pré-vérifié par Gemini Flash 2.5 (Phase v15.7.20)

Quand tu envoies une photo en mode colle avec `colle_format ∈ {photos, mixte}`, le backend fait **automatiquement** un OCR pré-traité par **Gemini Flash 2.5** AVANT que le tuteur principal ne la voie. Pourquoi : le tuteur principal (souvent Claude Opus / CLI subscription) est excellent pour le raisonnement pédagogique mais peut halluciner sur des objets structurés partiellement remplis (cas EN1 CC2 où le tuteur a validé une table avec colonne S vide, cf. v15.7.19).

**Workflow** :
1. Tu envoies ta photo (avec ou sans texte).
2. Backend lance `/api/ocr_photo` interne → Gemini Flash 2.5 OCR la photo case par case avec marqueurs `(vide)` / `(illisible)` / `(raturé)` (~1-2s).
3. L'OCR est **injecté** dans le contexte du tuteur principal (« [OCR pré-traitée par Gemini Flash 2.5, vérifie qu'elle correspond à ta lecture, sinon dis-le et signale la divergence] : … »).
4. Le tuteur fait sa propre lecture multimodale ET compare avec celle de Gemini. Si désaccord = signal explicite à l'étudiant.
5. **Tu vois aussi l'OCR** dans un bloc collapsible `<details>` sous ta bulle student : `🔍 OCR pré-vérifié par Gemini Flash · type · complétude X% · ⚠ N warnings`. Auto-ouvert si warnings ou completeness < 80%. Si l'OCR Gemini te paraît erroné, tu le signales au Compagnon dans ton prochain message.

**Choix de Gemini Flash forcé** : mêmes raisons que pour `/api/refine_search_query` (cf. v15.7.14) : latence ~1-2s, coût ~$0.0001-0.0005 par photo (négligeable), cohérence cross-engine. Gemini 2.5 Flash a une réputation solide en OCR multimodal sur écriture manuscrite.

**Double check par 2 LLM indépendants** = robustesse réelle. Si Gemini Flash hallucine aussi (rare), le tuteur principal le contredit dans sa réponse. Si les 2 sont d'accord → très haute confiance.

**Mode dégradé gracieux** : si `GEMINI_API_KEY` absente ou Gemini en panne, le bloc OCR est juste absent du message envoyé au tuteur (qui continue de voir l'image en multimodal natif depuis v15.7.18).

#### Bouton ⏹ Annuler la réflexion en cours (Phase v15.7.21)

Pendant que le Compagnon réfléchit (entre l'envoi de ton message et la fin de sa réponse), le bouton **Envoyer** se transforme en **`⏹ Annuler`** (rouge pulsant). Click → modal avec 3 options :

- **↩ Reprendre (garder mon message)** : annule juste le stream LLM en cours. Ton message reste dans le transcript, tu peux soit attendre que le tuteur reparte sur ce contexte (relance manuelle si besoin), soit lui envoyer un nouveau message.
- **🗑 Supprimer mon message** : annule + retire ton dernier message du transcript et de l'historique du tuteur. « Comme si tu n'avais rien envoyé. » Utile quand tu réalises que tu as posé une mauvaise question, ou que tu as envoyé une photo de travers.
- **← Retour (continuer la réflexion)** : ferme la modal sans rien annuler. Click outside = same. Garde-fou si tu as cliqué par erreur.

**Limite assumée** : le sub-process LLM (Claude CLI / Anthropic API / Gemini / etc.) peut continuer à tourner quelques secondes en background après ton click. Tes tokens sont consommés sur ce tour quoi qu'il arrive : on n'a pas implémenté de `subprocess.kill()` par moteur (compromis simplicité). L'important est que tu vois l'arrêt immédiatement côté UI et que tu puisses reprendre proprement sans bulle Compagnon orpheline.

Distinct du **Stop end-session** (qui termine la séance entière) : c'est juste annuler le tour courant.

#### LaTeX rendu sur les bulles student (Phase v15.7.20)

Si tu postes du LaTeX dans ta réponse (`$f(x) = x^2$`, `$\sum_{i=1}^n i$`, etc.), c'est désormais rendu via KaTeX comme dans les bulles Compagnon. Avant : seules les bulles Compagnon passaient par `renderMathIn`, l'étudiant qui postait du LaTeX voyait le markdown brut au re-render.

#### Comment chaque moteur voit les photos (Phase v15.7.18)

Quand tu envoies un message qui contient une image, le backend la transforme automatiquement au format multimodal natif du moteur courant : le tuteur la voit comme une vraie image, pas comme un chemin de fichier en texte.

| Moteur | Format envoyé | Vision | Notes |
|---|---|---|---|
| **CLI subscription** (`claude --print`) | Tool `Read` ouvert sur `COURS/` (mode colle limité à Read seul, mode guidé Read+Grep+Glob) | ✅ | Phase v15.7.17 |
| **Anthropic API** | `[{type:text}, {type:image, source:{type:base64, media_type, data}}]` | ✅ | Toutes versions Claude actuelles |
| **Gemini API** | `[{text}, {inline_data:{mime_type, data: bytes}}]` | ✅ | Gemini 1.5+ |
| **DeepSeek API** (`deepseek-chat` V3) | `[{type:text}, {type:image_url, image_url:{url:"data:image/jpeg;base64,..."}}]` | ❌ text-only | Le serveur ignore silencieusement. Pour vision : pas dispo chez DeepSeek aujourd'hui. |
| **Groq API** (`llama-3.3-70b-versatile` défaut) | Pareil OpenAI-compat | ❌ text-only | Pour vision : `$env:GROQ_MODEL = "llama-vision-..."` puis relance. |

Caps : 5 MB max par image (cap raisonnable photo téléphone HD), extensions JPEG/PNG/GIF/WebP/HEIC. Les images plus grandes ou format non supporté sont skip silencieusement avec log warning et un placeholder `[image trop grande: nom]` dans le texte que le tuteur reçoit.

### 10. TTS avec player avancé (play/pause/scrub/speed/voix) sur chaque bulle Compagnon

Click sur 🔊 dans `.turn-actions` d'une bulle Compagnon (au hover) → un mini-player audio apparaît sous la bulle avec :
- **▶/⏸ Play/Pause**
- **Timeline scrubbable** (curseur draggable, position courante / durée totale en `m:ss`)
- **Sélecteur de vitesse** : `0.5×`, `0.75×, 1×, 1.25×, 1.5×, 1.75×, 2×` (mémorisé en `localStorage`)
- **Sélecteur de voix** française : Denise (femme neutre), Henri (homme posé), Alain (homme mature), Brigitte (femme dynamique). Changer la voix en cours déclenche une re-synthèse
- **✕ Fermer le player** (libère le blob URL)

Backend : `/api/tts/synthesize` utilise [`edge-tts`](https://github.com/rany2/edge-tts), wrapper Python de l'API gratuite Microsoft Read Aloud (~270 voix Neural sans clé API requise). Cache MP3 sur disque (`_cache/tts/<sha1(voice+text)>.mp3`) : la même phrase n'est synthétisée qu'une fois.

Le texte envoyé au TTS est nettoyé du markdown (formules LaTeX → « (formule) », blocs code → « (bloc de code) », gras/italique strippés, balises `<<<...>>>` retirées) pour éviter que la voix prononce « dollar f de x dollar » au lieu de la formule.

Sur claude.ai et ChatGPT, le TTS existe (lecture seule) mais sans **scrubbing** ni sélection de **vitesse fine** ni choix de **voix**. Compagnon fournit l'expérience d'un vrai lecteur audio sur chaque réponse, comme un podcast scrubbable.

### 11. Sélecteur de moteur dans la nav, synchro GUI Tkinter

Bouton dans le header pour basculer le moteur (CLI Claude subscription / API Anthropic / Gemini / DeepSeek / Groq selon clés présentes) **à chaud sans interrompre la session**. La pref est persistée dans `_secrets/engine_pref.json` qui est aussi lu par la GUI Tkinter, donc tout changement côté navigateur est reflété au prochain démarrage tray, et inversement. Endpoint `POST /api/switch_engine` (session active) ou `POST /api/switch_engine_pref` (sans session). Sur claude.ai tu choisis le modèle dans la sidebar de conversation, mais sans synchro avec un autre runtime ; sur Cowork, le choix de moteur est fixé au démarrage de l'agent.

---

**Quand utiliser quoi** : pour de la révision active régulière sur 6 mois jusqu'aux CC3, le pipeline structuré du Compagnon économise des dizaines de copier-coller par semaine et fournit un cadre (session structurée, débrief, reprise propre) qu'aucun chat web ne donne. Pour des questions ponctuelles ou quand le quota Compagnon est cuit, claude.ai ou Cowork avec les prompts adaptés (`_prompts_claude_ai/`, `_prompts_claude_cowork/`) sont des replis acceptables : la posture pédagogique tient, mais le débrief structuré et l'auto-advance disparaissent.

---

## Limites du prompt engineering : comment les gommer (les 3 phases)

> Cette section sert de **doc pédagogique** pour expliquer pourquoi un prompt
> seul ne suffit pas en production, et quelles sont les 3 stratégies cumulatives
> que le projet utilise pour réduire le biais aléatoire des LLM. À garder à
> l'esprit pour quiconque écrit des produits LLM en 2026.

### Le problème de fond

Un LLM qui reçoit un long prompt système avec des règles en prose ne « suit » pas
ces règles comme un programme exécute des instructions. Il **prédit** le token
suivant statistiquement. Conséquence :

- **Ricochet** : si tu écris dans le prompt « ne JAMAIS dire X », tu augmentes
  paradoxalement la probabilité que X apparaisse dans la sortie (le pattern X est
  saillant dans le contexte).
- **Récitation** : des phrases-signatures du prompt (« RÈGLE INVIOLABLE »,
  « Cas réel à NE JAMAIS reproduire ») sont parfois recopiées textuellement
  dans la réponse.
- **Role hijacking** : si tu donnes des exemples sous forme `> Bon exemple : …`,
  le modèle prend le pattern pour un template et invente des dialogues simulés
  `USER: … ASSISTANT: …`.
- **Hétérogénéité entre modèles** : un prompt qui marche sur Claude Opus 4.7 ne
  donne pas le même résultat sur Gemini 2.5 Pro ou DeepSeek V3. Plus le prompt
  est verbeux, plus l'écart explose.
- **Variance d'un appel à l'autre** : à température > 0, le même prompt sur le
  même modèle donne 2 réponses différentes. À température 0, c'est plus stable
  mais pas déterministe (ordre des tokens, batching, GPU non-déterministe).

Le prompt engineering pur a donc des limites structurelles. Voici les **3
stratégies cumulatives** qu'on a implémentées pour gommer (partiellement) le
biais aléatoire.

---

### Phase 1 : Rails déterministes côté code

**Principe** : tout ce qui peut être garanti par code, ne le mets jamais dans le
prompt. C'est la couche la plus efficace, parce qu'elle ne dépend pas du modèle.

**Implémentation Compagnon** :

- `_scripts/dialogue/output_filters.py` : 4 filtres post-stream qui retirent les
  dérives connues **avant** stockage dans le transcript et avant injection dans
  le `_history` du prochain tour :
  - `strip_role_hijacking` retire les lignes qui commencent par `USER:`,
    `ASSISTANT:`, `AI:`, `HUMAN:`, `ÉTUDIANT:`, `TUTEUR:` (case-insensitive)
    **+ détection inline** (ex: `**USER: Slide 2…**` au milieu d'un paragraphe
    si le tuteur dérape en cours de bulle, on coupe à partir de la 1ʳᵉ
    occurrence avec lookbehind `(?<![A-Za-zÀ-ÿ])` pour préserver les vrais
    mots comme « DOSSIER: » ou « POSEUR: »).
  - `strip_recited_rules` retire les paragraphes qui contiennent des
    phrases-signatures du prompt système (« RÈGLE INVIOLABLE »,
    « Cas réel à NE JAMAIS reproduire », « [Note système : », etc.).
  - `strip_misplaced_next_slide` garde uniquement la balise `<<<NEXT_SLIDE>>>`
    finale et retire les occurrences au milieu d'un paragraphe.
  - `_capitalize_first_letter` (cosmétique post-filtrage) : si le filtrage a
    fait perdre la majuscule initiale (ex: « nouvelle slide à l'écran » après
    coupe d'un préfixe), capitalise la 1ʳᵉ lettre. Skip chiffres / ponctuation
    / markdown / emoji pour préserver les cas légitimes (`f(x) = …`).
- **Event SSE `final_text`** : le filtre s'applique côté backend après le
  streaming complet. Pour que l'utilisateur ne reste pas avec la version brute
  à l'écran, un event SSE pousse le texte filtré au front qui remplace
  `currentClaudeTurn.innerHTML` en live. Si le filtrage a tout coupé (le
  tuteur a dérivé d'emblée), affiche un marker discret « ⚠ Réponse filtrée
  (dérive détectée). Réessayez via 🔄 Recharger contexte. » au lieu d'une
  bulle vide.
- **Auto-injection NEXT_SLIDE** : si le tuteur écrit une phrase qui annonce
  une transition (« on passe à la slide suivante », « on enchaîne sur la
  slide N+1 ») mais oublie la balise `<<<NEXT_SLIDE>>>`, le backend détecte
  via 4 patterns regex et auto-injecte un `ParserEvent NEXT_SLIDE` dans la
  queue. Le front avance comme si la balise avait été émise. Heuristique
  conservative : seulement les patterns nets d'intention d'avance.
- Garde-fous JS dans `_scripts/web/static/app.js` :
  - Flag `respondingToSlideMeta` qui bloque toutes les transitions de slide
    pendant que le tuteur stream sa réponse à un meta d'arrivée. Évite les
    cascades multi-tour.
  - Cooldown 5s temporel entre transitions auto.
  - Détection des répétitions Whisper (regex 1-4 mots × 5+ → banner « nettoyer »).
- Eval suite manuelle : `tests/eval_prompt.md` (20 scénarios à passer avant) à passer avant
  chaque modif de prompt (S1 à S20). Métrique : ≥ 18/20 pour push.

**Effet** : la dérive du modèle ne se propage pas (le _history nettoyé n'amorce
pas la dérive du tour suivant). Tests unitaires dans
`tests/test_output_filters.py` (22 cas).

---

### Phase 2 : Tool calling natif au lieu de balises texte

**Principe** : au lieu de demander au modèle d'écrire des balises texte
(`<<<NEXT_SLIDE>>>`, `<<<SUGGESTED_EDIT>>>{…}<<<END>>>`), on lui expose des **tools**
(fonctions) avec schémas JSON validés côté server. Le modèle DOIT respecter le
schéma sinon le serveur rejette. C'est l'équivalent d'un type-checker au runtime
LLM.

**Pourquoi c'est mieux** :

- Pas de risque de récitation textuelle de la balise dans la réponse.
- Pas de risque de parsing partiel sur stream (les tool calls arrivent comme
  blocs structurés, pas comme du texte à extraire).
- Format homogène entre fournisseurs après une couche d'adaptation.
- Validation JSON Schema côté server (exemple : `goto_slide` exige un champ
  `n: integer >= 1`, impossible d'envoyer une string).

**Implémentation Compagnon** :

- `_scripts/dialogue/tool_schemas.py` : 3 tools (`next_slide`, `goto_slide`,
  `suggest_edit`) en 3 formats :
  - `ANTHROPIC_TOOLS` (format Anthropic native)
  - `get_gemini_function_declarations()` (Gemini)
  - `get_openai_compat_tools()` (OpenAI / DeepSeek / Groq)
- Helper `tool_call_to_payload(name, input)` qui synthétise un `ParserEvent`
  comme si la balise texte avait été émise : le pipeline `app.py` reste
  inchangé.
- Helper `tune_prompt_for_engine(prompt, engine)` : passe-plat pour
  Claude Opus, préfixe court anti-récitation pour Gemini / OpenAI-compat
  (qui tolèrent moins le verbeux).
- Branchement dans `claude_client.py._stream_via_api` (Anthropic) avec flag
  `_enable_native_tools` (off par défaut, à activer via `runtime_settings.json`
  quand testé).

**Limite Compagnon** : le moteur `cli_subscription` (mode gratuit Claude Pro Max
qui appelle `claude --print`) **ne supporte pas** les custom tools. Donc on
garde les balises texte pour ce mode + les filtres de Phase 1. Pour les modes
API (`api_anthropic`, `gemini_api`, `deepseek_api`, `groq_api`), tool calling
peut être activé.

Tests unitaires : `tests/test_tool_calling.py` (25 cas, mocks pour les blocks
Anthropic).

**État actuel** : code branché mais flag `enable_native_tools = False` par
défaut. Activation runtime à faire après test sur un mode API.

---

### Phase 3 : DSPy : compiler les prompts au lieu de les écrire

**Principe** : au lieu d'écrire un prompt en prose et d'espérer que le modèle le
suive, on **décrit la signature** (input fields → output fields + description du
comportement attendu) et le framework DSPy se charge de trouver la formulation
qui maximise un score sur un dataset d'évaluation.

C'est l'équivalent d'un **compilateur** pour prompts : input = ta signature +
ton dataset, output = un prompt optimisé reproductible.

**Pourquoi c'est révolutionnaire** :

- Plus de prose floue qui dérive selon le modèle.
- Tu peux **changer de modèle** (Claude → Gemini) et recompiler sans réécrire
  le prompt à la main : le compilateur retrouve la formulation optimale pour
  le nouveau modèle.
- Tu mesures objectivement la qualité (metric → score 0-1) au lieu d'évaluer
  à l'œil.
- Le module compilé est **sérialisable** (`.save()` / `.load()`) → pas de
  recompilation à chaque démarrage.

**Implémentation Compagnon (PoC)** :

- `_scripts/dialogue/dspy_compiler.py` :
  - 2 `Signature` DSPy : `RespondToSlideMeta` (input : index/total/title,
    output : response) et `RespondToStudentReading` (input : title/expected/
    student_reading, output : response + should_advance: bool).
  - Module `GuidedTutor` qui orchestre les 2 signatures via
    `dspy.Predict(...)`.
  - Dataset PoC : 5 exemples de meta-arrival + 3 exemples de reading
    (positifs/négatifs) tirés de `tests/eval_prompt.md`.
  - Metric `tutor_response_metric` qui scored 0-1 selon les filtres
    `output_filters` + checks longueur + checks balise position. C'est une
    metric **déterministe** : pas besoin d'un LLM pour évaluer la qualité,
    on utilise les rails de Phase 1.
  - Helper `compile_guided_tutor(lm)` qui invoque `dspy.BootstrapFewShot`
    pour optimiser le module.

**Comment compiler en pratique** :

```python
import dspy
from dspy_compiler import compile_guided_tutor

# Configure le LM (n'importe quel modèle dspy supporte : OpenAI, Anthropic,
# Gemini, Ollama local, vLLM, etc.)
lm = dspy.LM("anthropic/claude-opus-4-7", max_tokens=2000)
dspy.configure(lm=lm)

# Compile (peut prendre 10-30 minutes selon dataset size + LM speed)
compiled = compile_guided_tutor(lm=lm)

# Sauve le module compilé
compiled.save("compiled_guided_tutor.json")

# En runtime : recharge sans recompiler
from dspy_compiler import GuidedTutor
runtime_tutor = GuidedTutor()
runtime_tutor.load("compiled_guided_tutor.json")
prediction = runtime_tutor.on_slide_arrival(slide_index=2, slide_total=12, slide_title="Karnaugh")
```

**Limite Compagnon** : la compilation effective demande un LM configuré et
**plusieurs appels** (le compilateur teste différentes formulations et
few-shots). Coût : modéré sur Claude Opus / Gemini Pro, gratuit avec
Ollama local mais qualité moindre. Pour le déploiement public, on peut
compiler une fois en dev avec un bon LM, sérialiser, et déployer le module
compilé qui fonctionne ensuite avec n'importe quel LM.

Tests unitaires : `tests/test_dspy_compiler.py` (13 cas, sans appel LM
réel : valide signatures, dataset, metric).

**État actuel** : PoC fonctionnel, module instanciable, metric testée. La
compilation effective sera faite quand un LM gratuit sera disponible
(Ollama local ou Gemini free tier).

---

### Récap des 3 phases

| Phase | Outil | Force principale | Quand l'utiliser |
|---|---|---|---|
| **1. Rails déterministes** | `output_filters.py`, garde-fous JS | Indépendant du modèle, marche partout | Toujours, c'est la base |
| **2. Tool calling natif** | `tool_schemas.py` | Validation JSON server-side, format homogène | Quand le moteur supporte (API Anthropic/Gemini/OpenAI/etc.) |
| **3. DSPy compilation** | `dspy_compiler.py` | Optimisation automatique du prompt | Quand on a un dataset d'évals représentatif et un LM compileur |

Les 3 phases sont **cumulables**. Le projet utilise actuellement Phase 1 en
runtime + Phase 2 codée mais désactivée (flag `enable_native_tools=False` par
défaut, activable per-engine) + Phase 3 en PoC (signatures et metric prêtes,
compilation à faire quand LM dispo).

**Pour le déploiement public futur**, l'objectif est :
- Phase 1 toujours active (cheap insurance).
- Phase 2 activée pour les utilisateurs qui choisissent un mode API.
- Phase 3 compilée une fois en dev, embarquée dans le repo, rechargeable
  sans recompiler.

C'est l'évolution naturelle du prompt engineering en 2025-2026 :
**du prompt artisanal vers le prompt programmé**.

---

## Lancer une session

### Méthode recommandée : GUI (Phase A.6)

**Double-clic sur `start_gui.vbs`** (lanceur silencieux Windows). Ça ouvre une fenêtre Tkinter (depuis l'harmonisation du 2026-07-02, elle porte le thème sombre ambre de l'application Cartable, comme le front web) avec :
- formulaire de lancement (matière, type, num, exo, année, flags), auto-persisté à chaque cascade dans `_secrets/gui_state.json`
- quota Pro Max live (4 barres + seuils session/hebdo éditables, **auto-save 500 ms** dans `_secrets/runtime_settings.json` ; bouton « 🔄 Recharger depuis disque » pour réimporter après édition manuelle du JSON)
- choix moteur (CLI subscription / API Anthropic) sauvegardé à la volée
- caps contexte modifiables (panneau « Avancé ») : limites de tokens injectés dans le prompt système (transcription CM, TACHE perso, corrigés cumulés). Réglables si une session sature le contexte. **Auto-save 500 ms** également, mais lus à la création du `PromptBuilder`, donc un changement prend effet au **prochain démarrage de session**, pas pendant.

Côté chat, entre clic « Lancer » / « Envoyer » et le 1ᵉʳ chunk de réponse Claude (3-15 s d'attente), une bulle **« 🤔 Compagnon réfléchit… X.X s »** avec timer s'affiche pour confirmer que ça travaille et n'est pas planté.
- liste des sessions reprenables, raccourcis dossiers (`_sessions/`, `_logs/`, `_secrets/`…)
- console embarquée qui tail le stdout du subprocess `compagnon.py`
- bouton Stop (CTRL_BREAK + hard-kill arbre après 5s si récalcitrant)

La GUI lance `compagnon.py` en sous-process avec les bons args, donc le fonctionnement runtime reste identique au mode terminal.

### Workflow de pré-révision (avant la colle)

Dans le panneau « ▶ Lancer une session », deux boutons à côté de **🔄 Rescan COURS** :

- **📖 Ouvrir script** : ouvre ton `script_oral_*.txt` (ou `SCRIPT_*.md`) dans l'éditeur natif du système (VS Code, Notepad++, ce qui est associé au `.md`/`.txt`).
- **📊 Ouvrir slides** : ouvre `slides_*.pdf` dans Acrobat / Edge / ton lecteur PDF.

Workflow type : tu sélectionnes la matière/type/num/exo, tu cliques les deux boutons, tu lis le script avec les slides à côté pendant 15-20 min pour te remettre en tête, puis tu cliques **▶ Lancer** pour la colle.

Note : le contenu des slides n'est **pas** envoyé à Claude (le prompt mentionne juste le chemin pour mémoire : extraction multimodale prévue Phase B+ si besoin). Ces deux boutons sont là pour TOI pendant la phase de lecture passive, pas pour Claude.

### Méthode terminal (toujours valable)

```powershell
cd C:\dev\CompagnonRevision
python compagnon.py AN1 TD 5 3
python compagnon.py EN1 CC 1 full --annee 2025-26
```

→ ouvre l'UI sur `http://127.0.0.1:5680/` dans une fenêtre applicative Edge (`--app`, sans barre de navigateur, comme l'application Cartable ; repli sur le navigateur par défaut si Edge est absent), Claude pose la première question.

### Depuis l'application Cartable (contenu droit)

L'application Cartable (`C:\dev\Cartable`, double-clic sur `Cartable.vbs`) sait lancer une séance de révision directement : bouton Réviser global (ouvre cette GUI) ou puce « 🧠 Réviser » sur une séance de sa bibliothèque (ouvre la colle sur ce CM/TD via `compagnon.py <slug> <CM|TD> <n> full --source droit --autostart`, ou par URL profonde si le serveur tourne déjà).

Arguments :
- **matière** : `AN1`, `EN1`, `PSI`, `ISE`, `PRG2`
- **type** : `TD`, `CC`, `Examen`
- **num** : numéro du TD/CC (ex : `5`)
- **exo** : numéro de l'exercice (ex : `3`) ou `full` pour toute la séance
- **`--annee 2025-26`** (CC multi-millésime) : sinon le resolver prend le dernier disponible

Depuis la **Phase A.5**, le serveur charge automatiquement dans le contexte initial de Claude :
- l'**énoncé PDF** (`COURS/{MAT}/{TYPE}/{TYPE}{N}/enonce_*.pdf`)
- le **corrigé officiel** (`corrections/correction_*.pdf`) : source de vérité, le prompt système oblige Claude à le consulter avant tout jugement
- la **TACHE perso** (`TACHE_*.md`)
- le **script oral perso** (`scripts_oraux/script_oral_*.txt`)
- mention des **slides** (chemin seulement)

Reprendre une session interrompue :
```powershell
python compagnon.py AN1 TD 5 3 --resume
```

---

## Accès distant : onglet « 🔗 Distant »

Le panneau **🔗 Distant** dans la sidebar du dialogue desktop (anciennement « Mobile ») liste **toutes les voies de connexion** à Compagnon depuis n'importe où (téléphone à la maison, PC à la fac, ordinateur public). Chaque ligne a un bouton « Copier l'URL ». Banner 🔐 en haut quand l'auth Basic est activée.

**Quatre canaux possibles** (tu peux en activer un, plusieurs, ou tous) :

### 1. WiFi LAN local : `http://192.168.1.X:5680/`

Téléphone/PC sur **le même WiFi** que la machine qui fait tourner Compagnon. Pas de setup. Limites : ne marche pas si tu changes de réseau (4G, hotspot fac, etc.).

Pas de chiffrement bout en bout : à éviter sur les WiFi publics. **Windows Defender** bloque ces connexions par défaut sauf si tu as autorisé Python lors d'une popup ; vérifie le pare-feu si tu travailles sur un réseau partagé.

### 2. Tailscale tailnet : `http://100.X.Y.Z:5680/`

[Tailscale](https://tailscale.com) crée un VPN privé entre tes machines. Marche depuis n'importe où (4G/5G/autre WiFi). Pas d'auth supplémentaire requise : l'auth est gérée par Tailscale lui-même (ta tailnet est privée par défaut).

**Setup téléphone** :
1. Sur le PC : Tailscale installé, log avec un compte (Google/GitHub/email). Le PC apparaît dans ta liste de machines avec une IP `100.x.x.x`.
2. Sur le téléphone : app Tailscale (Play Store / App Store), log **avec le même compte**. Toggle « Connect » → icône VPN dans la barre de notification.
3. Sur le téléphone : navigateur → `http://<PC-tailscale-ip>:5680/` (URL copiable depuis le panneau Distant). Bookmark sur l'écran d'accueil (menu ⋮ → « Ajouter à l'écran d'accueil »).

Avantages : marche partout, chiffrement bout en bout, ton PC reste isolé du LAN public. **Limite** : nécessite un client Tailscale installé sur la machine qui veut se connecter, pas possible sur les PCs de la fac où tu n'as pas droit d'installer.

### 3. Tailscale Funnel : URL publique `https://compagnon-<host>.tail<orgid>.ts.net`

Pour accéder depuis un PC où tu **ne peux pas installer Tailscale** (PC de la fac, café, etc.). Tailscale Funnel expose ton Compagnon local via une URL HTTPS publique stable. **Aucune install côté distant**, juste le navigateur.

**Setup en 5 min** : voir [`_remote_access/SETUP_TAILSCALE_FUNNEL.md`](_remote_access/SETUP_TAILSCALE_FUNNEL.md). Pas de domaine requis.

⚠️ Comme l'URL est publique, **active obligatoirement l'auth Basic** côté Compagnon (`_secrets/remote_access.json`, voir doc). Sans ça, n'importe qui qui devine ton URL accède à ton outil.

### 4. Cloudflare Tunnel : URL publique `https://compagnon.<ton-domaine>.fr`

La voie **long terme**, pour une URL propre sur ton domaine perso (`compagnon.gaylordaboeka.fr`). Couche d'auth **Cloudflare Access** (Google OAuth) **avant** que le trafic n'atteigne ton Flask. Bandwidth illimité.

**Pré-requis** : un domaine acheté (~10 €/an chez OVH/Gandi/Namecheap) délégué à Cloudflare DNS.

**Setup détaillé** : voir [`_remote_access/SETUP_CLOUDFLARE.md`](_remote_access/SETUP_CLOUDFLARE.md).

**Pourquoi c'est la voie long-terme** : c'est la **même brique** que pour le futur portfolio `gaylordaboeka.fr` (nom de domaine arbitré 2026-05-21). Un seul `cloudflared` peut servir `compagnon.gaylordaboeka.fr` (privé, avec Access), `arsenal.gaylordaboeka.fr`, et `gaylordaboeka.fr` lui-même (hub statique public sur Cloudflare Pages). Faire le setup maintenant pour Compagnon **paie deux fois**. Cf. § « 🌐 Présentation publique » plus bas.

### Mode viewer : partager une session sans risque (Phase v15.4)

Si tu veux donner un accès **lecture seule** à un ami (typiquement pour qu'il observe l'outil tourner sans pouvoir consommer ton quota ni modifier la session), configure une 2ᵉ paire `viewer_user` / `viewer_pass` dans `_secrets/remote_access.json` :

```json
"basic_auth": {
  "enabled": true,
  "user": "gstar", "pass": "<ta-pass-owner-privée>",
  "viewer_user": "invite", "viewer_pass": "<une-pass-viewer-séparée>"
}
```

Le viewer atterrit sur l'UI avec un banner 🔒 jaune, le form Lancer caché, l'input caché, les action buttons cachés. Polling auto toutes les 5 s pour voir tes nouveautés en direct. **Backend retourne 403** sur tous les endpoints qui muteraient l'état ou consommeraient ton quota : sécurité côté serveur, pas seulement masquage front. Détails complets : [`_remote_access/README.md` § Mode viewer](_remote_access/README.md).

### Auth Basic : protéger les URLs publiques

Pour les voies 3 et 4, le panneau Distant affiche un banner 🔐 quand l'auth Basic est activée côté Compagnon. Le navigateur demande user/pass au premier accès, puis garde le credential par session.

**Activation** : `_secrets/remote_access.json` (gitignored) :

```json
{
  "schema_version": 1,
  "basic_auth": {
    "enabled": true,
    "user": "gstar",
    "pass": "<passphrase générée>"
  },
  "public_urls": {
    "tailscale_funnel": "https://compagnon-tailxxxx.ts.net",
    "cloudflare_tunnel": "https://compagnon.gaylordaboeka.fr"
  }
}
```

**Skip auth pour 127.0.0.1/::1** : la GUI Tk locale et le navigateur sur le même PC ne sont pas embêtés. Tout autre IP doit s'authentifier. Comparaison constant-time via `hmac.compare_digest`.

Génération d'une passphrase solide :

```powershell
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

### Bottleneck connu : la connexion home

Tous les canaux distants partagent le **même goulot d'étranglement** : la bande passante upload de ta connexion maison. Le PC fixe envoie le contenu vers le tunnel (Tailscale/Cloudflare) qui le redistribue au client distant.

| Trafic | Volume | Sensibilité au bottleneck |
|---|---|---|
| Stream texte SSE (réponses Claude) | ~1-3 KB / tour | invisible même en 1 Mbps upload |
| PNG corrigé/script (init panneau Docs) | ~150-300 KB × N pages | visible : 5-15 s pour un PDF de 10 pages sur connexion lente |
| Upload audio Whisper (depuis le navigateur distant) | ~50-100 KB/s pendant l'enregistrement | sensible si ton **download** home est faible |
| Image jointe (.jpg téléphone) | 500 KB - 3 MB | sensible : 10-30 s |

**TeamViewer / RemoteDesktop seraient pires** : ils encodent l'écran complet en continu (~100-500 KB/s permanent). Compagnon ne pousse que les réponses Claude + 1 PNG à la fois. Beaucoup plus économe sur une mauvaise connexion home.

Optimisations possibles si bottleneck : réduire `dpi` dans `slides_rasterize.rasterize_correction` (150 → 96 DPI = 2× plus léger), cache HTTP côté navigateur sur les PNGs.

### `/mobile` : page spécifique téléphone (capture photo)

La page `/mobile` (ajoute `/mobile` à n'importe quelle URL ci-dessus) est dédiée à la capture rapide de photos depuis le téléphone vers la session active. UI simplifiée pour mobile, bouton 📷 qui ouvre la caméra système, photos uploadées en direct dans la file d'attente backend (`pending_attachments`).

Use case typique : tu prends une photo de ton brouillon papier, tu reposes le téléphone, tu retournes au PC, tu commentes au clavier, tu envoies, et la photo + le commentaire partent ensemble au tuteur.

---

## Mode vocal : bouton micro toggle (Phase A.6.2, révisé v15.6.2)

À gauche du champ de saisie, un **bouton 🎤**. Clic pour démarrer l'enregistrement (le bouton devient rouge pulsant ⏹). Deux raccourcis :

- **Entrée / clic Envoyer** = envoi direct. Le mic s'arrête tout seul, ce qui est dans l'input part tel quel (preview WebSpeech sur Chrome/Edge, ou texte tapé). Léger surcoût en tokens (~5-15 % de fillers « euh / donc / voilà » qui restent) mais sur quota Pro Max c'est invisible. Pratique quand tu es dans le flow.
- **Re-click 🎤 (⏹)** = annule juste le mic, garde le contenu courant de l'input. Pas d'attente de transcription Whisper canonique. Si la preview WebSpeech a des erreurs (ponctuation absente, mot mal compris), le bouton **✨ Améliorer** corrige tout ça en 1 click avant envoi.

L'enregistrement se fait via `MediaRecorder` côté navigateur (WebM/Opus). Whisper reste branché côté backend (`POST /api/transcribe` + lazy-load large-v3 ~5-10 s + 3 Go VRAM) au cas où on en aurait besoin pour des cas particuliers, mais le flow par défaut s'appuie sur la preview WebSpeech + ✨ Améliorer (plus rapide).

### Live preview WebSpeech (Phase A.7.2 v6)

Pendant que tu parles, le champ texte affiche une **transcription en direct** via l'API `SpeechRecognition` native (Chrome/Edge uniquement). Qualité ~85-90 % en français, mauvaise sur le vocab technique, c'est ce qui part au tuteur en envoi direct, et c'est ce que **✨ Améliorer** nettoie si tu veux passer du temps de moins.

Privacy : l'API WebSpeech envoie l'audio chez Google pour reconnaissance. Acceptable sur localhost pour un usage perso. Pas dispo dans Firefox / Safari < 14.1 → tu vois juste le timer, pas le texte live, et l'envoi direct envoie un input vide → noop.

### Bouton ✨ Améliorer le brouillon (Phase A.7.2 v15.6, contexte tuteur depuis v15.7.1)

À côté du 📎, un **bouton ✨** qui ouvre un popover avec 4 actions de réécriture du brouillon **avant envoi**. Activé dès que ton input contient ≥8 caractères :

- 📝 **Reformuler** : plus clair et naturel, sens identique. Pour quand tu veux que le tuteur voie une version peignée plutôt que ton premier jet.
- ✂️ **Plus concis** : supprime hésitations, redondances, faux départs. Cible 30-50 % de la longueur. Pratique après une dictée vocale touffue.
- 📖 **Développer** : explicite les nuances et justifications implicites, ajoute des connecteurs logiques. Quand tu sens que ton message est elliptique.
- ✅ **Corriger fautes** : orthographe / grammaire / ponctuation **uniquement**. Ne reformule pas le style ni la structure. Depuis Phase v15.7.2 le prompt interdit explicitement de supprimer les faux départs (`« et non c'est »`), hésitations (`« euh », « ben »`), mots-béquilles et répétitions. Le résultat peut être « moche » ou décousu, c'est voulu : pour nettoyer ces tics oraux, choisis **Plus concis** ou **Reformuler**.

Click sur une action → bouton ✨ passe en ⏳ pendant ~1-3 s, puis ton input est remplacé. Un petit banner s'affiche au-dessus du footer avec un lien **↩ Annuler** (8 s avant auto-dismiss) qui restaure ton brouillon original. Aucun autre LLM grand public (ChatGPT, Claude.ai, Gemini, Mistral) n'expose cette capacité en standard.

#### Contexte conversationnel automatique (v15.7.1)

Depuis Phase A.7.2 v15.7.1, le rewriter reçoit aussi en ancrage **le dernier message du Compagnon** (capé à 2000 chars, truncation par le début pour garder la fin du tour où la question reformulée se trouve typiquement). Sans ça, le rewriter était aveugle au sujet de la conversation et faisait du bruit aléatoire.

**Exemple concret EN1 CC2 (multiplexeur)** : tuteur dit *« La sortie S recopie l'une des deux entrées E0 ou E1 selon SEL. Reprenez : si SEL vaut 0, laquelle des deux entrées est recopiée sur S ? »*. Tu dictes *« Si celle vaut 0, la sortie E1 est recopiée. »*. Avec le contexte tuteur en ancrage :
- 📝 **Reformuler** peut résoudre `« celle »` → `« SEL »` (le pronom orphelin) et corriger `« la sortie E1 »` → `« l'entrée E1 »` (le tuteur vient de rappeler le terme exact).
- ❌ Le rewriter n'a **PAS** le droit de corriger l'erreur de fond (le `E1` au lieu de `E0` quand SEL=0). Garde-fou explicite dans le system prompt : « le contexte sert UNIQUEMENT à lever les ambiguïtés de pronoms et aligner le vocabulaire ; n'ajoute, ne corrige et ne supprime AUCUN raisonnement, fait ou conclusion du brouillon ». Mode colle préservé : c'est à toi de trouver ton erreur de fond, pas au rewriter.

S'il n'y a aucune bulle Compagnon dans le dialogue (1ʳᵉ question juste avant le 1ᵉʳ tour tuteur), le contexte n'est simplement pas envoyé et le rewriter retombe sur le comportement v15.5 (rewrite stateless).

#### Coût

~300-1500 tokens in/out par appel selon longueur du brouillon, +500-1500 tokens si contexte tuteur injecté. Sur ton quota Pro Max c'est invisible (compté à la session, pas au token). Sur API Anthropic ~$0.005-0.015 par rewrite. Le moteur utilisé est celui sélectionné dans la barre du haut (CLI subscription / API / Gemini / DeepSeek / Groq).

### Mode legacy : hotkey clavier global

Si tu coches `--enable-audio` (ou la case « Hotkey clavier global Espace (legacy) » dans la GUI), tu retrouves l'ancien comportement : maintenir [Espace] global pour parler, relâcher pour envoyer. Géré par la lib `keyboard` côté Python (peut nécessiter admin sur certains setups Windows).

Pas vraiment utile en pratique : le bouton 🎤 est plus simple, ne conflite pas avec ce que tu tapes au clavier, et ne nécessite aucun privilège.

---

## Démarrer une session de dev (Claude Code)

```powershell
.\start_claude_code_session.ps1 -Task "Implémente le parser des balises selon ARCHITECTURE.md §3"
```

Lance Claude Code dans le projet avec :
- Vérification de la présence des fichiers de doctrine
- Affichage du quota Claude Max 5x au démarrage
- Préambule standard injecté (mode économe en tokens, règles absolues)
- Switch CLI subscription / API Anthropic selon `_secrets/engine_pref.json`

Voir le script lui-même pour les options (`-ExtraFile`, `-Verbose`).

---

## Arborescence

```
Compagnon_Revision/
├── CLAUDE.md                       Manuel pour Claude Code (ne pas modifier en dev)
├── ARCHITECTURE.md                 Spec technique détaillée
├── README.md                       Ce fichier
├── CHANGELOG.md                    Phases datées
├── compagnon.py                    Entry point
├── config.py                       Constantes, chemins
├── start_claude_code_session.ps1   Lanceur dev
│
├── _prompts/
│   └── PROMPT_SYSTEME_COMPAGNON.md Cœur pédagogique (sacré)
│
├── _scripts/                       Code Python, organisé par responsabilité
│   ├── audio/                      Capture micro + Whisper + TTS (Phase B)
│   ├── dialogue/                   Client Claude + parser + state machine
│   ├── watchers/                   photo_watcher.py (Phase B)
│   ├── web/                        Flask + SSE + front HTML
│   └── quota/                      Wrapper claude_usage.py (Arsenal)
│
├── _sessions/                      Logs JSON par séance
├── _photos_inbox/                  Drop Tailscale (Phase B)
├── _cache/tts/                     MP3 pré-générés (Phase B)
├── _secrets/                       Cookies, engine_pref.json (gitignore)
├── _logs/                          Logs rotation quotidienne
└── tests/                          Pytest
```

---

## Où trouver quoi

| Je cherche... | Je vais voir... |
|---|---|
| Comment Claude est censé me parler | `_prompts/PROMPT_SYSTEME_COMPAGNON.md` |
| Comment Claude Code est censé coder | `CLAUDE.md` §1 (séparation rôles), §3 (conventions) |
| Le schéma JSON d'une session | `ARCHITECTURE.md` §2 |
| Comment marche le parser SSE | `ARCHITECTURE.md` §3 (machine à états) |
| Pourquoi une session a été interrompue | Logs `_logs/compagnon_YYYY-MM-DD.log` + champ `interrupted_at` du JSON |
| Mon quota Claude Max 5x | Sidebar du front Flask, ou `python ../Arsenal_Arguments/claude_usage.py --fetch` |

---

## Règles que je dois respecter (note à moi-même)

1. **Ne pas modifier `CLAUDE.md`, `ARCHITECTURE.md`, `_prompts/PROMPT_SYSTEME_COMPAGNON.md` sans concertation Claude.ai.** Ce sont les fichiers de doctrine. Si une session révèle un problème de comportement, je remonte à Claude.ai qui édite.
2. **Ne pas commit `_secrets/`.** Vérifier qu'il est dans `.gitignore` si je versionne un jour.
3. **Mode économe en tokens** par défaut quand je dev avec Claude Code (cf. `CLAUDE.md` §6).
4. **Après chaque phase validée**, ajouter une entrée datée au `CHANGELOG.md`.

---

## Limites assumées (Phase A)

Ces limites sont **conscientes**, prévues pour évoluer en Phases B/C. Ne pas chercher à les contourner en Phase A.

- Pas de TTS : Claude répond en texte affiché uniquement.
- Pas de réception photo : il faudra dropper manuellement les photos dans `_photos_inbox/` plus tard (Phase B), et coder le watcher (Phase B).
- Pas de transfert auto téléphone → PC : j'utilise déjà Tailscale + drop manuel le temps de la Phase A. Le serveur Flask qui reçoit les photos depuis le téléphone arrivera en Phase C.
- Whisper non-streaming : la transcription se fait après que l'enregistrement est complet (clic d'arrêt sur le 🎤). En pratique, ça ajoute ~1-2 secondes de latence par tour de parole. Acceptable Phase A.
- Pas de mode multi-séances continues : une session = un TD/CC, point. Phase D.

### Conso tokens : gros budget par session

**Le Compagnon est un gros consommateur de tokens** par construction. Anthropic Claude Code CLI (mode subscription) **ne cache pas le contexte** : chaque tour replaye l'intégralité du prompt système + contexte + historique de conversation. Concrètement, à chaque message envoyé :

| Composant | Tokens (cap par défaut) |
|---|---|
| Prompt système lecture | ~3 300 |
| Transcription CM injectée | ~5 200 (4 000 mots) |
| TACHE + script perso | ~7 800 (6 000 mots) |
| Corrigés cumulés | ~20 000 (80 000 chars) |
| Historique conversation | +200 à +500 par tour |
| **Total input par tour** | **~37 000 tokens** |

Avec **Pro Max** (Opus 4.7) :

| Fenêtre | Quota | Tours estimés (mode guidé, caps défaut) |
|---|---|---|
| Session 5h | ~750 k tokens (variable selon Anthropic) | **~18-22 tours** avant blocage à 85 % |
| Hebdo 7j Opus | ~3-4 sessions complètes | ~4 sessions de 18-22 tours par semaine |
| Hebdo Sonnet | (pas utilisé en mode CLI subscription par défaut) | n/a |

Concrètement : **~1 séance de 1 h-1 h 30** (avec 3-5 min de réflexion entre chaque tour) avant d'épuiser la fenêtre 5 h, puis il faut attendre le reset. Sur la semaine, **~3-4 séances de révision** maximum. C'est étroit : le projet est pensé pour des sessions courtes et focalisées (un seul exo, ou un seul CM), pas pour réviser 6 h d'affilée.

**Pour étirer** quand tu sens que tu approches du seuil :
- **Baisse les caps contexte** dans le panneau « Avancé » de la GUI. Passer `correction_total_chars` de 80 000 à 20 000 économise ~15 k tokens/tour → +50-70 % de tours en plus. À ne faire que si tu sais ce que tu fais (le tuteur perd des références).
- **Mode colle** au lieu de **lecture** : pas d'injection script/TACHE/corrigés (que l'énoncé), context divisé par ~2.5 → ~85 k tokens/tour, soit 2-3 × plus de tours.
- **Bascule moteur API Anthropic** (`_secrets/engine_pref.json`) si tu as une clé : facturé en pay-as-you-go (~3 $/Mtok input Opus), donc pas de quota fenêtre, mais tu paies à l'usage.
- **Termine la séance proprement** quand tu as fini (`⏹` puis Terminer la séance) plutôt que de la laisser ouverte. Le contexte ne se libère pas tant que la session est active.

Le seuil session 5h est à 85 % par défaut (auto-save sur le Spinbox du panneau Quota), tu peux remonter à 95 % si tu veux gratter les derniers tours, mais Anthropic peut te couper sans préavis au-dessus.

### Latence en mode guidé : peut être très longue

En mode `lecture` (et `guidé`, qui partage le même prompt système), Claude a accès aux outils `Read`/`Grep`/`Glob` scopés à `COURS_ROOT`. Sur un input touffu (long passage lu à voix haute, multiples questions enchaînées), Claude peut **enchaîner 5 à 10 tool calls en cascade**, un par fichier qu'il consulte (CM, corrigé, slides) avant de répondre.

Chaque tool call = un round-trip Anthropic. À 20 à 40 secondes par round-trip, on peut **atteindre 300 secondes (5 min) d'attente** entre l'envoi du message et la première phrase rendue. Observé en session réelle (TD5 EN1 décodeur 7 segments, mai 2026).

C'est une **caractéristique du mode guidé**, pas un bug. Palliatifs disponibles :

- **Mode `colle` à la place** : pas de tools, réponse en 5 à 15 s. Adapté quand tu veux juste te faire interroger sec sans tuteur libre.
- **Spinner « 🤔 Compagnon réfléchit… X.X s »** déjà affiché côté GUI pour que tu saches que ça travaille.
- **Patience** : si tu vois >60 s sans rendu, c'est probablement une cascade de Read en cours. Avant 300 s, ça finit généralement par sortir.

Si c'est régulièrement bloquant pour ton usage, deux options de fix code (non livrées) :
1. **Timeout dur** côté `claude_client.py` (ex: 90 s) → coupe avec un message d'erreur lisible au lieu du vide.
2. **Restreindre les tools** en lecture à `Read` seul (pas `Grep`/`Glob`) pour limiter l'envie de scanner.

Décision : pas codé pour l'instant : l'attente est un signal que Claude bosse, pas une perte. À reconsidérer si la friction devient gênante.

### Densité de réponse : saturation cognitive

Le prompt système v1.1 cap à **2 concepts neufs par réplique** (cf. `_prompts/PROMPT_SYSTEME_GUIDE.md` §2.5) et oblige Claude à **demander ce que tu vois sur la slide PDF** plutôt que de redessiner Karnaughs / schémas en ASCII (§2.6). Mais Claude reste un modèle qui peut surcharger malgré le prompt, surtout sur les sujets denses (Karnaugh, De Morgan, chemin critique).

Si une réplique te paraît trop dense :
- Dis-le explicitement (« là c'est trop dense, reprends plus simple »), le prompt §2.7 oblige Claude à proposer la pause au 1er signe (« je suis perdu », « je suis fatigué »).
- Utilise les **boutons de ton** sous chaque réponse : 🎯 Plus simple, 📝 Plus concis, 🔄 Reformule.
- En dernier recours : ferme la session, ouvre claude.ai web ou Claude Cowork (cf. § "Pourquoi pas Claude Cowork" ci-dessous) : ces interfaces ont un format conversationnel parfois mieux adapté à la révision passive.

---

## Stack technique

- **Python 3.12** sur Windows 11
- **faster-whisper large-v3** sur RTX 2060 (int8_float16 + VAD)
- **Flask** + Server-Sent Events pour le streaming Claude → front
- **`keyboard`** pour le push-to-talk global
- **`sounddevice`** pour la capture audio
- **Claude Opus 4.7** via CLI subscription (Max 5x) ou API Anthropic, choisi dans `_secrets/engine_pref.json`
- **Gemini 2.5 Pro** via API (`google-genai`) en alternative pour les sessions de lecture longue (cf. § Moteurs supportés)
- **`claude_usage.py`** d'Arsenal_Arguments pour le tracking quota live (Anthropic uniquement)

---

## Moteurs supportés (Phase A.7.2 v7.2)

Le sélecteur radio « 🤖 Moteur » dans la GUI Tk choisit entre 5 backends ; le choix est sauvé dans `_secrets/engine_pref.json` (auto-save sur radio click) et lu par `compagnon.py` au démarrage du subprocess.

| Moteur | Identifiant | Forces | Limites | Coût |
|---|---|---|---|---|
| **Claude CLI subscription** (défaut) | `cli_subscription` | Suit le mieux le prompt (vouvoiement, balises). Outils Read/Grep/Glob natifs en guidé/découverte/workspace. | Quota fenêtre 5h serré (~18-22 tours, cf. § Conso tokens). | Inclus dans Pro Max. |
| **Claude API Anthropic** | `api_anthropic` | Même qualité que CLI, sans la fenêtre 5h. Outils Read/Grep/Glob **réels** + ingestion PDF native (boucle d'outils, Phase A.12). | Pay-as-you-go (~3 $ / Mtok input Opus). | Variable. |
| **Gemini 3.5 Flash** | `gemini_api` | Contexte 1M tokens. Rapide. Outils Read/Grep/Glob **réels** + ingestion PDF native (Phase A.12). | Doctrine calibrée pour Claude (drift possible sur les balises) | **Free tier** (`gemini-3.5-flash`, stable). |
| **DeepSeek V3 / R1** | `deepseek_api` | **Raisonnement math/code** : R1 fait de la chaîne de pensée, parfait pour debugger Idris. Outils Read/Grep/Glob (texte). | Text-only : ne lit pas les PDF/images. Free tier suspendu en cas de surcharge plateforme. | **Free tier** : 10 RPM (vérifier platform.deepseek.com). |
| **Groq + Llama 3.3 70B** | `groq_api` | **Free tier le plus généreux** (14 400 req/jour). Inférence ultra-rapide. Outils Read/Grep/Glob (texte). | Text-only : ne lit pas les PDF/images. Moins fort en raisonnement pur que R1. | **Free tier** : 30 RPM, 14 400 RPD. |

> **Note free tier Gemini : changement du 2026-05-21**. Google a annoncé **`gemini-3.5-flash`** le **2026-05-19** : modèle stable recommandé, contexte 1M, ~4× plus rapide que la génération précédente, **accessible en free tier**. Dans le même mouvement, `gemini-2.5-pro` a **perdu son free tier** (désormais payant-only sur l'API). Le **2026-05-21** (Phase A.12.1), le moteur Gemini du Compagnon a donc basculé son modèle par défaut de `gemini-2.5-pro` vers **`gemini-3.5-flash`**. Pour forcer 2.5 Pro malgré tout (clé payante), définis la variable d'env `GEMINI_MODEL=gemini-2.5-pro`. Les limites du free tier bougent ; le cap journalier reste la contrainte effective. Détail complet : `MOTEURS.md` (encadré en tête).

### Quand utiliser quel moteur

- **Mode colle** (interrogation 30-45 min) : Claude CLI. C'est ce qui suit le mieux la posture exigeante du prompt système (vouvoiement strict, balises, refus des formulations floues).
- **Mode guidé longue session** (relire un CM 1h30+) : Gemini. Contexte 1M tokens, pas de quota fenêtre 5h, ~5 sessions/jour avant cap journalier.
- **Debug code Idris ou démo math qui coince** : DeepSeek R1 (basculer le `DEEPSEEK_MODEL` vers `deepseek-reasoner`). Le modèle « réfléchit » avant de répondre, utile pour trouver une erreur dans un raisonnement.
- **Backup quand tout le reste sature** : Groq + Llama 3.3 70B. 14 400 req/jour gratuites, jamais bloqué en pratique. Moins fin sur le raisonnement mais hyper généraliste fiable.
- **Quota CLI épuisé en milieu de séance** : la GUI propose automatiquement la bascule (cf. § « Bascule auto » ci-dessous). L'historique de la session courante est perdu (Phase B prévoit la reprise cross-engine).

### Configuration des clés API

Les clés ne sont **jamais** committées. Deux mécanismes acceptés :

1. **Variable d'env** (préféré) :
   ```powershell
   $env:GEMINI_API_KEY   = "AIza..."   # PowerShell, session courante
   $env:DEEPSEEK_API_KEY = "sk-..."
   $env:GROQ_API_KEY     = "gsk_..."
   ```
   Pour persister : `setx GEMINI_API_KEY "AIza..."` (relance la GUI après).
2. **Fichier `_secrets/.env`** chargé par `python-dotenv` (Anthropic API utilise déjà ce mécanisme via `ANTHROPIC_API_KEY`).

Liens d'inscription (tous gratuits, compte requis) :
- Gemini : https://aistudio.google.com/app/apikey
- DeepSeek : https://platform.deepseek.com/api_keys
- Groq : https://console.groq.com/keys

### Bascule auto vers un fallback quand quota Anthropic atteint

Quand `compagnon.py` refuse le démarrage parce que le quota Anthropic est dépassé (« Impossible de démarrer : Quota 5h à 87 % »), la GUI détecte le pattern et propose un popup avec **le 1ᵉʳ provider de fallback dont la clé est définie** dans l'environnement :

> Quota Anthropic atteint. Basculer sur **{Gemini | DeepSeek | Groq}** pour cette séance ? [Oui / Non]

**Hiérarchie de candidat** (priorité décroissante pour les sessions de lecture longue) :
1. Gemini 2.5 Pro (contexte 1M, ~5 sessions/jour)
2. DeepSeek V3 (raisonnement, 10 RPM free)
3. Groq + Llama 3.3 70B (14 400 RPD free)

Si plusieurs clés sont définies, le 1ᵉʳ disponible est proposé dans le popup et les autres sont **mentionnées dans le message** comme alternatives : tu peux les choisir manuellement via le panneau Moteur de la GUI au lieu d'accepter le default.

Si **aucune** clé n'est définie, popup informatif avec les 3 liens d'inscription.

« Oui » → met à jour `_secrets/engine_pref.json`, relance immédiatement le subprocess avec les mêmes args.
« Non » → situation inchangée, libre d'attendre le reset Anthropic ou de monter le seuil session.

### Bascule à chaud en plein flow (Phase A.7.2 v7.3)

Distinct du popup ci-dessus (qui s'affiche **avant** le démarrage de session) : si le quota saute **pendant** la séance, typiquement après quelques tours sur Claude CLI subscription qui te rejette au tour suivant, le backend pousse un event SSE `quota_midflow` au front. Tu vois un card rouge dans le chat :

> ⚠️ Quota épuisé en cours de séance
> *Bascule à chaud sans perdre l'historique. Choisis un provider :*
> [→ Gemini 2.5 Pro] [→ DeepSeek V3 / R1] [→ Groq + Llama 3.3 70B]

Les boutons listés correspondent aux providers dont la clé API est définie. Clic → POST `/api/switch_engine` → backend recrée un `ClaudeClient` du provider choisi, **transfère l'historique** (le user message ayant fait sauter le quota est inclus) et relance le stream. Pas besoin de Stop + Lancer, pas de perte de contexte.

Si **aucune clé** de fallback n'est définie, le card explique qu'il faut configurer au moins une `GEMINI_API_KEY` / `DEEPSEEK_API_KEY` / `GROQ_API_KEY` puis Stop+Lancer (le subprocess actuel est mort, on ne peut plus continuer sans clé).

### Limites assumées (Phase A.7.2 v7.2)

- **Pas de Provider Factory abstraite.** Le multi-engine est implémenté en strategy-pattern minimal (`if/elif` dans `ClaudeClient.stream_response`) avec une factorisation `_stream_via_openai_compatible` pour les providers OpenAI-compatibles (DeepSeek, Groq) puisqu'ils partagent la même API. Suffisant à 5 engines ; au-delà, abstraction nécessaire.
- **Pas de tools Read/Grep côté Gemini/DeepSeek/Groq.** En mode guidé sous ces providers, le tuteur n'a accès qu'à ce qui est injecté dans le prompt initial : pas de vérif `script_perso vs CM` dynamique. Acceptable pour de la lecture libre, mais Claude reste le meilleur pour les sessions où tu veux qu'il fasse des Read/Grep.
- **Bascule à chaud activée** (Phase A.7.2 v7.3). Si le quota saute en plein flow, le backend pousse un event SSE `quota_midflow` listant les providers de fallback dispos (clés présentes dans l'env). Le front affiche un card avec un bouton par provider ; clic → POST `/api/switch_engine` → recrée un `ClaudeClient` du nouveau provider en transférant l'historique (`_history`) tel quel (le user message qui a fait sauter le quota est dedans, retry direct), puis relance le stream. Pas de perte de contexte, pas de Stop+Lancer.
- **Doctrine pédagogique unique.** Les `PROMPT_SYSTEME_*.md` sont calibrés pour Claude. Drift attendu sur la balise `<<<SUGGESTED_EDIT>>>` avec Gemini/DeepSeek/Groq : créer un issue si la dérive est gênante plutôt que forker le prompt par modèle.

---

## Quand quelque chose casse

| Symptôme | Vérifier d'abord... |
|---|---|
| Claude ne répond pas | `_logs/compagnon_YYYY-MM-DD.log` (erreur API ?), puis quota |
| Whisper transcrit mal | Niveau micro, langue forcée à `fr`, VAD `min_silence_duration_ms` |
| Le push-to-talk ne capte pas | `keyboard` peut nécessiter admin sur certains setups Windows |
| Session corrompue / json invalide | Dernière sauvegarde `.tmp` à côté du `.json` (atomic write a échoué) |
| Quota check toujours en erreur | Cookie `claude.ai` expiré, `python ../Arsenal_Arguments/claude_usage.py --set-cookie` |
| Le navigateur ne se connecte pas à Flask | Port 5680 déjà pris ? Pare-feu ? `netstat -ano \| findstr 5680` |

Si rien ne marche, je note le symptôme + extraits de logs et je remonte à Claude.ai (problème d'archi/pédagogie) ou Claude Code (bug de code).

---

## Mode colle vs Mode guidé (Phase A.7 → Z.8)

Deux modes de session depuis Phase Z.8 (suppression mode `lecture`, absorbé par `guidé`). Choisis dans le formulaire de lancement (ou via `--mode guidé` en CLI, ou les radios dans la GUI Tk) :

### Mode colle (défaut)
Claude joue un colleur d'oral exigeant. Il t'interroge, refuse les formulations floues, donne 3 indices progressifs avant la solution. Aucun accès filesystem : il n'a que le contexte chargé au démarrage. Prompt système : `_prompts/PROMPT_SYSTEME_COMPAGNON.md`.

#### Format colle : oral / photos / mixte (Phase v15.7.4)

Sous-paramètre du mode colle qui pilote **comment le tuteur gère les questions à objet structuré** (table de vérité, schéma logique, équation posée multi-lignes, dessin, pseudo-code long) : celles qui sont impossibles à dicter proprement à voix haute.

| Format | Comportement du tuteur sur objets structurés | Cas d'usage |
|---|---|---|
| **🎙 Oral** | Pas de photo mentionnée. Vérification orale partielle (« donnez juste la 3ᵉ ligne »). | Révision en transport, lieu sans cahier. |
| **📸 Photos** | Le tuteur **attend** la photo et la propose **en première intention**. Pas de validation d'une dictée bancale « pour gagner du temps ». | Séance prévue avec papier sous la main, validation rigoureuse. |
| **🔀 Mixte** *(défaut)* | Décision **au cas par cas** : photo proposée explicitement sur table de vérité / schéma / dessin / équation posée, oral pur sur définitions / théorèmes / raisonnements. | Le défaut, qui s'adapte. |

**3 voies de bascule** (redondantes, choisis selon contexte) :

1. **Au lancement** : radio « Format colle » dans la GUI Tk (visible si mode=colle), select dans le formulaire web, flag CLI `--colle-format oral|photos|mixte`. Persisté via `runtime_settings.last_selection.colle_format`.
2. **Chips UI en cours de séance** : bandeau au-dessus du dialogue avec 3 chips `🎙 Oral` / `📸 Photos` / `🔀 Mixte`. Click = bascule immédiate, chip actif highlighté. Visible seulement en mode colle. Pour quand tu vois le clavier.
3. **Slash-commands en cours de séance** : `/oral`, `/photos` (ou `/photo`), `/mixte` détectés en début de message → bascule sans envoi au tuteur. Tolérance casse insensible et point final pour la dictée vocale (« slash photos point. »). Pour quand tu dictes au mic.

À chaque bascule en cours de séance :
- Un **marker système sobre** s'affiche dans le fil : `🔀 Format → 📸 Photos`.
- Un marker synthétique `[FORMAT BASCULÉ → photos]` est injecté dans l'historique du tuteur.
- **Règle dure §4.11 du prompt système** : le tuteur acquitte d'**un seul fragment** (« Format photos. ») et adapte. Interdit absolu de demander « êtes-vous sûr ? », de dire « finissons d'abord cet exercice » ou tout autre commentaire pédagogique sur le choix. Tu as la main, il applique.

Tu peux re-basculer autant de fois que tu veux dans la séance, dans n'importe quel sens. Le format courant est persisté dans `_sessions/<id>.json` et survit à une reprise.

**Mode guidé non concerné** : le tuteur guidé a déjà accès aux PDF via `Read`/`Grep`/`Glob`, donc le paramètre est sans effet et le bloc `[FORMAT COLLE : ...]` n'est pas injecté.

#### Ancrage corrigé : strict / consultatif / aucun (Phase v15.7.30)

Sous-paramètre du mode colle qui pilote **comment le tuteur utilise le corrigé officiel du prof** (PDF chargé depuis `COURS/{MAT}/{TYPE}/{TYPE}{N}/corrections/`).

**Pourquoi ce paramètre existe** : depuis Phase A.5, le prompt v0.2 §1.4 fait du corrigé une **règle inviolable** (« le corrigé du prof fait foi »). Solide quand le corrigé est juste. Mais friction observée EN1 CC2 (2026-05-10) où le corrigé contenait probablement une erreur et le tuteur **tournait en boucle** sans pouvoir s'en émanciper, en répétant « le corrigé attend X » tour après tour. Ce paramètre te donne une soupape de sécurité.

| Mode | Comportement du tuteur | Cas d'usage |
|---|---|---|
| **📘 Strict** *(défaut)* | Corrigé fait foi, règle inviolable v0.5. Tout écart = renvoi au corrigé cité. | 1ᵉʳ tour de TD, validation conformité prof avant CC. |
| **📖 Consultatif** | Corrigé visible mais cité comme un point de vue parmi d'autres. Voies alternatives cohérentes validées sans exiger de reproduire le prof. Jugement sur la cohérence interne du raisonnement étudiant. | 2ᵉ tour de TD pour explorer des alternatives. **Quand tu suspectes que le corrigé est faux.** |
| **🚫 Sans corrigé** | Corrigé **pas injecté dans le contexte du tuteur**. Il s'appuie sur l'énoncé, les CM, les polys. Erreurs manifestes (calcul, logique) toujours signalées. | Révision blanche sans biais conformité. |

**3 voies de bascule** (identiques au format colle) :

1. **Au lancement** : radio « Ancrage corrigé » dans la GUI Tk (visible si mode=colle), select dans le formulaire web, flag CLI `--corrige-anchor strict|consultatif|aucun`. Persisté via `runtime_settings.last_selection.corrige_anchor`.
2. **Chips UI en cours de séance** : bandeau mauve sous celui du format colle avec 3 chips `📘 Strict` / `📖 Consultatif` / `🚫 Sans corrigé`. Click = bascule immédiate.
3. **Slash-commands** : `/strict`, `/consultatif`, `/aucun`, `/sans_corrigé` (alias tolérés `sans_corrige` / `sans corrigé`). Casse insensible, point final toléré (dictée vocale).

À chaque bascule en cours de séance :
- **Marker système sobre teinté mauve** : `📘 Ancrage → 📖 Consultatif`.
- Marker synthétique `[ANCRAGE BASCULÉ → consultatif]` injecté dans l'historique du tuteur.
- **Règle dure §4.12 du prompt v0.6** : le tuteur acquitte d'un seul fragment (« Mode consultatif. ») et adapte. **Interdit absolu** : « êtes-vous sûr ? », « le corrigé est pourtant la référence », « êtes-vous certain de vouloir abandonner le corrigé ? ». Tu as la main, il applique.

**Limite connue** : la bascule de `aucun` → `strict` / `consultatif` **ne re-injecte pas** le bloc CORRIGÉ OFFICIEL dans le contexte (s'il a été skippé au start, il reste absent jusqu'à la prochaine session). Le tuteur reste avec le contexte initial, juste avec une nouvelle posture pédagogique. Pour avoir le corrigé disponible après ce sens-là, redémarrer la session.

**Mode guidé non concerné** : le tuteur guidé résout les PDF lui-même via `Read`/`Grep`/`Glob`, l'ancrage est manuel et ce paramètre est ignoré.

#### Fin de séance : phase débrief + récap + mini-exos (Phase v15.7.31)

Quand tu termines une séance (bouton **Terminer** OU le tuteur émet `<<<END_SESSION>>>`), Compagnon ne ferme **plus** la session immédiatement. À la place :

1. **Récap Gemini Flash** scanne le transcript complet (3-8 s d'attente affichée) et produit un JSON structuré `{summary, concepts_covered, exercises_handled, suggestions}`.

2. **Carte récap** injectée dans le fil avec :
   - Résumé concis (≤150 mots)
   - Liste des concepts couverts (chacun avec un bouton **🎯** pour un mini-exo ciblé) + exercices traités
   - Suggestions concrètes de révision (ex : « refaire l'ex 3 du TD5 sans regarder »)
   - Bloc **🚀 Pour aller plus loin** (Phase A.11.1) : **📄 Bloc complet de la leçon** / **📄 Bloc complet des exos** / **📝 Série d'exos d'entraînement** / **🎯 Passer en mode colle**
   - 2 boutons d'action : **💬 Continuer en débrief** / **🚪 Fermer définitivement**

3. **Phase débrief** : la session **reste active** ; tu peux continuer à poser des questions au tuteur. Le prompt §1.7 lui dit de basculer en posture détaillée (ratio §2.1 relâché, indices §2.4 levés, mais **rigueur sur le vocabulaire §2.3 conservée**, sinon c'est un chatbot, pas un tuteur). Badge `🎓 débrief` ajouté dans le header session. Le débrief survit à un Ctrl+F5 (état persisté dans le JSON de session).

4. **Mini-exos ciblés** : click sur 🎯 d'un concept du récap → POST `/api/mini_exo {concept}` qui injecte `[MINI-EXO : concept=..., difficulté=..., context=...]` dans l'historique du tuteur + déclenche un stream qui produit un exo court (3-5 questions progressives, une à la fois). Posture colle re-activée **localement** pour le mini-exo, puis retour en posture débrief.

5. **Boutons d'avancement** (Phase A.11.1) : les 3 boutons 📄/📝 du bloc « Pour aller plus loin » → POST `/api/recap_action {action}` qui injecte une requête pré-rédigée dans l'historique du tuteur (compilation des leçons, des exos, ou génération de nouveaux exos d'entraînement) et streame la réponse, sans quitter le débrief. Le bouton 🎯 pré-arme le formulaire en mode colle sur la même matière (progression Découverte → Guidé → Colle).

6. **Fermeture définitive** : click 🚪 → POST `/api/session_close` qui set `phase=closed` + `final_closed_at` + `session_state.finalize()` (ended_at, duration_seconds). Plus possible de revenir après. Le bouton **Terminer** ré-cliqué pendant le débrief renvoie vers ce bouton dédié au lieu de re-déclencher le récap. Une fois fermée, une carte **✅ Séance terminée : et maintenant ?** propose de rebondir (🎯 mode colle / 🔁 nouvelle séance) plutôt que de laisser un écran mort.

#### Sélection de texte → popup contextuel + 🔖 Notes (Phase v15.7.23)

Sélectionne n'importe quel texte (≥ 3 caractères) dans une bulle Compagnon ou dans tes propres messages → un mini-popup apparaît juste au-dessus de la sélection avec 4 actions :

| Bouton | Effet |
|---|---|
| **💾 Save** | Sauvegarde la phrase dans le nouvel onglet sidebar 🔖 Notes (persistant en JSON de session) |
| **📋 Citer** | Insère `> texte\n\n` dans ton textarea (citation Markdown) pour répondre dans le contexte |
| **🤔 Explique** | Pré-remplit `Peux-tu m'expliquer : "texte"` dans ton textarea (tu valides en tapant Entrée) |
| **📝 Copier** | Copie dans le presse-papier (Ctrl+C amélioré, sans toucher la souris) |

Marche sur tes propres bulles aussi (pour citer ta propre réponse, ou save une note perso). Auto-hide après 8s d'inactivité ou si tu cliques ailleurs.

##### Onglet sidebar 🔖 Notes (entre 📚 Docs et 💬 Historique)

Liste de toutes tes sauvegardes pour la session courante (persisté en reprise). Pour chaque note :
- Header : rôle (Toi / Compagnon, bordure jaune ou bleue) + timestamp
- Body : extrait de texte sauvegardé (cliquable)
- Actions : **↪ Voir** scroll vers la bulle source + highlight bref jaune (animation 2.5s) ; **🗑** supprime

Si vide : message d'aide explicite. Si la bulle source a été supprimée entre temps (purge, autre branche) : alerte « bulle source introuvable ».

##### Onglet sidebar 🎓 Astuces (coach marks, Phase A.10.5)

Friction d'origine : *« j'imagine une sorte de tuto pour utiliser le truc […] avec pleins de trucs et quand on clique dessus ça peut faire des actions intelligente genre le même truc d'effet quand on clique sur photo dans navigateur et ça illumine accès distant en jaune »*.

L'onglet **🎓 Astuces** est un mini-cheatsheet **interactif** des fonctionnalités du Compagnon. 15 astuces curated couvrant ce qui est utile mais peu discoverable :
- 📷 Prendre une photo depuis ton téléphone → spotlight onglet `🔗 Distant`
- 📌 Épingler une consigne → spotlight onglet `📌 Consignes`
- 🤖 Demander au tuteur de retenir → pré-remplit `"Retiens que "` dans le textarea + spotlight Envoyer
- 💾 Sauvegarder une phrase comme note → spotlight onglet `🔖 Notes`
- 📸 Revoir les photos envoyées → spotlight onglet `📸 Photos`
- ✨ Reformuler ton brouillon → spotlight bouton `✨`
- 🎙 Dicter au micro → spotlight bouton `🎤`
- 🔀 Basculer le format → pré-remplit `/mixte`
- 📘 Basculer l'ancrage corrigé → pré-remplit `/consultatif`
- 📚 Lire l'énoncé/corrigé en séance → spotlight onglet `📚 Docs`
- 💬 Reprendre une session → spotlight onglet `💬 Historique`
- 📋 Importer des consignes → spotlight onglet `📌 Consignes`
- 📊 Surveiller ton quota → spotlight onglet `📊 Quota`
- ⌨ Push-to-talk Espace (raccourci clavier sans cible visuelle)
- 🛑 Annuler la réflexion en cours (raccourci clavier sans cible visuelle)

Chaque astuce a un bouton **`▶ Voir où`** qui déclenche un **coach mark** : l'élément cible scintille en jaune doré pendant ~3s (animation CSS `spotlight-pulse` ou `tab-spotlight-pulse` selon que la cible est un onglet du rail ou un bouton classique), avec `scrollIntoView` smooth pour s'assurer qu'il est visible.

Helper interne `_spotlight(target, opts)` réutilisable :
- `target` : sélecteur CSS ou Element directement
- Si cible = `.sb-tab` → click avant le pulse (bascule + scintille)
- `opts.scrollIntoView` : bool, défaut true
- `opts.duration` : ms, défaut 3000

Pour les astuces de type slash-commands (`/oral`, `/strict`, etc.), le bouton pré-remplit le textarea ET spotlight le bouton Envoyer : l'utilisateur voit *où* taper, pas juste *quoi* taper.

Catalogue dans `TIPS_CATALOG` (constante globale dans `app.js`), facile à étendre.

##### Onglet sidebar 📌 Consignes (mémoire persistante de séance, Phase A.10)

Friction d'origine : *« il omet les signatures et je lui demande explicitement de ne pas oublier, mais je pense qu'il va oublier c'est déjà arrivé dans d'autres session qu'il oublie. »* Le tuteur dilue parfois en 30 tours les consignes qu'on lui donne, surtout les consignes de **forme** (format de réponse, vocabulaire à utiliser, choses à ne pas oublier). Pas un bug, c'est la nature des LLM : ton message d'il y a 30 tours pèse moins lourd que le système prompt rappelé à chaque appel.

L'onglet **📌 Consignes** matérialise une **mémoire persistante de séance** : chaque consigne épinglée est réinjectée par le backend en préfixe de chaque user message LLM, sous la forme d'un bloc `[CONSIGNES ÉPINGLÉES PAR L'ÉTUDIANT, à respecter en priorité] … [/CONSIGNES ÉPINGLÉES]`. Le tuteur ne peut plus « l'oublier » : il la voit fraîche à chaque tour, comme un sous-prompt système.

**Deux façons d'épingler** :

1. **Chip 📌 hover sur tes bulles** dans le fil. Passe la souris sur une bulle à toi → bouton 📌 en haut à droite. Click → la bulle devient une consigne. Si elle fait plus de 200 chars, un prompt te laisse la raccourcir. Toast `📌 Consigne épinglée` + bascule auto sur l'onglet.

2. **Dis-le explicitement au tuteur** : « retiens que… », « note que… », « pour le reste de la séance, … ». Le tuteur émet alors la balise `<<<REMEMBER>>>{"text":"..."}<<<END>>>` (Phase A.10, documentée dans les 4 prompts système). Le backend persiste avec `kind="tutor"` et le front affiche un toast `📌 Consigne ajoutée par le tuteur : « … »`. Le tuteur ne peut PAS épingler de sa propre initiative : uniquement sur ta demande explicite.

**Gestion** :
- **Toggle ✅ Active / ⏸ Désactivée** par sticky : désactiver = la sticky reste dans la liste mais n'est plus injectée dans le contexte LLM. Utile si une consigne devient temporairement caduque.
- **Édition inline au double-clic** sur le texte. Enter pour valider, Esc pour annuler.
- **🗑** pour supprimer définitivement (avec confirm).
- **↪ Voir** pour scroll vers la bulle source (si épinglée via chip).
- Couleur de la bordure : 📌 jaune pour les consignes user, 🤖 bleu pour celles du tuteur.

**Import depuis une autre session** : bouton `📋 Importer…` du header. Modal 2 étapes : (1) liste des sessions avec stickies, (2) checkboxes par sticky. Tu peux importer en masse ou cherry-picker. Les IDs sont régénérés, le champ `imported_from` garde la trace.

**Portée** : par session uniquement (pas global, pas par matière). Choix assumé pour éviter la pollution cross-séances. Si tu veux propager une consigne sur une nouvelle session du même exo, tu l'importes explicitement.

**Cap technique** : 200 chars/sticky après normalisation whitespace. Au-delà, le backend refuse en POST/PATCH ; côté parser de balise `<<<REMEMBER>>>`, tronque à 197 + `…` avec warning loggué.

##### Onglet sidebar 📸 Photos (entre 🔖 Notes et 💬 Historique, Phase A.9.1)

À côté de l'onglet Notes (sauvegarde **manuelle** de texte), un onglet **📸 Photos** archive **automatiquement** chaque image que tu envoies au tuteur pendant la séance, qu'elle vienne du bouton 📷 (caméra mobile), du bouton 📎 (fichier disque), d'un paste Ctrl+V, d'un drag-drop, ou de la prise photo depuis ton téléphone via `🔗 Distant`.

Pourquoi : au bout de 30-50 tours de conversation, retrouver « cette photo de mon brouillon où j'avais écrit telle chose » dans le scroll devient pénible. La galerie te les ramène en grille de vignettes sous la main.

Comportement :
- **Auto-archivage** au moment du send (un envoi avec 3 photos = 3 entrées). Pas de bouton « save ».
- Grille de vignettes carrées (auto-fill 120 px), tri **anti-chronologique** (plus récente en haut).
- **Click sur la vignette** → ouvre la lightbox (le même composant que les slides guidées).
- **🗑 en overlay** au hover de chaque carte → confirm puis retire l'entrée de la galerie. **Le fichier disque reste conservé** (sous `_uploads/{session_id}/photos/` depuis A.10.2, ou sous `COURS/.../photos/` pour les sessions legacy, cf. backfill A.10.1) : si tu te trompes, le tracking JSON est nettoyé mais le fichier reste exploitable côté pipeline.
- Persisté dans `session_state.data["session_photos"]` (champ additif, conservé en reprise : au prochain `Resume Session` la galerie est rechargée).
- Indicateur de fichier introuvable (`🗎`) si le fichier a été déplacé hors COURS/.
- Bouton 🔄 dans le header pour forcer un refresh.

Limites assumées :
- Pas de tri par tour (juste par `sent_at` ISO).
- Pas de re-crop depuis la galerie : pour retoucher, il faut renvoyer la photo (le re-crop est dispo seulement dans le tray d'attente).
- Pas de bulk delete (un 🗑 par photo, exprès, moins de risque de purge accidentelle).

##### Cleanup KaTeX automatique (Phase v15.7.28)

Quand tu sélectionnes du texte qui contient des formules LaTeX rendues par KaTeX (par exemple « la sortie $Y_i$ vaut $E$ si $SEL = i$ »), `getSelection().toString()` capture par défaut une bouillie Unicode (couche MathML invisible avec chars `𝑌 𝑖 𝐸` + couche visuelle `Y i E` + retours à la ligne parasites + zero-width spaces). Au save, le texte est nettoyé via une regex qui retire les chars Mathematical Alphanumeric Symbols (U+1D400-U+1D7FF), les invisibles (ZWSP, ZWNJ, ZWJ, FUNCTION APPLICATION, INVISIBLE TIMES…) et collapse les whitespace.

Résultat : phrase lisible sans la mise en forme math (`Y_i` devient `Y i`), copiable, citable proprement. Le cleanup est **idempotent** et appliqué aussi au render des notes existantes : donc les anciennes notes pré-v15.7.28 (avec junk Unicode persisté) s'affichent propres après reload sans migration JSON.

Tradeoff assumé : pas de re-rendu KaTeX dans les notes. Si tu veux la formule rendue, va voir la bulle source via **↪ Voir** ou **highlight jaune persistant** posé au save.

##### Highlight persistant au save (Phase v15.7.26)

Au moment du **💾 Save**, la phrase sélectionnée est entourée d'un `<mark class="saved-note-mark">` dans la bulle source (fond jaune doux + soulignement pointillé jaune). Reste visible tant que la bulle est dans le DOM. Retiré automatiquement quand tu supprimes la note via 🗑.

Limitation connue : si la sélection traverse plusieurs nœuds (typique sur du KaTeX multi-spans), le highlight peut ne pas s'appliquer (`surroundContents` lève DOMException). Dans ce cas la note est sauvegardée quand même, juste sans highlight visuel.

##### Cache-bust auto sur les assets (Phase v15.7.27)

Les balises `<link>` et `<script>` du template `index.html` sont versionnées dynamiquement avec `?v=<mtime>` (timestamp de dernière modification du fichier). Le browser revalide à chaque commit qui touche `app.js` ou `style.css`, sans bump manuel. Évite le piège *« nouvelle feature pas visible parce que le browser cache l'ancien JS »*.

#### Suite d'outils contextuels « pas satisfait, autre chose ? » (Phase Z.8.4 → Z.9.7)

Cas d'usage : tu fais un CC en mode colle, tu bloques sur un exo. Quatre angles couverts par 4 endpoints isolés (qui ne polluent pas la conv principale du tuteur de la colle) :

##### Tone-toolbar sous chaque bulle Compagnon (modes colle, découverte et guidé)

Depuis Z.9.7, la barre est compacte. **Depuis A.10.23**, fusion 🔍 Exo voisin + 📚 Passage CM → 1 seul bouton 📚 Cours. **Depuis A.10.24**, étendu à tous les modes pédagogiques (colle / découverte / guidé), Workspace exclu (pas de contexte COURS).

```
[🎛 Modifier ▾] [📚 Cours] [🎬 Vidéo] [🌐 Internet]
```

- **🎛 Modifier ▾** ouvre un popover avec les 6 reformulations classiques de la dernière réponse (📝 Plus concis / ➕ Plus développé / 📖 Avec exemple / 🎯 Plus simple / 🔬 Plus rigoureux / 🔄 Reformule). Click outside ou re-click pour fermer. Auto-flip drop-up ↔ drop-down selon l'espace dispo (Z.9.8 : un popover sous une bulle en haut du viewport s'ouvrira vers le bas).
- **📚 Cours** (A.10.23) lance **en parallèle** 2 recherches isolées dans `COURS/` : exo voisin pour s'entraîner + passage CM qui définit le concept. Chacune produit sa propre bulle dans le dialogue (résultats UI inchangés). Avant A.10.23, étaient 2 boutons séparés (🔍 Exo voisin + 📚 Passage CM).
- Les 2 derniers boutons (🎬 Vidéo / 🌐 Internet) sont les **recherches externes isolées** détaillées ci-dessous, contextuelles : ils prennent automatiquement le texte de la bulle Compagnon parente + ton dernier message comme description.

##### 🔍 Trouve un exercice voisin dans tes cours

Cherche dans `COURS/{matiere}/` un exo similaire à celui qui te bloque. **N'a PAS le droit** de lire le corrigé du `(type, num)` en cours. Renvoie l'énoncé brut + 1 phrase sur la similarité. Pas de solution, pas d'indices.

Deux entrées :
1. **🔍 contextuel sous chaque bulle Compagnon** : utilise directement la question/réponse du tuteur comme description. Pas de prompt à remplir, c'est le démarrage classique.
2. **Re-clic depuis la bulle exo voisin** : 6 boutons « Pas satisfait ? » :
   - **📉 Plus simple** : exo introductif sur le même concept
   - **📈 Plus dur** : exo plus avancé pour stretch
   - **🔄 Autre angle** : autre type de question, niveau comparable
   - **✏ Affiner** : un prompt te permet d'ajouter une précision (« plus axé table de vérité », « avec un cas concret », etc.) qui s'ajoute en post-scriptum à la description contextuelle
   - **🌐 Sur internet** (cf. ci-dessous)
   - **🎬 Vidéo YouTube** (cf. ci-dessous)

Mémoire de session : les exos déjà proposés sont automatiquement exclus au re-clic, tu ne retombes pas sur les mêmes.

La bulle résultat (bordure orange) contient label + pourquoi + énoncé encadré + boutons **📄 Voir l'énoncé PDF** / **✅ Voir le corrigé PDF** qui ouvrent les fichiers dans un nouvel onglet via `/api/cours_file`.

##### 📚 Pointe-moi le passage du CM (Phase Z.9)

Quand tu ne sais pas par où commencer, tu n'as parfois pas besoin d'un autre exo : tu as besoin de relire la définition. Cherche dans `COURS/{matiere}/CM/` le passage du poly qui définit le concept ciblé. Renvoie nom du fichier + numéro de page + extrait court (3-8 lignes) + bouton 📄 pour ouvrir le PDF.

**Depuis A.10.23**, déclenché par le bouton fusionné **📚 Cours** (qui lance aussi find_similar_exo en parallèle). Aussi dans la bulle « rien trouvé » de l'exo voisin. Disponible dans tous les modes pédagogiques (colle / découverte / guidé) depuis A.10.24.

##### ✨ Reformulation LLM des queries de recherche (Phases v15.7.14 → v15.7.15)

Avant chaque recherche 🌐 ou 🎬, le contexte conversationnel (question du tuteur + ta dernière intervention) est **automatiquement reformulé en requête de recherche optimisée** par un workflow LLM **2-étapes** (Phase v15.7.15) :

**Étape 1 : Infer le concept sous-jacent** (~1.5s) : le LLM analyse la demande pédagogique brute et infère :
- Le **concept général** (« comparateur 3 bits » au lieu de « COMP »), avec 0-2 alternatives plausibles si ambigu
- Les **specs techniques en français** (« 3 entrées 2 sorties » au lieu de `S[1:0] A[2:0]`)
- Le **niveau pédagogique** (lycée / L1 / L2 / prépa / BTS / master / inconnu) **sans hardcode** : le LLM devine depuis les indices contextuels (vocabulaire, complexité, type de notation). Choix explicite : ne pas figer un niveau dans le prompt parce que ta trajectoire académique évoluera.

**Étape 2 : Compose la query** (~1.5s) : à partir du concept analysé, le LLM compose une vraie requête de recherche :

- Utilise le **concept français standard** (PAS l'identifiant brut `COMP`/`MUX21` qui est propre à ton énoncé et qui ne matche aucune ressource externe)
- Inclut les **specs en français** (« 3 bits », « 2 sorties »), JAMAIS la notation `[N:M]` qui ne matche rien sur YouTube/Google
- Calibre le **vocabulaire selon le niveau** (« exercice » pour lycée, « démonstration » pour prépa, neutre si inconnu)
- Renvoie 1 query principale + 2-3 alternatives qui explorent les concepts alternatifs ou varient l'angle

**Exemple concret** : *« Analysez le composant COMP pour déterminer S[1:0] en fonction de A[2:0]. Établissez la table de vérité complète sur papier. »* → étape 1 infère *« comparateur logique 3 bits, 3 entrées 2 sorties, L1, logique combinatoire »* → étape 2 produit *« comparateur logique 3 bits cours table de vérité »* avec alts *« circuit combinatoire 3 entrées 2 sorties exercice corrigé »*.

**Pourquoi 2 appels** : le LLM ne mélange plus analyse et composition. La tâche d'inférence est explicite et auditable (pas masquée dans une chaîne de pensée). Coût : 2× ~$0.0001 = $0.0002 par recherche, négligeable. Latence : ~3s vs ~1.5s en v1, acceptable.

**Choix de Gemini Flash forcé pour cette tâche** (peu importe ton moteur de séance) :

1. **Latence** : Gemini 2.5 Flash répond en ~0.5-1.5s vs ~3-5s pour Opus / Pro. Pour une transformation triviale (phrase → mots-clés) qui ne profite pas du raisonnement Opus, ça vaut pas la peine d'attendre. Tu vois la bulle « ✨ Reformulation… » disparaître vite, puis « 🌐 Recherche internet… » prend la suite.
2. **Coût** : ~200 tokens in / 50 tokens out par refine ≈ $0.0001 par recherche sur Gemini API. Sur Opus : $0.005 à 0.015, multiplie ça par 10 recherches dans une séance et c'est non négligeable. Sur Pro Max : invisible vu que c'est compté à la session.
3. **Cohérence** : que tu sois sur Opus, Sonnet, DeepSeek, CLI subscription ou Gemini Pro pour la séance, le refine reste rapide et pas cher. Sinon les utilisateurs sur Opus paieraient un délai désagréable juste pour transformer une phrase en mots-clés.

**Tradeoff assumé** : nécessite une clé `GEMINI_API_KEY` dans l'env (gratuite, free tier 15 RPM / 1M TPD largement suffisant). Si la clé est absente ou invalide, l'endpoint retourne 502 et le frontend tombe en fallback heuristique JS (extraction de la phrase la plus technique du tuteur, voir Phase v15.7.13).

**Bouton 🔄 Reformuler** (orange, à côté du champ « Édite la query ✨ ») : si la reformulation initiale ne te plaît pas, click → re-call Gemini avec `exclude=[query courante, alternatives déjà vues]` pour obtenir un autre angle. Quand toutes les alts sont épuisées, alerte explicite. Tu peux aussi **éditer manuellement** à tout moment.

##### 🌐 Cherche sur internet (Phase Z.9)

Quand le local ne suffit pas. Recherche sur sites éducatifs **français** : Bibmath, Exo7, Wikiversité, Khan Academy FR, fiches-bac.fr, kartable, schoolmouv. Évite explicitement les sites de devoirs corrigés gratuits.

⚠ **Engines supportés** : Claude API ou Gemini uniquement (recherche web native). DeepSeek/Groq/CLI subscription ne supportent pas → si tu cliques 🌐 sur ces engines, tu reçois un message clair + sélecteur de moteur qui clignote.

Bouton **🌐 Internet** dans la tone-toolbar, dans la bulle exo voisin (« Pas satisfait ? »), et dans la bulle « rien trouvé ». La bulle résultat (bordure bleue) liste 2-3 ressources avec titre + source + kind + pourquoi, plus :
- un bouton **🌐 Autre ressource** qui relance la recherche en excluant les URLs déjà vues (Z.9 mémoire `seenWebUrls`)
- un input éditable + bouton **🔍 Chercher sur Google** (Z.9.5) : fallback manuel garanti même si les liens LLM ne plaisent pas, l'algo Google est toujours plus fiable que les hallucinations

⚠ **Anti-hallucination (Z.9.1 → Z.9.4)** : avant de retourner les résultats, le backend vérifie chaque URL via HEAD/oembed. Les URLs mortes (DNS fail, 404, vidéos supprimées) sont filtrées. Si elles ont passé le check mais que le LLM a halluciné un site type soft-404-200 (ex `eeinap.com`), tu peux le voir au clic : utilise le bouton « Chercher directement » pour avoir le plan B.

##### 🎬 Vidéo YouTube éducative (Phase Z.9)

Privilégie les chaînes pédagogiques FR : Yvan Monka, JeChercheUneOrange, Maths Adultes, Heu?reka, Science Étonnante, Hygiène Mentale, etc. Évite les vidéos de devoirs corrigés et les vidéos en anglais.

Bouton **🎬 Vidéo** dans la tone-toolbar et la bulle exo voisin. Bulle résultat (bordure rouge) avec lien YouTube + chaîne + 1 phrase, plus :
- un bouton **🎬 Autre vidéo** qui relance en excluant les URLs déjà vues (mémoire `seenYoutubeUrls`)
- un input éditable + bouton **🔍 Chercher sur YouTube** : fallback manuel via l'algo natif YouTube. Indispensable car Gemini Search Grounding hallucine fréquemment des `videoId` plausibles (vérifié via oembed côté backend, mais quand tout est halluciné tu reçois la bulle d'erreur avec ce fallback).

##### Garanties communes

- **Conv principale non polluée** : tous ces appels sont **isolés**. Le tuteur de la colle ne voit ni l'exo voisin, ni la vidéo, ni les ressources internet, ni le passage de CM. Quand tu reviens, dis-le-lui pour qu'il sache que tu as fait le détour.
- **Mémoire de session** : `foundExoHistory`, `seenWebUrls`, `seenYoutubeUrls` reset à chaque démarrage de session, passés en `exclude*` à chaque re-clic « Autre… ». Tu ne retombes pas sur les mêmes refs.
- **Pédagogie préservée** : aucun de ces endpoints ne te donne la solution du CC en cours. L'exo voisin a son corrigé accessible (autre TD, donc OK pour s'auto-corriger), mais le corrigé du CC actuel reste protégé.

Coût : ~2-5k tokens in / 500-1500 tokens out par recherche. Invisible sur quota Pro Max, ~$0.01-0.03 sur API par appel.

### Mode guidé (ex-lecture + Phase A.7.2 v5 slide-par-slide)

Claude joue un tuteur patient. Tu lis ton script (potentiellement en parlant à voix haute via le 🎤), tu lui poses des questions au fur et à mesure. Il a accès aux outils **`Read`** / **`Grep`** / **`Glob`** scopés à `COURS/` (le sous-process CLI tourne avec `cwd=COURS_ROOT`), donc il peut consulter n'importe quel CM, poly, énoncé, correction de l'arbre pour vérifier la cohérence de ton script.

Quand il détecte une vraie incohérence (ex : ton script dit « f continue donc Rolle s'applique », le CM précise « f continue ET dérivable »), il émet une balise `<<<SUGGESTED_EDIT>>>{file, before, after, reason}<<<END>>>`. Le front affiche un panneau avec un diff côte-à-côte et un bouton **Appliquer** / **Rejeter**. Toi seul valides : Claude ne touche à rien sans ton clic.

Sécurités appliquées par `/api/apply_edit` :
- Chemin **relatif** à `COURS_ROOT` obligatoire, pas de `..`, pas de chemin absolu
- Whitelist d'extensions : `.md` et `.txt` uniquement (les `.pdf` du prof ne sont pas éditables)
- `before` doit apparaître **une seule fois** dans le fichier (sinon ambigu, rejet)
- Backup automatique `.bak` à côté du fichier avant chaque écriture
- Atomic write via `.tmp` + `os.replace`

Prompt système : `_prompts/PROMPT_SYSTEME_GUIDE.md` (v1.6, ex-LECTURE). Y compris une règle dure : Claude ne suggère **JAMAIS** d'édit sur `enonce_*.pdf`, `correction_*.pdf` ou les transcriptions CM, uniquement sur tes fichiers persos (`SCRIPT_*.md`, `script_oral_*.txt`, `TACHE_*.md`).

**UI slide-par-slide** (sur les TD/TP/CC qui ont un `SCRIPT_*.md` Feynman + un `slides_*.pdf`). À l'ouverture, le panneau sidebar affiche la 1ʳᵉ slide rasterisée en PNG, son titre, sa durée cible. Tu lis (à voix haute si tu veux), puis tu navigues :

- **Espace** ou **➡** : slide suivante
- **←** : slide précédente
- **🎯** : aller à une slide précise (prompt)
- **Clic sur la slide** : ouvre une lightbox plein écran (Échap ou clic sur l'overlay pour fermer), utile pour les schémas denses illisibles dans la sidebar

À chaque transition, un meta-message silencieux est envoyé à Claude : « l'étudiant vient d'arriver sur la slide N (titre), aperçu oral attendu : ..., interviens UNIQUEMENT si pertinent (piège, ancrage, lien cours) ». Le tuteur **décide d'enchaîner ou de rester silencieux**. C'est le mode « adaptatif » : pas de spam de questions à chaque slide, juste les interventions qui apportent quelque chose.

Le radio « Guidé » dans la GUI Tk est désactivé si le SCRIPT.md ou le slides PDF manque pour la sélection courante (les deux sont nécessaires pour le sub-mode slide-par-slide : SCRIPT pour la liste des slides + texte oral, PDF pour les images). Si la sélection courante est déjà sur Guidé et que les matériaux disparaissent (rescan COURS), le radio bascule automatiquement vers Colle.

**Détection auto incohérence SCRIPT ↔ slides PDF.** Si tu as régénéré l'un sans l'autre (ex : édité `SCRIPT_*.md` sans recompiler les slides Beamer), l'endpoint `/api/guided/init` détecte la divergence (nb slides script ≠ nb pages PDF) et le front affiche un banner ⚠️ avec la commande de régen et un bouton « 📋 Copier ». La règle (`COURS/CLAUDE.md §3`) : `SCRIPT.md` = source de vérité, le PDF se recompile via `python _scripts/run_script_oral.py {path}` côté COURS. La commande n'est pas lancée depuis le browser (besoin de MiKTeX + droits + CWD propre) : copier-coller dans un terminal.

### Et la version « Full » (à la Cowork) ?

J'ai aussi prototypé mentalement une version **« Full »** où Claude utiliserait directement les outils `Edit` / `Write` du CLI Claude Code, comme le ferait Cowork : il modifie tes fichiers en direct, on git-stash avant chaque session pour rollback facile, tu fais un `git diff` global après pour valider les changements en bulk.

Avantages : plus puissant, plus proche de Cowork, moins de frictions sur les corrections en chaîne. Inconvénients : moins de contrôle fin (tu ne valides plus chaque edit), risque que Claude touche à des fichiers que tu ne voulais pas, rupture du pattern « capture par balises » qui structure le reste du projet.

Pas implémenté pour l'instant : la version Light couvre 95 % du besoin pratique avec moins de risques. Si après quelques sessions réelles tu trouves la friction « valider chaque edit un par un » trop pénible, on pourra basculer vers Full en activant `--allowedTools "Read Grep Glob Edit Write"` dans `claude_client.py` + en ajoutant une commande `git stash push -u` avant chaque session lecture. ~3 jours de boulot incluant la GUI de diff post-session et le rollback. Décision repoussée jusqu'à validation par l'usage.

---

## Pourquoi pas Claude Cowork (et où sont les autres outils Claude)

Question légitime depuis que **Claude Cowork** est passé en GA (2026-05-05) sur tous les plans payants. Cowork est l'agent Anthropic qui lit/édite des fichiers locaux pour produire des livrables : il pourrait potentiellement « interroger l'étudiant en lisant le corrigé ». Réponse : non, il ne couvre pas le cœur de Compagnon. Pour s'y retrouver entre les 4 outils :

| Outil | Quoi | Où il intervient sur Compagnon | Où il n'intervient pas |
|---|---|---|---|
| **Claude.ai** (chat web) | Conversation. Doctrine, archi, prompt système. | Écrit `CLAUDE.md`, `ARCHITECTURE.md`, `PROMPT_SYSTEME_COMPAGNON.md`. | Ne tourne jamais en runtime. |
| **Claude Code** (CLI) | Agent de dev dans un repo. | Code Compagnon_Revision et Arsenal. Lit `CLAUDE.md` au démarrage. | Pas un runtime utilisateur final. |
| **Claude Cowork** (desktop) | Agent générique sur fichiers locaux. | Pourrait absorber la plomberie Phase B/C : génération de fiches de synthèse multi-CM, plans de révision. | **Ne couvre pas** le cœur Phase A : push-to-talk vocal Whisper GPU, prompt système colleur persistant tour après tour. |
| **Compagnon_Revision** (ce projet) | Runtime spécialisé colle d'oral vocale. | Le projet lui-même. | Ne fait rien d'autre, c'est volontaire. |
| **Arsenal_Arguments** (projet sœur) | Pipeline d'analyse vidéo politique → Discord. | Fournit `claude_usage.py` (quota Pro Max) et la stack Whisper. | Sans rapport pédagogique direct. |

Concrètement, pour un usage révision :
- **Pendant une session** (boucle vocale, exigence colleur, débrief) → **Compagnon_Revision**. Cowork ne fait pas ça.
- **Entre les sessions** (« relis mes transcripts AN1 et fais-moi un plan de révision pour la semaine ») → **Cowork** est probablement plus pratique que coder ces scripts soi-même.
- **Pour étendre Compagnon** (ajouter le TTS, brancher un watcher photo) → **Claude Code**.
- **Pour discuter d'un changement de design** (durcir le prompt système) → **Claude.ai**.

Conséquence pratique : la **Phase B** sera probablement réduite par rapport à la spec d'origine : TTS et reprise de session restent dans Compagnon, le reste peut passer côté Cowork sans coder.

### Et si Compagnon ne convient finalement pas pour réviser ?

Hypothèse à tenir ouverte. Compagnon a des désavantages cumulés (cf. § "Limites assumées" ci-dessus) qui peuvent rendre l'outil inadapté à un usage régulier de révision :

- **Latence 5h capée** (~18-22 tours par session 5h sur Pro Max).
- **Latence par tour potentiellement >5 min** en mode guidé (cascade tool calls).
- **Densité de réponse** parfois trop élevée malgré le cap à 2 concepts/réplique.
- **Whisper qui hallucine** sur les longs silences (banner de détection ajouté en v8, mais résiduel).
- **Tableaux/Karnaughs visuels** rendus en ASCII ou en table Markdown : moins lisible qu'une slide PDF dédiée.

Si l'expérience montre que ces frottements coûtent plus de temps qu'ils n'en font gagner, le repli est **claude.ai** (chat web, format conversationnel libre) ou **Claude Cowork** (agent desktop avec accès filesystem) avec un prompt système adapté à chacune des 3 postures pédagogiques (colle / lecture / guidé). Ces prompts seront rédigés et stockés dans :

- `_prompts_claude_ai/` : prompts à coller en début de conversation claude.ai (3 versions : colle, lecture, guidé)
- `_prompts_claude_cowork/` : prompts à mettre dans le system prompt d'un agent Cowork (3 versions idem)

À créer dans une prochaine conversation, en partant des prompts existants `PROMPT_SYSTEME_COMPAGNON.md` et `PROMPT_SYSTEME_GUIDE.md` mais purgés de tout ce qui est runtime Compagnon (balises, tools, format SSE, etc.).

L'expérience Compagnon reste enrichissante de toutes façons : les **3 prompts pédagogiques (colle/lecture/guidé)** sont l'apport principal (ils encodent une posture de tuteur exigeant rare à obtenir d'un LLM par défaut, et restent utilisables ailleurs). Le runtime Compagnon (Whisper, GUI, capture WP) est secondaire et remplaçable.

---

## Pourquoi ce projet existe

J'avais déjà construit RoleplayOverlay (lecture passive de scripts oraux figés) et ça ne m'a pas aidé à apprendre : je lisais sans comprendre. La révision active à voix haute avec un interlocuteur exigeant me manquait : une vraie colle, pas un prof bienveillant qui valide tout.

Le compagnon résout ce trou : il connaît mon TD, il m'interroge sec, il refuse mes formulations floues, et en fin de séance il fait un débrief des points où j'ai galéré.

Cible : réussir CC3 en mai-juin 2026 sans avoir à aller à la BU pour me forcer à réviser.

---

## 🌐 Présentation publique : vision portfolio (post-CC3)

> Cette section capture une intention de communication et d'archi web pour **présenter publiquement** mes projets une fois les CC3 passés. Pas d'implémentation prévue avant les grandes vacances 2026 (mai-juin → fin août). Notes prises pour ne pas perdre le fil.

### Contexte

Échange Discord avec un proche (2026-05-07, ~23h). En 2 mois j'ai produit plusieurs projets non-triviaux que je ne montre nulle part publiquement :

- **BotGSTAR** : bot Discord multi-cogs (cours, RSS tech, RSS politique, arsenal vidéo)
- **Arsenal_Arguments** : pipeline veille vidéo politique 6 plateformes avec transcription Whisper GPU + résumé Claude
- **Compagnon_Revision** : runtime de colle d'oral vocale (ce projet)
- **RoleplayOverlay** : lecture passive de scripts oraux (antérieur, archivé)
- **NosTale scrape_events** : projet jeu (archivé)

Plan de présentation :

- **LinkedIn** : déjà démarré, [profil](https://www.linkedin.com/in/gaylord-aboeka-538bb4370/) + [section projets](https://www.linkedin.com/in/gaylord-aboeka-538bb4370/details/projects/). Quelques projets déjà listés brut, à enrichir avec démos vidéo et liens vers sites de présentation.
- **Instagram** : format **face caméra**, je parle de chaque projet : la friction d'origine, le pivot d'archi, le retour d'usage. Plus narratif que LinkedIn.
- **Sites web** : un site dédié par projet majeur (démo + doc + lien GitHub), centralisés sous un domaine personnel.

### Architecture web envisagée

Conseil d'un proche (à retenir) : **un domaine personnel unique** plutôt que N domaines séparés. Trois variantes :

| Approche | Exemple | Pour | Contre |
|---|---|---|---|
| (a) Pages sous le même domaine | `gaylordaboeka.fr/compagnon`, `gaylordaboeka.fr/arsenal` | Setup minimal, un seul DNS, un seul certificat TLS, SEO concentré | Couplage front fort, harder de spec un projet vraiment indépendant |
| (b) Sous-domaines | `compagnon.gaylordaboeka.fr`, `arsenal.gaylordaboeka.fr` | Stack technique indépendante par projet (Flask vs Next.js etc.), isolation propre | Wildcard cert + DNS par sous-domaine, légèrement plus de boilerplate |
| (c) Domaines séparés | `nostar.fr`, `arsenal-veille.fr`, etc. | Branding fort par projet | Coût domaines × N, SEO dilué, signal « pas portfolio » |

**Choix probable : (a) ou (b)**, avec hub central `gaylordaboeka.fr` qui liste tous les projets en home + redirige vers chacun. (c) écarté : trop dispersé, pas de signal portfolio cohérent.

**Nom de domaine tranché (2026-05-21) : `gaylordaboeka.fr`.** Cohérent avec le handle Insta `@gaylordaboeka` (que je spamme dans les vidéos face cam), unique au monde, aucune confusion possible. Écartés : `gaylord.fr` (prénom trop commun, probablement déjà pris), `nostar.fr` / `praseodyme.net` (sous-domaines des projets d'un proche : mauvais signal portfolio, mauvais SEO racine), `gaboeka.fr` (moins lisible/mémorisable). Sous-pages vs sous-domaines = arbitrage projet par projet selon vocation marque autonome.

**Hébergement (2026-05-21) : workspace unique chez un proche.** `gaylordaboeka.fr` + le clone de `nostar.fr` (template à s'inspirer) + le futur bot Gaylord cohabitent **sur le même serveur, dans un seul workspace remote tunnel**. Raison : Claude Code navigue librement entre tous les projets en une seule passe (copier un template, ajouter une feature multi-projets, déployer en bloc). Cohérent avec le Cloudflare Tunnel déjà setupé pour le Compagnon (cf. § Remote access) : même brique technique.

### Implémentation pratique (notes pour plus tard)

Stack envisagée pour le hub portfolio :

- **Hébergement** : OVH ou Cloudflare Pages (les deux ont free tier suffisant pour du contenu statique).
- **Framework hub** : statique (Astro / 11ty) ou Next.js si besoin d'interactivité. Statique préférable pour la home : chargement instantané, SEO meilleur.
- **DNS** : Cloudflare (DNS gratuit + cert TLS auto + DDoS protection) avec un wildcard `*.gaylordaboeka.fr` si on part sur l'option (b).
- **Démos live** : selon projet,
  - BotGSTAR / Arsenal : pas de démo public possible (dépend du serveur Discord), capture vidéo + screenshots seulement.
  - Compagnon : pourrait avoir une démo « bac à sable » (un seul exo de math fictif, pas mes vraies données COURS), déployée sur le sous-domaine en mode read-only.
  - RoleplayOverlay : démo possible si je l'archive proprement.
- **Vidéos face cam** : tournage en une session par projet, montage léger. Hébergement YouTube unlisted + embed iframe sur le site, ou self-hosted (poids à surveiller).

Structure type d'une page projet :

1. **Hero** : screenshot principal + une ligne de pitch.
2. **Démo vidéo** (face cam, 2-3 min) : la friction qui m'a poussé, ce que ça résout.
3. **Capture(s) d'écran** ou screencast court de l'usage.
4. **Stack technique** : badges des techs principales.
5. **Lien GitHub** + **lien démo live** quand applicable.
6. **Pourquoi ce projet existe** (paragraphe narratif : réutilise le ton des sections « Pourquoi ce projet existe » de chaque README).

### Calendrier

- **D'ici fin juin 2026** : focus exclusif révision CC3, aucune dispersion vers le portfolio.
- **Juillet-août 2026** : grandes vacances → réservées à la mise en place. Ordre probable : (1) achat domaine + DNS Cloudflare, (2) hub statique avec page placeholder pour chaque projet, (3) tournage vidéos une à une, (4) montage + publication LinkedIn/Insta avec lien vers site, (5) itération sur retours.
- **Septembre 2026 et après** : maintenance light, ajout d'un projet par-ci par-là.

Pas de scope creep avant juillet : tout ce qui touche à la présentation publique est noté ici et reporté.

### Exportation du Compagnon vers le site portfolio (notes 2026-05-14)

Le Compagnon est conçu comme un **outil perso runtime** (Flask local + GUI Tk). Une version « site portfolio » serait un **fork user-facing** avec :

- **Tableau de bord utilisateur** : galerie sessions, photos archivées par projet/matière/sujet, consignes épinglées exportables, récaps de séance.
- **Tableau de bord admin** (moi seul) : vue globale de tous les utilisateurs, leur usage, leurs sessions, modération éventuelle.
- **Auth** : OAuth Google / GitHub / passwordless email magic link.
- **Multi-tenant** : chaque utilisateur a ses sessions/photos/stickies isolés.
- **Photos organisées** : convention de nommage descriptive (cf. ci-dessous) pour que la galerie soit **lisible par un humain qui découvre un dossier** (et pas qui voit `cropped_1778745734575_v1.jpg`).

#### Convention de nommage photos (envisagée)

Aujourd'hui : `cropped_<timestamp_ms>_vN.jpg` ou `<original_name>_vN.jpg`. Lisible côté machine, illisible côté humain. Pour le portfolio public **et pour mon usage perso quand je rouvre une vieille séance**, projet de renommer via l'OCR Gemini Flash qui tourne déjà sur les photos en mode colle/découverte (photos|mixte) :

```
YYYY-MM-DD_HHMM_<kind_detected>_<short_slug>_vN.ext
```

Exemples :
- `2026-05-14_1042_table_de_verite_AND_v1.jpg`
- `2026-05-14_1055_pseudo_code_leaf2_v1.jpg`
- `2026-05-12_2230_calcul_pose_division_euclidienne_v1.jpg`

Implications tech :
- Hook au moment où l'OCR Gemini termine (`api_send_message` boucle OCR) : générer le slug + rename physique + update `rel_path` partout (transcript, session_photos, dataset.rawText des bulles).
- Script de rattrapage `_scripts/rename_photos_from_ocr.py` pour les anciennes photos : ré-run l'OCR Gemini sur les `_uploads/` existants, populate.
- Conserver l'ID original quelque part en metadata (champ `original_filename` ou `migration_log`) pour audit + rollback.
- Garde-fou : si `kind_detected == "?"` ou `completeness_pct < 50`, garde le nom original (ne pas pourrir avec un slug médiocre).
- Coût quota : ~$0.0001 par OCR Gemini Flash 2.5. 33 photos existantes × 0.0001 = négligeable.

À spec et implémenter Phase A.11 (post CC3 ou si user le demande explicitement).

### Stack back-end candidate pour le site portfolio (notes prospectives)

Pistes pour la future appli web user-facing (à arbitrer plus tard). Critères : courbe d'apprentissage (Gstar maîtrise zéro framework back), écosystème, déploiement gratuit/cheap, capacité multi-tenant, intégration ML/IA.

| Stack | Pour | Contre | Verdict |
|---|---|---|---|
| **Next.js (React + TypeScript) + Supabase** | Full-stack JS unifié, déploiement Vercel/Netlify gratuit, écosystème massif, Supabase apporte PostgreSQL + auth + storage out-of-the-box. SSR pour SEO du hub. Très utilisé en 2026, beaucoup de tutos. | TypeScript = courbe pour débutant. Mais transposable depuis le JS qu'on écrit déjà ici. | ⭐ Recommandé n°1 |
| **SvelteKit + Supabase** | Moins de boilerplate que React, syntaxe proche du HTML/CSS classique, perf top. Apprenant plus rapide. | Communauté plus petite, moins de tutos FR. | ⭐ Recommandé n°2 |
| **Astro + Supabase + îlots React/Svelte** | Excellent pour le hub portfolio statique. On peut ajouter de l'interactivité par îlots seulement où c'est utile. Vite, SEO top. | Pas idéal si l'app user-facing devient très interactive (ex: live transcript). | ⭐ Pour le HUB seul |
| **Laravel (PHP) + Inertia + Vue/React** | Framework mature, communauté FR énorme, BDD-first, génération de scaffold rapide. Si Gstar voulait apprendre PHP, c'est la meilleure porte. | Hébergement PHP moins fun que static/JS (besoin d'un VPS, Forge, ou Laravel Cloud). | Plan B si veut apprendre PHP |
| **Django (Python) + HTMX ou React** | Cohérent avec le Python du Compagnon. Django Admin gratuit pour le dashboard admin. | Hébergement moins fluide (Railway / Fly / VPS), pas aussi sexy en frontend que les options JS. | Plan B si veut rester Python |
| **FastAPI + React** | Plus moderne que Django côté Python. Async natif. Excellent pour servir une API que le Next.js front consommerait. | Mais c'est juste un back : il faut quand même apprendre un framework front à côté. | Si on garde Python pour le back uniquement |

**Recommandation perso (Claude Code)** : **Next.js + Supabase**. Raisons :
1. **Tu codes déjà du JS** (app.js, app.json), donc TypeScript n'est qu'un incrément.
2. **Supabase = back complet en 1h** : PostgreSQL hosted, auth multi-provider, storage S3-like, row-level security pour le multi-tenant.
3. **Vercel deploy = gratuit** pour le tier hobby, suffisant pour un portfolio pas viral.
4. **Écosystème UI** : Tailwind + shadcn/ui pour avoir un design propre sans CSS-from-scratch.
5. **API routes Next.js** = équivalent d'une mini-Flask intégrée, pour les endpoints custom (ex: import session JSON, OCR sur upload public).

Plan d'apprentissage (pas avant juillet 2026) :
1. **1 semaine** : tutoriel Next.js officiel (gratuit), comprendre App Router, Server Components, Server Actions.
2. **3 à 5 jours** : Supabase quickstart, auth + une table + un upload.
3. **2 semaines** : MVP du hub portfolio (juste la home + 1 projet listé).
4. **3-4 semaines** : exportation Compagnon en mode read-only (galerie sessions + photos + transcripts publics).
5. **Itération** : autres projets ajoutés un par un.

### Vision multi-projets (le site doit centraliser TOUT)

Le site portfolio doit servir de **point d'entrée unique** pour TOUS mes projets. Liste actuelle à exporter :

- **Compagnon_Revision** : galerie sessions + photos + stickies + replay transcripts (read-only)
- **Arsenal_Arguments** : dossiers vidéo politique avec résumés Claude, frames timestampées, recherche full-text
- **BotGSTAR (cog veille tech)** : digests RSS quotidiens consultables web
- **BotGSTAR (cog veille politique)** : idem catégorie Option C
- **Battle Arena** *(projet en cours côté serveur Discord ISTIC L1 G2)* : à intégrer
- **Mes musiques** : discographie / écoute
- **Programme LFI** : projet éditorial sur le programme politique LFI (point fort « parti pris assumé »)
- *Autres au fil du temps.*

**Convention de mémoire** : à chaque projet ajouté, son README doit contenir une section **« 🌐 Présentation publique »** miroir de celle-ci, avec ses notes spécifiques (stack, démo possible, captures, points narratifs). Quand on bossera sur l'export, je dirai à Claude Code « va regarder tous les README » et il ira logiquement collecter ces sections : donc important de toujours les écrire.

Memory tag à conserver côté Claude : `project_vitrine_publique_ete_2026` (existant), étendu pour mentionner cette vision multi-projets + le besoin de la convention README.
