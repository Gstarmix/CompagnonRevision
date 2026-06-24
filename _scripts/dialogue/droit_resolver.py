import logging
import re
from pathlib import Path
from typing import Optional
logger = logging.getLogger(__name__)
_NON_MATIERE_DIRS = frozenset({"_methodo", "_inbox", "_archives"})
_KNOWN_TYPES = ("CM", "TD")
_TRANSCRIPT_RE = re.compile(r"^(?P<type>CM|TD)(?P<num>\d+)_", re.IGNORECASE)
_FICHE_RE = re.compile(r"^fiche_(?P<type>CM|TD)(?P<num>\d+)_", re.IGNORECASE)
def list_matieres(droit_root: Path) -> list[str]:
    if not droit_root.is_dir():
        return []
    out = []
    for p in droit_root.iterdir():
        if not p.is_dir():
            continue
        if p.name in _NON_MATIERE_DIRS or p.name.startswith((".", "_")):
            continue
        out.append(p.name)
    return sorted(out)
def list_types_for_matiere(droit_root: Path, slug: str) -> list[str]:
    base = droit_root / slug
    if not base.is_dir():
        return []
    out = []
    if _has_material(base / "CM"):
        out.append("CM")
    if _has_material(base / "TD"):
        out.append("TD")
    return out
def list_nums_for_type(droit_root: Path, slug: str, type_code: str) -> list[str]:
    type_code = type_code.upper()
    nums: set[str] = set()
    for folder, regex in _material_dirs(droit_root, slug, type_code):
        if not folder.is_dir():
            continue
        for f in folder.iterdir():
            if not f.is_file():
                continue
            m = regex.match(f.name)
            if m and m.group("type").upper() == type_code:
                nums.add(m.group("num"))
    return sorted(nums, key=lambda n: (int(n) if n.isdigit() else 10**6, n))
def find_transcription(
    droit_root: Path, slug: str, type_code: str, num: str,
) -> Optional[Path]:
    type_code = type_code.upper()
    folder = _transcript_dir(droit_root, slug, type_code)
    return _match_num(folder, _TRANSCRIPT_RE, type_code, num, ".txt")
def find_fiche(
    droit_root: Path, slug: str, type_code: str, num: str,
) -> Optional[Path]:
    type_code = type_code.upper()
    folder = _fiche_dir(droit_root, slug, type_code)
    return _match_num(folder, _FICHE_RE, type_code, num, ".md")
def list_arrets(droit_root: Path, slug: str) -> list[Path]:
    return _list_files(droit_root / slug / "arrets", (".md", ".txt", ".pdf"))
def list_methodo_matiere(droit_root: Path, slug: str) -> list[Path]:
    return _list_files(droit_root / slug / "methodo", (".md", ".txt", ".pdf"))
def list_methodo_transverse(droit_root: Path) -> list[Path]:
    return _list_files(droit_root / "_methodo", (".md",))
def _has_material(folder: Path) -> bool:
    if not folder.is_dir():
        return False
    for sub in (folder, folder / "transcriptions", folder / "fiches"):
        if not sub.is_dir():
            continue
        for f in sub.iterdir():
            if f.is_file() and (
                _TRANSCRIPT_RE.match(f.name) or _FICHE_RE.match(f.name)
            ):
                return True
    return False
def _transcript_dir(droit_root: Path, slug: str, type_code: str) -> Path:
    if type_code == "CM":
        return droit_root / slug / "CM" / "transcriptions"
    return droit_root / slug / "TD"
def _fiche_dir(droit_root: Path, slug: str, type_code: str) -> Path:
    if type_code == "CM":
        return droit_root / slug / "CM" / "fiches"
    return droit_root / slug / "TD"
def _material_dirs(droit_root: Path, slug: str, type_code: str):
    yield _transcript_dir(droit_root, slug, type_code), _TRANSCRIPT_RE
    yield _fiche_dir(droit_root, slug, type_code), _FICHE_RE
def _match_num(
    folder: Path, regex: re.Pattern, type_code: str, num: str, ext: str,
) -> Optional[Path]:
    if not folder.is_dir():
        return None
    try:
        names = sorted((p.name for p in folder.iterdir() if p.is_file()), reverse=True)
    except OSError:
        return None
    for name in names:
        if not name.lower().endswith(ext):
            continue
        m = regex.match(name)
        if m and m.group("type").upper() == type_code and m.group("num") == num:
            return folder / name
    return None
def _list_files(folder: Path, exts: tuple[str, ...]) -> list[Path]:
    if not folder.is_dir():
        return []
    exts_lower = tuple(e.lower() for e in exts)
    try:
        items = sorted(folder.iterdir())
    except OSError:
        return []
    return [
        p for p in items
        if p.is_file() and p.suffix.lower() in exts_lower and p.name != ".gitkeep"
    ]