from __future__ import annotations
import re
from typing import Optional
_ROLE_PREFIXES = (
    "USER", "ASSISTANT", "AI", "HUMAN", "SYSTEM",
    "ÉTUDIANT", "ETUDIANT", "TUTEUR", "COMPAGNON",
)
_ROLE_PREFIX_LINE_RE = re.compile(
    r"^\s*(?:" + "|".join(re.escape(p) for p in _ROLE_PREFIXES) + r"):\s+",
    re.IGNORECASE | re.MULTILINE,
)
_ROLE_INLINE_RE = re.compile(
    r"(?<![A-Za-zÀ-ÿ])(?:" + "|".join(re.escape(p) for p in _ROLE_PREFIXES) + r"):\s",
    re.IGNORECASE,
)
def strip_role_hijacking(text: str) -> tuple[str, int]:
    if not text:
        return text, 0
    lines = text.split("\n")
    kept = []
    removed = 0
    for line in lines:
        if _ROLE_PREFIX_LINE_RE.match(line):
            removed += 1
            continue
        kept.append(line)
    out = "\n".join(kept)
    inline_match = _ROLE_INLINE_RE.search(out)
    if inline_match:
        cut_pos = inline_match.start()
        cut_portion = out[cut_pos:]
        n_inline = len(_ROLE_INLINE_RE.findall(cut_portion))
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
    if not text:
        return text, 0
    text_lower = text.lower()
    flagged = False
    for phrase in _RECITED_PROMPT_PHRASES:
        if phrase.lower() in text_lower:
            flagged = True
            break
    if not flagged:
        return text, 0
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
_NEXT_SLIDE_TAG = "<<<NEXT_SLIDE>>>"
def has_pending_question(text: str) -> bool:
    if not text:
        return False
    stripped = text.rstrip()
    if stripped.endswith(_NEXT_SLIDE_TAG):
        stripped = stripped[: -len(_NEXT_SLIDE_TAG)].rstrip()
    return stripped.endswith("?")
def strip_next_slide_if_pending_question(text: str) -> tuple[str, int]:
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
    if _NEXT_SLIDE_TAG not in text:
        return text, 0
    count = text.count(_NEXT_SLIDE_TAG)
    if count == 1:
        if text.rstrip().endswith(_NEXT_SLIDE_TAG):
            return text, 0
        return text.replace(_NEXT_SLIDE_TAG, ""), 1
    last_idx = text.rfind(_NEXT_SLIDE_TAG)
    after_last = text[last_idx + len(_NEXT_SLIDE_TAG):]
    last_is_at_end = after_last.strip() == ""
    if last_is_at_end:
        before = text[:last_idx].replace(_NEXT_SLIDE_TAG, "")
        out = before + text[last_idx:]
        return out, count - 1
    return text.replace(_NEXT_SLIDE_TAG, ""), count
_OCR_BLOCK_START_RE = re.compile(
    r"^[\s>]*📸\s*Ce que je lis dans votre photo\s*:.*(?:\n|\Z)",
    re.MULTILINE | re.IGNORECASE,
)
def strip_hallucinated_ocr_block(
    text: str, user_had_image: bool,
) -> tuple[str, int]:
    if user_had_image:
        return text, 0
    match = _OCR_BLOCK_START_RE.search(text)
    if not match:
        return text, 0
    start = match.start()
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
                if seen_blockquote_line:
                    state = "after_blockquote"
                continue
            break
        if state == "after_blockquote":
            if not stripped:
                consumed += len(line)
                continue
            if stripped.lower().startswith("vérification"):
                consumed += len(line)
                state = "in_verif"
                continue
            break
        if state == "in_verif":
            if not stripped:
                consumed += len(line)
                state = "done"
                continue
            consumed += len(line)
            continue
        break
    end = match.end() + consumed
    filtered = text[:start] + text[end:]
    filtered = re.sub(r"\n{3,}", "\n\n", filtered).strip()
    return (filtered + "\n" if filtered else ""), 1
def _capitalize_first_letter(text: str) -> str:
    if not text:
        return text
    for i, ch in enumerate(text):
        if ch.isalpha():
            if ch.islower():
                return text[:i] + ch.upper() + text[i + 1:]
            return text
        if ch.isdigit() or ch in "*_`#~":
            return text
    return text
def apply_all_filters(
    text: str, user_had_image: bool = True,
) -> tuple[str, dict]:
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