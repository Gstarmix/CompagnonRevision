"""Conversion CC3 PRG2 : pattern different des autres sessions. Pas de
blockquote `>`, mais des sequences `trigger phrase + bloc ``` code ````
ou `trigger phrase + prose courte`. Le tuteur Gemini de CC3 a improvise
un format sans blockquote.

Strategie :
- Detecte le trigger phrase (`Recopiez-le`, `Sur votre cahier`, etc.)
- Cherche le 1er bloc ``` ``` qui suit dans les 500 chars
- Si trouve : wrap (titre + code block) dans <<<CAHIER>>>...<<<END>>>
- Sinon : wrap les 1-3 prochaines lignes de prose
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(r'C:/Users/Gstar/OneDrive/Documents/BotGSTAR/Compagnon_Revision/_sessions')
SESSION = '2026-05-15_PRG2_CC3_exfull_decouverte_photos_strict_1.json'

# Patterns
TRIGGER_RE = re.compile(
    r'((?:Recopiez[- ](?:le|la)|Sur votre cahier|Prenez votre cahier|Notez (?:le|la|ce|cette|votre|ces)|'
    r'votre cahier)(?:[^\n]{0,80}?))(:|\.)\s*\n',
    re.IGNORECASE,
)
CODE_BLOCK_RE = re.compile(r'```[a-z]*\n[\s\S]*?\n```')
TITLE_AFTER_TRIGGER_RE = re.compile(
    r'(?:titre|Question)\s*(?:suivant|:)?\s*(?:\*\*)?([^*\n]{3,80})(?:\*\*)?',
    re.IGNORECASE,
)


def _rebuild_transcript(d):
    msgs = d.get('messages') or {}
    transcript = d.get('transcript') or []
    branch = d.get('current_branch_path') or []
    new_transcript = []
    for mid in branch:
        m = msgs.get(mid)
        if not m:
            continue
        existing = next((e for e in transcript if e.get('id') == mid), None)
        entry = {
            'id': mid,
            'role': m.get('role'),
            'text': m.get('text', ''),
            'at': m.get('at') or (existing.get('at') if existing else ''),
        }
        if existing:
            for k in ('photo_paths', 'tts_marker', 'edited', 'edited_at'):
                if k in existing:
                    entry[k] = existing[k]
        new_transcript.append(entry)
    d['transcript'] = new_transcript


def convert_cc3_message(text):
    """Pour CC3 : detecte plusieurs patterns sans blockquote.

    Pattern A : trigger + ```code``` (le plus simple).
    Pattern B : trigger + prose multiligne suivante (1-5 lignes).
    """
    cards_created = [0]

    # Pattern A : trigger phrase + ``` block ``` (prioritaire)
    # Tolère whitespace entre la phrase trigger et la ponctuation finale
    # (« Recopiez-le :\n``` » avait un espace avant `:` qu'on ratait).
    pattern_a = re.compile(
        r'((?:Recopiez[- ](?:le|la)|Sur votre cahier[^\n]*|Prenez votre cahier[^\n]*|'
        r'Notez (?:le|la|ce|cette|ces|votre)[^\n]*|votre cahier[^\n]*?))\s*(?::|\.)\s*\n+'
        r'(```[a-z]*\n[\s\S]*?\n```)',
        re.IGNORECASE,
    )

    def replace_a(m):
        trigger = m.group(1).strip()
        code_block = m.group(2)
        ctx_start = max(0, m.start() - 250)
        ctx = text[ctx_start:m.start()]
        title = ''
        ttl = re.search(r'\*\*(Question\s+\d+[^\n*]{0,60}|\d+\.\s+[^\n*]{3,80})\*\*', ctx)
        if ttl:
            title = ttl.group(1).strip()
        else:
            ttl2 = re.search(r'titre\s*(?:suivant)?\s*:\s*\*\*([^*\n]{3,80})\*\*', trigger, re.IGNORECASE)
            if ttl2:
                title = ttl2.group(1).strip()
        cards_created[0] += 1
        attr = f' titre="{title}"' if title else ''
        return f'{trigger} :\n\n<<<CAHIER{attr}>>>\n{code_block}\n<<<END>>>\n'

    new_text = pattern_a.sub(replace_a, text)

    # Pattern B : trigger phrase + prose paragraphe suivant (sans code block)
    # On ne match QUE si pas deja convert (donc skip les <<<CAHIER>>> existants)
    pattern_b = re.compile(
        r'((?:Recopiez[- ](?:le|la)|Sur votre cahier[^\n]*|Prenez votre cahier[^\n]*|'
        r'Notez (?:le|la|ce|cette|ces|votre)[^\n]*?))(?::|\.)\s*\n\n'
        r'((?:[^\n<]+\n){1,8})',
        re.IGNORECASE,
    )

    def replace_b(m):
        # Skip si la prose suivante contient un CAHIER ouvert (deja convert)
        if '<<<CAHIER' in m.group(0):
            return m.group(0)
        # Skip si la prose contient un block fenced (deja matche par A)
        if '```' in m.group(2):
            return m.group(0)
        trigger = m.group(1).strip()
        body = m.group(2).rstrip()
        # Limite a 3 lignes pour eviter de wrapper trop
        body_lines = body.split('\n')
        if len(body_lines) > 5:
            return m.group(0)  # trop long, probablement pas un cahier moment
        ctx_start = max(0, m.start() - 250)
        ctx = text[ctx_start:m.start()]
        title = ''
        ttl = re.search(r'\*\*(Question\s+\d+[^\n*]{0,60}|\d+\.\s+[^\n*]{3,80})\*\*', ctx)
        if ttl:
            title = ttl.group(1).strip()
        cards_created[0] += 1
        attr = f' titre="{title}"' if title else ''
        return f'{trigger} :\n\n<<<CAHIER{attr}>>>\n{body.strip()}\n<<<END>>>\n\n'

    new_text = pattern_b.sub(replace_b, new_text)

    # Pattern C : trigger phrase + titre bold **Question N (...)** suivi
    # de pseudo-code bullets `* ...` (1-15 lignes). Couvre le pattern le
    # plus frequent en CC3 (« Sur votre cahier, ajoutez le titre : **Q4
    # splitAt** puis notez la logique en pseudo-code : * Cas de base
    # ... * Cas général ... »).
    # Note : le titre peut etre sur la MEME ligne que le trigger
    # (« ajoutez le titre : **Question 3 ...** ») ou sur la ligne suivante.
    pattern_c = re.compile(
        r'((?:Recopiez[- ](?:le|la)|Sur votre cahier[^\n]*?|Prenez votre cahier[^\n]*?|'
        r'Notez (?:le|la|ce|cette|ces|votre)[^\n]*?|votre cahier[^\n]*?))\s*(?::|\.)\s*'
        r'(\*\*[^*\n]{5,150}\*\*)\s*\n'
        r'((?:(?:Et |Puis,? )?[Ee]?cri[vt][^\n]*\n|[^\n<]+\n){0,4})?'
        r'(\*\s+[\s\S]*?)(?=\n\n[A-Z]|\n\n[^\s*]|\Z)',
        re.IGNORECASE,
    )

    def replace_c(m):
        # Skip si CAHIER deja present dans le snippet
        if '<<<CAHIER' in m.group(0):
            return m.group(0)
        if '```' in m.group(0):
            return m.group(0)  # deja matche par A
        trigger = m.group(1).strip()
        title_md = m.group(2)
        bridge = (m.group(3) or '').strip()
        bullets = m.group(4).strip()
        # Strip ** du titre
        title_clean = re.sub(r'^\*\*|\*\*$', '', title_md).strip()
        # Limite : si bullets > 20 lignes, skip (probable hors-cadre)
        if bullets.count('\n') > 20:
            return m.group(0)
        cards_created[0] += 1
        body = bridge + ('\n\n' if bridge else '') + bullets
        attr = f' titre="{title_clean}"' if title_clean else ''
        return f'{trigger} :\n\n<<<CAHIER{attr}>>>\n{body.strip()}\n<<<END>>>\n\n'

    new_text = pattern_c.sub(replace_c, new_text)

    # Pattern D : trigger + titre bold + prose 1-3 lignes avec inline code
    # (sans bullets, sans fenced). Couvre les definitions simples « Notez
    # le titre : **1. Type d'Arbre Binaire**. Sous ce titre, recopiez :
    # `data BT a = Leaf a | Node (BT a) a (BT a)`. ».
    pattern_d = re.compile(
        r'((?:Recopiez[- ](?:le|la)|Sur votre cahier[^\n]*?|Prenez votre cahier[^\n]*?|'
        r'Notez (?:le|la|ce|cette|ces|votre)[^\n]*?|votre cahier[^\n]*?))\s*(?::|\.)\s*'
        r'(\*\*[^*\n]{5,150}\*\*)\s*[\.\s]*\n'
        r'((?:[^\n<*]+`[^`]+`[^\n]*\n?){1,4})(?=\n\n[A-Z]|\n\n[^\s*]|\Z)',
        re.IGNORECASE,
    )

    def replace_d(m):
        if '<<<CAHIER' in m.group(0):
            return m.group(0)
        if '```' in m.group(0):
            return m.group(0)
        if re.search(r'^\s*\*\s', m.group(3) or '', re.MULTILINE):
            return m.group(0)  # bullets → pattern C job
        trigger = m.group(1).strip()
        title_md = m.group(2)
        body = m.group(3).strip()
        title_clean = re.sub(r'^\*\*|\*\*$', '', title_md).strip()
        cards_created[0] += 1
        attr = f' titre="{title_clean}"' if title_clean else ''
        return f'{trigger} :\n\n<<<CAHIER{attr}>>>\n{body}\n<<<END>>>\n\n'

    new_text = pattern_d.sub(replace_d, new_text)

    return new_text, cards_created[0]


def main():
    p = ROOT / SESSION
    if not p.exists():
        print('!! manque :', SESSION)
        return
    d = json.loads(p.read_text(encoding='utf-8'))
    msgs = d.get('messages') or {}
    n_converted = 0
    for mid, m in msgs.items():
        if m.get('role') != 'claude':
            continue
        text = m.get('text') or ''
        if '<<<CAHIER' in text:
            continue
        new_text, ncards = convert_cc3_message(text)
        if ncards > 0 and new_text != text:
            m.setdefault('text_history', [])
            m['text_history'].append({
                'replaced_at': '2026-05-15T_cahier_cc3_migration',
                'text': text,
            })
            m['text'] = new_text
            n_converted += ncards
    if n_converted > 0:
        _rebuild_transcript(d)
        tmp = p.with_suffix(p.suffix + '.tmp')
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(tmp, p)
    print('CC3 :', n_converted, 'cartes converties.')


if __name__ == '__main__':
    main()
