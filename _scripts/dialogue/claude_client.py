"""
claude_client.py : wrapper unifié pour les deux moteurs Claude.

Deux moteurs supportés :

- ``cli_subscription`` : appel via subprocess de la CLI ``claude`` avec
  ``ANTHROPIC_API_KEY`` retirée de l'env (force OAuth/keychain). Mode par
  défaut, gratuit dans le quota Max 5x.
- ``api_anthropic`` : appel via SDK ``anthropic`` Python. Facturé à la
  consommation. Mode pour quand le quota Max 5x est tendu.

Le client maintient un historique conversationnel multi-tour qui est
repassé à chaque appel pour la continuité du dialogue.

Cf. ARCHITECTURE.md §4.
"""

import json
import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Callable, Optional

import fs_tools
from parser import ParserEvent, ParserEventType, StreamParser

logger = logging.getLogger(__name__)


# ============================================================ Exceptions

class ClaudeClientError(Exception):
    """Erreur générale du client Claude."""


class ClaudeQuotaExhaustedError(ClaudeClientError):
    """Quota CLI subscription épuisé ou rate limit API."""


class ClaudeNetworkError(ClaudeClientError):
    """Erreur réseau pendant le streaming."""


# ============================================================ Constantes

DEFAULT_MODEL = "claude-opus-4-7"
#: Plafond de tokens de sortie. Monté de 4096 → 8192 (Phase A.11.1) : un
#: récap dense en LaTeX (ex. compilation de 20+ fiches méthodologiques)
#: dépassait 4096 et le stream était coupé en silence en plein bloc.
DEFAULT_MAX_TOKENS = 8192
ENGINE_CLI = "cli_subscription"
ENGINE_API = "api_anthropic"
ENGINE_GEMINI = "gemini_api"
ENGINE_DEEPSEEK = "deepseek_api"
ENGINE_GROQ = "groq_api"

#: Modèle Gemini par défaut. ``gemini-3.5-flash`` (sorti le 2026-05-19) :
#: modèle stable recommandé par Google, contexte 1M, ~4× plus rapide que la
#: génération précédente, et, point décisif, **accessible en free tier**.
#: ``gemini-2.5-pro`` est lui passé payant-only sur l'API (plus de free tier),
#: d'où la bascule du défaut. Surchargeable via la variable d'env
#: ``GEMINI_MODEL`` (ex. ``gemini-2.5-pro`` si l'on dispose d'une clé payante).
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"

#: Modèle DeepSeek par défaut. ``deepseek-chat`` = V3 (généraliste rapide).
#: Pour les problèmes de raisonnement pur (math/info, debug Idris), basculer
#: sur ``deepseek-reasoner`` (R1) via env ``DEEPSEEK_MODEL``.
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"

#: Modèle Groq par défaut. Llama 3.3 70B = bon généraliste, free tier
#: 30 RPM / 14 400 RPD (très généreux). Surchageable via env ``GROQ_MODEL``.
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

#: Engines OpenAI-compatibles : on factorise leur impl streaming dans
#: ``_stream_via_openai_compatible`` au lieu de dupliquer 2 fois la logique.
_OPENAI_COMPATIBLE_PROVIDERS = {
    ENGINE_DEEPSEEK: {
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "default_model": DEFAULT_DEEPSEEK_MODEL,
        "model_env": "DEEPSEEK_MODEL",
        "provider_name": "DeepSeek",
        "signup_url": "https://platform.deepseek.com/api_keys",
        "model_prefix": "deepseek-",
    },
    ENGINE_GROQ: {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "default_model": DEFAULT_GROQ_MODEL,
        "model_env": "GROQ_MODEL",
        "provider_name": "Groq",
        "signup_url": "https://console.groq.com/keys",
        "model_prefix": "llama-",
    },
}

#: Balises ouvrantes qui réclament une fermeture ``<<<END>>>``. Sert au
#: rattrapage des réponses tronquées (cf. ``_autoclose_truncated_tags``).
#: ``<<<CAHIER>>>`` est traité à part car il admet une variante avec
#: attribut ``titre="..."``.
_TAGS_NEEDING_CLOSE = (
    "<<<TTS>>>", "<<<SUGGESTED_EDIT>>>", "<<<GOTO_SLIDE>>>",
    "<<<SHOW_DOC>>>", "<<<REMEMBER>>>",
)


def _autoclose_truncated_tags(text: str) -> str:
    """Renvoie le(s) ``<<<END>>>`` manquant(s) pour une réponse tronquée.

    Quand un moteur coupe le stream en plein milieu d'un bloc (limite de
    tokens atteinte), une balise ``<<<CAHIER…>>>`` / ``<<<TTS>>>`` reste
    ouverte et le rendu casse côté front. On compte les ouvertures non
    refermées et on renvoie autant de ``<<<END>>>`` qu'il en manque
    (chaîne vide si la réponse est déjà équilibrée).
    """
    closes = text.count("<<<END>>>")
    opens = sum(text.count(t) for t in _TAGS_NEEDING_CLOSE)
    # Tolérance A.12.3 : Gemini émet parfois `<<<CAHIER …">` (1 seul `>`).
    opens += len(re.findall(r"<<<CAHIER(?:\s[^>]*)?>{1,3}", text))
    missing = opens - closes
    return "<<<END>>>" * missing if missing > 0 else ""


#: Liste des engines supportés. Étendue ici plutôt que dans 4 endroits
#: séparés (gui.py, app.py, claude_client.py).
SUPPORTED_ENGINES = (
    ENGINE_CLI, ENGINE_API, ENGINE_GEMINI, ENGINE_DEEPSEEK, ENGINE_GROQ,
)

#: Modes de session (Phase A.7 light + Z.8 suppression lecture + A.8 ajout découverte).
#: Le mode `lecture` (tuteur + accès FS + suggestions, Phase A.7-light)
#: a été supprimé en Phase Z.8 (2026-05-09) : le mode `guidé`
#: l'absorbe entièrement. `guidé` = mêmes capacités tuteur (Read/Grep/Glob,
#: SUGGESTED_EDIT) + UI slide-par-slide structurée.
#:
#: Phase A.8 (2026-05-12) : nouveau mode `découverte` pour démarrer un sujet
#: jamais (ou peu) suivi en CM. Tuteur explicateur, zéro prérequis, parts
#: de zéro avec exposition courte + question + validation. Pédagogie idéale
#: : Découverte → Guidé (consolidation) → Colle (vérification stricte).
MODE_COLLE = "colle"            # interrogation pure, pas d'accès FS
MODE_GUIDE = "guidé"            # tuteur slide-par-slide + accès FS Read/Grep/Glob
MODE_DECOUVERTE = "découverte"  # tuteur explicateur zéro prérequis + accès FS Read/Grep/Glob
MODE_WORKSPACE = "workspace"    # Phase A.9 : tuteur sur un dossier arbitraire
                                # (workspace_root) hors COURS/. Accès FS scopé via
                                # cwd subprocess. Décline en posture explain/quiz
                                # selon le cadrage initial de l'utilisateur.

#: Tools du CLI Claude Code activés en mode guidé (lecture FS seule).
#: ``Edit`` / ``Write`` non listés volontairement : on passe par la
#: balise ``<<<SUGGESTED_EDIT>>>`` validée par l'utilisateur (cf. parser).
GUIDE_ALLOWED_TOOLS = "Read,Grep,Glob"

#: Phase A.8 : même set qu'en guidé, le tuteur découverte peut piocher
#: dans les CM/polys de la matière au besoin (cf. PROMPT_SYSTEME_DECOUVERTE
#: §1.3). Pas d'écriture filesystem.
DECOUVERTE_ALLOWED_TOOLS = "Read,Grep,Glob"

#: Phase A.9, workspace mode : exploration libre d'un dossier sélectionné.
#: Read pour lire les fichiers, Grep pour chercher des motifs, Glob pour
#: lister les fichiers par pattern. Pas d'Edit/Write : le tuteur n'écrit
#: jamais dans le workspace (même pas une suggestion via SUGGESTED_EDIT).
WORKSPACE_ALLOWED_TOOLS = "Read,Grep,Glob"

#: Phase A.12 : modes dont la pédagogie repose sur un accès filesystem réel.
#: Pour ces modes, les moteurs API (Gemini/Anthropic/DeepSeek/Groq) exposent
#: les outils ``Read``/``Grep``/``Glob`` en function-calling natif et le
#: backend exécute réellement les appels (cf. fs_tools.py + boucle d'outils
#: dans chaque ``_stream_via_*``). Avant, seul ``cli_subscription`` câblait
#: ces outils ; sur un moteur API le tuteur hallucinait le contenu des
#: fichiers (cf. session WORKSPACE 2026-05-21, sujet de TP inventé).
_FS_TOOL_MODES = frozenset({MODE_GUIDE, MODE_DECOUVERTE, MODE_WORKSPACE})

CLI_BINARY = "claude"
CLI_WAIT_TIMEOUT_SECONDS = 60


def _resolve_claude_binary() -> str:
    """Retourne le chemin absolu vers le binaire `claude` ou ``"claude"``
    si introuvable (laissé pour message d'erreur clair côté Popen).

    Pourquoi : la GUI peut être lancée via `start_gui.vbs` → `pythonw.exe`
    avec un PATH partiel qui n'inclut pas `~/.local/bin/` ou
    `~/AppData/Roaming/npm/`. ``shutil.which("claude")`` échoue alors
    même quand la CLI est correctement installée. On tente les chemins
    canoniques Windows avant d'abandonner.
    """
    import shutil
    # 1. PATH courant
    hit = shutil.which(CLI_BINARY)
    if hit:
        return hit
    # 2. Chemins canoniques Windows (npm + installeur user-local)
    home = Path.home()
    candidates = [
        home / ".local" / "bin" / "claude.exe",
        home / "AppData" / "Roaming" / "npm" / "claude.cmd",
        home / "AppData" / "Roaming" / "npm" / "claude.exe",
        home / "AppData" / "Local" / "Programs" / "claude" / "claude.exe",
    ]
    for cand in candidates:
        if cand.is_file():
            return str(cand)
    # 3. Échec : on laisse "claude" et le Popen lèvera FileNotFoundError
    # avec le message clair attendu (cf. except plus bas).
    return CLI_BINARY


# Résolu au module load (pas de coût récurrent).
_CLI_BINARY_RESOLVED = _resolve_claude_binary()
logger.info("CLI claude résolue : %s", _CLI_BINARY_RESOLVED)


# ============================================================ Multimodal helpers (Phase v15.7.18)

import re as _re_img

#: Regex pour les images Markdown : ![alt](path). Capture le path.
#: Tolère les espaces autour, alt vide, paths relatifs ou absolus.
_INLINE_IMAGE_RE = _re_img.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

#: Extensions image reconnues + mapping vers media_type. Anthropic API
#: supporte JPEG/PNG/GIF/WebP. Gemini idem + HEIC. OpenAI-compat (DeepSeek
#: text-only ne lit RIEN ; Groq llama-3.3 vision lit JPEG/PNG).
_IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif",
    ".webp": "image/webp", ".heic": "image/heic",
}

#: Cap de taille par image envoyée au LLM (5 MB ~ photo téléphone HD).
#: Au-delà : skip silencieux + log warning. Évite explosion tokens / quota.
_MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _extract_inline_images(text: str, cours_root: Optional[Path]):
    """Parse les ![alt](path) du texte, lit les fichiers en bytes.

    Returns:
        (text_without_images, images: list[dict]) où chaque image est
        un dict {alt, path, rel_path, media_type, data_b64}.

    Skip silencieusement les images dont :
        - le path n'existe pas (sur disque)
        - l'extension n'est pas reconnue (cf. _IMAGE_MEDIA_TYPES)
        - la taille dépasse _MAX_IMAGE_BYTES (avec log warning)

    Le texte retourné conserve un placeholder `[image: <alt>]` à la
    position de chaque image trouvée : ça aide le LLM à savoir où dans
    le flux conversationnel l'image se rattache.

    Si ``cours_root`` est None, on tente quand même les paths absolus
    et les chemins relatifs au cwd courant.
    """
    if not text or "![" not in text:
        return text, []
    import base64
    images = []

    def _replace(m):
        alt = (m.group(1) or "").strip() or "image"
        rel_path = m.group(2).strip()
        # Résolution path : absolu d'abord, sinon relatif à cours_root
        path = Path(rel_path)
        if not path.is_absolute() and cours_root is not None:
            path = cours_root / rel_path
        try:
            ext = path.suffix.lower()
            if ext not in _IMAGE_MEDIA_TYPES:
                logger.debug("Image extension non supportée, skip : %s", path)
                return f"[image non incluse: {alt}]"
            if not path.is_file():
                logger.debug("Image introuvable, skip : %s", path)
                return f"[image introuvable: {alt}]"
            size = path.stat().st_size
            if size > _MAX_IMAGE_BYTES:
                logger.warning(
                    "Image trop grande (%d bytes > %d), skip : %s",
                    size, _MAX_IMAGE_BYTES, path,
                )
                return f"[image trop grande: {alt}]"
            data = path.read_bytes()
            data_b64 = base64.b64encode(data).decode("ascii")
            images.append({
                "alt": alt,
                "path": str(path),
                "rel_path": rel_path,
                "media_type": _IMAGE_MEDIA_TYPES[ext],
                "data_b64": data_b64,
                "size_bytes": size,
            })
            return f"[image: {alt}]"
        except OSError as e:
            logger.warning("Echec lecture image %s : %s", path, e)
            return f"[image lecture échouée: {alt}]"

    new_text = _INLINE_IMAGE_RE.sub(_replace, text)
    return new_text, images


def _messages_to_anthropic_multimodal(history, cours_root):
    """Convertit l'historique en messages Anthropic multimodaux.

    Les user messages contenant ``![alt](path)`` sont transformés en
    content list ``[{type:text}, {type:image, source:{base64,...}}]``.
    Les autres messages restent inchangés (role, content string).

    Cette transformation est faite à la volée au moment de l'appel API,
    pas dans ``_history`` (qui reste en string pour replay/debug/JSON).
    """
    out = []
    for msg in history:
        content = msg.get("content")
        if msg.get("role") == "user" and isinstance(content, str):
            new_text, images = _extract_inline_images(content, cours_root)
            if images:
                blocks = [{"type": "text", "text": new_text}]
                for img in images:
                    blocks.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": img["media_type"],
                            "data": img["data_b64"],
                        },
                    })
                out.append({"role": msg["role"], "content": blocks})
                continue
        out.append(msg)
    return out


def _messages_to_openai_multimodal(history, cours_root):
    """Convertit l'historique en messages OpenAI-compat multimodaux.

    Format : ``[{type:text, text:...}, {type:image_url, image_url:{url:"data:image/jpeg;base64,..."}}]``

    DeepSeek-V3 (deepseek-chat) ne supporte PAS l'image en input : il
    ignore silencieusement le champ image_url. Groq llama-vision oui.
    On envoie de toute façon, le serveur décide.
    """
    out = []
    for msg in history:
        content = msg.get("content")
        if msg.get("role") == "user" and isinstance(content, str):
            new_text, images = _extract_inline_images(content, cours_root)
            if images:
                blocks = [{"type": "text", "text": new_text}]
                for img in images:
                    blocks.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{img['media_type']};base64,{img['data_b64']}",
                        },
                    })
                out.append({"role": msg["role"], "content": blocks})
                continue
        out.append(msg)
    return out


def _messages_to_gemini_parts(history, cours_root):
    """Convertit l'historique en messages Gemini avec Parts multimodaux.

    Retourne une liste de dicts ``{role, parts}`` où chaque part est soit
    ``{"text": "..."}``, soit ``{"inline_data": {"mime_type", "data"}}``
    (data en bytes brut, pas base64 ; google.genai gère l'encoding).

    Gemini API utilise "user" et "model" comme roles (pas "assistant").
    On translate ici pour éviter au caller de le faire.

    Note : on retourne le format dict-style compatible avec
    ``google.genai.types.Content`` qui accepte les dict en input.
    """
    import base64
    out = []
    for msg in history:
        content = msg.get("content")
        role = msg.get("role")
        gemini_role = "user" if role == "user" else "model"
        if role == "user" and isinstance(content, str):
            new_text, images = _extract_inline_images(content, cours_root)
            if images:
                parts = [{"text": new_text}]
                for img in images:
                    parts.append({
                        "inline_data": {
                            "mime_type": img["media_type"],
                            "data": base64.b64decode(img["data_b64"]),
                        },
                    })
                out.append({"role": gemini_role, "parts": parts})
                continue
        out.append({"role": gemini_role, "parts": [{"text": content or ""}]})
    return out


def _anthropic_document_block(document: dict) -> dict:
    """Construit un content block Anthropic à partir d'un ``FsToolResult.document``.

    Phase A.12 : quand ``Read`` cible un PDF ou une image, le fichier est
    ingéré nativement : on l'attache au tour conversationnel comme content
    block ``document`` (PDF) ou ``image`` à côté du ``tool_result``.
    """
    import base64
    media = document["media_type"]
    b64 = base64.b64encode(document["data"]).decode("ascii")
    block_type = "document" if media == "application/pdf" else "image"
    return {
        "type": block_type,
        "source": {"type": "base64", "media_type": media, "data": b64},
    }


# ============================================================ ClaudeClient

class ClaudeClient:
    """Wrapper unique pour les deux moteurs (CLI subscription / API Anthropic).

    Usage :

        client = ClaudeClient(
            engine="cli_subscription",
            system_prompt=builder.system_prompt,
        )
        client.append_user_message(builder.build_initial_context_message(ctx))
        stats = client.stream_response(on_event=lambda e: ...)
        # client._history a maintenant l'échange [user, assistant]
        client.append_user_message("réponse étudiant ...")
        stats = client.stream_response(on_event=...)
    """

    def __init__(
        self,
        engine: str,
        system_prompt: str,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        mode: str = MODE_COLLE,
        cours_root: Optional[Path] = None,
    ):
        if engine not in SUPPORTED_ENGINES:
            raise ValueError(
                f"Engine inconnu : {engine!r}. "
                f"Attendu un de {SUPPORTED_ENGINES}."
            )
        if mode not in (MODE_COLLE, MODE_GUIDE, MODE_DECOUVERTE, MODE_WORKSPACE):
            raise ValueError(
                f"Mode inconnu : {mode!r}. Attendu un de "
                f"{MODE_COLLE!r}, {MODE_GUIDE!r}, {MODE_DECOUVERTE!r}, "
                f"{MODE_WORKSPACE!r}."
            )
        self._engine = engine
        # Phase MT v15 : prompt système tuné selon le moteur (préfixe court
        # pour Gemini / OpenAI-compat qui tolèrent moins bien le verbeux,
        # passe-plat pour Claude Opus qui gère bien). cf. tool_schemas.
        try:
            from tool_schemas import tune_prompt_for_engine
            self._system_prompt = tune_prompt_for_engine(system_prompt, engine)
        except ImportError:
            self._system_prompt = system_prompt
        self._model = model
        self._max_tokens = max_tokens
        self._mode = mode
        self._cours_root = Path(cours_root) if cours_root else None
        self._history: list[dict] = []
        # Phase A.7.2 v15 : tool calling natif activable par moteur API.
        # Si True ET le moteur supporte les tools (api_anthropic, gemini_api,
        # deepseek_api, groq_api), le client expose les tools définis dans
        # tool_schemas.py et synthétise des ParserEvent à partir des tool_use
        # blocks reçus. Désactivé par défaut tant que pas testé en runtime
        # (peut être activé via runtime_settings.json en Phase B).
        self._enable_native_tools: bool = False
        # Phase Z.9 : flag pour activer la recherche internet native
        # quand supportée par le moteur (api_anthropic via tool
        # web_search_20250305, gemini_api via google_search grounding).
        # Activable via set_enable_web_search() pour les endpoints
        # /api/web_search_exo et /api/find_youtube_video.
        self._enable_web_search: bool = False

    # ---------------------------------------------------------------- propriétés

    @property
    def engine(self) -> str:
        return self._engine

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def model(self) -> str:
        return self._model

    @property
    def history(self) -> list[dict]:
        """Snapshot de l'historique (read-only ; le caller ne doit pas muter)."""
        return list(self._history)

    @property
    def native_tools_active(self) -> bool:
        """True si tool calling natif est activé ET supporté par le moteur."""
        try:
            from tool_schemas import engine_supports_native_tools
        except ImportError:
            return False
        return self._enable_native_tools and engine_supports_native_tools(self._engine)

    def set_enable_native_tools(self, enable: bool) -> None:
        """Active/désactive le tool calling natif. Désactivé par défaut.
        À activer via runtime_settings ou flag CLI quand tests OK."""
        self._enable_native_tools = bool(enable)

    def set_enable_web_search(self, enable: bool) -> None:
        """Active/désactive la recherche internet native (Phase Z.9).

        Supporté sur ``api_anthropic`` (tool ``web_search_20250305``) et
        ``gemini_api`` (``google_search`` grounding). Sur les autres
        moteurs, c'est un no-op silencieux : le LLM répond depuis sa
        connaissance interne sans accès réseau (fallback dégradé mais
        utilisable).
        """
        self._enable_web_search = bool(enable)

    # ---------------------------------------------------------------- outils FS

    def _should_use_fs_tools(self) -> bool:
        """True si le mode courant doit exposer les outils FS Read/Grep/Glob.

        Phase A.12 : vrai pour les modes ``guidé`` / ``découverte`` /
        ``workspace`` quand une racine (`cours_root`) est connue. Faux si la
        recherche web est active : côté Gemini, ``google_search`` grounding
        et ``function_declarations`` ne peuvent pas coexister dans une même
        requête. Le moteur ``cli_subscription`` n'appelle jamais cette
        méthode : il a ses propres outils natifs via ``--allowedTools``.
        """
        return (
            self._mode in _FS_TOOL_MODES
            and self._cours_root is not None
            and not self._enable_web_search
        )

    def _handle_pedagogical_tool(self, name, tool_input, on_event) -> None:
        """Synthétise un ParserEvent depuis un tool pédagogique non-FS.

        Couvre ``next_slide`` / ``goto_slide`` / ``suggest_edit`` quand le
        tool calling natif est activé (cf. tool_schemas). Les outils FS sont
        traités à part dans la boucle d'outils de chaque moteur.
        """
        try:
            from tool_schemas import TOOL_NAME_TO_EVENT_TYPE, tool_call_to_payload
        except ImportError:
            return
        if name not in TOOL_NAME_TO_EVENT_TYPE:
            logger.warning("Tool non-FS inconnu reçu : %s", name)
            return
        try:
            payload = tool_call_to_payload(name, tool_input or {})
            event_type = ParserEventType(TOOL_NAME_TO_EVENT_TYPE[name])
        except (ValueError, KeyError, TypeError) as e:
            logger.warning("Tool %s payload invalide : %s", name, e)
            return
        on_event(ParserEvent(type=event_type, payload=payload))

    # ---------------------------------------------------------------- API publique

    def append_user_message(self, text: str) -> None:
        """Ajoute un message utilisateur sans appeler Claude.

        Utilisé pour le contexte initial (généré par PromptBuilder) puis
        à chaque réponse étudiante. Le streaming ultérieur via
        ``stream_response()`` appellera Claude avec cet historique.
        """
        self._history.append({"role": "user", "content": text})

    def stream_response(
        self,
        on_event: Callable[[ParserEvent], None],
    ) -> dict:
        """Appelle Claude avec l'historique courant et streame la réponse.

        Délègue le parsing à un ``StreamParser`` local : chaque chunk reçu
        est ``feed`` au parser qui émet des ``ParserEvent`` typés vers
        ``on_event``. Le texte brut complet (avec balises) est ajouté à
        l'historique comme message ``assistant`` à la fin.

        Returns:
            dict avec ``input_tokens``, ``output_tokens`` (int ou None
            selon la dispo côté backend).

        Raises:
            ClaudeQuotaExhaustedError, ClaudeNetworkError, ClaudeClientError.
        """
        if self._engine == ENGINE_CLI:
            return self._stream_via_cli(on_event)
        if self._engine == ENGINE_GEMINI:
            return self._stream_via_gemini(on_event)
        if self._engine in _OPENAI_COMPATIBLE_PROVIDERS:
            return self._stream_via_openai_compatible(
                on_event, _OPENAI_COMPATIBLE_PROVIDERS[self._engine]
            )
        return self._stream_via_api(on_event)

    # ---------------------------------------------------------------- API Gemini

    def _stream_via_gemini(self, on_event) -> dict:
        """Stream une réponse via l'API Gemini.

        Pour les sessions CM longues : Gemini 2.5 Pro a un contexte de
        ~1M tokens et un cache implicite, donc la conso est nettement plus
        modérée que Claude CLI subscription pour le même volume de matière
        injectée.

        Phase A.12, accès FS réel : en mode guidé/découverte/workspace, les
        outils ``Read``/``Grep``/``Glob`` sont exposés en function-calling et
        le backend exécute réellement les appels (boucle d'outils ci-dessous).
        Avant, sans canal d'outil, Gemini hallucinait le contenu des fichiers.

        Le SDK convertit le format historique ``[{role:user|assistant,
        content:str}]`` vers le format Gemini ``[{role:user|model,
        parts:[{text:str}]}]``. Le system_prompt passe via
        ``GenerateContentConfig.system_instruction``.

        Auth : variable d'env ``GEMINI_API_KEY`` (créer sur
        https://aistudio.google.com/app/apikey, free tier généreux).

        Le parser texte (StreamParser) reste agnostique : Gemini émet
        les balises ``<<<SUGGESTED_EDIT>>>`` etc. en suivant le prompt
        système (qui ne mentionne aucun modèle particulier : on garde
        la doctrine pédagogique unique, tested with Claude, monitored
        for drift on Gemini).
        """
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as e:
            raise ClaudeClientError(
                f"SDK google-genai indisponible ({e}). "
                f"pip install google-genai (>=0.3.0 requis)."
            ) from e

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ClaudeClientError(
                "GEMINI_API_KEY absent. Crée une clé sur "
                "https://aistudio.google.com/app/apikey puis "
                "$env:GEMINI_API_KEY = 'AIza...' (PowerShell) ou "
                "ajoute-la dans _secrets/.env."
            )

        # Modèle : self._model si commence par 'gemini-', sinon défaut.
        # Permet de surcharger via le formulaire start_session.
        model_name = (
            self._model
            if self._model.startswith("gemini-")
            else os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        )

        # Phase v15.7.18 : conversion via helper qui détecte les images
        # Markdown ![alt](path) dans les user messages et les transforme
        # en parts inline_data (base64). Fallback ancien comportement
        # (text-only) pour les messages sans image.
        gemini_contents = _messages_to_gemini_parts(
            self._history, self._cours_root,
        )
        use_fs = self._should_use_fs_tools()

        full_raw: list[str] = []
        parser = StreamParser(on_event)
        total_in = 0
        total_out = 0

        try:
            client = genai.Client(api_key=api_key)
            # Phase A.12, boucle d'outils FS : le modèle peut émettre des
            # function_call (Read/Grep/Glob), qu'on exécute réellement sur le
            # disque (fs_tools.execute_fs_tool) et ré-injecte, jusqu'à
            # MAX_TOOL_ROUNDS round-trips. Au dernier tour les outils sont
            # retirés pour forcer une réponse texte finale.
            for round_idx in range(fs_tools.MAX_TOOL_ROUNDS + 1):
                last_round = round_idx == fs_tools.MAX_TOOL_ROUNDS
                cfg_kwargs = {
                    "system_instruction": self._system_prompt,
                    "max_output_tokens": self._max_tokens,
                }
                # Phase Z.9 : Search Grounding natif si recherche web demandée.
                # Incompatible avec function_declarations → priorité au search.
                if self._enable_web_search:
                    try:
                        cfg_kwargs["tools"] = [
                            genai_types.Tool(
                                google_search=genai_types.GoogleSearch()),
                        ]
                    except AttributeError:
                        logger.warning(
                            "Gemini SDK sans Tool(google_search) : "
                            "fallback knowledge interne sans grounding")
                elif use_fs and not last_round:
                    cfg_kwargs["tools"] = [
                        genai_types.Tool(
                            function_declarations=fs_tools.gemini_fs_declarations()),
                    ]
                config = genai_types.GenerateContentConfig(**cfg_kwargs)
                stream = client.models.generate_content_stream(
                    model=model_name,
                    contents=gemini_contents,
                    config=config,
                )
                round_text: list[str] = []
                fcall_parts: list = []  # Part d'origine (thought_signature préservée)
                finish_reason = None
                round_in = 0
                round_out = 0
                for chunk in stream:
                    cands = getattr(chunk, "candidates", None)
                    if cands:
                        cand = cands[0]
                        fr = getattr(cand, "finish_reason", None)
                        if fr is not None:
                            finish_reason = fr
                        content = getattr(cand, "content", None)
                        for part in (getattr(content, "parts", None) or []):
                            txt = getattr(part, "text", None)
                            if txt:
                                round_text.append(txt)
                                full_raw.append(txt)
                                parser.feed(txt)
                            fc = getattr(part, "function_call", None)
                            if fc is not None and getattr(fc, "name", None):
                                fcall_parts.append(part)
                    usage = getattr(chunk, "usage_metadata", None)
                    if usage is not None:
                        round_in = (
                            getattr(usage, "prompt_token_count", None)
                            or round_in)
                        round_out = (
                            getattr(usage, "candidates_token_count", None)
                            or round_out)
                total_in += round_in
                total_out += round_out

                if not fcall_parts or last_round:
                    # Phase A.11.1, réponse tronquée par la limite de tokens :
                    # le stream s'arrête en silence (pas d'exception côté
                    # Gemini). On referme les balises restées ouvertes et on
                    # signale la troncature dans le fil.
                    fr_name = getattr(
                        finish_reason, "name", str(finish_reason or ""))
                    if fr_name == "MAX_TOKENS":
                        repair = _autoclose_truncated_tags("".join(full_raw))
                        tail = repair + (
                            "\n\n> ⚠ **Réponse tronquée** : la limite de "
                            "tokens a été atteinte. Demandez « continue » "
                            "pour obtenir la suite."
                        )
                        full_raw.append(tail)
                        parser.feed(tail)
                        logger.warning(
                            "Gemini : reponse tronquee (MAX_TOKENS), %d "
                            "balise(s) refermee(s)", repair.count("<<<END>>>"))
                    break

                # Round-trip d'outils : on rejoue le tour modèle puis on
                # injecte les résultats d'exécution.
                # Phase A.12.2 : les Part de function_call sont renvoyés
                # TELS QUELS (objets Part d'origine). Gemini 3.x y attache
                # une `thought_signature` obligatoire ; la reconstruire en
                # dict la perdrait → 400 INVALID_ARGUMENT « Function call is
                # missing a thought_signature » au tour suivant.
                model_parts: list = []
                if round_text:
                    model_parts.append(
                        genai_types.Part(text="".join(round_text)))
                model_parts.extend(fcall_parts)
                gemini_contents.append(
                    genai_types.Content(role="model", parts=model_parts))

                resp_parts: list = []
                markers: list[str] = []
                for fc_part in fcall_parts:
                    fc = fc_part.function_call
                    fc_args = dict(getattr(fc, "args", None) or {})
                    res = fs_tools.execute_fs_tool(
                        fc.name, fc_args, self._cours_root,
                    )
                    fr_payload: dict = {
                        "name": fc.name,
                        "response": {"result": res.text},
                    }
                    # Corrélation des appels parallèles si Gemini fournit un id.
                    if getattr(fc, "id", None):
                        fr_payload["id"] = fc.id
                    resp_parts.append({"function_response": fr_payload})
                    # Ingestion native PDF/image : le binaire est attaché en
                    # inline_data dans le même tour user que la réponse outil.
                    if res.document is not None:
                        resp_parts.append({"inline_data": {
                            "mime_type": res.document["media_type"],
                            "data": res.document["data"],
                        }})
                    markers.append(fs_tools.tool_call_marker(
                        fc.name,
                        fs_tools.tool_call_label(fc.name, fc_args), res.ok))
                    logger.info("Gemini : outil FS %s (ok=%s)", fc.name, res.ok)
                gemini_contents.append({"role": "user", "parts": resp_parts})
                # Puce(s) visuelle(s) injectée(s) dans le flux : le front les
                # rend en « 🔍 Lecture de X » entre le texte d'avant et d'après.
                marker_text = "\n\n" + "\n".join(markers) + "\n\n"
                full_raw.append(marker_text)
                parser.feed(marker_text)
            parser.flush()
        except Exception as e:  # noqa: BLE001 (google-genai expose plein d'erreurs)
            # Distinction quota vs réseau : message-based, faute de mieux
            msg = str(e).lower()
            if "quota" in msg or "resource_exhausted" in msg or "rate" in msg:
                raise ClaudeQuotaExhaustedError(
                    f"Gemini quota / rate limit : {e}"
                ) from e
            if "deadline" in msg or "unavailable" in msg or "connection" in msg:
                raise ClaudeNetworkError(f"Gemini reseau : {e}") from e
            raise ClaudeClientError(f"Gemini erreur : {e}") from e

        self._history.append({
            "role": "assistant",
            "content": "".join(full_raw),
        })
        return {"input_tokens": total_in or None, "output_tokens": total_out or None}

    # ---------------------------------------------------------------- API OpenAI-compatibles (DeepSeek, Groq)

    def _stream_via_openai_compatible(self, on_event, cfg: dict) -> dict:
        """Stream via une API OpenAI-compatible (DeepSeek, Groq).

        Les deux providers exposent l'API ``chat.completions`` au format
        OpenAI standard, donc le SDK ``openai`` (>=1.0) marche en pointant
        ``base_url`` vers leur endpoint. On factorise ici les 2 impls au
        lieu de dupliquer la logique.

        ``cfg`` est une entrée de ``_OPENAI_COMPATIBLE_PROVIDERS`` :
        ``base_url``, ``api_key_env``, ``default_model``, ``model_env``,
        ``provider_name``, ``signup_url``, ``model_prefix``.

        Raisons par provider :
        - **DeepSeek V3 / R1** : excellent en raisonnement math/code (R1
          est entraîné spécifiquement pour la chaîne de pensée). Free
          tier généreux quand actif (10 RPM, ~10 M tokens/mois), peut
          être suspendu en cas de surcharge sur deepseek.com.
        - **Groq + Llama 3.3 70B** : free tier ultra-stable (30 RPM,
          14 400 RPD), inférence très rapide (~500 tok/s sur LPU). Moins
          fort en reasoning pur que R1 mais hyper généreux en quota.

        Comme Gemini : pas d'accès FS Read/Grep côté SDK simple. Les
        balises ``<<<SUGGESTED_EDIT>>>`` etc. sont émises en texte par
        le modèle qui suit le prompt système ; le parser reste agnostique.
        """
        try:
            from openai import OpenAI
            from openai import APIConnectionError, APITimeoutError
            from openai import APIError, RateLimitError
        except ImportError as e:
            raise ClaudeClientError(
                f"SDK openai indisponible ({e}). pip install openai"
            ) from e

        api_key = os.environ.get(cfg["api_key_env"])
        if not api_key:
            raise ClaudeClientError(
                f"{cfg['api_key_env']} absent. Crée une clé sur "
                f"{cfg['signup_url']} puis "
                f"$env:{cfg['api_key_env']} = '...' (PowerShell) ou "
                f"ajoute-la dans _secrets/.env."
            )

        # Modèle : self._model si commence par le préfixe attendu, sinon
        # défaut. Permet de surcharger via env ou via le formulaire start.
        model_name = (
            self._model
            if self._model.startswith(cfg["model_prefix"])
            else os.environ.get(cfg["model_env"], cfg["default_model"])
        )

        # Format OpenAI : system prompt = 1ᵉʳ message role=system, puis
        # historique tel quel (notre format role/content est déjà compatible).
        # Phase v15.7.18 : transforme les user messages contenant des
        # images Markdown en blocs multimodaux OpenAI-compat. Note :
        # DeepSeek-V3 (text-only) ignorera silencieusement les blocs
        # image_url. Groq llama-3.3-70b-versatile ignore aussi (pas vision)
        # mais les variantes vision (llama-vision*, llava-*) liraient.
        # On envoie de toute façon, le serveur décide.
        messages = [{"role": "system", "content": self._system_prompt}]
        messages.extend(_messages_to_openai_multimodal(
            self._history, self._cours_root,
        ))

        use_fs = self._should_use_fs_tools()
        tools = fs_tools.openai_fs_tools() if use_fs else None

        full_raw: list[str] = []
        parser = StreamParser(on_event)
        total_in = 0
        total_out = 0

        try:
            client = OpenAI(api_key=api_key, base_url=cfg["base_url"])
            # Phase A.12, boucle d'outils FS : le modèle peut émettre des
            # tool_calls (Read/Grep/Glob), exécutés réellement et ré-injectés.
            # DeepSeek/Groq sont text-only : un Read de PDF renvoie un message
            # honnête (le binaire ne peut pas être ingéré sur ces moteurs).
            for round_idx in range(fs_tools.MAX_TOOL_ROUNDS + 1):
                last_round = round_idx == fs_tools.MAX_TOOL_ROUNDS
                create_kwargs: dict = {
                    "model": model_name,
                    "messages": messages,
                    "max_tokens": self._max_tokens,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                }
                if tools and not last_round:
                    create_kwargs["tools"] = tools
                stream = client.chat.completions.create(**create_kwargs)
                round_text: list[str] = []
                tool_acc: dict = {}  # index -> {id, name, args}
                for chunk in stream:
                    if chunk.choices:
                        delta = chunk.choices[0].delta
                        if delta and delta.content:
                            round_text.append(delta.content)
                            full_raw.append(delta.content)
                            parser.feed(delta.content)
                        for tc in (getattr(delta, "tool_calls", None) or []):
                            slot = tool_acc.setdefault(
                                tc.index, {"id": "", "name": "", "args": ""})
                            if tc.id:
                                slot["id"] = tc.id
                            fn = getattr(tc, "function", None)
                            if fn is not None:
                                if fn.name:
                                    slot["name"] = fn.name
                                if fn.arguments:
                                    slot["args"] += fn.arguments
                    # Le dernier chunk porte usage (avec stream_options).
                    usage = getattr(chunk, "usage", None)
                    if usage is not None:
                        total_in += getattr(usage, "prompt_tokens", None) or 0
                        total_out += (
                            getattr(usage, "completion_tokens", None) or 0)
                calls = [
                    tool_acc[i] for i in sorted(tool_acc)
                    if tool_acc[i]["name"]
                ]
                if not calls or last_round:
                    break

                # Round-trip : rejoue le tour assistant (avec tool_calls) puis
                # un message role=tool par appel exécuté.
                call_ids = [
                    c["id"] or f"call_{i}" for i, c in enumerate(calls)
                ]
                messages.append({
                    "role": "assistant",
                    "content": "".join(round_text) or None,
                    "tool_calls": [
                        {
                            "id": call_ids[i],
                            "type": "function",
                            "function": {
                                "name": c["name"],
                                "arguments": c["args"] or "{}",
                            },
                        }
                        for i, c in enumerate(calls)
                    ],
                })
                markers: list[str] = []
                for i, c in enumerate(calls):
                    try:
                        cargs = (
                            json.loads(c["args"]) if c["args"].strip() else {}
                        )
                    except json.JSONDecodeError:
                        cargs = {}
                    res = fs_tools.execute_fs_tool(
                        c["name"], cargs, self._cours_root)
                    content = res.text
                    if res.document is not None:
                        content = (
                            f"[Le fichier « {res.document['label']} » est un "
                            f"document binaire (PDF/image). Ce moteur ne peut "
                            f"pas l'ingérer ; demande à l'étudiant d'en coller "
                            f"le contenu, ou suggère le moteur Gemini ou "
                            f"Claude pour ce dossier.]"
                        )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_ids[i],
                        "content": content,
                    })
                    markers.append(fs_tools.tool_call_marker(
                        c["name"],
                        fs_tools.tool_call_label(c["name"], cargs), res.ok))
                    logger.info(
                        "%s : outil FS %s (ok=%s)",
                        cfg["provider_name"], c["name"], res.ok)
                # Puce(s) visuelle(s) des appels FS injectées dans le flux.
                marker_text = "\n\n" + "\n".join(markers) + "\n\n"
                full_raw.append(marker_text)
                parser.feed(marker_text)
            parser.flush()
        except RateLimitError as e:
            raise ClaudeQuotaExhaustedError(
                f"{cfg['provider_name']} rate limit / quota : {e}"
            ) from e
        except (APIConnectionError, APITimeoutError) as e:
            raise ClaudeNetworkError(
                f"{cfg['provider_name']} reseau : {e}"
            ) from e
        except APIError as e:
            # Phase v15.6.4 : plusieurs erreurs « moteur HS pour ta
            # requête, change de moteur » que les SDK OpenAI mappent en
            # APIError générique au lieu de RateLimitError :
            #
            # - 402 Payment Required / Insufficient Balance (DeepSeek
            #   sans solde sur la clé API).
            # - 413 Request too large / TPM dépassé (Groq free tier
            #   12k TPM, le contexte de la session avec script +
            #   corrigés + transcript fait souvent 30-60k → erreur).
            # - 400 context_length_exceeded (DeepSeek 64k, Gemini 1M
            #   atteint sur des sessions très longues).
            #
            # Sémantiquement tous ces cas demandent à l'utilisateur de
            # basculer de moteur. On les remappe en
            # ClaudeQuotaExhaustedError pour réutiliser le flow
            # quota_midflow / propose-bascule existant. Le détail brut
            # de l'erreur (taille demandée vs limite, etc.) reste dans
            # le message pour informer l'utilisateur.
            err_str = str(e).lower()
            unusable_for_request = (
                "402" in err_str
                or "insufficient balance" in err_str
                or "insufficient_balance" in err_str
                or "payment required" in err_str
                or "413" in err_str
                or "request too large" in err_str
                or "tokens per minute" in err_str
                or "context_length_exceeded" in err_str
                or "context length" in err_str
                or "rate_limit_exceeded" in err_str
            )
            if unusable_for_request:
                raise ClaudeQuotaExhaustedError(
                    f"{cfg['provider_name']} indisponible pour cette requête : {e}"
                ) from e
            raise ClaudeClientError(
                f"{cfg['provider_name']} erreur : {e}"
            ) from e

        self._history.append({
            "role": "assistant",
            "content": "".join(full_raw),
        })
        return {"input_tokens": total_in or None, "output_tokens": total_out or None}

    # ---------------------------------------------------------------- API Anthropic

    def _stream_via_api(self, on_event) -> dict:
        try:
            import anthropic
        except ImportError as e:
            raise ClaudeClientError(
                f"SDK anthropic indisponible ({e}). pip install anthropic"
            ) from e

        full_raw: list[str] = []
        parser = StreamParser(on_event)

        # Phase v15.7.18 : transforme les user messages contenant des images
        # Markdown en blocs multimodaux Anthropic (base64 inline).
        messages = _messages_to_anthropic_multimodal(
            self._history, self._cours_root,
        )

        # Tools exposés : FS (Phase A.12, modes guidé/découverte/workspace) +
        # pédagogiques natifs (next_slide/goto_slide/suggest_edit, si activés
        # via set_enable_native_tools) + web_search (Phase Z.9).
        use_fs = self._should_use_fs_tools()
        tools: list = []
        if use_fs:
            tools += fs_tools.anthropic_fs_tools()
        if self.native_tools_active:
            from tool_schemas import ANTHROPIC_TOOLS
            tools += list(ANTHROPIC_TOOLS)
        if self._enable_web_search:
            tools.append({
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 5,
            })

        total_in = 0
        total_out = 0
        try:
            client = anthropic.Anthropic()
            # Phase A.12, boucle d'outils : tant que le modèle répond avec
            # des blocs tool_use, on exécute les appels FS et on relance.
            for round_idx in range(fs_tools.MAX_TOOL_ROUNDS + 1):
                last_round = round_idx == fs_tools.MAX_TOOL_ROUNDS
                api_kwargs: dict = {
                    "model": self._model,
                    "max_tokens": self._max_tokens,
                    "system": self._system_prompt,
                    "messages": messages,
                }
                if tools and not last_round:
                    api_kwargs["tools"] = tools
                with client.messages.stream(**api_kwargs) as stream:
                    for text in stream.text_stream:
                        full_raw.append(text)
                        parser.feed(text)
                    final = stream.get_final_message()
                usage = self._extract_usage_from_final(final)
                total_in += usage.get("input_tokens") or 0
                total_out += usage.get("output_tokens") or 0

                blocks = getattr(final, "content", None) or []
                tool_uses = [
                    b for b in blocks
                    if getattr(b, "type", None) == "tool_use"
                ]
                if not tool_uses or last_round:
                    break

                # Round-trip : rejoue le tour assistant puis injecte un tour
                # user avec un tool_result par tool_use (Anthropic l'exige).
                messages.append({"role": "assistant", "content": blocks})
                results: list = []
                extra_docs: list = []
                markers: list[str] = []
                for block in tool_uses:
                    name = getattr(block, "name", None)
                    tid = getattr(block, "id", None)
                    tin = getattr(block, "input", None) or {}
                    if name in fs_tools.FS_TOOL_NAMES:
                        res = fs_tools.execute_fs_tool(
                            name, tin, self._cours_root)
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tid,
                            "content": res.text,
                            "is_error": not res.ok,
                        })
                        # Ingestion native PDF/image : content block document
                        # ou image à côté du tool_result, même tour user.
                        if res.document is not None:
                            extra_docs.append(
                                _anthropic_document_block(res.document))
                        markers.append(fs_tools.tool_call_marker(
                            name, fs_tools.tool_call_label(name, tin),
                            res.ok))
                        logger.info(
                            "API Anthropic : outil FS %s (ok=%s)",
                            name, res.ok)
                    else:
                        # Tool pédagogique : synthétise l'event, répond "ok".
                        self._handle_pedagogical_tool(name, tin, on_event)
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": tid,
                            "content": "ok",
                        })
                messages.append({
                    "role": "user",
                    "content": results + extra_docs,
                })
                # Puce(s) visuelle(s) des appels FS injectées dans le flux.
                if markers:
                    marker_text = "\n\n" + "\n".join(markers) + "\n\n"
                    full_raw.append(marker_text)
                    parser.feed(marker_text)
            parser.flush()
        except anthropic.RateLimitError as e:
            raise ClaudeQuotaExhaustedError(
                f"API Anthropic rate limit / quota epuise : {e}"
            ) from e
        except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
            raise ClaudeNetworkError(f"API Anthropic reseau : {e}") from e
        except anthropic.APIError as e:
            raise ClaudeClientError(f"API Anthropic erreur : {e}") from e

        self._history.append({
            "role": "assistant",
            "content": "".join(full_raw),
        })
        return {"input_tokens": total_in or None, "output_tokens": total_out or None}

    def _emit_tool_events_from_final(self, final, on_event) -> None:
        """Parcourt les content blocks d'une réponse Anthropic pour
        synthétiser des ParserEvent à partir des tool_use blocks. Approche
        agnostique au stream : on traite le message final qui contient
        tous les blocks (text + tool_use éventuels).

        UNTESTED en runtime tant que pas de credit Anthropic. Tests
        unitaires avec mock dans tests/test_tool_calling.py.
        """
        from tool_schemas import (
            TOOL_NAME_TO_EVENT_TYPE,
            tool_call_to_payload,
        )
        content = getattr(final, "content", None) or []
        for block in content:
            block_type = getattr(block, "type", None)
            if block_type != "tool_use":
                continue
            tool_name = getattr(block, "name", None)
            tool_input = getattr(block, "input", None) or {}
            if tool_name not in TOOL_NAME_TO_EVENT_TYPE:
                logger.warning("Tool inconnu reçu : %s", tool_name)
                continue
            try:
                payload = tool_call_to_payload(tool_name, tool_input)
            except (ValueError, KeyError, TypeError) as e:
                logger.warning("Tool %s payload invalide : %s", tool_name, e)
                continue
            event_type_str = TOOL_NAME_TO_EVENT_TYPE[tool_name]
            try:
                event_type = ParserEventType(event_type_str)
            except ValueError:
                logger.warning("ParserEventType inconnu : %s", event_type_str)
                continue
            on_event(ParserEvent(type=event_type, payload=payload))
            logger.info("Tool %s → ParserEvent %s", tool_name, event_type_str)

    @staticmethod
    def _extract_usage_from_final(final) -> dict:
        usage = getattr(final, "usage", None)
        if usage is None:
            return {"input_tokens": None, "output_tokens": None}
        return {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        }

    # ---------------------------------------------------------------- CLI subscription

    def _stream_via_cli(self, on_event) -> dict:
        """Appel CLI ``claude --print --output-format stream-json``.

        Note Phase A : la CLI ``claude`` ne supporte pas nativement un
        historique multi-tour en argument. On concatène l'historique courant
        en un seul prompt rôle-balisé. C'est une approximation : Claude
        perd la structure exacte des tours, mais voit tout le contexte.
        Si ça pose problème en pratique, on basculera vers une approche
        avec sessions persistantes du CLI (option ``-r`` resume) en Phase B.

        Format des events stream-json : on tente plusieurs formes connues
        (Claude Code, Anthropic streaming), à valider en runtime.
        """
        prompt = self._build_cli_prompt()
        env = os.environ.copy()
        # Force OAuth/keychain : clé mémoire-stockée par claude.com auth
        env.pop("ANTHROPIC_API_KEY", None)

        # Windows CreateProcess limite la cmdline à ~32k chars. Le system
        # prompt (~5-15k) + le prompt initial (contexte CM avec script
        # complet, ~22k+) dépassent cette limite et lèvent
        # `FileNotFoundError [WinError 206] Nom de fichier ou extension
        # trop long`. Fix : passer system_prompt via fichier temporaire
        # (`--append-system-prompt-file`) et le prompt principal via
        # stdin (au lieu de positional). La cmdline reste sous 1 KB.
        import tempfile
        sysprompt_fd, sysprompt_path = tempfile.mkstemp(
            suffix=".md", prefix="compagnon_sys_"
        )
        try:
            os.write(sysprompt_fd, self._system_prompt.encode("utf-8"))
        finally:
            os.close(sysprompt_fd)

        cmd = [
            _CLI_BINARY_RESOLVED,
            "--print",
            "--output-format", "stream-json",
            "--include-partial-messages",  # nécessaire pour avoir les deltas chunk
            "--verbose",                    # imposé par CLI quand --print + stream-json
            "--append-system-prompt-file", sysprompt_path,
        ]

        # Mode guidé (Phase A.7-light → Z.8) : ouvrir Read/Grep/Glob scopés à
        # COURS_ROOT pour que le tuteur puisse vérifier le script perso vs les
        # corrigés prof, et émettre des suggestions de correction validées par
        # l'utilisateur via la balise <<<SUGGESTED_EDIT>>>.
        #
        # Mode colle (Phase v15.7.17) : autorise UNIQUEMENT `Read` scopé à
        # COURS_ROOT, pas Grep/Glob qui permettraient l'exploration libre.
        # Sans Read, la CLI Claude ne pouvait PAS lire les images attachées
        # par l'étudiant via `![photo](path)` → "permission refusée" reporté
        # au tuteur en réponse. Avec juste Read, le tuteur peut lire les
        # fichiers EXPLICITEMENT cités (image, PDF en pièce jointe), mais
        # ne peut pas fouiner : alignement pédagogique préservé.
        cwd = None
        if self._mode == MODE_GUIDE and self._cours_root is not None:
            cmd += ["--allowedTools", GUIDE_ALLOWED_TOOLS]
            cwd = str(self._cours_root)
        elif self._mode == MODE_DECOUVERTE and self._cours_root is not None:
            # Phase A.8, même set d'outils qu'en guidé : le tuteur découverte
            # peut piocher dans les CM/polys au besoin (cf. §1.3 du prompt).
            cmd += ["--allowedTools", DECOUVERTE_ALLOWED_TOOLS]
            cwd = str(self._cours_root)
        elif self._mode == MODE_WORKSPACE and self._cours_root is not None:
            # Phase A.9, workspace : exploration libre du dossier sélectionné.
            # `_cours_root` ici pointe sur workspace_root (override via
            # `ClaudeClient(cours_root=workspace_root, ...)`). Le cwd
            # subprocess sandbox effectivement les tools à cette racine ;
            # Read tente toujours le path absolu avant relatif, donc
            # techniquement Claude peut lire en dehors si chemin absolu
            # explicite ; en pratique le prompt l'oriente vers
            # ./ relatifs (cf. §3 PROMPT_SYSTEME_WORKSPACE).
            cmd += ["--allowedTools", WORKSPACE_ALLOWED_TOOLS]
            cwd = str(self._cours_root)
        elif self._mode == MODE_COLLE and self._cours_root is not None:
            cmd += ["--allowedTools", "Read"]
            cwd = str(self._cours_root)

        # Note : pas de `cmd.append(prompt)`, le prompt est piped via stdin.
        # Sur Windows, CREATE_NO_WINDOW supprime la console parasite qui
        # popait à chaque message envoyé (chaque tour Claude = un Popen).
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=env,
                cwd=cwd,
                creationflags=creationflags,
            )
        except FileNotFoundError as e:
            try:
                os.unlink(sysprompt_path)
            except OSError:
                pass
            raise ClaudeClientError(
                f"Commande {CLI_BINARY!r} introuvable. Installe Claude Code "
                f"CLI ou ajoute-la au PATH."
            ) from e

        # Écrit le prompt principal sur stdin du subprocess puis ferme.
        # `claude --print` (sans positional) lit stdin comme prompt user.
        try:
            assert proc.stdin is not None
            proc.stdin.write(prompt)
            proc.stdin.close()
        except (OSError, ValueError):
            # Le subprocess peut avoir mort prématurément (cas rare)
            logger.exception("Echec ecriture prompt sur stdin CLI")

        full_raw: list[str] = []
        parser = StreamParser(on_event)
        stats: dict = {"input_tokens": None, "output_tokens": None}

        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    # Ligne non-JSON, peut arriver si la CLI mixe du log
                    logger.debug("Ligne CLI non-JSON ignoree : %r", line[:100])
                    continue
                text = self._extract_cli_delta(event)
                if text:
                    full_raw.append(text)
                    parser.feed(text)
                usage = self._extract_cli_usage(event)
                if usage:
                    stats.update({k: v for k, v in usage.items() if v is not None})
            parser.flush()
            try:
                proc.wait(timeout=CLI_WAIT_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                proc.terminate()
                raise ClaudeNetworkError(
                    f"CLI n'a pas termine apres {CLI_WAIT_TIMEOUT_SECONDS}s"
                )
        finally:
            if proc.poll() is None:
                proc.kill()
            # Cleanup du tempfile system_prompt, quel que soit le résultat.
            try:
                os.unlink(sysprompt_path)
            except OSError:
                pass

        if proc.returncode != 0:
            stderr = (proc.stderr.read() if proc.stderr else "") or ""
            lower = stderr.lower()
            if "quota" in lower or "rate limit" in lower or "limit reached" in lower:
                raise ClaudeQuotaExhaustedError(
                    f"CLI quota / rate limit : {stderr.strip()[:300]}"
                )
            raise ClaudeClientError(
                f"CLI exit {proc.returncode} : {stderr.strip()[:300]}"
            )

        self._history.append({
            "role": "assistant",
            "content": "".join(full_raw),
        })
        return stats

    def _build_cli_prompt(self) -> str:
        """Concatène l'historique en un prompt unique rôle-balisé.

        Format simple : ``USER: ...\\n\\nASSISTANT: ...\\n\\nUSER: ...``.
        Le dernier message est toujours user (invariant : on appelle
        stream_response après append_user_message).
        """
        parts: list[str] = []
        for msg in self._history:
            role = "USER" if msg["role"] == "user" else "ASSISTANT"
            parts.append(f"{role}: {msg['content']}")
        return "\n\n".join(parts)

    @staticmethod
    def _extract_cli_delta(event: dict) -> Optional[str]:
        """Extrait le texte d'un event stream-json (format Claude Code 2.x).

        Format observé en runtime (CLI 2.1.126) :
            {"type":"stream_event",
             "event":{"type":"content_block_delta",
                      "delta":{"type":"text_delta","text":"ok"}},
             ...}

        Ne PAS lire les events ``"type":"assistant"`` (qui contiennent le
        message complet) : ça doublonnerait le texte streamé.
        """
        if not isinstance(event, dict):
            return None

        # Format Claude Code 2.x avec wrapping stream_event
        if event.get("type") == "stream_event":
            inner = event.get("event")
            if isinstance(inner, dict) and inner.get("type") == "content_block_delta":
                delta = inner.get("delta")
                if isinstance(delta, dict) and delta.get("type") == "text_delta":
                    return delta.get("text") or None
            return None

        # Fallbacks pour formats simples (anciennes versions / variantes)
        if event.get("type") == "content_block_delta":
            delta = event.get("delta")
            if isinstance(delta, dict) and delta.get("type") == "text_delta":
                return delta.get("text") or None
        if event.get("type") == "text" and isinstance(event.get("text"), str):
            return event["text"]
        if event.get("type") == "delta" and isinstance(event.get("text"), str):
            return event["text"]
        for key in ("text", "delta"):
            v = event.get(key)
            if isinstance(v, str):
                return v
        return None

    @staticmethod
    def _extract_cli_usage(event: dict) -> Optional[dict]:
        """Extrait ``input_tokens`` / ``output_tokens`` depuis n'importe quel event.

        Le CLI émet ``usage`` à plusieurs endroits selon le type :
        - ``stream_event > event > usage`` (message_delta intermédiaire)
        - ``stream_event > event > message > usage`` (message_start)
        - ``message > usage`` (event ``"type":"assistant"``)
        - ``usage`` au top level (event ``"type":"result"`` final)

        On les renvoie tous, le caller (boucle ``_stream_via_cli``) écrase
        sur les valeurs successives : la dernière vue (du ``result`` final)
        gagne.
        """
        if not isinstance(event, dict):
            return None

        usage = None
        # Format Claude Code 2.x avec wrapping
        if event.get("type") == "stream_event":
            inner = event.get("event")
            if isinstance(inner, dict):
                usage = inner.get("usage")
                if usage is None:
                    msg = inner.get("message")
                    if isinstance(msg, dict):
                        usage = msg.get("usage")
        # Top-level (events "result", "assistant")
        if usage is None:
            usage = event.get("usage")
        if usage is None:
            msg = event.get("message")
            if isinstance(msg, dict):
                usage = msg.get("usage")
        if not isinstance(usage, dict):
            return None
        return {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
        }
