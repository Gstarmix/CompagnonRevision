"""
rename_old_photos.py : Phase A.10.13g (2026-05-14).

Renommage rétroactif des photos pré-A.10.13d (qui sont restées avec
des noms illisibles type `cropped_1778561703186_v1.jpg` ou
`photo_AN1_TD5_ex11_v1.jpg`). Appelle Gemini Flash 2.5 sur chaque
photo pour obtenir 3-5 mots-clés descriptifs, génère un slug, renomme
physiquement le fichier, et met à jour les références dans le JSON
de session (`session_photos[]` + markdown du transcript).

Modes :
    python rename_old_photos.py                    # dry-run (default)
    python rename_old_photos.py --apply            # exécute
    python rename_old_photos.py --apply --limit 10 # limite à 10 photos
    python rename_old_photos.py --session-id X     # une session précise

Garde-fous :
- Skip les photos déjà au format OCR-renamed (regex match).
- Skip les fichiers physiquement introuvables.
- Backup auto de _sessions/ vers _sessions/_backup_pre_rename_a10_13g/.
- Idempotent : un re-run ne refait rien.
- Coût Gemini Flash 2.5 : ~$0.0001 par image. 33 photos = ~$0.003.

Prérequis :
- GEMINI_API_KEY dans l'env ou _secrets/.env (cf. claude_client.py §Gemini).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import COURS_ROOT, SESSIONS_DIR, UPLOADS_DIR  # noqa: E402

logger = logging.getLogger(__name__)

# Pattern OCR-renamed (A.10.13d) : YYYY-MM-DD_HHMM_<kind>_<slug>_vN.ext
_RE_ALREADY_RENAMED = re.compile(
    r"^\d{4}-\d{2}-\d{2}_\d{4}_[a-z0-9_]+_v\d+\.[a-z0-9]+$",
    re.IGNORECASE,
)

# Stopwords FR (pour purger les mots inutiles du slug Gemini)
_STOPWORDS_FR = {
    "le", "la", "les", "des", "une", "un", "que", "qui", "pour", "avec",
    "dans", "sur", "par", "est", "ont", "ces", "son", "ses", "fait",
    "tout", "plus", "très", "tres", "bien", "comme", "mais", "donc",
    "etre", "être", "avoir", "cette", "leur", "leurs", "votre", "vos",
    "notre", "nos", "image", "photo", "voici", "ceci", "cela",
}

_RE_KEYWORDS_PROMPT = """\
Décris ce qui est sur cette image en 3 à 5 mots-clés descriptifs.
Format strict : UN SEUL mot composé minuscule, mots reliés par underscore.
- Sans accents, sans espaces, sans ponctuation
- Mots significatifs uniquement (pas d'articles « le », « les », « un »)
- Si c'est une photo d'écriture/cahier scolaire, prends 3-5 mots-clés
  qui résument le contenu (concepts, formules, exo)
- Si tu ne peux pas identifier, réponds : "image_indistincte"

Exemples valides :
- table_verite_xor
- pseudo_code_recursion
- equation_quadratique_discriminant
- schema_circuit_and_or
- calcul_pose_division_euclidienne
- texte_definition_complexite

Réponds UNIQUEMENT par le mot composé, sans phrase ni explication.
"""

_GEMINI_MODEL_DEFAULT = "gemini-2.5-flash"


def _slug_from_gemini_response(text: str) -> Optional[str]:
    """Nettoie la réponse Gemini pour en faire un slug valide.
    Garde max 40 chars, alphanum + underscore."""
    if not text:
        return None
    text = text.strip().splitlines()[0].strip().strip(".,;:!?")
    if not text or text.lower() in ("image_indistincte", "indistincte"):
        return None
    text = text.lower()
    # Sanitize : alphanum + _ uniquement
    text = re.sub(r"[^a-z0-9_]", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        return None
    # Filtre stopwords sur les mots individuels
    words = [w for w in text.split("_") if w and w not in _STOPWORDS_FR]
    if not words:
        return None
    slug = "_".join(words[:5])  # max 5 mots
    return slug[:40]  # cap 40 chars


def _call_gemini_on_image(image_path: Path, model: str) -> Optional[str]:
    """Appelle Gemini Flash sur une image, retourne le slug extrait ou None."""
    try:
        from google import genai
        from google.genai import types as genai_types
    except ImportError:
        logger.error("SDK google-genai indisponible. pip install google-genai")
        return None

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY absent (env ou _secrets/.env)")
        return None

    try:
        image_bytes = image_path.read_bytes()
    except OSError as e:
        logger.warning("Lecture image %s : %s", image_path, e)
        return None

    ext = image_path.suffix.lstrip(".").lower()
    mime_map = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "webp": "image/webp", "gif": "image/gif", "heic": "image/heic",
    }
    mime = mime_map.get(ext, "image/jpeg")

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=[
                genai_types.Part.from_bytes(data=image_bytes, mime_type=mime),
                _RE_KEYWORDS_PROMPT,
            ],
        )
        text = (response.text or "").strip()
    except Exception as e:  # noqa: BLE001
        logger.warning("Gemini call a échoué pour %s : %s", image_path.name, e)
        return None

    return _slug_from_gemini_response(text)


def _try_load_secrets_env() -> None:
    """Charge _secrets/.env si présent (sans dépendance dotenv)."""
    env_path = ROOT / "_secrets" / ".env"
    if not env_path.is_file():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and v and k not in os.environ:
                os.environ[k] = v
    except OSError:
        pass


def _atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _do_backup(sessions_dir: Path) -> Optional[Path]:
    backup_dir = sessions_dir / "_backup_pre_rename_a10_13g"
    if backup_dir.exists():
        raise RuntimeError(
            f"Backup déjà présent : {backup_dir}. "
            "Supprime-le ou renomme-le avant de relancer."
        )
    backup_dir.mkdir(parents=True)
    import shutil
    n = 0
    for src in sessions_dir.glob("*.json"):
        shutil.copy2(str(src), str(backup_dir / src.name))
        n += 1
    logger.info("Backup : %d sessions copiées dans %s", n, backup_dir)
    return backup_dir


def _rename_photo_entry(
    photo_entry: dict,
    session_data: dict,
    *,
    dry_run: bool,
    model: str,
) -> Optional[dict]:
    """Renomme une photo entry. Retourne {old_rel, new_rel} si OK."""
    storage = photo_entry.get("storage") or "cours"
    base_root = UPLOADS_DIR if storage == "uploads" else COURS_ROOT
    old_rel = photo_entry.get("rel_path") or ""
    if not old_rel:
        return None

    # Skip si déjà renommé
    old_filename = photo_entry.get("filename") or Path(old_rel).name
    if _RE_ALREADY_RENAMED.match(old_filename):
        return None

    try:
        old_full = (base_root / old_rel).resolve()
        old_full.relative_to(base_root.resolve())
    except (ValueError, OSError):
        logger.warning("Skip (path invalide) : %s", old_rel)
        return None
    if not old_full.is_file():
        logger.warning("Skip (introuvable) : %s", old_full)
        return None

    # Appelle Gemini pour générer le slug
    if dry_run:
        logger.info("DRY-RUN appellerait Gemini sur %s", old_full.name)
        return {"old_rel": old_rel, "new_rel": old_rel + "  (dry-run)"}

    slug = _call_gemini_on_image(old_full, model=model)
    if not slug:
        logger.info("Skip (slug vide) : %s", old_full.name)
        return None

    # Détermine le timestamp : utilise sent_at de l'entry si dispo, sinon mtime
    sent_at = photo_entry.get("sent_at") or ""
    try:
        if sent_at:
            ts = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
        else:
            ts = datetime.fromtimestamp(old_full.stat().st_mtime)
    except (ValueError, OSError):
        ts = datetime.now()
    timestamp = ts.strftime("%Y-%m-%d_%H%M")

    ext = old_full.suffix.lstrip(".").lower() or "jpg"
    # Kind générique pour le rattrapage (on n'a pas l'OCR détaillé)
    safe_kind = "image"
    base_name = f"{timestamp}_{safe_kind}_{slug}"
    parent = old_full.parent
    v = 1
    while (parent / f"{base_name}_v{v}.{ext}").exists():
        v += 1
        if v > 99:
            return None
    new_full = parent / f"{base_name}_v{v}.{ext}"
    try:
        old_full.rename(new_full)
    except OSError as e:
        logger.error("rename %s → %s : %s", old_full, new_full, e)
        return None

    try:
        new_rel = new_full.relative_to(base_root.resolve()).as_posix()
    except ValueError:
        return None
    logger.info("✓ %s → %s", old_filename, new_full.name)

    # Update l'entry photo
    photo_entry["rel_path"] = new_rel
    photo_entry["filename"] = new_full.name
    photo_entry["renamed_from_ocr"] = old_filename

    # Update le markdown dans les messages du transcript
    # ![original_name](old_rel) → ![original_name](new_rel)
    # Avec préfixe _uploads/ si storage="uploads"
    old_md_path = f"_uploads/{old_rel}" if storage == "uploads" else old_rel
    new_md_path = f"_uploads/{new_rel}" if storage == "uploads" else new_rel
    messages = session_data.get("messages") or {}
    for msg in messages.values():
        if isinstance(msg, dict) and msg.get("role") == "student":
            text = msg.get("text") or ""
            if old_md_path in text:
                msg["text"] = text.replace(old_md_path, new_md_path)
    # Re-dérive transcript[]
    branch_path = session_data.get("current_branch_path") or []
    if branch_path:
        new_transcript = []
        for mid in branch_path:
            entry = messages.get(mid)
            if isinstance(entry, dict):
                new_transcript.append({
                    "role": entry.get("role"),
                    "text": entry.get("text"),
                    "at": entry.get("at"),
                    "id": mid,
                })
        session_data["transcript"] = new_transcript

    return {"old_rel": old_rel, "new_rel": new_rel}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Renomme rétroactivement les anciennes photos via Gemini Flash OCR"
    )
    parser.add_argument("--apply", action="store_true",
                       help="Exécute le rename (sinon dry-run)")
    parser.add_argument("--limit", type=int, default=0,
                       help="Limite N photos (0 = pas de limite)")
    parser.add_argument("--session-id", type=str, default=None,
                       help="Limite à une session précise (ex : 2026-05-14_PRG2_TP8_…)")
    parser.add_argument("--no-backup", action="store_true",
                       help="Skip le backup auto (déconseillé)")
    parser.add_argument("--model", default=_GEMINI_MODEL_DEFAULT,
                       help=f"Modèle Gemini (défaut : {_GEMINI_MODEL_DEFAULT})")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    _try_load_secrets_env()

    mode = "APPLY" if args.apply else "DRY-RUN"
    logger.info("=== Rename rétroactif photos via Gemini Flash (%s) ===", mode)

    if args.apply and not args.no_backup:
        try:
            _do_backup(SESSIONS_DIR)
        except RuntimeError as e:
            logger.error("Backup refusé : %s", e)
            return 2

    sessions_paths = sorted(SESSIONS_DIR.glob("*.json"))
    if args.session_id:
        sessions_paths = [p for p in sessions_paths if p.stem == args.session_id]
        if not sessions_paths:
            logger.error("Session %s introuvable", args.session_id)
            return 1

    total_renamed = 0
    total_scanned = 0
    for sess_path in sessions_paths:
        try:
            with sess_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Skip %s : %s", sess_path.name, e)
            continue
        photos = data.get("session_photos") or []
        if not photos:
            continue
        session_renamed = []
        for ph in photos:
            total_scanned += 1
            if args.limit and total_renamed >= args.limit:
                break
            result = _rename_photo_entry(
                ph, data,
                dry_run=not args.apply,
                model=args.model,
            )
            if result:
                session_renamed.append(result)
                total_renamed += 1
        if session_renamed:
            logger.info("Session %s : %d photo(s) renommée(s)",
                       sess_path.name, len(session_renamed))
            if args.apply:
                _atomic_write_json(sess_path, data)
        if args.limit and total_renamed >= args.limit:
            logger.info("Limit %d atteinte, stop.", args.limit)
            break

    logger.info("")
    logger.info("Total scannés : %d photo(s)", total_scanned)
    logger.info("Total renommés : %d", total_renamed)
    if not args.apply:
        logger.info("Mode dry-run. Pour appliquer : --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
