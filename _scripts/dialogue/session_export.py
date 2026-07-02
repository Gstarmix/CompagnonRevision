"""
session_export.py : Phase A.10.13b (2026-05-14).

Exporte une session JSON en MD + PDF on-demand. Remplace l'archive live
.md de la Phase A.8.1 (supprimée Phase A.10.11) par un générateur ponctuel
sur clic utilisateur.

Le contenu inclut (mode "compréhensif" choisi par l'user) :
- Frontmatter YAML : session_id, matière, type, num, exo, mode, engine,
  model, ancrage, colle_format, started_at, last_alive
- Header lisible : titre + date + mode
- Transcript role-balisé `## 🤖 Tuteur` / `## 👤 Étudiant`, photos
  référencées en markdown (les chemins restent `_uploads/...` ou
  `COURS/...` selon storage)
- 📋 Récap de séance phase débrief (si applicable)
- 📌 Consignes épinglées (Phase A.10)

API publique :
- ``render_session_md(data: dict) -> str``
- ``render_session_pdf_bytes(data: dict) -> bytes``

Le PDF est rendu via reportlab (mêmes patterns que l'ex-invented_pdf.py
supprimé Phase A.10.13a, mais ici le contenu est un transcript de
séance, pas un énoncé inventé).
"""

from __future__ import annotations

import io
import logging
import re
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_TRANSCRIPT_CHARS_FOR_PDF = 200_000  # cap sécurité, ~100-150 pages

_RE_H1 = re.compile(r"^#\s+(.+)$")
_RE_H2 = re.compile(r"^##\s+(.+)$")
_RE_H3 = re.compile(r"^###\s+(.+)$")
_RE_LIST_BULLET = re.compile(r"^\s*[-*]\s+(.+)$")
_RE_LIST_NUM = re.compile(r"^\s*\d+\.\s+(.+)$")
_RE_BOLD = re.compile(r"\*\*(.+?)\*\*")
_RE_ITALIC = re.compile(r"(?<!\*)\*([^*]+?)\*(?!\*)")
_RE_CODE_INLINE = re.compile(r"`([^`]+)`")
_RE_IMG_MD = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")


# ============================================================ Markdown

def render_session_md(data: dict) -> str:
    """Rend une session JSON en Markdown lisible."""
    session_id = data.get("session_id", "?")
    matiere = data.get("matiere") or "?"
    type_code = data.get("type") or "?"
    num = data.get("num") or "?"
    exo = data.get("exo") or "?"
    annee = data.get("annee")
    mode = data.get("mode") or "colle"
    engine = data.get("engine") or "?"
    model = data.get("model") or "?"
    started_at = data.get("started_at") or "?"
    last_alive = data.get("last_alive") or started_at
    colle_format = data.get("colle_format") or "mixte"
    corrige_anchor = data.get("corrige_anchor") or "strict"

    lines: list[str] = []

    # ---------- Frontmatter YAML
    lines.append("---")
    lines.append(f"session_id: {_yaml_str(session_id)}")
    lines.append(f"matiere: {_yaml_str(matiere)}")
    lines.append(f"type: {_yaml_str(type_code)}")
    lines.append(f"num: {_yaml_str(num)}")
    lines.append(f"exo: {_yaml_str(exo)}")
    if annee:
        lines.append(f"annee: {_yaml_str(annee)}")
    lines.append(f"mode: {_yaml_str(mode)}")
    lines.append(f"colle_format: {_yaml_str(colle_format)}")
    lines.append(f"corrige_anchor: {_yaml_str(corrige_anchor)}")
    lines.append(f"engine: {_yaml_str(engine)}")
    lines.append(f"model: {_yaml_str(model)}")
    lines.append(f"started_at: {_yaml_str(started_at)}")
    lines.append(f"last_alive: {_yaml_str(last_alive)}")
    if data.get("sujet_libre"):
        lines.append(f"sujet_libre: {_yaml_str(data['sujet_libre'])}")
    if data.get("workspace_root"):
        lines.append(f"workspace_root: {_yaml_str(data['workspace_root'])}")
    lines.append(f"exported_at: {_yaml_str(datetime.now().isoformat())}")
    lines.append("---")
    lines.append("")

    # ---------- Header
    annee_part = f" {annee}" if annee else ""
    sujet = data.get("sujet_libre")
    if sujet:
        lines.append(f"# Séance : sujet libre « {sujet} »")
    else:
        lines.append(f"# Séance {matiere} {type_code}{num}{annee_part} (exo {exo})")
    lines.append("")
    lines.append(
        f"**Date** : {started_at} • **Mode** : {mode} • "
        f"**Moteur** : {engine} ({model})"
    )
    lines.append("")

    # ---------- Consignes épinglées (Phase A.10)
    stickies = data.get("stickies") or []
    active_stickies = [s for s in stickies if isinstance(s, dict) and s.get("enabled", True)]
    if active_stickies:
        lines.append("## 📌 Consignes épinglées")
        lines.append("")
        for s in active_stickies:
            kind = s.get("kind") or "user"
            icon = "🤖" if kind == "tutor" else "📌"
            text = (s.get("text") or "").strip()
            lines.append(f"- {icon} {text}")
        lines.append("")

    # ---------- Transcript
    lines.append("## 💬 Conversation")
    lines.append("")
    transcript = data.get("transcript") or []
    if not transcript:
        lines.append("*(transcript vide)*")
        lines.append("")
    for entry in transcript:
        role = entry.get("role") or "?"
        text = (entry.get("text") or "").strip()
        at = entry.get("at") or ""
        if role == "claude":
            label = "🤖 Tuteur"
        elif role == "student":
            label = "👤 Étudiant"
        elif role == "system":
            label = "⚙ Système"
        else:
            label = role
        ts = _format_ts_short(at)
        lines.append(f"### {label} (*{ts}*)")
        lines.append("")
        if text:
            lines.append(text)
        lines.append("")

    # ---------- Récap de séance phase débrief
    recap = data.get("recap")
    if isinstance(recap, dict):
        lines.append("## 📋 Récap de séance (phase débrief)")
        lines.append("")
        summary = (recap.get("summary") or "").strip()
        if summary:
            lines.append("### Résumé")
            lines.append("")
            lines.append(summary)
            lines.append("")
        concepts = recap.get("concepts_covered") or []
        if concepts:
            lines.append("### Concepts couverts")
            lines.append("")
            for c in concepts:
                lines.append(f"- {c}")
            lines.append("")
        exos = recap.get("exercises_handled") or []
        if exos:
            lines.append("### Exercices traités")
            lines.append("")
            for e in exos:
                lines.append(f"- {e}")
            lines.append("")
        suggestions = recap.get("suggestions") or []
        if suggestions:
            lines.append("### Suggestions de révision")
            lines.append("")
            for s in suggestions:
                lines.append(f"- {s}")
            lines.append("")

    return "\n".join(lines)


# ============================================================ PDF

def render_session_pdf_bytes(data: dict) -> bytes:
    """Rend une session JSON en PDF (bytes prêts à download)."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, ListFlowable, ListItem,
            Preformatted,
        )
        from reportlab.lib.enums import TA_LEFT
    except ImportError as e:
        raise ImportError(
            f"reportlab indisponible ({e}). pip install reportlab"
        ) from e

    md_text = render_session_md(data)
    if len(md_text) > _MAX_TRANSCRIPT_CHARS_FOR_PDF:
        md_text = md_text[:_MAX_TRANSCRIPT_CHARS_FOR_PDF] + (
            "\n\n*[Contenu tronqué : limite atteinte.]*"
        )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("ExportH1", parent=styles["Heading1"],
                       fontSize=16, spaceAfter=10, alignment=TA_LEFT)
    h2 = ParagraphStyle("ExportH2", parent=styles["Heading2"],
                       fontSize=13, spaceAfter=8, spaceBefore=12, alignment=TA_LEFT)
    h3 = ParagraphStyle("ExportH3", parent=styles["Heading3"],
                       fontSize=11, spaceAfter=6, spaceBefore=10, alignment=TA_LEFT,
                       textColor="#444477")
    body = ParagraphStyle("ExportBody", parent=styles["BodyText"],
                         fontSize=9.5, leading=13, spaceAfter=4, alignment=TA_LEFT)
    meta = ParagraphStyle("ExportMeta", parent=styles["Italic"],
                         fontSize=8, textColor="#666666", alignment=TA_LEFT,
                         spaceAfter=8)

    flowables = []
    flowables.extend(_md_to_flowables(md_text, h1, h2, h3, body, meta, cm))

    buf = io.BytesIO()
    session_id = data.get("session_id") or "session"
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=f"Compagnon : {session_id}",
        author="Compagnon_Revision",
    )
    doc.build(flowables)
    return buf.getvalue()


def _md_to_flowables(md: str, h1_style, h2_style, h3_style, body_style,
                     meta_style, cm_unit) -> list:
    """Parse markdown minimal et retourne une liste de flowables reportlab."""
    from reportlab.platypus import (
        Paragraph, Spacer, ListFlowable, ListItem, Preformatted,
    )

    out = []
    lines = md.splitlines()
    para_buffer: list[str] = []
    list_buffer: list[str] = []
    list_is_numbered = False
    code_buffer: list[str] = []
    in_code_fence = False
    in_frontmatter = False
    frontmatter_lines: list[str] = []

    def _flush_para():
        if para_buffer:
            text = " ".join(para_buffer).strip()
            if text:
                out.append(Paragraph(_md_inline_to_html(text), body_style))
            para_buffer.clear()

    def _flush_list():
        nonlocal list_is_numbered
        if list_buffer:
            items = [
                ListItem(Paragraph(_md_inline_to_html(t), body_style))
                for t in list_buffer
            ]
            out.append(ListFlowable(
                items,
                bulletType="1" if list_is_numbered else "bullet",
                leftIndent=18,
            ))
            list_buffer.clear()
            list_is_numbered = False

    def _flush_code():
        if code_buffer:
            code_text = "\n".join(code_buffer)
            try:
                out.append(Preformatted(code_text, body_style))
            except Exception:  # noqa: BLE001
                out.append(Paragraph(_escape_html(code_text), body_style))
            code_buffer.clear()

    for line in lines:
        # Frontmatter : skip (déjà dans le header structuré)
        if line.strip() == "---":
            if not in_frontmatter and not out and not para_buffer:
                in_frontmatter = True
                continue
            elif in_frontmatter:
                in_frontmatter = False
                # Mets les méta dans le PDF aussi (compact)
                if frontmatter_lines:
                    text = " · ".join(
                        line.strip() for line in frontmatter_lines if line.strip()
                    )
                    out.append(Paragraph(_escape_html(text), meta_style))
                    frontmatter_lines.clear()
                continue
        if in_frontmatter:
            frontmatter_lines.append(line)
            continue
        # Bloc code fence ```
        if line.startswith("```"):
            if in_code_fence:
                _flush_code()
                in_code_fence = False
            else:
                _flush_para()
                _flush_list()
                in_code_fence = True
            continue
        if in_code_fence:
            code_buffer.append(line)
            continue
        # Headings
        m = _RE_H1.match(line)
        if m:
            _flush_para()
            _flush_list()
            out.append(Paragraph(_md_inline_to_html(m.group(1)), h1_style))
            continue
        m = _RE_H2.match(line)
        if m:
            _flush_para()
            _flush_list()
            out.append(Paragraph(_md_inline_to_html(m.group(1)), h2_style))
            continue
        m = _RE_H3.match(line)
        if m:
            _flush_para()
            _flush_list()
            out.append(Paragraph(_md_inline_to_html(m.group(1)), h3_style))
            continue
        # Listes
        m = _RE_LIST_BULLET.match(line)
        if m:
            _flush_para()
            if list_is_numbered:
                _flush_list()
            list_buffer.append(m.group(1))
            list_is_numbered = False
            continue
        m = _RE_LIST_NUM.match(line)
        if m:
            _flush_para()
            if not list_is_numbered and list_buffer:
                _flush_list()
            list_buffer.append(m.group(1))
            list_is_numbered = True
            continue
        # Ligne vide = fin de paragraphe + fin de liste
        if not line.strip():
            _flush_para()
            _flush_list()
            continue
        # Texte normal
        _flush_list()
        para_buffer.append(line)
    _flush_para()
    _flush_list()
    _flush_code()
    return out


# ============================================================ Helpers

def _md_inline_to_html(text: str) -> str:
    """Convertit le markdown inline (bold/italic/code/images) en HTML reportlab.
    Remplace les markdown d'images par une mention text-only (les images
    ne sont pas embarquées dans le PDF : trop coûteux et paths externes)."""
    text = _RE_IMG_MD.sub(r"📎 image : \1", text)
    text = _escape_html(text)
    # Re-applique markdown APRÈS escape pour ne pas double-encoder
    text = _RE_BOLD.sub(r"<b>\1</b>", text)
    text = _RE_ITALIC.sub(r"<i>\1</i>", text)
    text = _RE_CODE_INLINE.sub(r"<font face='Courier'>\1</font>", text)
    return text


def _escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _yaml_str(s) -> str:
    """Sérialise une string en YAML sans guillemets si possible."""
    s = str(s)
    if not s or any(c in s for c in ':#@%[]{},"\'\n'):
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return s


def _format_ts_short(iso: Optional[str]) -> str:
    """Formate un ISO timestamp en court (YYYY-MM-DD HH:MM:SS) ou '?' si vide."""
    if not iso:
        return "?"
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return iso
