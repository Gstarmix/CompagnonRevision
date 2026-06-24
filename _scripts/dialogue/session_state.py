import json
import logging
import threading
import uuid
from pathlib import Path
from typing import Optional
from config import COURS_ROOT, PROJECT_ROOT, SCHEMA_VERSION_SESSION
from utils import atomic_write_json, now_iso, parse_iso, seconds_since
from prompt_builder import SessionContext
logger = logging.getLogger(__name__)
RESUMABLE_LAST_ALIVE_THRESHOLD_SECONDS = 5 * 60
class SessionState:
    HEARTBEAT_INTERVAL_SECONDS = 30
    def __init__(
        self,
        session_id: str,
        sessions_dir: Path,
        context: SessionContext,
        engine: str,
        model: str,
    ):
        self._path: Path = sessions_dir / f"{session_id}.json"
        self._lock = threading.Lock()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_heartbeat = threading.Event()
        self._context: SessionContext = context
        self._data: dict = self._build_initial_data(
            session_id, context, engine, model
        )
    @classmethod
    def load(cls, path: Path) -> "SessionState":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("schema_version") != SCHEMA_VERSION_SESSION:
            logger.warning(
                "Session %s : schema_version %r != %r attendu",
                path.name, raw.get("schema_version"), SCHEMA_VERSION_SESSION,
            )
        instance = cls.__new__(cls)
        instance._path = path
        instance._lock = threading.Lock()
        instance._heartbeat_thread = None
        instance._stop_heartbeat = threading.Event()
        instance._data = raw
        try:
            instance._context = SessionContext(
                matiere=raw.get("matiere", ""),
                type=raw.get("type", ""),
                num=raw.get("num", ""),
                exo=raw.get("exo", "full"),
                annee=raw.get("annee") or None,
            )
        except Exception as exc:
            logger.warning(
                "Session %s : reconstruction context a échoué (%s), context=None",
                path.name, exc,
            )
            instance._context = None
        return instance
    @classmethod
    def find_resumable(cls, sessions_dir: Path) -> list[Path]:
        if not sessions_dir.exists():
            return []
        results: list[Path] = []
        for path in sorted(sessions_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("Session illisible ignorée : %s (%s)", path.name, e)
                continue
            if data.get("interrupted"):
                results.append(path)
                continue
            if data.get("ended_at"):
                continue
            elapsed = seconds_since(data.get("last_alive"))
            if elapsed is None or elapsed > RESUMABLE_LAST_ALIVE_THRESHOLD_SECONDS:
                results.append(path)
        return results
    def start(self) -> None:
        with self._lock:
            self._data["last_alive"] = now_iso()
            atomic_write_json(self._path, self._data)
        self._start_heartbeat()
    def finalize(self, interrupted: bool = False) -> None:
        self._stop_heartbeat.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(
                timeout=self.HEARTBEAT_INTERVAL_SECONDS + 5
            )
            self._heartbeat_thread = None
        with self._lock:
            ended = now_iso()
            self._data["ended_at"] = ended
            self._data["last_alive"] = ended
            self._data["interrupted"] = bool(interrupted)
            self._data["interrupted_at"] = ended if interrupted else None
            try:
                started = parse_iso(self._data["started_at"])
                ended_dt = parse_iso(ended)
                self._data["duration_seconds"] = int(
                    (ended_dt - started).total_seconds()
                )
            except (KeyError, ValueError, TypeError):
                self._data["duration_seconds"] = None
            atomic_write_json(self._path, self._data)
    def append_exchange(
        self,
        role: str,
        text: str,
        audio_path: Optional[Path] = None,
    ) -> None:
        if role not in ("claude", "student"):
            raise ValueError(
                f"role invalide : {role!r} (attendu 'claude' | 'student')"
            )
        msg_id = f"msg_{uuid.uuid4().hex[:12]}"
        with self._lock:
            self._ensure_branches_initialized()
            path = self._data["current_branch_path"]
            parent_id = path[-1] if path else None
            entry: dict = {
                "id": msg_id,
                "parent_id": parent_id,
                "role": role,
                "at": now_iso(),
                "text": text,
            }
            if audio_path is not None:
                entry["audio_path"] = self._relativize(audio_path)
            self._data["messages"][msg_id] = entry
            path.append(msg_id)
            self._data["transcript"] = self._derive_transcript()
            self._data["stats"]["total_exchanges"] += 1
            atomic_write_json(self._path, self._data)
    def edit_message_in_place(self, msg_id: str, new_text: str) -> dict:
        with self._lock:
            self._ensure_branches_initialized()
            messages = self._data["messages"]
            if msg_id not in messages:
                raise KeyError(f"message inconnu : {msg_id}")
            entry = messages[msg_id]
            entry["text"] = new_text
            entry["edited_at"] = now_iso()
            self._data["transcript"] = self._derive_transcript()
            atomic_write_json(self._path, self._data)
            return dict(entry)
    def create_branch_at(self, msg_id: str, new_text: str) -> dict:
        with self._lock:
            self._ensure_branches_initialized()
            messages = self._data["messages"]
            if msg_id not in messages:
                raise KeyError(f"message inconnu : {msg_id}")
            original = messages[msg_id]
            new_id = f"msg_{uuid.uuid4().hex[:12]}"
            new_entry = {
                "id": new_id,
                "parent_id": original.get("parent_id"),
                "role": original["role"],
                "at": now_iso(),
                "text": new_text,
                "branched_from": msg_id,
            }
            messages[new_id] = new_entry
            path = self._data["current_branch_path"]
            try:
                cut = path.index(msg_id)
                self._data["current_branch_path"] = path[:cut] + [new_id]
            except ValueError:
                chain = [new_id]
                p = new_entry["parent_id"]
                while p is not None:
                    chain.insert(0, p)
                    p = messages.get(p, {}).get("parent_id")
                self._data["current_branch_path"] = chain
            self._data["transcript"] = self._derive_transcript()
            atomic_write_json(self._path, self._data)
            return dict(new_entry)
    def switch_branch_to(self, target_msg_id: str) -> list[str]:
        with self._lock:
            self._ensure_branches_initialized()
            messages = self._data["messages"]
            if target_msg_id not in messages:
                raise KeyError(f"message inconnu : {target_msg_id}")
            chain: list[str] = [target_msg_id]
            p = messages[target_msg_id].get("parent_id")
            while p is not None:
                chain.insert(0, p)
                p = messages.get(p, {}).get("parent_id")
            cursor = target_msg_id
            while True:
                children = [
                    m_id for m_id, m in messages.items()
                    if m.get("parent_id") == cursor
                ]
                if not children:
                    break
                children.sort()
                next_id = children[-1]
                chain.append(next_id)
                cursor = next_id
            self._data["current_branch_path"] = chain
            self._data["transcript"] = self._derive_transcript()
            atomic_write_json(self._path, self._data)
            return list(chain)
    def get_siblings(self, msg_id: str) -> list[dict]:
        with self._lock:
            self._ensure_branches_initialized()
            messages = self._data["messages"]
            if msg_id not in messages:
                raise KeyError(f"message inconnu : {msg_id}")
            parent_id = messages[msg_id].get("parent_id")
            siblings = [
                dict(m) for m in messages.values()
                if m.get("parent_id") == parent_id
            ]
            siblings.sort(key=lambda m: m.get("at", ""))
            return siblings
    def _derive_transcript(self) -> list[dict]:
        messages = self._data.get("messages") or {}
        path = self._data.get("current_branch_path") or []
        out = []
        for mid in path:
            entry = messages.get(mid)
            if entry:
                out.append(dict(entry))
        return out
    def _ensure_branches_initialized(self) -> None:
        if "messages" in self._data and "current_branch_path" in self._data:
            return
        legacy = self._data.get("transcript") or []
        messages: dict[str, dict] = {}
        path: list[str] = []
        prev_id: Optional[str] = None
        for entry in legacy:
            mid = f"msg_{uuid.uuid4().hex[:12]}"
            new_entry = dict(entry)
            new_entry["id"] = mid
            new_entry["parent_id"] = prev_id
            messages[mid] = new_entry
            path.append(mid)
            prev_id = mid
        self._data["messages"] = messages
        self._data["current_branch_path"] = path
    def increment_stat(self, key: str, delta: float = 1) -> None:
        with self._lock:
            self._data["stats"][key] = self._data["stats"].get(key, 0) + delta
            atomic_write_json(self._path, self._data)
    def set_meta(self, key: str, value) -> None:
        with self._lock:
            self._data[key] = value
            atomic_write_json(self._path, self._data)
    @property
    def path(self) -> Path:
        return self._path
    @property
    def data(self) -> dict:
        return self._data
    @property
    def context(self) -> SessionContext:
        return self._context
    def _build_initial_data(
        self,
        session_id: str,
        context: SessionContext,
        engine: str,
        model: str,
    ) -> dict:
        now = now_iso()
        return {
            "schema_version": SCHEMA_VERSION_SESSION,
            "session_id": session_id,
            "matiere": context.matiere,
            "type": context.type,
            "num": context.num,
            "exo": context.exo,
            "annee": context.annee,
            "started_at": now,
            "ended_at": None,
            "last_alive": now,
            "interrupted": False,
            "interrupted_at": None,
            "resumed_at": None,
            "duration_seconds": None,
            "engine": engine,
            "model": model,
            "colle_format": "mixte",
            "corrige_anchor": "strict",
            "phase": "active",
            "recap": None,
            "recap_at": None,
            "final_closed_at": None,
            "context_files": self._build_context_files(context),
            "transcript": [],
            "messages": {},
            "current_branch_path": [],
            "stats": {
                "total_exchanges": 0,
                "claude_tokens_input": 0,
                "claude_tokens_output": 0,
                "whisper_seconds": 0.0,
                "tts_calls": 0,
                "photos_received": 0,
                "silences_detected": 0,
            },
        }
    def _build_context_files(self, context: SessionContext) -> dict:
        files: dict = {}
        if context.enonce_path is not None:
            files["enonce"] = self._relativize(context.enonce_path)
        if context.correction_paths:
            files["corrections"] = [
                self._relativize(p) for p in context.correction_paths
            ]
        if context.tache_path is not None:
            files["tache"] = self._relativize(context.tache_path)
        if context.script_oral_path is not None:
            files["script_oral"] = self._relativize(context.script_oral_path)
        if context.slides_pdf_path is not None:
            files["slides_pdf"] = self._relativize(context.slides_pdf_path)
        if context.cm_transcription_path is not None:
            files["transcription_cm"] = self._relativize(context.cm_transcription_path)
        if context.cm_poly_path is not None:
            files["poly_cm"] = self._relativize(context.cm_poly_path)
        return files
    def _relativize(self, path) -> str:
        if path is None:
            raise TypeError("_relativize: path is None (call-site doit gater)")
        path = Path(path)
        for root in (COURS_ROOT, PROJECT_ROOT):
            try:
                rel = path.resolve().relative_to(root.resolve())
                return rel.as_posix()
            except (ValueError, OSError):
                continue
        return path.as_posix()
    def _start_heartbeat(self) -> None:
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            return
        self._stop_heartbeat.clear()
        thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="session-heartbeat",
        )
        self._heartbeat_thread = thread
        thread.start()
    def _heartbeat_loop(self) -> None:
        while not self._stop_heartbeat.is_set():
            with self._lock:
                self._data["last_alive"] = now_iso()
                try:
                    atomic_write_json(self._path, self._data)
                except OSError as e:
                    logger.warning("Heartbeat atomic_write a échoué : %s", e)
            self._stop_heartbeat.wait(self.HEARTBEAT_INTERVAL_SECONDS)