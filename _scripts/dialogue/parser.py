"""
parser.py : machine à états SSE pour Claude streaming.

Consomme un flux SSE caractère par caractère et émet des événements typés
(``TEXT_CHUNK``, ``TTS``, ``END_SESSION``). Le contenu d'une balise spéciale
n'est jamais visible côté front Flask : il est buffé puis extrait pour être
routé vers le moteur TTS ou la finalisation de session.

Cf. ARCHITECTURE.md §3 et CLAUDE.md §4.
"""

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional, Union

logger = logging.getLogger(__name__)


# ============================================================ États

class ParserState(Enum):
    OUTSIDE = "outside"                  # texte normal, accumulé pour batch flush
    PROBE_OPENING = "probe_opening"      # vu '<', on accumule pour matcher une balise
    INSIDE_TTS = "inside_tts"            # entre <<<TTS>>> et <<<END>>>
    INSIDE_SUGGESTED_EDIT = "inside_suggested_edit"  # entre <<<SUGGESTED_EDIT>>> et <<<END>>> (mode guidé)
    INSIDE_GOTO_SLIDE = "inside_goto_slide"  # entre <<<GOTO_SLIDE>>> et <<<END>>> (mode guidé, saut arbitraire)
    INSIDE_SHOW_DOC = "inside_show_doc"  # entre <<<SHOW_DOC>>> et <<<END>>> (mode guidé, panneau Docs)
    INSIDE_REMEMBER = "inside_remember"  # entre <<<REMEMBER>>> et <<<END>>> (Phase A.10, mémoire persistante)
    INSIDE_END_SESSION = "inside_end_session"  # réservé, non utilisé en pratique
    PROBE_CLOSING = "probe_closing"      # à l'intérieur d'une balise, vu '<' candidat


# ============================================================ Événements

class ParserEventType(Enum):
    TEXT_CHUNK = "text_chunk"
    TTS = "tts"
    SUGGESTED_EDIT = "suggested_edit"
    END_SESSION = "end_session"
    NEXT_SLIDE = "next_slide"
    GOTO_SLIDE = "goto_slide"
    SHOW_DOC = "show_doc"
    REMEMBER = "remember"  # Phase A.10 : sticky persistante émise par le tuteur


@dataclass
class ParserEvent:
    type: ParserEventType
    payload: Union[str, dict]


# ============================================================ Balises

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


# ============================================================ Parser

class StreamParser:
    """Machine à états qui consomme un stream SSE caractère par caractère
    et émet des événements pour le front et la couche dialogue.

    Tolérante aux malformations : une balise au JSON cassé est logguée
    en warning et l'événement n'est pas émis (la session continue).
    """

    def __init__(self, on_event: Callable[[ParserEvent], None]):
        self._on_event = on_event
        self._state: ParserState = ParserState.OUTSIDE
        self._probe_buffer: str = ""        # depuis '<' en attente de match
        self._inner_buffer: str = ""        # contenu entre balises (TTS / WP json)
        self._text_buffer: str = ""         # texte accumulé en OUTSIDE pour batch
        self._return_state: Optional[ParserState] = None  # parent depuis PROBE_CLOSING

    # ---------------------------------------------------------------- API publique

    def feed(self, chunk: str) -> None:
        """Consomme un chunk de stream et émet les événements appropriés."""
        for char in chunk:
            self._step(char)

    def flush(self) -> None:
        """Vide ce qui reste à la fin du stream.

        - Le ``_text_buffer`` accumulé en OUTSIDE part en TEXT_CHUNK final.
        - Le ``_probe_buffer`` (PROBE_OPENING en cours) part aussi en TEXT_CHUNK :
          un fragment de balise tronqué vaut mieux que rien côté affichage.
        - Si on est dans un INSIDE_*, le contenu accumulé est perdu avec un
          warning : on n'invente pas un event TTS depuis un fragment.
        """
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

    # ---------------------------------------------------------------- step interne

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
            # Mode guidé : le tuteur signale qu'on peut passer à la slide
            # suivante. Le SSE pousse l'event au front qui appelle
            # gotoNextSlide() après un court délai (laisser lire la réponse).
            self._probe_buffer = ""
            self._state = ParserState.OUTSIDE
            self._emit(ParserEventType.NEXT_SLIDE, "")
        elif self._probe_buffer == _TAG_GOTO_SLIDE_OPEN:
            # Mode guidé : saut arbitraire à une slide N. Contenu JSON
            # `{"n": int}` parsé entre la balise ouvrante et <<<END>>>.
            self._probe_buffer = ""
            self._state = ParserState.INSIDE_GOTO_SLIDE
        elif self._probe_buffer == _TAG_SHOW_DOC_OPEN:
            # Mode guidé : le tuteur prend le contrôle du panneau
            # Docs pour montrer une page précise (énoncé/corrigé/script).
            # Contenu JSON `{"kind": "...", "page": int}`.
            self._probe_buffer = ""
            self._state = ParserState.INSIDE_SHOW_DOC
        elif self._probe_buffer == _TAG_REMEMBER_OPEN:
            # Phase A.10 : mémoire persistante. Le tuteur signale qu'une
            # consigne doit être épinglée sur demande explicite de
            # l'étudiant (« retiens que… »). Contenu JSON `{"text": str}`
            # (text ≤ 200 chars). Le backend persiste via add_sticky
            # kind="tutor" + push event SSE pour refresh UI.
            self._probe_buffer = ""
            self._state = ParserState.INSIDE_REMEMBER
        elif not self._is_opening_prefix(self._probe_buffer):
            # Faux positif : flush comme texte, retour OUTSIDE.
            self._emit(ParserEventType.TEXT_CHUNK, self._probe_buffer)
            self._probe_buffer = ""
            self._state = ParserState.OUTSIDE
        # sinon (préfixe valide pas encore complet), on attend

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
            # Pas un close : réintégrer le probe au inner_buffer et retour parent.
            self._inner_buffer += self._probe_buffer
            self._probe_buffer = ""
            self._state = self._return_state
            self._return_state = None
        # sinon (préfixe valide), on attend

    # ---------------------------------------------------------------- helpers

    def _is_opening_prefix(self, buf: str) -> bool:
        return any(p.startswith(buf) for p in _OPENING_PATTERNS)

    def _flush_text_buffer(self) -> None:
        if self._text_buffer:
            self._emit(ParserEventType.TEXT_CHUNK, self._text_buffer)
            self._text_buffer = ""

    def _emit(self, event_type: ParserEventType, payload) -> None:
        self._on_event(ParserEvent(type=event_type, payload=payload))

    def _try_parse_suggested_edit(self, raw_json: str) -> Optional[dict]:
        """Parse + validation light d'un SUGGESTED_EDIT (mode guidé).

        Schéma attendu :
            {
              "file": "<chemin relatif COURS_ROOT>",
              "before": "<texte exact à remplacer>",
              "after": "<nouveau texte>",
              "reason": "<phrase courte, optionnel>"
            }

        La validation chemin (no traversal, sous COURS_ROOT) et l'unicité
        de ``before`` sont vérifiées au moment de l'**application** côté
        backend (``/api/apply_edit``), pas ici. Le parser émet seulement
        si le JSON est syntaxiquement bon et a les 3 champs requis.
        """
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
        # reason optionnel : coerce en string si présent
        if "reason" in data and not isinstance(data["reason"], str):
            data["reason"] = str(data["reason"])
        return data

    def _try_parse_goto_slide(self, raw_json: str) -> Optional[dict]:
        """Parse + valide le JSON d'un GOTO_SLIDE (mode guidé, saut arbitraire).

        Schéma attendu : ``{"n": int}`` où n est >= 1. La validation que n
        est dans la plage des slides chargées est faite côté front (le
        backend ne connaît pas le nombre total de slides du contexte).
        """
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
        """Parse + valide le JSON d'un SHOW_DOC.

        Schéma attendu : ``{"kind": "enonce"|"correction"|"script", "page": int}``.
        Le tuteur peut aussi écrire `"corrigé"` / `"énoncé"` / `"script"` en
        français ; on normalise vers les kind canoniques (sans accents).
        """
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
        # Normalise variantes FR/accentuées vers canoniques.
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
        """Parse + validation light d'un REMEMBER (Phase A.10, mémoire persistante).

        Schéma attendu :
            {"text": "<consigne courte impérative, ≤ 200 chars>"}

        Validation :
            - JSON syntaxique valide
            - `text` requis, string, non vide après strip
            - Cap soft à 200 chars (au-delà : warning, tronqué proprement
              à 197 chars + ellipsis) : protège contre un tuteur qui
              dump tout un paragraphe en sticky.

        La persistance effective (kind="tutor", ID, dedoublonnage texte
        identique) est faite côté backend Flask qui consomme l'event
        REMEMBER dans le pipeline SSE.
        """
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
        # Normalise les whitespace internes (multi-espaces, retours à la
        # ligne → un seul espace) pour stocker du texte propre.
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
