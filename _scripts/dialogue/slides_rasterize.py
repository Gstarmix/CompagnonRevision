from __future__ import annotations
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional
logger = logging.getLogger(__name__)
MIKTEX_PDFTOPPM = (
    r"C:\Users\Gstar\AppData\Local\Programs\MiKTeX\miktex\bin\x64\pdftoppm.exe"
)
def _resolve_pdftoppm() -> str:
    hit = shutil.which("pdftoppm")
    if hit:
        return hit
    if Path(MIKTEX_PDFTOPPM).is_file():
        return MIKTEX_PDFTOPPM
    return "pdftoppm"
def rasterize_pdf(
    pdf_path: Path,
    out_dir: Optional[Path] = None,
    prefix: str = "slide",
    dpi: int = 150,
) -> list[Path]:
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
    return rasterize_pdf(pdf_path, prefix="slide", dpi=dpi)
def rasterize_correction(pdf_path: Path, dpi: int = 150) -> list[Path]:
    out_dir = pdf_path.parent / f".pngs_{pdf_path.stem}"
    return rasterize_pdf(pdf_path, out_dir=out_dir, prefix="page", dpi=dpi)
def _png_num(name: str, prefix: str) -> int:
    import re
    m = re.match(rf"{re.escape(prefix)}-(\d+)\.png$", name, re.IGNORECASE)
    return int(m.group(1)) if m else 0
def _slide_num(name: str) -> int:
    return _png_num(name, "slide")