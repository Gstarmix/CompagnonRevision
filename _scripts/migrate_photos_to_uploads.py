from __future__ import annotations
import argparse
import json
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from config import COURS_ROOT, SESSIONS_DIR, UPLOADS_DIR
logger = logging.getLogger(__name__)
_IMG_MD_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "heic", "gif", "svg", "bmp", "tiff"}
@dataclass
class MoveOp:
    session_id: str
    msg_id: str
    old_rel: str
    old_full: Path
    new_rel: str
    new_full: Path
    alt: str
@dataclass
class SessionStats:
    session_id: str
    moves: list[MoveOp] = field(default_factory=list)
    skipped_missing: list[str] = field(default_factory=list)
    skipped_other: list[str] = field(default_factory=list)
    json_updated: bool = False
def _is_cours_relative_path(rel: str) -> bool:
    rel = rel.strip()
    if not rel:
        return False
    if rel.startswith(("http://", "https://", "_uploads/", "/api/")):
        return False
    if rel.startswith(("/", "\\")):
        return False
    if len(rel) >= 2 and rel[1] == ":":
        return False
    return True
def _plan_session(data: dict, session_id: str) -> SessionStats:
    stats = SessionStats(session_id=session_id)
    messages = data.get("messages") or {}
    if not isinstance(messages, dict):
        return stats
    seen_old_paths: set[str] = set()
    for msg_id, msg in messages.items():
        if not isinstance(msg, dict):
            continue
        if msg.get("role") != "student":
            continue
        text = msg.get("text") or ""
        for m in _IMG_MD_RE.finditer(text):
            alt = m.group(1).strip()
            old_rel = m.group(2).strip().replace("\\", "/")
            if not _is_cours_relative_path(old_rel):
                continue
            try:
                old_full = (COURS_ROOT / old_rel).resolve()
                old_full.relative_to(COURS_ROOT.resolve())
            except (ValueError, OSError):
                stats.skipped_other.append(old_rel)
                continue
            if not old_full.is_file():
                stats.skipped_missing.append(old_rel)
                continue
            ext = old_full.suffix.lower().lstrip(".")
            if ext not in _IMAGE_EXTS:
                stats.skipped_other.append(old_rel)
                continue
            if old_rel in seen_old_paths:
                first = next((mv for mv in stats.moves if mv.old_rel == old_rel), None)
                if first is not None:
                    stats.moves.append(MoveOp(
                        session_id=session_id, msg_id=msg_id,
                        old_rel=old_rel, old_full=old_full,
                        new_rel=first.new_rel, new_full=first.new_full,
                        alt=alt,
                    ))
                continue
            seen_old_paths.add(old_rel)
            new_dir = UPLOADS_DIR / session_id / "photos"
            new_full = new_dir / old_full.name
            v = 1
            stem = old_full.stem
            suffix = old_full.suffix
            base_stem = stem
            while new_full.exists():
                new_full = new_dir / f"{base_stem}_mig{v}{suffix}"
                v += 1
            new_rel = new_full.relative_to(UPLOADS_DIR).as_posix()
            stats.moves.append(MoveOp(
                session_id=session_id, msg_id=msg_id,
                old_rel=old_rel, old_full=old_full,
                new_rel=new_rel, new_full=new_full, alt=alt,
            ))
    return stats
def _apply_moves(data: dict, stats: SessionStats, *, dry_run: bool) -> bool:
    if not stats.moves:
        return False
    physical_moves: dict[str, Path] = {}
    for mv in stats.moves:
        if mv.old_rel in physical_moves:
            continue
        physical_moves[mv.old_rel] = mv.new_full
        if dry_run:
            continue
        mv.new_full.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(mv.old_full), str(mv.new_full))
        except (OSError, shutil.Error) as e:
            logger.error("move FAILED %s → %s : %s", mv.old_full, mv.new_full, e)
            raise
    messages = data.get("messages") or {}
    by_msg: dict[str, list[MoveOp]] = {}
    for mv in stats.moves:
        by_msg.setdefault(mv.msg_id, []).append(mv)
    for msg_id, mvs in by_msg.items():
        msg = messages.get(msg_id)
        if not isinstance(msg, dict):
            continue
        text = msg.get("text") or ""
        for mv in mvs:
            old_md = f"![{mv.alt}]({mv.old_rel})"
            new_md = f"![{mv.alt}](_uploads/{mv.new_rel})"
            text = text.replace(old_md, new_md)
        msg["text"] = text
    branch_path = data.get("current_branch_path") or []
    if branch_path and isinstance(branch_path, list):
        new_transcript = []
        for mid in branch_path:
            entry = messages.get(mid)
            if not isinstance(entry, dict):
                continue
            new_transcript.append({
                "role": entry.get("role"),
                "text": entry.get("text"),
                "at": entry.get("at"),
                "id": mid,
            })
        data["transcript"] = new_transcript
    session_photos = data.get("session_photos") or []
    if isinstance(session_photos, list):
        for ph in session_photos:
            if not isinstance(ph, dict):
                continue
            if ph.get("storage") == "uploads":
                continue
            old_rel = ph.get("rel_path") or ""
            if old_rel in physical_moves:
                new_full = physical_moves[old_rel]
                new_rel = new_full.relative_to(UPLOADS_DIR).as_posix()
                ph["rel_path"] = new_rel
                ph["storage"] = "uploads"
                ph["migrated_from"] = old_rel
    return True
def _atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
def _do_backup(sessions_dir: Path) -> Path:
    backup_dir = sessions_dir / "_backup_pre_a10_3"
    if backup_dir.exists():
        raise RuntimeError(
            f"Backup déjà présent : {backup_dir}. Supprime-le ou renomme-le "
            "avant de relancer (le script refuse d'écraser un backup existant)."
        )
    backup_dir.mkdir(parents=True)
    n = 0
    for src in sessions_dir.glob("*.json"):
        shutil.copy2(str(src), str(backup_dir / src.name))
        n += 1
    logger.info("Backup : %d sessions copiées dans %s", n, backup_dir)
    return backup_dir
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Migre les photos de séance depuis COURS/.../photos/ vers _uploads/{session_id}/photos/"
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Exécute la migration (sinon dry-run uniquement, défaut)",
    )
    parser.add_argument(
        "--no-backup", action="store_true",
        help="Skip le backup auto de _sessions/ (déconseillé)",
    )
    parser.add_argument(
        "--sessions-dir", type=Path, default=SESSIONS_DIR,
        help=f"Dossier des sessions (défaut : {SESSIONS_DIR})",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    sessions_dir: Path = args.sessions_dir
    if not sessions_dir.is_dir():
        logger.error("Sessions dir introuvable : %s", sessions_dir)
        return 1
    mode = "APPLY" if args.apply else "DRY-RUN"
    logger.info("=== Migration photos COURS → _uploads (%s) ===", mode)
    logger.info("Sessions dir : %s", sessions_dir)
    logger.info("COURS_ROOT    : %s", COURS_ROOT)
    logger.info("UPLOADS_DIR   : %s", UPLOADS_DIR)
    if args.apply and not args.no_backup:
        try:
            _do_backup(sessions_dir)
        except RuntimeError as e:
            logger.error("Backup refusé : %s", e)
            return 2
    plans: list[tuple[Path, dict, SessionStats]] = []
    for json_path in sorted(sessions_dir.glob("*.json")):
        try:
            with json_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Skip %s : %s", json_path.name, e)
            continue
        session_id = data.get("session_id") or json_path.stem
        stats = _plan_session(data, session_id)
        if stats.moves or stats.skipped_missing:
            plans.append((json_path, data, stats))
    total_moves = sum(len({mv.old_rel for mv in p[2].moves}) for p in plans)
    total_md_updates = sum(len(p[2].moves) for p in plans)
    total_missing = sum(len(p[2].skipped_missing) for p in plans)
    total_other = sum(len(p[2].skipped_other) for p in plans)
    logger.info("Sessions avec changements : %d", len(plans))
    logger.info("Photos à déplacer (uniques) : %d", total_moves)
    logger.info("Références markdown à update : %d", total_md_updates)
    logger.info("Fichiers introuvables (skip) : %d", total_missing)
    logger.info("Autres skip (ext/path)        : %d", total_other)
    for json_path, _data, stats in plans:
        unique_moves = len({mv.old_rel for mv in stats.moves})
        if unique_moves == 0 and not stats.skipped_missing:
            continue
        logger.info("--- %s", json_path.name)
        logger.info("    %d photos → _uploads/%s/photos/", unique_moves, stats.session_id)
        if stats.skipped_missing:
            logger.info(
                "    %d fichier(s) introuvable(s) (le markdown reste pointer vers COURS, pas grave) : %s",
                len(stats.skipped_missing),
                ", ".join(stats.skipped_missing[:3]) + ("…" if len(stats.skipped_missing) > 3 else ""),
            )
    if not args.apply:
        logger.info("")
        logger.info("Mode dry-run. Pour appliquer : --apply")
        return 0
    logger.info("")
    logger.info("=== APPLY ===")
    applied_sessions = 0
    applied_moves = 0
    for json_path, data, stats in plans:
        if not stats.moves:
            continue
        try:
            mutated = _apply_moves(data, stats, dry_run=False)
        except (OSError, shutil.Error) as e:
            logger.error("Session %s : abandonnée à cause de l'erreur : %s",
                         json_path.name, e)
            continue
        if mutated:
            _atomic_write_json(json_path, data)
            applied_sessions += 1
            applied_moves += len({mv.old_rel for mv in stats.moves})
    logger.info("Migration terminée : %d sessions modifiées, %d photos déplacées",
                applied_sessions, applied_moves)
    return 0
if __name__ == "__main__":
    raise SystemExit(main())