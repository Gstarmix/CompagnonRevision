r"""
script_parser.py : extraction des slides depuis un SCRIPT_*.md (Phase A.7.2 v5).

Le format SCRIPT_*.md (cf. `COURS/_prompts_claude_ai/SPEC_script_oral_v2.md`)
structure un cours en sections numérotées :

    ## [SLIDE 1] Titre (X min)

    > *Ton : ...*

    Texte oral à lire à voix haute.

    <<<BEAMER>>>
    \begin{frame}{...}
        ... contenu LaTeX ...
    \end{frame}
    <<<END>>>

    ## [SLIDE 2] Autre titre (Y min)
    ...

Le mode `guidé` parse cette structure pour proposer une navigation
slide-par-slide à l'étudiant. On extrait pour chaque slide :
- son **numéro** (N)
- son **titre** (string libre)
- sa **durée cible en minutes** (entier)
- le **texte oral** (entre le header `## [SLIDE N]` et le bloc Beamer)
- le **bloc Beamer** (utile pour interroger l'étudiant sur son contenu)

Cf. ARCHITECTURE.md §11 (Phase A.7.2 v5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Header de section : `## [SLIDE 7] Titre éventuel (5 min)`. La durée est
# optionnelle (certains scripts pilote n'en ont pas), le titre aussi.
# Le titre peut contenir des parenthèses (ex: `La composition (.)`), donc
# on utilise `.*?` non-greedy plutôt que `[^()\n]*?`.
_SLIDE_HEADER_RE = re.compile(
    r"^##\s+\[SLIDE\s+(\d+)\]\s*(.*?)\s*(?:\((\d+)\s*min\))?\s*$",
    re.MULTILINE | re.IGNORECASE,
)

# Bloc Beamer entre balises (peut s'étendre sur plusieurs lignes).
_BEAMER_BLOCK_RE = re.compile(
    r"<<<BEAMER>>>\s*(.*?)\s*<<<END>>>",
    re.DOTALL,
)


@dataclass
class SlideMeta:
    """Métadonnées d'une slide extraites du SCRIPT_*.md."""

    n: int                  # numéro 1-indexé
    title: str              # titre humain (peut être vide)
    duration_min: Optional[int]  # durée cible en minutes (None si non spécifiée)
    oral_text: str          # texte à lire à voix haute (sans les blocs Beamer)
    beamer_source: str      # contenu LaTeX du frame Beamer (sans les balises)


@dataclass
class ScriptStructure:
    """Structure complète d'un SCRIPT_*.md."""

    slides: list[SlideMeta] = field(default_factory=list)
    titre_global: str = ""  # titre du SCRIPT (depuis YAML frontmatter)


def parse_script(script_path: Path) -> ScriptStructure:
    """Parse un fichier ``SCRIPT_*.md`` et retourne sa structure.

    Robuste : ignore les sections sans header `## [SLIDE N]` (intro,
    métadonnées pédagogiques, récap final). Si le fichier n'existe pas
    ou est vide, retourne une structure vide.
    """
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
        # Body = entre la fin du header courant et le début du suivant
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
    """Le titre humain est dans le YAML frontmatter ``titre: '...'``."""
    m = re.search(r"^titre:\s*['\"]?([^'\"\n]+?)['\"]?\s*$",
                  content, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _split_oral_and_beamer(body: str) -> tuple[str, str]:
    """Sépare le texte oral du bloc Beamer (qui sert à interroger).

    Le texte oral est tout ce qui est AVANT le premier `<<<BEAMER>>>`.
    Le bloc Beamer est concaténé si plusieurs (rare).
    """
    beamer_blocks = _BEAMER_BLOCK_RE.findall(body)
    beamer = "\n\n".join(b.strip() for b in beamer_blocks)
    # Texte oral = body avec tous les blocs Beamer retirés
    oral = _BEAMER_BLOCK_RE.sub("", body).strip()
    # Strip aussi les indications de ton (`> *Ton : ...*`) qui ne servent
    # pas à un humain qui lit la slide
    oral = re.sub(r"^>\s*\*Ton\s*:.*?\*\s*$", "", oral,
                  flags=re.MULTILINE).strip()
    return oral, beamer
