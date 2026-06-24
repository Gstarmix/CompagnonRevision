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
class ClaudeClientError(Exception):
    pass
class ClaudeQuotaExhaustedError(ClaudeClientError):
    pass
class ClaudeNetworkError(ClaudeClientError):
    pass
DEFAULT_MODEL = "claude-opus-4-7"
DEFAULT_MAX_TOKENS = 8192
ENGINE_CLI = "cli_subscription"
ENGINE_API = "api_anthropic"
ENGINE_GEMINI = "gemini_api"
ENGINE_DEEPSEEK = "deepseek_api"
ENGINE_GROQ = "groq_api"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
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
_TAGS_NEEDING_CLOSE = (
    "<<<TTS>>>", "<<<SUGGESTED_EDIT>>>", "<<<GOTO_SLIDE>>>",
    "<<<SHOW_DOC>>>", "<<<REMEMBER>>>",
)
def _autoclose_truncated_tags(text: str) -> str:
    closes = text.count("<<<END>>>")
    opens = sum(text.count(t) for t in _TAGS_NEEDING_CLOSE)
    opens += len(re.findall(r"<<<CAHIER(?:\s[^>]*)?>{1,3}", text))
    missing = opens - closes
    return "<<<END>>>" * missing if missing > 0 else ""
SUPPORTED_ENGINES = (
    ENGINE_CLI, ENGINE_API, ENGINE_GEMINI, ENGINE_DEEPSEEK, ENGINE_GROQ,
)
MODE_COLLE = "colle"
MODE_GUIDE = "guidé"
MODE_DECOUVERTE = "découverte"
MODE_WORKSPACE = "workspace"
GUIDE_ALLOWED_TOOLS = "Read,Grep,Glob"
DECOUVERTE_ALLOWED_TOOLS = "Read,Grep,Glob"
WORKSPACE_ALLOWED_TOOLS = "Read,Grep,Glob"
_FS_TOOL_MODES = frozenset({MODE_GUIDE, MODE_DECOUVERTE, MODE_WORKSPACE})
CLI_BINARY = "claude"
CLI_WAIT_TIMEOUT_SECONDS = 60
def _resolve_claude_binary() -> str:
    import shutil
    hit = shutil.which(CLI_BINARY)
    if hit:
        return hit
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
    return CLI_BINARY
_CLI_BINARY_RESOLVED = _resolve_claude_binary()
logger.info("CLI claude résolue : %s", _CLI_BINARY_RESOLVED)
import re as _re_img
_INLINE_IMAGE_RE = _re_img.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_IMAGE_MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".gif": "image/gif",
    ".webp": "image/webp", ".heic": "image/heic",
}
_MAX_IMAGE_BYTES = 5 * 1024 * 1024
def _extract_inline_images(text: str, cours_root: Optional[Path]):
    if not text or "![" not in text:
        return text, []
    import base64
    images = []
    def _replace(m):
        alt = (m.group(1) or "").strip() or "image"
        rel_path = m.group(2).strip()
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
    import base64
    media = document["media_type"]
    b64 = base64.b64encode(document["data"]).decode("ascii")
    block_type = "document" if media == "application/pdf" else "image"
    return {
        "type": block_type,
        "source": {"type": "base64", "media_type": media, "data": b64},
    }
class ClaudeClient:
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
        self._enable_native_tools: bool = False
        self._enable_web_search: bool = False
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
        return list(self._history)
    @property
    def native_tools_active(self) -> bool:
        try:
            from tool_schemas import engine_supports_native_tools
        except ImportError:
            return False
        return self._enable_native_tools and engine_supports_native_tools(self._engine)
    def set_enable_native_tools(self, enable: bool) -> None:
        self._enable_native_tools = bool(enable)
    def set_enable_web_search(self, enable: bool) -> None:
        self._enable_web_search = bool(enable)
    def _should_use_fs_tools(self) -> bool:
        return (
            self._mode in _FS_TOOL_MODES
            and self._cours_root is not None
            and not self._enable_web_search
        )
    def _handle_pedagogical_tool(self, name, tool_input, on_event) -> None:
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
    def append_user_message(self, text: str) -> None:
        self._history.append({"role": "user", "content": text})
    def stream_response(
        self,
        on_event: Callable[[ParserEvent], None],
    ) -> dict:
        if self._engine == ENGINE_CLI:
            return self._stream_via_cli(on_event)
        if self._engine == ENGINE_GEMINI:
            return self._stream_via_gemini(on_event)
        if self._engine in _OPENAI_COMPATIBLE_PROVIDERS:
            return self._stream_via_openai_compatible(
                on_event, _OPENAI_COMPATIBLE_PROVIDERS[self._engine]
            )
        return self._stream_via_api(on_event)
    def _stream_via_gemini(self, on_event) -> dict:
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
        model_name = (
            self._model
            if self._model.startswith("gemini-")
            else os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
        )
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
            for round_idx in range(fs_tools.MAX_TOOL_ROUNDS + 1):
                last_round = round_idx == fs_tools.MAX_TOOL_ROUNDS
                cfg_kwargs = {
                    "system_instruction": self._system_prompt,
                    "max_output_tokens": self._max_tokens,
                }
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
                fcall_parts: list = []
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
                    if getattr(fc, "id", None):
                        fr_payload["id"] = fc.id
                    resp_parts.append({"function_response": fr_payload})
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
                marker_text = "\n\n" + "\n".join(markers) + "\n\n"
                full_raw.append(marker_text)
                parser.feed(marker_text)
            parser.flush()
        except Exception as e:
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
    def _stream_via_openai_compatible(self, on_event, cfg: dict) -> dict:
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
        model_name = (
            self._model
            if self._model.startswith(cfg["model_prefix"])
            else os.environ.get(cfg["model_env"], cfg["default_model"])
        )
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
                tool_acc: dict = {}
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
    def _stream_via_api(self, on_event) -> dict:
        try:
            import anthropic
        except ImportError as e:
            raise ClaudeClientError(
                f"SDK anthropic indisponible ({e}). pip install anthropic"
            ) from e
        full_raw: list[str] = []
        parser = StreamParser(on_event)
        messages = _messages_to_anthropic_multimodal(
            self._history, self._cours_root,
        )
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
    def _stream_via_cli(self, on_event) -> dict:
        prompt = self._build_cli_prompt()
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
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
            "--include-partial-messages",
            "--verbose",
            "--append-system-prompt-file", sysprompt_path,
        ]
        cwd = None
        if self._mode == MODE_GUIDE and self._cours_root is not None:
            cmd += ["--allowedTools", GUIDE_ALLOWED_TOOLS]
            cwd = str(self._cours_root)
        elif self._mode == MODE_DECOUVERTE and self._cours_root is not None:
            cmd += ["--allowedTools", DECOUVERTE_ALLOWED_TOOLS]
            cwd = str(self._cours_root)
        elif self._mode == MODE_WORKSPACE and self._cours_root is not None:
            cmd += ["--allowedTools", WORKSPACE_ALLOWED_TOOLS]
            cwd = str(self._cours_root)
        elif self._mode == MODE_COLLE and self._cours_root is not None:
            cmd += ["--allowedTools", "Read"]
            cwd = str(self._cours_root)
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
        try:
            assert proc.stdin is not None
            proc.stdin.write(prompt)
            proc.stdin.close()
        except (OSError, ValueError):
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
        parts: list[str] = []
        for msg in self._history:
            role = "USER" if msg["role"] == "user" else "ASSISTANT"
            parts.append(f"{role}: {msg['content']}")
        return "\n\n".join(parts)
    @staticmethod
    def _extract_cli_delta(event: dict) -> Optional[str]:
        if not isinstance(event, dict):
            return None
        if event.get("type") == "stream_event":
            inner = event.get("event")
            if isinstance(inner, dict) and inner.get("type") == "content_block_delta":
                delta = inner.get("delta")
                if isinstance(delta, dict) and delta.get("type") == "text_delta":
                    return delta.get("text") or None
            return None
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
        if not isinstance(event, dict):
            return None
        usage = None
        if event.get("type") == "stream_event":
            inner = event.get("event")
            if isinstance(inner, dict):
                usage = inner.get("usage")
                if usage is None:
                    msg = inner.get("message")
                    if isinstance(msg, dict):
                        usage = msg.get("usage")
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