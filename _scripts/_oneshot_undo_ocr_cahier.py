"""Undo des faux positifs : les cartes CAHIER qui sont en realite des OCR
de photo du tuteur (preceded by `📸 Ce que je lis dans votre photo`).
Detection : `<<<CAHIER>>>...<<<END>>>` precede des ~200 chars par un trigger
OCR. Revert : restore depuis `text_history[]` la version sauvegardee, OU
defaire le tag CAHIER en blockquote standard.
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(r'C:/Users/Gstar/OneDrive/Documents/BotGSTAR/Compagnon_Revision/_sessions')

SESSIONS = [
    '2026-05-14_PRG2_TP8_exfull_decouverte_photos_strict_1.json',
    '2026-05-15_PRG2_TP9_exfull_decouverte_photos_strict_1.json',
    '2026-05-14_AN1_CCT_exfull_decouverte_photos_consultatif_1.json',
]

OCR_HEADER_RE = re.compile(
    r'(📸|Ce que je lis dans (votre|ta) photo|Lecture de (votre|ta) photo)',
    re.IGNORECASE,
)
CAHIER_RE = re.compile(r'<<<CAHIER([^>]*)>>>([\s\S]*?)<<<END>>>')


def _is_ocr_card(text, card_start):
    """Le bloc CAHIER qui commence a `card_start` est-il un faux positif OCR ?
    Heuristique : trigger OCR dans les 200 chars qui precedent."""
    window_start = max(0, card_start - 250)
    window = text[window_start:card_start]
    return bool(OCR_HEADER_RE.search(window))


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


def revert_message(text):
    """Detecte les CAHIER OCR faux-positifs et les decapsule en blockquote.
    Retourne (nouveau_texte, nb_reverts)."""
    reverts = [0]

    def replace(m):
        card_start = m.start()
        if _is_ocr_card(text, card_start):
            # Restore en blockquote standard
            attrs, body = m.group(1), m.group(2)
            # Strip les balises couleur eventuelles
            clean = re.sub(r'\{(?:bleu|rouge|vert|noir|hl-(?:jaune|vert|rose|violet))\}([\s\S]*?)\{/(?:bleu|rouge|vert|noir|hl-(?:jaune|vert|rose|violet))\}', r'\1', body)
            # Ajoute prefixe `> ` sur chaque ligne
            quoted_lines = ['> ' + line for line in clean.strip().split('\n')]
            reverts[0] += 1
            return '\n'.join(quoted_lines)
        return m.group(0)

    new_text = CAHIER_RE.sub(replace, text)
    return new_text, reverts[0]


def main():
    total = 0
    for sname in SESSIONS:
        p = ROOT / sname
        if not p.exists():
            print('!! manque :', sname)
            continue
        d = json.loads(p.read_text(encoding='utf-8'))
        msgs = d.get('messages') or {}
        n_reverted = 0
        for mid, m in msgs.items():
            if m.get('role') != 'claude':
                continue
            text = m.get('text') or ''
            if '<<<CAHIER' not in text:
                continue
            new_text, nrev = revert_message(text)
            if nrev > 0 and new_text != text:
                m.setdefault('text_history', [])
                m['text_history'].append({
                    'replaced_at': '2026-05-15T_ocr_revert',
                    'text': text,
                })
                m['text'] = new_text
                n_reverted += nrev
        total += n_reverted
        if n_reverted > 0:
            _rebuild_transcript(d)
            tmp = p.with_suffix(p.suffix + '.tmp')
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(tmp, p)
        print('  ' + sname[:55] + ' : ' + str(n_reverted) + ' OCR faux positifs revert')
    print()
    print('TOTAL :', total, 'cards OCR-faux-positif decapsulees.')


if __name__ == '__main__':
    main()
