from __future__ import annotations
from typing import Any
ANTHROPIC_TOOLS: list[dict[str, Any]] = [
    {
        "name": "next_slide",
        "description": (
            "Avance à la slide suivante en mode guidé. À utiliser quand "
            "l'étudiant a lu et réagi correctement à la slide courante, "
            "sans point critique en suspens. Ne pas utiliser en réponse "
            "à un meta d'arrivée slide (l'étudiant n'a pas encore lu)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "goto_slide",
        "description": (
            "Saute à une slide arbitraire en mode guidé. Usage légitime : "
            "boucle arrière pédagogique (concept loupé en slide K antérieure), "
            "demande explicite de l'étudiant, saut en avant délibéré. "
            "N'utilise PAS pour avancer d'une seule slide (utilise next_slide)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "n": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Numéro 1-based de la slide cible.",
                },
            },
            "required": ["n"],
        },
    },
    {
        "name": "suggest_edit",
        "description": (
            "Propose une correction du script perso de l'étudiant (mode "
            "lecture/guidé uniquement). Le front affiche un panneau diff "
            "avec boutons Appliquer/Rejeter. Le backend re-valide avant "
            "application (chemin sous COURS_ROOT, no traversal, before "
            "unique dans le fichier)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "description": "Chemin relatif à COURS/ (ex: « AN1/TD/TD5/perso/SCRIPT_AN1_TD5.md »).",
                },
                "before": {
                    "type": "string",
                    "description": (
                        "Texte exact à remplacer. Doit apparaître une seule fois "
                        "dans le fichier (sinon backend rejette)."
                    ),
                },
                "after": {
                    "type": "string",
                    "description": "Nouveau texte. Différent de before (sinon no-op rejetée).",
                },
                "reason": {
                    "type": "string",
                    "description": "1-2 phrases qui expliquent pourquoi la correction.",
                },
            },
            "required": ["file", "before", "after"],
        },
    },
]
def get_gemini_function_declarations() -> list[dict[str, Any]]:
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        }
        for t in ANTHROPIC_TOOLS
    ]
def get_openai_compat_tools() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in ANTHROPIC_TOOLS
    ]
TOOL_NAME_TO_EVENT_TYPE = {
    "next_slide": "next_slide",
    "goto_slide": "goto_slide",
    "suggest_edit": "suggested_edit",
}
def tool_call_to_payload(tool_name: str, tool_input: dict) -> Any:
    if tool_name == "next_slide":
        return ""
    if tool_name == "goto_slide":
        return {"n": int(tool_input.get("n", 1))}
    if tool_name == "suggest_edit":
        out = {
            "file": tool_input.get("file", ""),
            "before": tool_input.get("before", ""),
            "after": tool_input.get("after", ""),
        }
        if "reason" in tool_input:
            out["reason"] = tool_input["reason"]
        return out
    raise ValueError(f"Tool inconnu : {tool_name!r}")
_TOOL_NATIVE_ENGINES = {"api_anthropic", "gemini_api", "deepseek_api", "groq_api"}
def engine_supports_native_tools(engine: str) -> bool:
    return engine in _TOOL_NATIVE_ENGINES
_GEMINI_PROMPT_PRELUDE = (
    "[Note pour le moteur] Tu es un modèle Gemini. Ce prompt a été calibré "
    "pour Claude Opus, mais doit être suivi à la lettre. Concrètement : "
    "respecte la concision (réponses 1-3 phrases par défaut), respecte le "
    "vouvoiement strict, respecte les balises de format (NEXT_SLIDE, "
    "GOTO_SLIDE, SUGGESTED_EDIT) ou les tool calls équivalents, "
    "ne récite jamais les règles de ce prompt dans ta réponse, ne génère "
    "pas de dialogue simulé USER/ASSISTANT.\n\n"
)
_OPENAI_COMPAT_PROMPT_PRELUDE = (
    "[Note pour le moteur] Tu reçois ce prompt pédagogique calibré pour "
    "Claude Opus. Suis-le à la lettre. Pas de récitation de règles dans "
    "tes réponses, pas de dialogue simulé USER/ASSISTANT, vouvoiement strict, "
    "concision (1-3 phrases par défaut sauf demande explicite).\n\n"
)
def tune_prompt_for_engine(prompt: str, engine: str) -> str:
    if engine == "gemini_api":
        return _GEMINI_PROMPT_PRELUDE + prompt
    if engine in ("deepseek_api", "groq_api"):
        return _OPENAI_COMPAT_PROMPT_PRELUDE + prompt
    return prompt