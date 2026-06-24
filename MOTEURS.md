# MOTEURS.md : choix et arbitrage des moteurs LLM

> **À qui s'adresse ce document.** Gstar, pour avoir une référence stable
> sur le choix de moteur (Compagnon, Arsenal) sans devoir reposer la
> question à chaque fois. Et pour expliquer à un tiers (ami, recruteur,
> jury) pourquoi 5 moteurs et pas un seul.
>
> **Dernière maj** : 2026-05-21 (Phase A.12.1 : bascule du moteur Gemini par défaut).
> Prix indicatifs début 2026, à vérifier sur les consoles avant tout batch.

> **⚠ 2026-05-21 : Gemini 2.5 Pro n'est plus gratuit.**
> Google a annoncé **`gemini-3.5-flash`** le **2026-05-19** : modèle stable,
> contexte 1M, ~4× plus rapide que la génération précédente, et **accessible
> en free tier**. Dans le même mouvement, **`gemini-2.5-pro` a perdu son free
> tier** : il est désormais payant-only sur l'API Gemini.
>
> Conséquence : le Compagnon a basculé son `DEFAULT_GEMINI_MODEL` de
> `gemini-2.5-pro` vers **`gemini-3.5-flash`** le **2026-05-21** (Phase A.12.1,
> `_scripts/dialogue/claude_client.py`). Override possible via la variable
> d'env `GEMINI_MODEL` (ex. `gemini-2.5-pro` si l'on a une clé payante).
>
> Dans tout ce document, les anciennes mentions « Gemini 2.5 Pro free » sont
> **caduques** : lire « **Gemini 3.5 Flash free** ». Les limites exactes du
> free tier 3.5 Flash (RPM/RPD) ne sont pas publiées précisément et bougent :
> vérifier sur `ai.google.dev/gemini-api/docs/pricing`.

---

## 1. Les 5 moteurs supportés (et le 6ᵉ qu'on a snobbé)

Le wrapper `claude_client.ClaudeClient` (cf. `_scripts/dialogue/claude_client.py`)
expose 5 engines via une interface unique de streaming. Le choix se fait
via `_secrets/engine_pref.json` (clé `engine`) ou la barre du haut de
l'UI web.

| ID engine | Modèle | Provider | Type d'accès |
|---|---|---|---|
| `cli_subscription` | Claude Opus 4.7 (1M ctx) | Anthropic via CLI `claude --print` | Quota Pro Max |
| `api_anthropic` | Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5 | Anthropic SDK | Pay-as-you-go |
| `gemini_api` | Gemini 3.5 Flash (1M ctx) | Google `google-genai` | Free tier |
| `deepseek_api` | DeepSeek V3 (généraliste) ou R1 (raisonnement) | API OpenAI-compat | Pay-as-you-go |
| `groq_api` | Llama 3.3 70B (et autres open-weight) | API OpenAI-compat | Free tier + Dev Tier |

**Le 6ᵉ écarté volontairement : OpenAI / GPT.** Détail dans §5.

---

## 2. Tarifs comparés (par million de tokens)

Prix début 2026, à vérifier ; l'**ordre de grandeur** est stable.

| Modèle | Input $/M | Output $/M | Free tier ? |
|---|---|---|---|
| **Claude Opus 4.7** | 15.00 | 75.00 | non (mais inclus dans Pro Max via CLI) |
| **Claude Sonnet 4.6** | 3.00 | 15.00 | non |
| **Claude Haiku 4.5** | 0.80 | 4.00 | non |
| **Gemini 3.5 Flash** *(défaut Compagnon)* | voir console¹ | voir console¹ | **OUI** (free tier maintenu) |
| **Gemini 2.5 Flash** | 0.075 | 0.30 | OUI |
| ~~Gemini 2.5 Pro~~ | 1.25 | 10.00 | **non : free tier supprimé (mai 2026)** |
| **DeepSeek V3** | 0.27 | 1.10 | non (~$0 free) |
| **DeepSeek R1** | 0.55 | 2.19 | non |
| **Groq Llama 3.3 70B** | 0.59 | 0.79 | **OUI : 30 RPM / 12k TPM / 14400 RPD** |
| **Groq Llama 3.1 8B** | 0.05 | 0.08 | OUI |
| OpenAI GPT-5 | ~5.00 | ~15.00 | non |
| OpenAI GPT-4o-mini | 0.15 | 0.60 | OUI uniquement via data-sharing opt-in |

> ¹ `gemini-3.5-flash` : free tier confirmé, mais le tarif payant exact
> ($/M) n'est pas figé ici, il bouge. Voir `ai.google.dev/gemini-api/docs/pricing`.

**Hiérarchie coût input** (du moins cher au plus cher, pour les modèles
généralistes que tu utiliserais vraiment) :
Groq Llama 8B < Gemini Flash < OpenAI mini < DeepSeek V3 < DeepSeek R1 <
Groq Llama 70B < Claude Haiku < Gemini 2.5 Pro < Claude Sonnet < OpenAI GPT-5
< Claude Opus.

**Hiérarchie coût output** (souvent plus important, l'output coûtant ~3-5×
l'input) : même ordre approximatif, mais l'écart se creuse côté Anthropic
(Claude Opus à $75/M output reste l'extrême haut).

---

## 3. Free tiers réels : limites pratiques

Ce qui compte vraiment quand on veut éviter de payer.

| Provider | RPM | TPM | RPD | Context | Tracking données ? |
|---|---|---|---|---|---|
| **Gemini 3.5 Flash free** | n/d | élevé | n/d | **1M** | **OUI** (data utilisée pour entraînement) |
| **Groq Llama 3.3 70B free** | 30 | **12 000** ⚠ | **14 400** | 128k | non (open-weight hosted) |
| **Groq Llama 3.1 8B free** | 30 | 6 000 | 14 400 | 128k | non |
| Claude Pro Max (CLI subscription) | n/a | n/a | n/a (quota session 5h + hebdo 7j) | 1M (Opus 4.7) | non |
| OpenAI data-sharing | varie | varie | jusqu'à **1M tokens/jour** sur gpt-4o-mini | 128k | **OUI** (et c'est l'objet du deal) |

**Le piège du TPM Groq** : si ta session dépasse 12 000 tokens (Compagnon
TD long avec script + corrigés, Arsenal résumé long), Groq free tier
renvoie HTTP 413 « Request too large » même si tu fais 1 seule requête
par minute. **C'est le free tier le plus restrictif en pratique pour
les sessions à gros contexte.**

**Le piège Gemini free** : tes prompts/réponses peuvent être utilisés
par Google pour entraîner. Sans enjeu pour les révisions de cours, mais
problématique si tu veux des prompts business sensibles ou un portfolio
public où tu refuses d'alimenter les concurrents.

---

## 4. Use cases : quand utiliser quoi

### 4.1 Compagnon de révision (sessions interactives 1-3 par jour)

**Défaut recommandé : `gemini_api` (Gemini 3.5 Flash free).**

Justification :
- 1M context absorbe sans broncher script + corrigés + transcript long
  (souvent 30-60k tokens).
- **Free tier maintenu** (contrairement à `gemini-2.5-pro` qui l'a perdu
  en mai 2026), ce qui donne un coût zéro tant que tu restes sous les caps journaliers.
- ~4× plus rapide que la génération précédente, donc moins d'attente entre
  les tours d'une colle d'oral.
- Qualité « frontier » annoncée par Google même pour ce modèle Flash,
  suffisante pour les colles d'oral et la pédagogie pas-à-pas.

**Bascule sur `cli_subscription` (Claude Pro Max) quand** :
- Sessions sensibles que tu refuses de partager avec Google (portfolio,
  contenu non-public).
- Gemini RPD saturé (rare en pratique).
- Tu veux la qualité Opus 4.7 sur un raisonnement particulièrement fin
  (ex : preuve formelle, analyse de complexité).

**Bascule sur `groq_api` (Llama 3.3 70B) quand** :
- Quiz très court / exo standalone qui rentre dans 12k TPM.
- Tu veux des réponses ultra-rapides pour un brainstorm, autocomplete,
  validation rapide. Vitesse ~500 tok/s vs ~30-80 tok/s ailleurs.
- Tu as saturé Pro Max ET Gemini RPD.

**Bascule sur `deepseek_api` (V3 ou R1) quand** :
- Tout le reste sature et tu veux un backup payant ultra-éco.
- Tu as une question de raisonnement math/info pur où R1 peut briller
  (parfois meilleur que Claude Sonnet sur les benchmarks d'algo).

### 4.2 Arsenal Intelligence Unit (batch summarize 1478+ items)

**Défaut historique : `cli_subscription` Claude Pro Max via subprocess.**

Marche très bien (qualité Opus 4.7 + 0 € direct), mais grille les quotas
hebdo Pro Max si on lance un re-summarize de tout.

**Pour un re-summarize complet (cf. §6 ci-dessous), évaluer** :
- DeepSeek V3 (~$7) ou Groq Llama 70B paid (~$10-12) si on accepte
  ~70-85 % de la qualité Sonnet.
- Claude Sonnet 4.6 via API (~$80) pour la qualité native.

### 4.3 Rewrite ✨ (Phase v15.5+, micro-tâche one-shot)

L'engine actuel (lu via `_read_engine_pref()`), quel qu'il soit. Le
rewrite tourne autour de 300-1500 tokens in/out, c'est négligeable peu
importe le moteur. Pas d'auto-fallback : si le moteur courant n'a pas
de solde, l'utilisateur reçoit un message FR clair pour basculer
manuellement (cf. v15.6.4).

---

## 5. Pourquoi pas OpenAI / GPT

Question récurrente. La réponse honnête, en 4 points :

1. **Pas de free tier classique** comme Gemini. Les crédits offerts
   ($5-18 nouveaux comptes) expirent en 3-6 mois. Au-delà, paie.

2. **Le programme « free tokens for data sharing »** (apparu courant
   2024-2025) donne jusqu'à 1M tokens/jour gratuits, MAIS :
   - Seulement sur `gpt-4o-mini` (entry-level, ≈ Claude Haiku, pas
     GPT-5 ni GPT-4o).
   - Tes prompts/réponses sont **utilisés pour entraîner OpenAI** :
     c'est l'objet du deal, pas un effet de bord.
   - Donc même niveau que Gemini Flash en data-sharing, mais le free
     tier Gemini te donne `gemini-3.5-flash` (modèle stable récent de
     Google) sans opt-in séparé.

3. **Aucun avantage différenciant pour notre use case** :
   - Génération de code : Claude Opus/Sonnet meilleur depuis 2024.
   - Pédagogie / suivi instructions long prompt : Claude meilleur.
   - Contexte 1M : Gemini 3.5 Flash le fait gratuitement, GPT-5 ne le
     fait qu'à $5/M input.
   - Vitesse : Groq écrase tout le monde.
   - Coût bas : DeepSeek écrase OpenAI.

4. **Écosystème pas pertinent pour BotGSTAR** : pas d'usage scientifique
   précis qui nécessiterait spécifiquement un modèle OpenAI. Le projet
   peut s'en passer entièrement.

**Conclusion** : ajouter OpenAI augmenterait la complexité de la matrice
moteurs sans gain mesurable. Si un jour OpenAI sort un modèle 10×
meilleur sur un axe précis, on reconsidérera.

---

## 6. Cas d'étude : re-summarize de tout Arsenal

### 6.1 Données factuelles (état au 2026-05-09)

```
suivi_global.csv         : 1790 entrées totales
                            ├── 1478 SUCCESS (avec résumé)
                            ├──  293 PENDING
                            └──   19 FAILED

03_ai_summaries/         : 1477 fichiers .md
                          Total 6 287 KB | Moy 4 359 bytes (~1100 tokens)
                          Max 12.9 KB

02_whisper_transcripts/  : 1900 fichiers
                          Total 5.3 MB | Moy 2 902 bytes (~800 tokens)
                          Max 131 KB (~33 000 tokens)
```

### 6.2 Estimation tokens par item à re-summarize

Pour Arsenal, l'input n'est pas que le transcript :

| Composant | Tokens approx |
|---|---|
| System prompt politique/tech (multi-archétype) | 3 000 - 5 000 |
| Transcript Whisper | 800 (moy) à 33 000 (max) |
| Frames vidéo OCR (Phase Z.6) | 500 - 5 000 selon nb |
| Commentaires (jusqu'à 100) | 1 000 - 5 000 |
| Métadonnées (engagement, hashtags, profil) | 200 - 500 |
| **Total input par item (moy)** | **~10 000 - 12 000** |
| **Output (résumé final)** | **~1 200** |

Pour 1478 items à re-summarize :
- Input total : 1478 × 11 000 ≈ **16.3 M tokens input**
- Output total : 1478 × 1 200 ≈ **1.78 M tokens output**

### 6.3 Coût final par moteur (1478 items)

| Moteur | Calcul | Coût total |
|---|---|---|
| Claude Opus 4.7 API | 16.3 × $15 + 1.78 × $75 | **~$378** ⚠ |
| Claude Sonnet 4.6 API | 16.3 × $3 + 1.78 × $15 | **~$76** |
| Gemini 2.5 Pro paid | 16.3 × $1.25 + 1.78 × $10 | **~$38** |
| Claude Haiku 4.5 API | 16.3 × $0.80 + 1.78 × $4 | **~$20** |
| Groq Llama 3.3 70B paid | 16.3 × $0.59 + 1.78 × $0.79 | **~$11** |
| DeepSeek V3 | 16.3 × $0.27 + 1.78 × $1.10 | **~$6.4** |
| **Claude CLI Pro Max** | $0 facial mais grille **largement** ton hebdo | **0 € + perte de quota** |

### 6.4 Considérations qualité (vs Claude Anthropic référence)

Llama 3.3 70B (Groq) sur le use case Arsenal spécifiquement :

✅ **Bons points** :
- Compréhension du contenu vidéo et résumé factuel.
- Suivi global de la structure de sortie (sections, ton).
- Vitesse de batch : 5-10× plus rapide que Claude.

⚠️ **Risques connus** :
- **Suivi instructions long prompt** : Llama drift plus que Claude sur
  les system prompts > 3000 tokens. Le prompt Arsenal multi-archétype
  politique/tech est complexe : drift de format à attendre sur
  ~10-15 % des items.
- **Noms propres / dates / citations** : Llama hallucine plus. Sur du
  contenu politique français où la précision des citations compte
  (« qui a dit quoi quand »), c'est un risque réel.
- **Nuances FR** : Llama est multilingue mais surpondéré anglais.
  Claude/Gemini sont entraînés massivement sur du FR donc captent
  mieux les implicites idiomatiques.

DeepSeek V3 sur le même use case : qualité **comparable à Llama 70B**,
peut-être légèrement meilleur sur le raisonnement structuré, mais
moins testé sur le FR politique. Coût ~40 % moins cher.

### 6.5 Recommandation

**Avant de lancer le batch complet** :
1. **Test ciblé** : prends 5-10 items représentatifs (1 court, 1 long,
   1 avec frames, 1 politique, 1 tech). Re-summarize avec Groq Llama
   3.3 70B et DeepSeek V3 en parallèle. Compare avec Claude.
2. Si la dérive de qualité te convient → batch sur le moteur le moins
   cher (DeepSeek V3 à ~$7).
3. Sinon → Claude Sonnet 4.6 API à ~$80 reste raisonnable, qualité
   Anthropic-grade.
4. **Ne JAMAIS** faire le batch sur Claude CLI Pro Max : tu griller
   ton quota hebdo en quelques heures et tu te coupes le Compagnon
   pour les jours suivants.

**Anti-conseil** : ne lance pas un batch sur Gemini free tier non plus.
1500 RPD = il te faudrait ~24 heures de batch ininterrompu, et le free
tier peut couper sans préavis. Si tu choisis Gemini, prends le tier
payant.

---

## 7. Hiérarchie de bascule recommandée (en cas de panne)

Quand un moteur saute (quota, solde, rate limit, contexte trop grand),
la liste à essayer dans l'ordre :

1. **Gemini 3.5 Flash free** (par défaut sur le Compagnon).
2. **Claude CLI Pro Max** (sessions sensibles, ou Gemini saturé).
3. **Groq Llama 70B free** (sessions courtes < 12k TPM).
4. **DeepSeek V3** (backup payant ultra-éco).
5. **Claude Sonnet 4.6 API** (qualité Anthropic-grade payante).
6. **Claude Opus 4.7 API** (luxury, raisonnement le plus fin).

L'UI te montre l'erreur en français avec une suggestion d'action et
fait clignoter le sélecteur de moteur (Phase v15.6.4). **Pas
d'auto-fallback** : tu restes maître du choix.

---

## 8. À surveiller dans le futur

- **OpenAI** peut sortir un modèle 10× meilleur sur un axe précis
  (raisonnement, code, agent). Reconsidérer si ça arrive.
- **Mistral** : pas dans la matrice actuelle, mais le free tier (le
  Chat) est généreux. À évaluer si Gemini se restreint.
- **Anthropic Claude Opus 5** : annoncé courant 2026 ? Update si sortie.
- **Gemini free tier** : Google fait bouger ses tiers ; en **mai 2026**,
  `gemini-2.5-pro` a perdu son free tier (d'où la bascule sur
  `gemini-3.5-flash`, cf. encadré en tête de document). Garder
  DeepSeek/Groq en backup configurés au cas où 3.5 Flash se restreigne
  à son tour.
- **Groq Dev Tier** : si le free tier 12k TPM devient bloquant pour
  Compagnon, le Dev Tier (~$0.59/M input) reste le moins cher du marché
  pour Llama 70B. Évaluer le passage en payant si volume Arsenal +
  Compagnon devient sérieux.