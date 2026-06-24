import logging
import re
from pathlib import Path
from typing import Optional
logger = logging.getLogger(__name__)
_CONCAT_FILE_PATTERN = "concat_{type}{num}_{matiere}.pdf"
_EXCLUDED_TOP_DIRS = frozenset({
    "_moodle", "_archives", "_inbox_dl", "_contextes_reprise",
    "_A_TRIER", "_a_trier", "_audit", "_publish_queue",
    "_prompts_claude_ai", "_prompts_claude_code", "_perso",
    "_scripts", "_INBOX", "_A_VALIDER", "_temp_latex", "_archived",
    "_lectures",
    "scripts_oraux",
})
_FREE_ENONCE_HINTS = ("annale_synthese", "enonce", "exos", "sujet")
_FREE_CORRIGE_HINTS = ("correction", "annale_synthese", "corrige", "corrigé")
_FREE_POLY_HINTS = ("aide_memoire", "poly", "cheat_sheet", "synthese")
_FREE_IMPRIMABLE_HINTS = ("script_imprimable", "_recopie", "a4_recopie")
_FREE_SLIDES_HINTS = ("slides",)
_FREE_MATERIAL_EXTS = (".pdf", ".md", ".txt")
def _has_material_recursive(folder: Path, max_depth: int = 2) -> bool:
    if not folder.is_dir():
        return False
    try:
        for p in folder.iterdir():
            if p.is_file() and p.suffix.lower() in _FREE_MATERIAL_EXTS:
                return True
            if p.is_dir() and max_depth > 0:
                if _has_material_recursive(p, max_depth - 1):
                    return True
    except OSError:
        return False
    return False
_has_pdf_recursive = _has_material_recursive
def _is_canonical_type(type_code: str) -> bool:
    return type_code.upper() in ("TD", "TP", "CC", "CM", "QUIZ", "EXAMEN")
def _get_free_type_dir(cours_root: Path, matiere: str, type_code: str) -> Optional[Path]:
    if _is_canonical_type(type_code):
        return None
    base = cours_root / matiere.upper()
    if not base.is_dir():
        return None
    candidate = base / type_code
    if candidate.is_dir():
        return candidate
    target_lower = type_code.lower()
    for p in base.iterdir():
        if p.is_dir() and p.name.lower() == target_lower:
            return p
    return None
def _match_free_pdf(
    folder: Path,
    hints: tuple[str, ...],
    exts: tuple[str, ...] = (".pdf",),
) -> Optional[Path]:
    if not folder.is_dir():
        return None
    exts_lower = tuple(e.lower() for e in exts)
    try:
        files = [
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in exts_lower
        ]
    except OSError:
        return None
    if not files:
        return None
    ext_priority = {e: i for i, e in enumerate(exts_lower)}
    files_sorted = sorted(
        files,
        key=lambda p: (ext_priority.get(p.suffix.lower(), 99), -ord(p.name[0]) if p.name else 0, p.name),
    )
    files_sorted.sort(key=lambda p: (ext_priority.get(p.suffix.lower(), 99), p.name), reverse=False)
    for hint in hints:
        for p in files_sorted:
            if hint in p.name.lower():
                return p
    return None
def _scan_free_corrections(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    try:
        items = sorted(folder.iterdir())
    except OSError:
        return []
    out: list[Path] = []
    seen_stems: set[str] = set()
    for p in items:
        if not p.is_file() or p.suffix.lower() != ".pdf":
            continue
        low = p.name.lower()
        if any(h in low for h in _FREE_CORRIGE_HINTS):
            out.append(p)
            seen_stems.add(p.stem.lower())
    for p in items:
        if not p.is_file() or p.suffix.lower() != ".md":
            continue
        low = p.name.lower()
        if not any(h in low for h in _FREE_CORRIGE_HINTS):
            continue
        if p.stem.lower() in seen_stems:
            continue
        out.append(p)
    return out
def _find_free_script(
    folder: Path,
    exts: tuple[str, ...],
    theme: Optional[str] = None,
) -> Optional[Path]:
    is_themed = theme and theme.lower() != "full"
    theme_lower = (theme or "").lower()
    for sub_name in ("scripts", "scripts_oraux"):
        sub = folder / sub_name
        if not sub.is_dir():
            continue
        try:
            names = sorted((p.name for p in sub.iterdir() if p.is_file()))
        except OSError:
            continue
        for name in names:
            low = name.lower()
            if not any(low.endswith(e) for e in exts):
                continue
            if "script_oral" not in low:
                continue
            if is_themed:
                if (f"_{theme_lower}." not in low) and (f"_{theme_lower}_" not in low):
                    continue
            return sub / name
        if not is_themed:
            for name in names:
                low = name.lower()
                if any(low.endswith(e) for e in exts):
                    return sub / name
    return None
def _detect_themes_in_free_dir(folder: Path) -> list[str]:
    if not folder.is_dir():
        return []
    themes: set[str] = set()
    patterns = (
        ("script_oral_", (".txt", ".md")),
        ("slides_", (".pdf",)),
        ("script_imprimable_", (".pdf",)),
    )
    for sub_name in ("scripts", "scripts_oraux"):
        sub = folder / sub_name
        if not sub.is_dir():
            continue
        try:
            names = list(p.name for p in sub.iterdir() if p.is_file())
        except OSError:
            continue
        for name in names:
            for prefix, exts in patterns:
                low = name.lower()
                if not low.startswith(prefix):
                    continue
                for ext in exts:
                    if low.endswith(ext):
                        theme = name[len(prefix):-len(ext)]
                        if theme:
                            themes.add(theme)
                        break
    return sorted(themes)
def _match_free_pdf_themed(
    folder: Path,
    hints: tuple[str, ...],
    theme: Optional[str] = None,
    exts: tuple[str, ...] = (".pdf",),
) -> Optional[Path]:
    is_themed = theme and theme.lower() != "full"
    if not is_themed:
        return _match_free_pdf(folder, hints, exts)
    theme_lower = theme.lower()
    if not folder.is_dir():
        return None
    exts_lower = tuple(e.lower() for e in exts)
    try:
        files = [
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in exts_lower
        ]
    except OSError:
        return None
    if not files:
        return None
    for hint in hints:
        for p in sorted(files, key=lambda p: p.name):
            low = p.name.lower()
            if hint in low and theme_lower in low:
                return p
    return None
def find_free_poly(
    cours_root: Path,
    matiere: str,
    type_code: str,
) -> Optional[Path]:
    free_dir = _get_free_type_dir(cours_root, matiere, type_code)
    if free_dir is None:
        return None
    return _match_free_pdf(free_dir, _FREE_POLY_HINTS, exts=(".pdf", ".md"))
def find_enonce_pdf(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    annee: Optional[str] = None,
) -> Optional[Path]:
    free_dir = _get_free_type_dir(cours_root, matiere, type_code)
    if free_dir is not None:
        is_themed = num and num.lower() != "full"
        if is_themed:
            themed = _match_free_pdf_themed(
                free_dir, ("exos",),
                theme=num, exts=(".pdf", ".md"),
            )
            if themed is not None:
                return themed
        return None
    type_code = type_code.upper()
    matiere = matiere.upper()
    for folder in _candidate_exercise_folders(cours_root, matiere, type_code, num, annee):
        hit = _find_enonce_in_folder(folder, type_code, num, matiere, annee)
        if hit is not None:
            return hit
    return None
def _find_enonce_in_folder(
    folder: Path,
    type_code: str,
    num: str,
    matiere: str,
    annee: Optional[str],
) -> Optional[Path]:
    if not folder.is_dir():
        return None
    if type_code.upper() == "CM":
        poly = folder / f"cm_{matiere.lower()}_{num}.pdf"
        if poly.is_file():
            return poly
        try:
            names = sorted((p.name for p in folder.iterdir() if p.is_file()))
        except OSError:
            names = []
        for name in names:
            low = name.lower()
            if not (low.startswith(f"cm_{matiere.lower()}_") and low.endswith(".pdf")):
                continue
            m = re.match(rf"^cm_{matiere.lower()}_({re.escape(num)})\.pdf$",
                         name, re.IGNORECASE)
            if m:
                return folder / name
        return None
    if annee:
        exact = folder / f"enonce_{type_code}{num}_{annee}_{matiere}.pdf"
        if exact.is_file():
            return exact
    exact_no_annee = folder / f"enonce_{type_code}{num}_{matiere}.pdf"
    if exact_no_annee.is_file():
        return exact_no_annee
    try:
        names = sorted((p.name for p in folder.iterdir() if p.is_file()), reverse=True)
    except OSError:
        names = []
    for name in names:
        low = name.lower()
        if not (low.startswith("enonce_") and low.endswith(".pdf")):
            continue
        if f"{type_code.lower()}{num}" not in low:
            continue
        if matiere.lower() not in low:
            continue
        if annee and f"_{annee}_" not in name:
            continue
        return folder / name
    legacy = folder / "enonce.pdf"
    if legacy.is_file():
        return legacy
    return None
def resolve_corrections(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    exo: str,
    annee: Optional[str] = None,
    prefer_concat: bool = True,
) -> list[Path]:
    free_dir = _get_free_type_dir(cours_root, matiere, type_code)
    if free_dir is not None:
        return _scan_free_corrections(free_dir)
    type_code = type_code.upper()
    matiere = matiere.upper()
    folders = list(_candidate_exercise_folders(cours_root, matiere, type_code, num, annee))
    if exo == "full":
        return _collect_full_corrections(
            folders, type_code, num, matiere, annee, prefer_concat=prefer_concat
        )
    return _collect_single_correction(folders, type_code, num, exo, matiere, annee)
def _collect_single_correction(
    folders: list[Path],
    type_code: str,
    num: str,
    exo: str,
    matiere: str,
    annee: Optional[str],
) -> list[Path]:
    for folder in folders:
        for corr_dir in (folder / "corrections", folder):
            if not corr_dir.is_dir():
                continue
            hit = _match_correction_file(
                corr_dir, type_code, num, matiere, annee, exo=exo
            )
            if hit is not None:
                return [hit]
    return []
def _collect_full_corrections(
    folders: list[Path],
    type_code: str,
    num: str,
    matiere: str,
    annee: Optional[str],
    prefer_concat: bool = True,
) -> list[Path]:
    if prefer_concat:
        concat_names: list[str] = []
        if type_code.upper() == "CC" and annee:
            concat_names.append(
                f"concat_{type_code}{num}_{annee}_{matiere}.pdf"
            )
        concat_names.append(_CONCAT_FILE_PATTERN.format(
            type=type_code, num=num, matiere=matiere
        ))
        for concat_name in concat_names:
            for folder in folders:
                for parent in (folder / "corrections", folder):
                    concat = parent / concat_name
                    if concat.is_file():
                        return [concat]
    results: list[Path] = []
    seen: set[Path] = set()
    for folder in folders:
        for corr_dir in (folder / "corrections", folder):
            if not corr_dir.is_dir():
                continue
            try:
                files = sorted(corr_dir.iterdir(), reverse=True)
            except OSError:
                continue
            for cand in files:
                if cand.suffix.lower() != ".pdf":
                    continue
                name = cand.name
                low = name.lower()
                if not low.startswith("correction_"):
                    continue
                if f"{type_code}{num}".lower() not in low:
                    continue
                if matiere.lower() not in low:
                    continue
                if annee and f"_{annee}_" not in name:
                    continue
                if cand in seen:
                    continue
                seen.add(cand)
                results.append(cand)
    if not prefer_concat:
        def _exo_sort_key(p: Path) -> tuple[int, str]:
            m = re.search(r"_ex([\d-]+)", p.stem, re.IGNORECASE)
            if not m:
                return (10**6, p.stem)
            head = m.group(1).split("-")[0]
            try:
                return (int(head), p.stem)
            except ValueError:
                return (10**6, p.stem)
        results.sort(key=_exo_sort_key)
    return results
def _match_correction_file(
    corr_dir: Path,
    type_code: str,
    num: str,
    matiere: str,
    annee: Optional[str],
    exo: str,
) -> Optional[Path]:
    try:
        files = sorted(corr_dir.iterdir(), reverse=True)
    except OSError:
        return None
    target_ex = re.compile(rf"_ex{re.escape(exo)}(?:_|\.pdf$)", re.IGNORECASE)
    for cand in files:
        if cand.suffix.lower() != ".pdf":
            continue
        name = cand.name
        low = name.lower()
        if not low.startswith("correction_"):
            continue
        if f"{type_code}{num}".lower() not in low:
            continue
        if matiere.lower() not in low:
            continue
        if annee and f"_{annee}_" not in name:
            continue
        if not target_ex.search(name):
            continue
        return cand
    return None
def find_perso_tache(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    exo: str,
    annee: Optional[str] = None,
) -> Optional[Path]:
    type_code = type_code.upper()
    matiere = matiere.upper()
    for folder in _candidate_exercise_folders(cours_root, matiere, type_code, num, annee):
        if exo == "full":
            concat = folder / f"concat_TACHE_{type_code}{num}_{matiere}.md"
            if concat.is_file():
                return concat
        if type_code == "CC":
            cc_root = cours_root / matiere / "CC"
            if annee:
                cand = cc_root / f"TACHE_{matiere}_CC{num}_{annee}.md"
                if cand.is_file():
                    return cand
            try:
                matches = sorted(
                    (p for p in cc_root.iterdir()
                     if p.name.startswith(f"TACHE_{matiere}_CC{num}_")
                     and p.suffix == ".md"),
                    reverse=True,
                )
            except OSError:
                matches = []
            if matches:
                return matches[0]
        else:
            cand = folder / f"TACHE_{matiere}_{type_code}{num}_ex{exo}.md"
            if cand.is_file():
                return cand
    return None
def find_perso_script_oral(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    annee: Optional[str] = None,
) -> Optional[Path]:
    free_dir = _get_free_type_dir(cours_root, matiere, type_code)
    if free_dir is not None:
        return _find_free_script(free_dir, (".txt", ".md"), theme=num)
    type_code = type_code.upper()
    matiere = matiere.upper()
    for folder in _candidate_exercise_folders(cours_root, matiere, type_code, num, annee):
        scripts = folder / "scripts_oraux"
        if not scripts.is_dir():
            continue
        prefer = ("transcription", "")
        for variant in prefer:
            for ext in (".txt", ".md"):
                hit = _scan_script_dir(scripts, matiere, type_code, num, annee, variant, ext)
                if hit is not None:
                    return hit
    return None
def _scan_script_dir(
    scripts_dir: Path,
    matiere: str,
    type_code: str,
    num: str,
    annee: Optional[str],
    variant: str,
    ext: str,
) -> Optional[Path]:
    try:
        names = sorted(p.name for p in scripts_dir.iterdir() if p.is_file())
    except OSError:
        return None
    target = f"{type_code.lower()}{num}"
    for name in names:
        low = name.lower()
        if not low.endswith(ext):
            continue
        if not (low.startswith("script_oral_") or low.startswith("script_")):
            continue
        if matiere.lower() not in low:
            continue
        if target not in low:
            continue
        if annee and f"_{annee}" not in name:
            continue
        if variant and variant not in low:
            continue
        return scripts_dir / name
    return None
def find_perso_script_md(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    annee: Optional[str] = None,
) -> Optional[Path]:
    free_dir = _get_free_type_dir(cours_root, matiere, type_code)
    if free_dir is not None:
        for sub_name in ("scripts", "scripts_oraux"):
            sub = free_dir / sub_name
            if not sub.is_dir():
                continue
            theme_lower = (num or "").lower()
            try:
                names = sorted(p.name for p in sub.iterdir() if p.is_file())
            except OSError:
                continue
            for name in names:
                low = name.lower()
                if not (low.startswith("script_") and low.endswith(".md")):
                    continue
                if not name.startswith("SCRIPT_"):
                    continue
                middle = low[len("script_"):-len(".md")]
                if middle == theme_lower or theme_lower in middle:
                    return sub / name
        return None
    type_code = type_code.upper()
    matiere = matiere.upper()
    for folder in _candidate_exercise_folders(cours_root, matiere, type_code, num, annee):
        scripts = folder / "scripts_oraux"
        if not scripts.is_dir():
            continue
        prefer = ("transcription", "")
        for variant in prefer:
            hit = _scan_script_dir(scripts, matiere, type_code, num, annee, variant, ".md")
            if hit is not None:
                return hit
    return None
def find_perso_script_imprimable(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    annee: Optional[str] = None,
) -> Optional[Path]:
    free_dir = _get_free_type_dir(cours_root, matiere, type_code)
    if free_dir is not None:
        is_themed = num and num.lower() != "full"
        for sub_name in ("scripts", "scripts_oraux"):
            sub = free_dir / sub_name
            if is_themed:
                hit = _match_free_pdf_themed(
                    sub, _FREE_IMPRIMABLE_HINTS, theme=num,
                )
            else:
                hit = _match_free_pdf(sub, _FREE_IMPRIMABLE_HINTS)
            if hit is not None:
                return hit
        if is_themed:
            hit = _match_free_pdf_themed(
                free_dir, _FREE_IMPRIMABLE_HINTS, theme=num,
            )
            if hit is not None:
                return hit
        return _match_free_pdf(free_dir, _FREE_IMPRIMABLE_HINTS)
    type_code = type_code.upper()
    matiere = matiere.upper()
    for folder in _candidate_exercise_folders(cours_root, matiere, type_code, num, annee):
        scripts = folder / "scripts_oraux"
        if not scripts.is_dir():
            continue
        try:
            names = sorted((p.name for p in scripts.iterdir() if p.is_file()), reverse=True)
        except OSError:
            continue
        target = f"{type_code.lower()}{num}"
        for name in names:
            low = name.lower()
            if not (low.startswith("script_imprimable_") and low.endswith(".pdf")):
                continue
            if matiere.lower() not in low:
                continue
            if target not in low:
                continue
            if annee and f"_{annee}" not in name:
                continue
            return scripts / name
    return None
def find_perso_slides_pdf(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    annee: Optional[str] = None,
) -> Optional[Path]:
    free_dir = _get_free_type_dir(cours_root, matiere, type_code)
    if free_dir is not None:
        is_themed = num and num.lower() != "full"
        for sub_name in ("scripts", "scripts_oraux"):
            sub = free_dir / sub_name
            if is_themed:
                hit = _match_free_pdf_themed(
                    sub, _FREE_SLIDES_HINTS, theme=num,
                )
            else:
                hit = _match_free_pdf(sub, _FREE_SLIDES_HINTS)
            if hit is not None:
                return hit
        return None
    type_code = type_code.upper()
    matiere = matiere.upper()
    for folder in _candidate_exercise_folders(cours_root, matiere, type_code, num, annee):
        scripts = folder / "scripts_oraux"
        if not scripts.is_dir():
            continue
        try:
            names = sorted((p.name for p in scripts.iterdir() if p.is_file()), reverse=True)
        except OSError:
            continue
        target = f"{type_code.lower()}{num}"
        for name in names:
            low = name.lower()
            if not (low.startswith("slides_") and low.endswith(".pdf")):
                continue
            if matiere.lower() not in low:
                continue
            if target not in low:
                continue
            if annee and f"_{annee}" not in name:
                continue
            return scripts / name
    return None
_BROWSER_KNOWN_TYPES = ("TD", "TP", "CC", "CM", "Quiz", "Examen")
def list_matieres(cours_root: Path) -> list[str]:
    if not cours_root.is_dir():
        return []
    out = []
    for p in cours_root.iterdir():
        if not p.is_dir():
            continue
        if re.match(r"^[A-Z][A-Z0-9]{1,5}$", p.name):
            out.append(p.name)
    return sorted(out)
def list_types_for_matiere(cours_root: Path, matiere: str) -> list[str]:
    base = cours_root / matiere
    if not base.is_dir():
        return []
    canon: list[str] = []
    free: list[str] = []
    for p in base.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if name in _EXCLUDED_TOP_DIRS:
            continue
        if name in _BROWSER_KNOWN_TYPES:
            canon.append(name)
        elif _has_pdf_recursive(p, max_depth=2):
            free.append(name)
    return sorted(canon) + sorted(free)
def list_nums_for_type(
    cours_root: Path,
    matiere: str,
    type_code: str,
) -> list[str]:
    if not _is_canonical_type(type_code):
        free_dir = _get_free_type_dir(cours_root, matiere, type_code)
        if free_dir is None:
            return []
        themes = _detect_themes_in_free_dir(free_dir)
        if themes:
            return ["full"] + themes
        return ["full"]
    type_code = type_code.upper()
    base = cours_root / matiere / type_code
    if not base.is_dir():
        return []
    nums: set[str] = set()
    if type_code == "CC":
        for p in base.iterdir():
            if p.is_file():
                m = re.match(
                    r"^enonce_CC([A-Z0-9]+)_", p.name, re.IGNORECASE
                )
                if m:
                    nums.add(m.group(1).upper())
            elif p.is_dir() and re.match(r"^\d{4}-\d{2,4}$", p.name):
                for sub in p.iterdir():
                    if sub.is_dir():
                        m = re.match(
                            r"^CC([A-Z0-9]+)$", sub.name, re.IGNORECASE
                        )
                        if m:
                            nums.add(m.group(1).upper())
    elif type_code == "CM":
        scripts_dir = base / "scripts_oraux"
        if scripts_dir.is_dir():
            for p in scripts_dir.iterdir():
                if not p.is_file():
                    continue
                m = re.match(
                    rf"^(?:SCRIPT|script_oral|script_imprimable|slides)_{matiere}_CM([A-Z0-9]+)",
                    p.name, re.IGNORECASE,
                )
                if m:
                    nums.add(m.group(1).upper())
        for p in base.iterdir():
            if not p.is_file():
                continue
            m = re.match(
                rf"^CM([A-Z0-9]+)_{matiere}_", p.name, re.IGNORECASE,
            )
            if m:
                nums.add(m.group(1).upper())
                continue
            m = re.match(
                rf"^cm_{matiere.lower()}_(\d+)\.pdf$", p.name, re.IGNORECASE,
            )
            if m:
                nums.add(m.group(1).upper())
    else:
        for p in base.iterdir():
            if not p.is_dir():
                continue
            m = re.match(
                rf"^{type_code}([A-Z0-9]+)$", p.name, re.IGNORECASE
            )
            if m:
                nums.add(m.group(1).upper())
    return sorted(nums, key=_natural_num_key)
def list_annees_for_cc(
    cours_root: Path,
    matiere: str,
    num: str,
    type_code: Optional[str] = None,
) -> list[str]:
    if type_code is not None and not _is_canonical_type(type_code):
        return []
    base = cours_root / matiere / "CC"
    if not base.is_dir():
        return []
    annees: set[str] = set()
    annee_re = re.compile(
        rf"^enonce_CC{re.escape(num)}_(\d{{4}}-\d{{2,4}})_", re.IGNORECASE
    )
    for p in base.iterdir():
        if p.is_file():
            m = annee_re.match(p.name)
            if m:
                annees.add(m.group(1))
        elif p.is_dir() and re.match(r"^\d{4}-\d{2,4}$", p.name):
            sub = p / f"CC{num}"
            if sub.is_dir():
                annees.add(p.name)
    return sorted(annees, reverse=True)
def list_exos_for_num(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    annee: Optional[str] = None,
) -> list[str]:
    if not _is_canonical_type(type_code):
        return ["full"]
    type_code = type_code.upper()
    out: list[str] = ["full"]
    if type_code in ("CC", "CM"):
        return out
    folder = cours_root / matiere / type_code / f"{type_code}{num}"
    if not folder.is_dir():
        return out
    exos: set[str] = set()
    corr_dir = folder / "corrections"
    if corr_dir.is_dir():
        corr_re = re.compile(
            rf"^correction_{type_code}{re.escape(num)}_ex(\d+)_",
            re.IGNORECASE,
        )
        for p in corr_dir.iterdir():
            if p.is_file():
                m = corr_re.match(p.name)
                if m:
                    exos.add(m.group(1))
    tache_re = re.compile(
        rf"^TACHE_{matiere}_{type_code}{re.escape(num)}_ex(\d+)\.md$",
        re.IGNORECASE,
    )
    for p in folder.iterdir():
        if p.is_file():
            m = tache_re.match(p.name)
            if m:
                exos.add(m.group(1))
    out.extend(sorted(exos, key=lambda e: int(e)))
    return out
def _natural_num_key(s: str):
    if s.isdigit():
        return (0, int(s), s)
    return (1, 0, s)
def _candidate_exercise_folders(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    annee: Optional[str],
):
    if type_code in ("TD", "TP"):
        yield cours_root / matiere / type_code / f"{type_code}{num}"
        return
    if type_code == "CM":
        yield cours_root / matiere / "CM"
        return
    if type_code == "CC":
        if annee:
            yield cours_root / matiere / "CC" / annee / f"CC{num}"
        else:
            cc_root = cours_root / matiere / "CC"
            if cc_root.is_dir():
                try:
                    for entry in sorted(cc_root.iterdir(), reverse=True):
                        if entry.is_dir() and re.match(r"^\d{4}-\d{2,4}$", entry.name):
                            sub = entry / f"CC{num}"
                            if sub.is_dir():
                                yield sub
                except OSError:
                    pass
        yield cours_root / matiere / "CC"
        return
    yield cours_root / matiere / type_code / f"{type_code}{num}"