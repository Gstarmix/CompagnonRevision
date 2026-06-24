from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
_SLIDE_HEADER_RE = re.compile(
    r"^##\s+\[SLIDE\s+(\d+)\]\s*(.*?)\s*(?:\((\d+)\s*min\))?\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_BEAMER_BLOCK_RE = re.compile(
    r"<<<BEAMER>>>\s*(.*?)\s*<<<END>>>",
    re.DOTALL,
)
@dataclass
class SlideMeta:
    n: int
    title: str
    duration_min: Optional[int]
    oral_text: str
    beamer_source: str
@dataclass
class ScriptStructure:
    slides: list[SlideMeta] = field(default_factory=list)
    titre_global: str = ""
def parse_script(script_path: Path) -> ScriptStructure:
    if not script_path.is_file():
        return ScriptStructure()
    try:
        content = script_path.read_text(encoding="utf-8")
    except OSError:
        return ScriptStructure()
    titre_global = _extract_titre_global(content)
    matches = list(_SLIDE_HEADER_RE.finditer(content))
    slides: list[SlideMeta] = []
    for i, m in enumerate(matches):
        n = int(m.group(1))
        title = (m.group(2) or "").strip()
        duration_str = m.group(3)
        duration = int(duration_str) if duration_str else None
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[body_start:body_end].strip()
        oral_text, beamer_source = _split_oral_and_beamer(body)
        slides.append(SlideMeta(
            n=n,
            title=title,
            duration_min=duration,
            oral_text=oral_text,
            beamer_source=beamer_source,
        ))
    return ScriptStructure(slides=slides, titre_global=titre_global)
def _extract_titre_global(content: str) -> str:
    m = re.search(r"^titre:\s*['\"]?([^'\"\n]+?)['\"]?\s*$",
                  content, re.MULTILINE)
    return m.group(1).strip() if m else ""
def _split_oral_and_beamer(body: str) -> tuple[str, str]:
    beamer_blocks = _BEAMER_BLOCK_RE.findall(body)
    beamer = "\n\n".join(b.strip() for b in beamer_blocks)
    oral = _BEAMER_BLOCK_RE.sub("", body).strip()
    oral = re.sub(r"^>\s*\*Ton\s*:.*?\*\s*$", "", oral,
                  flags=re.MULTILINE).strip()
    return oral, beamer