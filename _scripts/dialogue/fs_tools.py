from __future__ import annotations
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
logger = logging.getLogger(__name__)
FS_TOOL_NAMES: tuple[str, ...] = ("Read", "Grep", "Glob")
MAX_TOOL_ROUNDS = 6
_READ_MAX_CHARS = 60_000
_GREP_MAX = 200
_GREP_MAX_FILES = 3000
_GLOB_MAX = 400
_DOC_MAX_BYTES = 10 * 1024 * 1024
_GREP_FILE_MAX_BYTES = 2 * 1024 * 1024
_IMAGE_EXTS: dict[str, str] = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp",
}
_SKIP_DIRS = frozenset({
    ".git", "node_modules", "venv", ".venv", "__pycache__", "_secrets",
    ".idea", ".vscode", "dist", "build", ".pytest_cache", ".mypy_cache",
    ".next", ".cache", "site-packages",
})
_SENSITIVE_SUBSTR = ("secret", "password", "token", "api_key", "apikey",
                     "credential")
_SENSITIVE_EXT = frozenset({".key", ".pem", ".env"})
_BINARY_EXTS = frozenset({
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico",
    ".zip", ".gz", ".tar", ".7z", ".rar", ".exe", ".dll", ".so", ".dylib",
    ".pyc", ".pyo", ".mp3", ".mp4", ".wav", ".m4a", ".avi", ".mov",
    ".bin", ".lock", ".woff", ".woff2", ".ttf", ".otf", ".eot",
})
@dataclass
class FsToolResult:
    tool: str
    ok: bool
    text: str
    document: Optional[dict] = None
class FsToolError(Exception):
    pass
_NEUTRAL: dict[str, dict[str, Any]] = {
    "Read": {
        "description": (
            "Lit le contenu d'un fichier du dossier de travail. À utiliser "
            "AVANT d'affirmer quoi que ce soit sur le contenu d'un fichier, "
            "ne jamais deviner ni inventer. Gère le texte, le code, les PDF "
            "et les images (le contenu binaire est fourni directement au "
            "modèle). Renvoie le texte numéroté par ligne pour faciliter la "
            "citation chemin:ligne."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": (
                        "Chemin du fichier, relatif à la racine du dossier de "
                        "travail (ex: 'rapport.tex', 'src/main.py')."
                    ),
                },
                "offset": {
                    "type": "integer",
                    "description": (
                        "Optionnel : première ligne à lire (1-based). Pour "
                        "relire la suite d'un fichier tronqué."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": (
                        "Optionnel : nombre de lignes à lire depuis offset."
                    ),
                },
            },
            "required": ["path"],
        },
    },
    "Grep": {
        "description": (
            "Cherche un motif (expression régulière) dans les fichiers texte "
            "du dossier de travail. Renvoie les lignes correspondantes avec "
            "leur chemin et leur numéro de ligne."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Expression régulière à chercher.",
                },
                "path": {
                    "type": "string",
                    "description": (
                        "Optionnel : sous-dossier ou fichier où chercher "
                        "(relatif à la racine). Défaut : tout le dossier."
                    ),
                },
                "glob": {
                    "type": "string",
                    "description": (
                        "Optionnel : filtre de fichiers (ex: '*.py', "
                        "'**/*.tex'). Défaut : tous les fichiers texte."
                    ),
                },
                "ignore_case": {
                    "type": "boolean",
                    "description": "Optionnel : recherche insensible à la casse.",
                },
            },
            "required": ["pattern"],
        },
    },
    "Glob": {
        "description": (
            "Liste les fichiers du dossier de travail dont le chemin "
            "correspond à un motif glob (ex: '**/*.py', 'src/*.tex'). À "
            "utiliser pour découvrir quels fichiers existent."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": (
                        "Motif glob relatif à la racine (ex: '**/*.md')."
                    ),
                },
            },
            "required": ["pattern"],
        },
    },
}
def _uppercase_types(node: Any) -> Any:
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "type" and isinstance(v, str):
                out[k] = v.upper()
            else:
                out[k] = _uppercase_types(v)
        return out
    if isinstance(node, list):
        return [_uppercase_types(x) for x in node]
    return node
def gemini_fs_declarations() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": spec["description"],
            "parameters": _uppercase_types(spec["parameters"]),
        }
        for name, spec in _NEUTRAL.items()
    ]
def anthropic_fs_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": name,
            "description": spec["description"],
            "input_schema": spec["parameters"],
        }
        for name, spec in _NEUTRAL.items()
    ]
def openai_fs_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": spec["description"],
                "parameters": spec["parameters"],
            },
        }
        for name, spec in _NEUTRAL.items()
    ]
def _resolve(root: Path, rel: str) -> Path:
    root = root.resolve()
    p = Path(rel)
    cand = (p if p.is_absolute() else root / p).resolve()
    if cand != root and root not in cand.parents:
        raise FsToolError(f"chemin hors du dossier de travail : {rel}")
    return cand
def _in_skipped_dir(path: Path, root: Path) -> bool:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return True
    return any(part in _SKIP_DIRS for part in rel.parts)
def _is_sensitive(path: Path) -> bool:
    name = path.name.lower()
    if name == ".env" or name.endswith(".env"):
        return True
    if path.suffix.lower() in _SENSITIVE_EXT:
        return True
    return any(s in name for s in _SENSITIVE_SUBSTR)
def _do_read(root: Path, args: dict) -> FsToolResult:
    rel = (args.get("path") or args.get("file_path") or "").strip()
    if not rel:
        raise FsToolError("paramètre 'path' manquant")
    target = _resolve(root, rel)
    if _in_skipped_dir(target, root) or _is_sensitive(target):
        raise FsToolError(
            f"fichier sensible ou ignoré, lecture refusée : {rel}"
        )
    if not target.exists():
        raise FsToolError(f"fichier introuvable : {rel}")
    if not target.is_file():
        raise FsToolError(f"n'est pas un fichier : {rel}")
    ext = target.suffix.lower()
    size = target.stat().st_size
    if ext == ".pdf" or ext in _IMAGE_EXTS:
        if size > _DOC_MAX_BYTES:
            raise FsToolError(
                f"fichier trop volumineux pour ingestion ({size} octets) : {rel}"
            )
        media = "application/pdf" if ext == ".pdf" else _IMAGE_EXTS[ext]
        kind = "PDF" if ext == ".pdf" else "image"
        return FsToolResult(
            "Read", True,
            text=(
                f"[{kind} « {rel} » joint à ce message : son contenu t'est "
                f"fourni directement, lis-le pour répondre.]"
            ),
            document={
                "media_type": media,
                "data": target.read_bytes(),
                "label": rel,
            },
        )
    raw = target.read_bytes()
    if b"\x00" in raw[:8192]:
        raise FsToolError(f"fichier binaire non lisible en texte : {rel}")
    content = raw.decode("utf-8", errors="replace")
    lines = content.splitlines()
    start = 0
    offset = args.get("offset")
    if isinstance(offset, int) and offset > 0:
        start = offset - 1
    elif isinstance(offset, str) and offset.isdigit() and int(offset) > 0:
        start = int(offset) - 1
    selected = lines[start:]
    limit = args.get("limit")
    if isinstance(limit, int) and limit > 0:
        selected = selected[:limit]
    elif isinstance(limit, str) and limit.isdigit() and int(limit) > 0:
        selected = selected[:int(limit)]
    numbered = "\n".join(
        f"{start + i + 1:>6}\t{ln}" for i, ln in enumerate(selected)
    )
    truncated = len(numbered) > _READ_MAX_CHARS
    if truncated:
        numbered = numbered[:_READ_MAX_CHARS]
    header = f"# {rel} ({len(lines)} ligne(s))"
    if truncated:
        header += " : RÉSULTAT TRONQUÉ, relire avec offset/limit pour la suite"
    return FsToolResult("Read", True, text=f"{header}\n{numbered}")
def _do_glob(root: Path, args: dict) -> FsToolResult:
    pattern = (args.get("pattern") or "").strip()
    if not pattern:
        raise FsToolError("paramètre 'pattern' manquant")
    if ".." in pattern or pattern.startswith(("/", "\\")):
        raise FsToolError(f"motif glob invalide : {pattern}")
    root = root.resolve()
    matches: list[str] = []
    try:
        for p in sorted(root.glob(pattern)):
            if not p.is_file():
                continue
            if _in_skipped_dir(p, root) or _is_sensitive(p):
                continue
            matches.append(str(p.relative_to(root)).replace("\\", "/"))
            if len(matches) >= _GLOB_MAX:
                break
    except (ValueError, OSError) as e:
        raise FsToolError(f"motif glob invalide : {e}") from e
    if not matches:
        return FsToolResult(
            "Glob", True, text=f"Aucun fichier ne correspond à « {pattern} »."
        )
    head = f"{len(matches)} fichier(s) pour « {pattern} »"
    if len(matches) >= _GLOB_MAX:
        head += " (limite atteinte)"
    return FsToolResult("Glob", True, text=f"{head} :\n" + "\n".join(matches))
def _do_grep(root: Path, args: dict) -> FsToolResult:
    pattern = (args.get("pattern") or "").strip()
    if not pattern:
        raise FsToolError("paramètre 'pattern' manquant")
    flags = re.IGNORECASE if args.get("ignore_case") else 0
    try:
        rx = re.compile(pattern, flags)
    except re.error as e:
        raise FsToolError(f"expression régulière invalide : {e}") from e
    root = root.resolve()
    base = root
    sub = (args.get("path") or "").strip()
    if sub:
        base = _resolve(root, sub)
        if not base.exists():
            raise FsToolError(f"chemin introuvable : {sub}")
    file_glob = (args.get("glob") or "**/*").strip()
    if ".." in file_glob:
        raise FsToolError(f"motif glob invalide : {file_glob}")
    if base.is_file():
        files = [base]
    else:
        try:
            files = sorted(base.glob(file_glob))
        except (ValueError, OSError) as e:
            raise FsToolError(f"motif glob invalide : {e}") from e
    out: list[str] = []
    scanned = 0
    for f in files:
        if scanned >= _GREP_MAX_FILES or len(out) >= _GREP_MAX:
            break
        if not f.is_file():
            continue
        if _in_skipped_dir(f, root) or _is_sensitive(f):
            continue
        if f.suffix.lower() in _BINARY_EXTS:
            continue
        try:
            if f.stat().st_size > _GREP_FILE_MAX_BYTES:
                continue
            raw = f.read_bytes()
        except OSError:
            continue
        if b"\x00" in raw[:4096]:
            continue
        scanned += 1
        rel = str(f.relative_to(root)).replace("\\", "/")
        for i, ln in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
            if rx.search(ln):
                out.append(f"{rel}:{i}: {ln.strip()[:240]}")
                if len(out) >= _GREP_MAX:
                    break
    if not out:
        return FsToolResult(
            "Grep", True,
            text=f"Aucune correspondance pour /{pattern}/ "
                 f"({scanned} fichier(s) scanné(s)).",
        )
    head = f"{len(out)} correspondance(s) pour /{pattern}/"
    if len(out) >= _GREP_MAX:
        head += " (limite atteinte, affine le motif)"
    return FsToolResult("Grep", True, text=f"{head} :\n" + "\n".join(out))
def execute_fs_tool(name: str, args: Optional[dict], root) -> FsToolResult:
    args = args or {}
    try:
        root_path = Path(root)
        if name == "Read":
            return _do_read(root_path, args)
        if name == "Grep":
            return _do_grep(root_path, args)
        if name == "Glob":
            return _do_glob(root_path, args)
        return FsToolResult(name, False, text=f"Erreur : outil inconnu « {name} ».")
    except FsToolError as e:
        return FsToolResult(name, False, text=f"Erreur : {e}")
    except Exception as e:
        logger.exception("execute_fs_tool(%s) a levé", name)
        return FsToolResult(name, False, text=f"Erreur interne : {e}")
TOOL_MARKER_OPEN = "<<<TOOLCALL>>>"
TOOL_MARKER_CLOSE = "<<<TOOLEND>>>"
def tool_call_label(name: str, args: Optional[dict]) -> str:
    args = args or {}
    if name == "Read":
        return str(args.get("path") or args.get("file_path") or "?")
    if name in ("Grep", "Glob"):
        return str(args.get("pattern") or "?")
    return name
def tool_call_marker(name: str, label: str, ok: bool) -> str:
    payload = json.dumps(
        {"tool": name, "label": label, "ok": bool(ok)}, ensure_ascii=False,
    )
    return f"{TOOL_MARKER_OPEN}{payload}{TOOL_MARKER_CLOSE}"