"""
slides_rasterize.py : rasterisation slides_*.pdf → slide-NN.png (Phase A.7.2 v5).

Le mode `guidé` du Compagnon affiche chaque slide en image dans la sidebar.
Source : `slides_{MAT}_{TYPE}{N}.pdf` (Beamer compilé, généré par
`run_script_oral.py` côté COURS).

Convention de sortie : à côté du PDF, dans le même `scripts_oraux/`,
fichiers nommés ``slide-1.png``, ``slide-2.png``, ... (numérotation
1-indexée par `pdftoppm`). 150 DPI = bon compromis qualité/taille
(~150 KB par slide pour du Beamer 16:9).

Idempotent : si les PNGs existent déjà ET sont plus récents que le PDF,
on skip. Sinon on (re)rasterize l'ensemble.

Cf. ARCHITECTURE.md §11 (Phase A.7.2 v5).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

#: Chemin standard MiKTeX Windows (cf. COURS/_scripts/run_script_oral.py).
MIKTEX_PDFTOPPM = (
    r"C:\Users\Gstar\AppData\Local\Programs\MiKTeX\miktex\bin\x64\pdftoppm.exe"
)


def _resolve_pdftoppm() -> str:
    """Retourne le chemin pdftoppm (PATH puis chemin canonique MiKTeX)."""
    hit = shutil.which("pdftoppm")
    if hit:
        return hit
    if Path(MIKTEX_PDFTOPPM).is_file():
        return MIKTEX_PDFTOPPM
    return "pdftoppm"  # laissera FileNotFoundError remonter


def rasterize_pdf(
    pdf_path: Path,
    out_dir: Optional[Path] = None,
    prefix: str = "slide",
    dpi: int = 150,
) -> list[Path]:
    """Rasterize ``pdf_path`` en ``{prefix}-1.png``, ..., ``{prefix}-N.png``.

    Idempotent : skip si tous les PNGs sont plus récents que le PDF. Sinon
    purge les anciens PNGs (au cas où le nombre de pages ait changé) et
    régénère.

    ``out_dir`` par défaut : dossier parent du PDF.

    Retourne la liste triée des chemins PNGs produits (ou existants si
    skip). Liste vide si le PDF n'existe pas.
    """
    if not pdf_path.is_file():
        return []
    if out_dir is None:
        out_dir = pdf_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_mtime = pdf_path.stat().st_mtime

    existing = sorted(out_dir.glob(f"{prefix}-*.png"),
                      key=lambda p: _png_num(p.name, prefix))
    if existing:
        all_fresh = all(p.stat().st_mtime >= pdf_mtime for p in existing)
        if all_fresh:
            logger.info("PDF déjà rasterizé (skip) : %s → %d PNGs",
                        pdf_path.name, len(existing))
            return existing

    for p in existing:
        try:
            p.unlink()
        except OSError:
            logger.warning("Cleanup PNG a échoué : %s", p)

    pdftoppm = _resolve_pdftoppm()
    out_prefix = out_dir / prefix
    cmd = [
        pdftoppm,
        "-png",
        "-r", str(dpi),
        str(pdf_path),
        str(out_prefix),
    ]
    logger.info("Rasterisation : %s → %s/%s-*.png (%d DPI)",
                pdf_path.name, out_dir.name, prefix, dpi)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            creationflags=(subprocess.CREATE_NO_WINDOW
                           if os.name == "nt" else 0),
        )
    except FileNotFoundError as e:
        logger.error("pdftoppm introuvable : %s", e)
        return []
    except subprocess.TimeoutExpired:
        logger.error("pdftoppm timeout (>120s) sur %s", pdf_path.name)
        return []
    if result.returncode != 0:
        logger.error("pdftoppm exit %d : %s",
                     result.returncode, result.stderr.strip()[:200])
        return []
    out = sorted(out_dir.glob(f"{prefix}-*.png"),
                 key=lambda p: _png_num(p.name, prefix))
    logger.info("Rasterisation terminée : %d PNGs", len(out))
    return out


def rasterize_if_needed(pdf_path: Path, dpi: int = 150) -> list[Path]:
    """Wrapper historique : rasterize côté ``slide-N.png`` (mode guidé)."""
    return rasterize_pdf(pdf_path, prefix="slide", dpi=dpi)


def rasterize_correction(pdf_path: Path, dpi: int = 150) -> list[Path]:
    """Rasterize un PDF de correction dans un sous-dossier caché par PDF
    (``.pngs_{stem}/``) pour éviter les collisions quand plusieurs
    corrections cohabitent dans ``corrections/``.
    """
    out_dir = pdf_path.parent / f".pngs_{pdf_path.stem}"
    return rasterize_pdf(pdf_path, out_dir=out_dir, prefix="page", dpi=dpi)


def _png_num(name: str, prefix: str) -> int:
    """`{prefix}-7.png` → 7. Pour tri numérique."""
    import re
    m = re.match(rf"{re.escape(prefix)}-(\d+)\.png$", name, re.IGNORECASE)
    return int(m.group(1)) if m else 0


def _slide_num(name: str) -> int:
    """Compat historique."""
    return _png_num(name, "slide")
