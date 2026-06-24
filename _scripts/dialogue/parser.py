import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Union
logger = logging.getLogger(__name__)
class ParserState(Enum):
    OUTSIDE = "outside"
    PROBE_OPENING = "probe_opening"
    INSIDE_TTS = "inside_tts"
    INSIDE_SUGGESTED_EDIT = "inside_suggested_edit"
    INSIDE_GOTO_SLIDE = "inside_goto_slide"
    INSIDE_SHOW_DOC = "inside_show_doc"
    INSIDE_REMEMBER = "inside_remember"
    INSIDE_END_SESSION = "inside_end_session"
    PROBE_CLOSING = "probe_closing"
class ParserEventType(Enum):
    TEXT_CHUNK = "text_chunk"
    TTS = "tts"
    SUGGESTED_EDIT = "suggested_edit"
    END_SESSION = "end_session"
    NEXT_SLIDE = "next_slide"
    GOTO_SLIDE = "goto_slide"
    SHOW_DOC = "show_doc"
    REMEMBER = "remember"
@dataclass
class ParserEvent:
    type: ParserEventType
    payload: Union[str, dict]
_TAG_TTS_OPEN = "<<<TTS>>>"
_TAG_SE_OPEN = "<<<SUGGESTED_EDIT>>>"
_TAG_END_SESSION = "<<<END_SESSION>>>"
_TAG_NEXT_SLIDE = "<<<NEXT_SLIDE>>>"
_TAG_GOTO_SLIDE_OPEN = "<<<GOTO_SLIDE>>>"
_TAG_SHOW_DOC_OPEN = "<<<SHOW_DOC>>>"
_TAG_REMEMBER_OPEN = "<<<REMEMBER>>>"
_TAG_CLOSE = "<<<END>>>"
_OPENING_PATTERNS = [
    _TAG_TTS_OPEN, _TAG_SE_OPEN,
    _TAG_END_SESSION, _TAG_NEXT_SLIDE, _TAG_GOTO_SLIDE_OPEN,
    _TAG_SHOW_DOC_OPEN,
    _TAG_REMEMBER_OPEN,
]
_VALID_SHOW_DOC_KINDS = {"enonce", "correction", "script"}
class StreamParser:
    def __init__(self, on_event: Callable[[ParserEvent], None]):
        self._on_event = on_event
        self._state: ParserState = ParserState.OUTSIDE
        self._probe_buffer: str = ""
        self._inner_buffer: str = ""
        self._text_buffer: str = ""
        self._return_state: Optional[ParserState] = None
    def feed(self, chunk: str) -> None:
        for char in chunk:
            self._step(char)
    def flush(self) -> None:
        self._flush_text_buffer()
        if self._probe_buffer:
            self._emit(ParserEventType.TEXT_CHUNK, self._probe_buffer)
            self._probe_buffer = ""
        if self._state != ParserState.OUTSIDE:
            logger.warning(
                "Stream tronque dans etat %s, contenu inner=%r perdu",
                self._state.value, self._inner_buffer
            )
            self._inner_buffer = ""
            self._return_state = None
            self._state = ParserState.OUTSIDE
    def _step(self, char: str) -> None:
        s = self._state
        if s == ParserState.OUTSIDE:
            self._step_outside(char)
        elif s == ParserState.PROBE_OPENING:
            self._step_probe_opening(char)
        elif s in (
            ParserState.INSIDE_TTS,
            ParserState.INSIDE_SUGGESTED_EDIT,
            ParserState.INSIDE_GOTO_SLIDE,
            ParserState.INSIDE_SHOW_DOC,
            ParserState.INSIDE_REMEMBER,
        ):
            self._step_inside_content(char)
        elif s == ParserState.PROBE_CLOSING:
            self._step_probe_closing(char)
    def _step_outside(self, char: str) -> None:
        if char == "<":
            self._flush_text_buffer()
            self._probe_buffer = char
            self._state = ParserState.PROBE_OPENING
        else:
            self._text_buffer += char
    def _step_probe_opening(self, char: str) -> None:
        self._probe_buffer += char
        if self._probe_buffer == _TAG_TTS_OPEN:
            self._probe_buffer = ""
            self._state = ParserState.INSIDE_TTS
        elif self._probe_buffer == _TAG_SE_OPEN:
            self._probe_buffer = ""
            self._state = ParserState.INSIDE_SUGGESTED_EDIT
        elif self._probe_buffer == _TAG_END_SESSION:
            self._probe_buffer = ""
            self._state = ParserState.OUTSIDE
            self._emit(ParserEventType.END_SESSION, "")
        elif self._probe_buffer == _TAG_NEXT_SLIDE:
            self._probe_buffer = ""
            self._state = ParserState.OUTSIDE
            self._emit(ParserEventType.NEXT_SLIDE, "")
        elif self._probe_buffer == _TAG_GOTO_SLIDE_OPEN:
            self._probe_buffer = ""
            self._state = ParserState.INSIDE_GOTO_SLIDE
        elif self._probe_buffer == _TAG_SHOW_DOC_OPEN:
            self._probe_buffer = ""
            self._state = ParserState.INSIDE_SHOW_DOC
        elif self._probe_buffer == _TAG_REMEMBER_OPEN:
            self._probe_buffer = ""
            self._state = ParserState.INSIDE_REMEMBER
        elif not self._is_opening_prefix(self._probe_buffer):
            self._emit(ParserEventType.TEXT_CHUNK, self._probe_buffer)
            self._probe_buffer = ""
            self._state = ParserState.OUTSIDE
    def _step_inside_content(self, char: str) -> None:
        if char == "<":
            self._return_state = self._state
            self._probe_buffer = char
            self._state = ParserState.PROBE_CLOSING
        else:
            self._inner_buffer += char
    def _step_probe_closing(self, char: str) -> None:
        self._probe_buffer += char
        if self._probe_buffer == _TAG_CLOSE:
            if self._return_state == ParserState.INSIDE_TTS:
                self._emit(ParserEventType.TTS, self._inner_buffer)
            elif self._return_state == ParserState.INSIDE_SUGGESTED_EDIT:
                parsed = self._try_parse_suggested_edit(self._inner_buffer)
                if parsed is not None:
                    self._emit(ParserEventType.SUGGESTED_EDIT, parsed)
            elif self._return_state == ParserState.INSIDE_GOTO_SLIDE:
                parsed = self._try_parse_goto_slide(self._inner_buffer)
                if parsed is not None:
                    self._emit(ParserEventType.GOTO_SLIDE, parsed)
            elif self._return_state == ParserState.INSIDE_SHOW_DOC:
                parsed = self._try_parse_show_doc(self._inner_buffer)
                if parsed is not None:
                    self._emit(ParserEventType.SHOW_DOC, parsed)
            elif self._return_state == ParserState.INSIDE_REMEMBER:
                parsed = self._try_parse_remember(self._inner_buffer)
                if parsed is not None:
                    self._emit(ParserEventType.REMEMBER, parsed)
            self._probe_buffer = ""
            self._inner_buffer = ""
            self._return_state = None
            self._state = ParserState.OUTSIDE
        elif not _TAG_CLOSE.startswith(self._probe_buffer):
            self._inner_buffer += self._probe_buffer
            self._probe_buffer = ""
            self._state = self._return_state
            self._return_state = None
    def _is_opening_prefix(self, buf: str) -> bool:
        return any(p.startswith(buf) for p in _OPENING_PATTERNS)
    def _flush_text_buffer(self) -> None:
        if self._text_buffer:
            self._emit(ParserEventType.TEXT_CHUNK, self._text_buffer)
            self._text_buffer = ""
    def _emit(self, event_type: ParserEventType, payload) -> None:
        self._on_event(ParserEvent(type=event_type, payload=payload))
    def _try_parse_suggested_edit(self, raw_json: str) -> Optional[dict]:
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.warning("SUGGESTED_EDIT JSON invalide: %s - raw=%r", e, raw_json)
            return None
        if not isinstance(data, dict):
            logger.warning("SUGGESTED_EDIT pas un dict: raw=%r", raw_json)
            return None
        required = {"file", "before", "after"}
        missing = required - data.keys()
        if missing:
            logger.warning(
                "SUGGESTED_EDIT champs manquants: %s - raw=%r", missing, raw_json,
            )
            return None
        for key in required:
            if not isinstance(data[key], str):
                logger.warning(
                    "SUGGESTED_EDIT champ %r pas une string: %r", key, data[key],
                )
                return None
        if not data["before"]:
            logger.warning("SUGGESTED_EDIT before vide")
            return None
        if data["before"] == data["after"]:
            logger.warning("SUGGESTED_EDIT before == after, edit no-op ignoree")
            return None
        if "reason" in data and not isinstance(data["reason"], str):
            data["reason"] = str(data["reason"])
        return data
    def _try_parse_goto_slide(self, raw_json: str) -> Optional[dict]:
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.warning("GOTO_SLIDE JSON invalide: %s - raw=%r", e, raw_json)
            return None
        if not isinstance(data, dict):
            logger.warning("GOTO_SLIDE pas un dict: raw=%r", raw_json)
            return None
        if "n" not in data:
            logger.warning("GOTO_SLIDE champ 'n' manquant: raw=%r", raw_json)
            return None
        n = data["n"]
        if not isinstance(n, int) or n < 1:
            logger.warning("GOTO_SLIDE n invalide (attendu int >= 1): %r", n)
            return None
        return {"n": n}
    def _try_parse_show_doc(self, raw_json: str) -> Optional[dict]:
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.warning("SHOW_DOC JSON invalide: %s - raw=%r", e, raw_json)
            return None
        if not isinstance(data, dict):
            logger.warning("SHOW_DOC pas un dict: raw=%r", raw_json)
            return None
        kind_raw = data.get("kind")
        if not isinstance(kind_raw, str):
            logger.warning("SHOW_DOC kind manquant ou pas string: %r", kind_raw)
            return None
        kind = kind_raw.strip().lower()
        kind_aliases = {
            "énoncé": "enonce", "enonce": "enonce", "énoncé officiel": "enonce",
            "corrigé": "correction", "corrige": "correction",
            "correction": "correction",
            "script": "script", "script imprimable": "script",
        }
        kind = kind_aliases.get(kind, kind)
        if kind not in _VALID_SHOW_DOC_KINDS:
            logger.warning("SHOW_DOC kind inconnu: %r", kind_raw)
            return None
        page = data.get("page")
        if not isinstance(page, int) or page < 1:
            logger.warning("SHOW_DOC page invalide (attendu int >= 1): %r", page)
            return None
        return {"kind": kind, "page": page}
    def _try_parse_remember(self, raw_json: str) -> Optional[dict]:
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            logger.warning("REMEMBER JSON invalide: %s - raw=%r", e, raw_json[:200])
            return None
        if not isinstance(data, dict):
            logger.warning("REMEMBER pas un dict: raw=%r", raw_json[:200])
            return None
        text = data.get("text")
        if not isinstance(text, str):
            logger.warning("REMEMBER champ 'text' manquant/pas string: %r", text)
            return None
        text = " ".join(text.split())
        if not text:
            logger.warning("REMEMBER text vide après normalisation")
            return None
        if len(text) > 200:
            logger.warning(
                "REMEMBER text %d chars > 200, tronqué", len(text),
            )
            text = text[:197].rstrip() + "…"
        return {"text": text}