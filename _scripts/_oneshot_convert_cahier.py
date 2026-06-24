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
TRIGGER_RE = re.compile(
    r'(notez|prenez votre cahier|sur votre cahier|votre cahier|nouveau titre|titre\s*:|ecrivez|ecrivons|notons)',
    re.IGNORECASE,
)
QUOTE_RE = re.compile(r'((?:^|\n)(?:>\s?[^\n]*\n?){2,})', re.MULTILINE)
def _strip_quote_prefix(quote_block):
    lines = quote_block.lstrip('\n').rstrip().split('\n')
    return '\n'.join(re.sub(r'^>\s?', '', l) for l in lines)
def _extract_title(inner):
    lines = inner.split('\n')
    while lines and not lines[0].strip():
        lines.pop(0)
    if not lines:
        return '', ''
    first = lines[0].strip()
    m = re.match(r'^\*\*Titre\s*[:\.]?\s*(.+?)\*\*\s*$', first, re.IGNORECASE)
    if m:
        return m.group(1).strip(), '\n'.join(lines[1:]).strip()
    m = re.match(r'^\*\*(\d+\.\s+.+?)\*\*\s*$', first)
    if m:
        return m.group(1).strip(), '\n'.join(lines[1:]).strip()
    m = re.match(r'^\*\*(.+?)\*\*\s*$', first)
    if m:
        return m.group(1).strip(), '\n'.join(lines[1:]).strip()
    m = re.match(r'^(\d+\.\s+.+)$', first)
    if m:
        return m.group(1).strip(), '\n'.join(lines[1:]).strip()
    if len(first) < 100 and not first.endswith('.'):
        return first, '\n'.join(lines[1:]).strip()
    return '', inner.strip()
def _split_code_blocks(body):
    parts = []
    in_code = False
    buf = []
    for line in body.split('\n'):
        if line.strip().startswith('```'):
            if buf:
                parts.append(('code' if in_code else 'prose', '\n'.join(buf)))
                buf = []
            buf.append(line)
            if in_code:
                parts.append(('code', '\n'.join(buf)))
                buf = []
                in_code = False
            else:
                in_code = True
            continue
        buf.append(line)
    if buf:
        parts.append(('code' if in_code else 'prose', '\n'.join(buf)))
    return parts
def _color_after_label(text, label_re_str, color_tag, max_total, counter):
    label_re = re.compile(label_re_str, re.IGNORECASE)
    result = []
    last_end = 0
    for m in label_re.finditer(text):
        result.append(text[last_end:m.end()])
        last_end = m.end()
        if counter.get(color_tag, 0) >= max_total:
            continue
        window = text[m.end():m.end() + 400]
        bt = re.search(r'`([^`\n]+)`', window)
        if not bt:
            continue
        pre = window[:bt.start()]
        result.append(pre)
        result.append('{' + color_tag + '}' + bt.group(0) + '{/' + color_tag + '}')
        counter[color_tag] = counter.get(color_tag, 0) + 1
        last_end = m.end() + bt.end()
    result.append(text[last_end:])
    return ''.join(result)
def _color_after_exemple(text, max_per_section=3):
    label_re = re.compile(r'\*\*Exemples?\s*:\*\*', re.IGNORECASE)
    result = []
    last_end = 0
    for m in label_re.finditer(text):
        result.append(text[last_end:m.end()])
        last_end = m.end()
        window = text[m.end():m.end() + 700]
        count = 0
        window_pos = 0
        for bt in re.finditer(r'`([^`\n]+)`', window):
            if count >= max_per_section:
                break
            pre = window[window_pos:bt.start()]
            result.append(pre)
            result.append('{vert}' + bt.group(0) + '{/vert}')
            window_pos = bt.end()
            count += 1
        result.append(window[window_pos:])
        last_end = m.end() + len(window)
    result.append(text[last_end:])
    return ''.join(result)
def _apply_colors(body):
    if not body:
        return body
    if '{rouge}' in body or '{vert}' in body or '{hl-' in body:
        return body
    counter = {'rouge': 0, 'vert': 0}
    parts = _split_code_blocks(body)
    out_parts = []
    for kind, content in parts:
        if kind == 'code':
            out_parts.append(content)
            continue
        content = _color_after_label(
            content,
            r'\*\*(?:Definition|Definition|Theoreme|Theoreme|Methode|Methode|Propriete|Propriete|Concept-cle|Concept-cle)\s*:\*\*',
            'rouge', 2, counter,
        )
        content = _color_after_label(
            content,
            r'\*\*[\w\sa-zA-ZÀ-ſ\-]{3,40}\s*:\*\*',
            'rouge', 2, counter,
        )
        content = _color_after_exemple(content, max_per_section=3)
        out_parts.append(content)
    return '\n'.join(out_parts)
def convert_message(text):
    if not TRIGGER_RE.search(text):
        return text, 0
    cards_created = [0]
    def replace_quote(m):
        quote_block = m.group(1)
        inner = _strip_quote_prefix(quote_block)
        title, body = _extract_title(inner)
        if not body and not title:
            return quote_block
        body_colored = _apply_colors(body) if body else ''
        cards_created[0] += 1
        if title:
            safe_title = title.replace('"', '\\"')
            return '\n<<<CAHIER titre="' + safe_title + '">>>\n' + body_colored + '\n<<<END>>>\n'
        return '\n<<<CAHIER>>>\n' + body_colored + '\n<<<END>>>\n'
    new_text = QUOTE_RE.sub(replace_quote, text)
    return new_text, cards_created[0]
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
def main():
    total_cards = 0
    for sname in SESSIONS:
        p = ROOT / sname
        if not p.exists():
            print('!! manque :', sname)
            continue
        d = json.loads(p.read_text(encoding='utf-8'))
        msgs = d.get('messages') or {}
        n_converted = 0
        for mid, m in msgs.items():
            if m.get('role') != 'claude':
                continue
            text = m.get('text') or ''
            if '<<<CAHIER' in text:
                continue
            new_text, ncards = convert_message(text)
            if ncards > 0 and new_text != text:
                m.setdefault('text_history', [])
                m['text_history'].append({
                    'replaced_at': '2026-05-15T_cahier_migration',
                    'text': text,
                })
                m['text'] = new_text
                n_converted += ncards
        total_cards += n_converted
        if n_converted > 0:
            _rebuild_transcript(d)
            tmp = p.with_suffix(p.suffix + '.tmp')
            tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding='utf-8')
            os.replace(tmp, p)
        print('  ' + sname[:55] + ' : ' + str(n_converted) + ' cartes')
    print()
    print('TOTAL :', total_cards, 'cartes cahier appliquees retroactivement.')
if __name__ == '__main__':
    main()