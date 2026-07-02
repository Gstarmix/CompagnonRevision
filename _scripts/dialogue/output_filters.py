"""Filtres de post-process appliqués sur la sortie complète du tuteur.

Phase A.7.2 v15 : guardrails déterministes contre les dérives connues du
modèle Claude (CLI subscription) en mode guidé :

1. **Role hijacking** : le tuteur invente parfois un dialogue
   ``USER: ... ASSISTANT: ...`` et simule des bulles de l'étudiant.
   Cause : exemples de dialogue dans le prompt système qui sont pris
   pour des templates. Le filtre détecte ces patterns et les retire.

2. **Récitation du prompt** : le tuteur recopie parfois textuellement
   des règles du prompt système (« RÈGLE INVIOLABLE », « Cas réel à NE
   JAMAIS reproduire »…). Le filtre détecte les phrases-signatures du
   prompt et les retire de la sortie.

Approche : ces filtres sont déterministes (regex + matching de strings),
appliqués sur la sortie complète après le streaming du tuteur, avant
stockage dans le transcript et dans le _history du ClaudeClient. Ainsi
le tuteur ne voit pas ses propres hallucinations dans son contexte au
prochain tour (effet de ricochet évité).

Les filtres retournent un tuple ``(filtered_text, removed_count)`` pour
permettre au caller de logger les retraits et d'avertir si trop de
filtrage (signe que le tuteur dérive franchement → peut-être déclencher
une régénération automatique).
"""
from __future__ import annotations

import re
from typing import Optional

# ============================================================ Role hijacking

# Préfixes de rôle qui signalent un dialogue simulé halluciné par le modèle.
_ROLE_PREFIXES = (
    "USER", "ASSISTANT", "AI", "HUMAN", "SYSTEM",
    "ÉTUDIANT", "ETUDIANT", "TUTEUR", "COMPAGNON",
)

# Match en début de ligne (cas net : « \nUSER: blabla »)
_ROLE_PREFIX_LINE_RE = re.compile(
    r"^\s*(?:" + "|".join(re.escape(p) for p in _ROLE_PREFIXES) + r"):\s+",
    re.IGNORECASE | re.MULTILINE,
)

# Match inline avec préfixe markdown gras/italique (cas piégeant :
# « **USER: ...** ») ou en début de ligne, ou après ponctuation.
# Le lookbehind ``(?<![A-Za-zÀ-ÿ])`` garantit qu'on ne match PAS
# « previously stored as USER:... » (où USER est précédé d'une lettre).
_ROLE_INLINE_RE = re.compile(
    r"(?<![A-Za-zÀ-ÿ])(?:" + "|".join(re.escape(p) for p in _ROLE_PREFIXES) + r"):\s",
    re.IGNORECASE,
)


def strip_role_hijacking(text: str) -> tuple[str, int]:
    """Détecte et retire les patterns de dialogue user/assistant halluciné.

    Stratégie en deux passes :

    1. **Lignes complètes** : si une ligne commence par ``USER:``,
       ``ASSISTANT:``, etc. (avec ``\\s*`` initial), on la retire entièrement.
    2. **Inline** : si le texte contient le pattern n'importe où ailleurs
       (ex: ``... 2. **USER: Slide 2. ASSISTANT: ...**``), on **coupe
       tout à partir de la première occurrence**. Le tuteur a basculé en
       mode dialogue simulé : la suite ne peut être que dérivée.

    Le compteur retourné est le total des lignes ou occurrences retirées.

    >>> strip_role_hijacking("Bon résumé.\\nUSER: OK\\nASSISTANT: Bien.")
    ('Bon résumé.', 2)
    >>> strip_role_hijacking("Le user a posé une question importante.")
    ('Le user a posé une question importante.', 0)
    >>> out, n = strip_role_hijacking("Allez-y. **USER: Slide 2.** Suite")
    >>> n > 0
    True
    >>> "USER:" in out
    False
    """
    if not text:
        return text, 0

    # Passe 1 : retire les lignes qui commencent par un préfixe rôle
    lines = text.split("\n")
    kept = []
    removed = 0
    for line in lines:
        if _ROLE_PREFIX_LINE_RE.match(line):
            removed += 1
            continue
        kept.append(line)
    out = "\n".join(kept)

    # Passe 2 : si encore une occurrence inline (cas markdown bold,
    # ponctuation, etc.), coupe tout à partir de la première.
    inline_match = _ROLE_INLINE_RE.search(out)
    if inline_match:
        cut_pos = inline_match.start()
        # Compte les rôles dans la portion coupée pour stat
        cut_portion = out[cut_pos:]
        n_inline = len(_ROLE_INLINE_RE.findall(cut_portion))
        # Recule le cut jusqu'au début du markdown bold/italique le plus
        # proche pour ne pas laisser un `**` orphelin (« **USER »).
        # Cherche dans les 5 chars avant la position pour des * ou _.
        backtrack_zone = out[max(0, cut_pos - 5):cut_pos]
        m = re.search(r"[*_]+\s*$", backtrack_zone)
        if m:
            cut_pos -= len(backtrack_zone) - m.start()
        out = out[:cut_pos]
        removed += n_inline

    if removed == 0:
        return text, 0

    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out, removed


# ============================================================ Récitation du prompt

# Phrases-signatures du prompt système qui ne devraient JAMAIS apparaître
# textuellement dans la sortie du tuteur. Si on les détecte, le tuteur a
# recopié des morceaux de mes instructions au lieu de les appliquer.
# Insensible à la casse (le tuteur peut capitaliser différemment).
_RECITED_PROMPT_PHRASES = (
    "RÈGLE INVIOLABLE",
    "REGLE INVIOLABLE",
    "Cas réel à NE JAMAIS reproduire",
    "Cas reel a NE JAMAIS reproduire",
    "[Note système :",
    "[Note systeme :",
    "Pas de balise NEXT_SLIDE",
    "Pas de balise GOTO_SLIDE",
    "Attendez que l'étudiant lise et réagisse",
    "Attendez que l'etudiant lise et reagisse",
    "Pas de commentaire sur le contenu de la slide",
    "vous ne récitez pas ces règles",
    "vous ne recitez pas ces regles",
)


def strip_recited_rules(text: str) -> tuple[str, int]:
    """Détecte les phrases du prompt système recopiées dans la sortie.

    Quand la sortie contient une de ces phrases-signatures, c'est que le
    tuteur récite mes instructions au lieu de les appliquer. Le filtre
    retire le paragraphe contenant la phrase (du dernier saut de ligne
    avant au prochain saut de ligne après).

    Retourne ``(filtered_text, n_paragraphs_removed)``.

    >>> _, n = strip_recited_rules("Bon résumé.\\n\\nRÈGLE INVIOLABLE: ...")
    >>> n
    1
    >>> strip_recited_rules("Réponse normale du tuteur.")
    ('Réponse normale du tuteur.', 0)
    """
    if not text:
        return text, 0
    # Lower-cased pour le match (les phrases-signatures sont déjà comparées
    # case-insensitive via .lower()). On retire ensuite par paragraphes.
    text_lower = text.lower()
    flagged = False
    for phrase in _RECITED_PROMPT_PHRASES:
        if phrase.lower() in text_lower:
            flagged = True
            break
    if not flagged:
        return text, 0
    # Retire les paragraphes qui contiennent une phrase-signature
    paragraphs = re.split(r"\n\s*\n", text)
    kept = []
    removed = 0
    for para in paragraphs:
        para_lower = para.lower()
        contains_recited = any(
            phrase.lower() in para_lower for phrase in _RECITED_PROMPT_PHRASES
        )
        if contains_recited:
            removed += 1
            continue
        kept.append(para)
    out = "\n\n".join(kept).strip()
    return out, removed


# ============================================================ Validation positionnelle balises

# Une balise <<<NEXT_SLIDE>>> n'a de sens qu'à la TOUTE FIN du message.
# Si elle apparaît au milieu, c'est que le tuteur a inventé un dialogue
# où il décrit l'effet d'une transition (ex: « j'émets <<<NEXT_SLIDE>>>
# ici ») au lieu de réellement la déclencher. On retire ces occurrences
# orphelines, en gardant seulement la dernière si elle est en queue.
_NEXT_SLIDE_TAG = "<<<NEXT_SLIDE>>>"


def has_pending_question(text: str) -> bool:
    """True si le texte se termine par une question (point d'interrogation
    final, après strip whitespace et éventuelle balise NEXT_SLIDE).

    Sert de garde-fou : si le tuteur pose une question, la transition
    automatique de slide doit être bloquée : l'étudiant doit avoir le
    temps de répondre. Heuristique conservative : on regarde uniquement
    le dernier caractère significatif, pas l'analyse sémantique.

    >>> has_pending_question("Bon résumé. Vous me les énumérez ?")
    True
    >>> has_pending_question("Bon résumé. <<<NEXT_SLIDE>>>")
    False
    >>> has_pending_question("Vous me les énumérez ? <<<NEXT_SLIDE>>>")
    True
    """
    if not text:
        return False
    stripped = text.rstrip()
    if stripped.endswith(_NEXT_SLIDE_TAG):
        stripped = stripped[: -len(_NEXT_SLIDE_TAG)].rstrip()
    # Retire d'éventuels retours de ligne, ponctuation finale légère
    return stripped.endswith("?")


def strip_next_slide_if_pending_question(text: str) -> tuple[str, int]:
    """Retire la balise <<<NEXT_SLIDE>>> finale si le texte contient une
    question (le tuteur ne devrait pas avancer la slide quand il vient de
    poser une question : l'étudiant doit avoir le temps de répondre).

    Retourne ``(text, n_removed)``.
    """
    if _NEXT_SLIDE_TAG not in text:
        return text, 0
    if not has_pending_question(text):
        return text, 0
    out = text.rstrip()
    if out.endswith(_NEXT_SLIDE_TAG):
        out = out[: -len(_NEXT_SLIDE_TAG)].rstrip()
        return out, 1
    return text, 0


def strip_misplaced_next_slide(text: str) -> tuple[str, int]:
    """Garde uniquement le ``<<<NEXT_SLIDE>>>`` final, retire les autres.

    Le tuteur peut écrire la balise en plein milieu d'un paragraphe
    (« je vais émettre <<<NEXT_SLIDE>>> pour passer ») au lieu de la mettre
    seule à la toute fin. Ces occurrences au milieu doivent être ignorées :
    seule la dernière, en fin de message, déclenche une vraie transition.

    Retourne ``(text, n_misplaced_removed)``. La balise finale (si présente
    en queue) est conservée telle quelle.

    >>> strip_misplaced_next_slide("OK <<<NEXT_SLIDE>>> la suite. <<<NEXT_SLIDE>>>")
    ('OK la suite. <<<NEXT_SLIDE>>>', 1)
    >>> strip_misplaced_next_slide("Réponse propre. <<<NEXT_SLIDE>>>")
    ('Réponse propre. <<<NEXT_SLIDE>>>', 0)
    >>> strip_misplaced_next_slide("Pas de balise du tout.")
    ('Pas de balise du tout.', 0)
    """
    if _NEXT_SLIDE_TAG not in text:
        return text, 0
    count = text.count(_NEXT_SLIDE_TAG)
    if count == 1:
        # Une seule balise. Elle doit être en fin (ignorant le whitespace
        # de queue). Sinon on la retire.
        if text.rstrip().endswith(_NEXT_SLIDE_TAG):
            return text, 0
        return text.replace(_NEXT_SLIDE_TAG, ""), 1
    # Plusieurs occurrences : on garde la dernière si elle est en fin,
    # on retire toutes les autres.
    last_idx = text.rfind(_NEXT_SLIDE_TAG)
    after_last = text[last_idx + len(_NEXT_SLIDE_TAG):]
    last_is_at_end = after_last.strip() == ""
    if last_is_at_end:
        # Garde la dernière, retire toutes les précédentes
        before = text[:last_idx].replace(_NEXT_SLIDE_TAG, "")
        out = before + text[last_idx:]
        return out, count - 1
    # Aucune n'est en queue → on retire toutes
    return text.replace(_NEXT_SLIDE_TAG, ""), count


# ============================================================ Hallucination OCR photo

# Phase A.8.4 : bloc OCR halluciné par le tuteur quand il n'y a pas
# d'image dans le user message. Bug observé 2026-05-12 session PSI
# TP_Shannon : user oublie d'attacher la photo, tuteur invente une
# transcription complète sous `📸 Ce que je lis dans votre photo :`.
#
# Stratégie : si user_had_image=False et qu'on détecte le bloc OCR,
# on retire tout le bloc (du marker `📸` jusqu'à la fin du bloc citation
# blockquote `>` qui suit) + un éventuel paragraphe `Vérification : ...`
# immédiatement après.
# NOTE : on consomme aussi le \n final du marker pour que la machine à
# états démarre proprement sur la 1ʳᵉ ligne du blockquote (sinon le
# \n laissé fait virer la state machine en "after_blockquote"
# immédiatement et la transcription inventée fuite dans la sortie).
_OCR_BLOCK_START_RE = re.compile(
    r"^[\s>]*📸\s*Ce que je lis dans votre photo\s*:.*(?:\n|\Z)",
    re.MULTILINE | re.IGNORECASE,
)


def strip_hallucinated_ocr_block(
    text: str, user_had_image: bool,
) -> tuple[str, int]:
    """Retire le bloc OCR `📸 Ce que je lis dans votre photo : ...` quand
    le user_message n'avait pas d'image attachée.

    Le bloc va du marker `📸 Ce que je lis dans votre photo :` jusqu'à
    la fin du bloc citation blockquote qui le suit (lignes commençant
    par `>`), plus un éventuel paragraphe `Vérification : ...`. Si le
    bloc se prolonge sans blockquote (forme libre), on retire tout
    jusqu'à la prochaine ligne vide.

    Best-effort : retourne le texte inchangé si user_had_image=True
    (le bloc est légitime puisqu'une photo a vraiment été envoyée).

    Returns: (filtered_text, removed_count). removed_count = 1 si le bloc
    a été retiré, 0 sinon.
    """
    if user_had_image:
        return text, 0
    match = _OCR_BLOCK_START_RE.search(text)
    if not match:
        return text, 0
    start = match.start()
    # Machine à états pour consommer le bloc OCR + éventuel paragraphe
    # `Vérification : ...` qui suit, sans déborder sur la suite légitime.
    #
    # États :
    #   "in_blockquote"   : on consomme les lignes `> ...` du blockquote
    #                       de transcription OCR
    #   "after_blockquote" : blockquote fini, on attend un éventuel
    #                       paragraphe `Vérification : ...`
    #   "in_verif"        : on consomme les lignes du paragraphe Vérification
    #   "done"            : tout consommé, on s'arrête au prochain contenu
    lines_after = text[match.end():].splitlines(keepends=True)
    consumed = 0
    state = "in_blockquote"
    seen_blockquote_line = False
    for line in lines_after:
        stripped = line.strip()
        if state == "in_blockquote":
            if stripped.startswith(">"):
                consumed += len(line)
                seen_blockquote_line = True
                continue
            if not stripped:
                consumed += len(line)
                # Si on a déjà vu une ligne blockquote, fin du blockquote.
                # Sinon, on tolère les blank lines initiales (entre le
                # marker `📸...` et le `> contenu` du blockquote).
                if seen_blockquote_line:
                    state = "after_blockquote"
                continue
            # Ligne non-blockquote non-vide → fin du bloc OCR
            break
        if state == "after_blockquote":
            if not stripped:
                consumed += len(line)  # blank line(s) supplémentaire(s)
                continue
            if stripped.lower().startswith("vérification"):
                consumed += len(line)
                state = "in_verif"
                continue
            # Autre paragraphe → fin du bloc (pas de Vérification)
            break
        if state == "in_verif":
            if not stripped:
                consumed += len(line)
                state = "done"
                continue
            # Ligne du paragraphe Vérification (continuation)
            consumed += len(line)
            continue
        # state == "done" → on s'arrête au premier contenu légitime
        break
    end = match.end() + consumed
    filtered = text[:start] + text[end:]
    # Cleanup : normalise les newlines multiples laissées par la coupe
    filtered = re.sub(r"\n{3,}", "\n\n", filtered).strip()
    return (filtered + "\n" if filtered else ""), 1


# ============================================================ Pipeline complet

def _capitalize_first_letter(text: str) -> str:
    """Si le texte commence par une lettre minuscule (cas qui peut survenir
    après un filtrage qui a coupé un préfixe), on capitalise la première
    lettre. Cosmétique : évite des bulles « nouvelle slide à l'écran »
    avec n minuscule en début. On ne touche pas si commence par chiffre,
    ponctuation, emoji, balise markdown, etc.

    >>> _capitalize_first_letter("nouvelle slide à l'écran")
    "Nouvelle slide à l'écran"
    >>> _capitalize_first_letter("**Bold**")
    '**Bold**'
    >>> _capitalize_first_letter("📍 Slide 2")
    '📍 Slide 2'
    """
    if not text:
        return text
    # Trouve le premier caractère alphabétique (en sautant whitespace/markdown)
    for i, ch in enumerate(text):
        if ch.isalpha():
            if ch.islower():
                return text[:i] + ch.upper() + text[i + 1:]
            return text  # déjà capitalisé
        if ch.isdigit() or ch in "*_`#~":
            return text  # markdown/emoji/digit → on ne capitalise pas
        # whitespace → continue
    return text


def apply_all_filters(
    text: str, user_had_image: bool = True,
) -> tuple[str, dict]:
    """Applique les filtres en cascade. Retourne le texte filtré + un dict
    de stats pour logger ce qui a été retiré.

    Pipeline :
      1. strip_role_hijacking → retire les lignes USER:/ASSISTANT:/...
      2. strip_recited_rules → retire les paragraphes qui recopient le prompt
      3. strip_misplaced_next_slide → retire les balises hors-position
      4. strip_next_slide_if_pending_question → retire NEXT_SLIDE si question
      5. strip_hallucinated_ocr_block → retire le `📸 Ce que je lis...`
         si user_had_image=False (Phase A.8.4)
      6. capitalize_first_letter → fix cosmétique si filtrage a fait perdre
         la majuscule initiale

    ``user_had_image`` : si True (défaut, rétrocompat), pas de filtrage OCR.
    Si False, le filtre strip_hallucinated_ocr_block est appliqué.

    Le caller logge les stats : si l'un des compteurs est élevé, c'est que
    le tuteur a franchement déraillé sur ce tour, peut-être déclencher une
    régénération automatique.
    """
    out, n_role = strip_role_hijacking(text)
    out, n_recited = strip_recited_rules(out)
    out, n_misplaced = strip_misplaced_next_slide(out)
    out, n_question_block = strip_next_slide_if_pending_question(out)
    out, n_ocr_hallu = strip_hallucinated_ocr_block(out, user_had_image)
    any_filtered = (
        n_role + n_recited + n_misplaced + n_question_block + n_ocr_hallu
    ) > 0
    if any_filtered:
        out = _capitalize_first_letter(out)
    return out, {
        "role_hijacking_lines_removed": n_role,
        "recited_paragraphs_removed": n_recited,
        "misplaced_next_slide_removed": n_misplaced,
        "next_slide_blocked_by_question": n_question_block,
        "hallucinated_ocr_block_removed": n_ocr_hallu,
        "any_filtered": any_filtered,
    }
