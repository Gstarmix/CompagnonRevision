"""Schémas JSON des tools pédagogiques (Phase A.7.2 v15, Phase MT).

Au lieu de demander au modèle d'écrire des balises texte
``<<<NEXT_SLIDE>>>`` etc., on lui expose des **tools** (fonctions)
qu'il peut appeler avec des arguments JSON validés. Avantages :

- Structured output garanti par le moteur (Anthropic, Gemini, OpenAI
  tous supportent un format de tool calling avec validation côté server).
- Pas de risque de récitation textuelle de la balise dans la réponse.
- Pas de risque de parsing partiel sur stream (les tool calls arrivent
  comme blocs structurés, pas comme du texte à parser).
- Format homogène entre fournisseurs après une couche d'adaptation
  (cf. ``claude_client.py``).

Les tools sont **les mêmes** que les balises actuelles, mais exposés
en JSON Schema. Quand le modèle appelle ``next_slide()``, on synthétise
côté backend un ``ParserEvent(NEXT_SLIDE)`` comme si la balise avait
été émise : le pipeline app.py reste inchangé.

Mode CLI subscription : ne supporte pas les tools custom → on garde
les balises texte (cf. ``claude_client.py`` mode_uses_balises()).
"""
from __future__ import annotations

from typing import Any

# ============================================================ Schémas Anthropic native

# Format Anthropic : {name, description, input_schema}. Validé côté Anthropic
# au call API, le modèle DOIT respecter le schéma sinon erreur.
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


# ============================================================ Schémas Gemini

# Format Gemini : {name, description, parameters: <JSON Schema>}.
# Conversion mécanique depuis ANTHROPIC_TOOLS (input_schema → parameters).
def get_gemini_function_declarations() -> list[dict[str, Any]]:
    """Retourne les tool schemas au format Gemini (function declarations)."""
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        }
        for t in ANTHROPIC_TOOLS
    ]


# ============================================================ Schémas OpenAI-compat (DeepSeek/Groq)

# Format OpenAI : {type: "function", function: {name, description, parameters}}.
def get_openai_compat_tools() -> list[dict[str, Any]]:
    """Retourne les tool schemas au format OpenAI tool_use (compatible
    DeepSeek, Groq, OpenAI/GPT)."""
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


# ============================================================ Helper conversion tool_use → ParserEvent

# Mapping nom de tool → ParserEventType. Utilisé par claude_client après
# qu'un mode API natif retourne un appel tool, pour synthétiser un event
# ParserEvent(NEXT_SLIDE) compatible avec le reste du pipeline (le
# stream_response côté API fait le hook).
TOOL_NAME_TO_EVENT_TYPE = {
    "next_slide": "next_slide",
    "goto_slide": "goto_slide",
    "suggest_edit": "suggested_edit",
}


def tool_call_to_payload(tool_name: str, tool_input: dict) -> Any:
    """Convertit un appel tool en payload ParserEvent.

    Les payloads doivent matcher ce que le parser de balises produirait :
    - next_slide : payload "" (balise nue)
    - goto_slide : dict {"n": int}
    - suggest_edit : dict (passe-plat)
    """
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


# ============================================================ Helper : modes qui utilisent tools natifs

_TOOL_NATIVE_ENGINES = {"api_anthropic", "gemini_api", "deepseek_api", "groq_api"}


def engine_supports_native_tools(engine: str) -> bool:
    """True si le moteur supporte le tool calling natif. False pour
    cli_subscription qui doit continuer à utiliser les balises texte."""
    return engine in _TOOL_NATIVE_ENGINES


# ============================================================ Tuning prompt par engine

# Préfixe injecté en haut du prompt système pour les moteurs qui
# tolèrent moins bien le verbeux (Gemini Pro 2.5 a tendance à diluer
# l'attention sur les longs prompts). Pour Claude Opus / API Anthropic /
# CLI subscription, le prompt original passe sans modification.
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
    """Adapte le prompt système selon le moteur.

    Pour ``cli_subscription`` et ``api_anthropic`` : retourne le prompt
    tel quel (Claude Opus tolère bien le verbeux).

    Pour ``gemini_api`` et OpenAI-compat (deepseek_api, groq_api) : préfixe
    un avertissement court qui rappelle les règles essentielles
    (concision, format, anti-récitation). Évite d'avoir à maintenir des
    versions divergentes du prompt par moteur.

    >>> tune_prompt_for_engine("Vous êtes un colleur.", "cli_subscription")
    'Vous êtes un colleur.'
    >>> 'Note pour le moteur' in tune_prompt_for_engine("X", "gemini_api")
    True
    """
    if engine == "gemini_api":
        return _GEMINI_PROMPT_PRELUDE + prompt
    if engine in ("deepseek_api", "groq_api"):
        return _OPENAI_COMPAT_PROMPT_PRELUDE + prompt
    return prompt
