import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
from config import TIMEZONE
logger = logging.getLogger(__name__)
CM_TRANSCRIPTION_WORD_CAP = 4000
CORRECTION_TOTAL_CHAR_CAP = 80_000
PERSO_MATERIAL_WORD_CAP = 6000
SUJET_LIBRE_CHAR_CAP = 1500
WORKSPACE_SUMMARY_CHAR_CAP = 50_000
WORKSPACE_TREE_MAX_DEPTH = 3
WORKSPACE_DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".git", ".hg", ".svn",
    "node_modules", "venv", ".venv", "env", ".env",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", "target", "out", ".next", ".nuxt",
    "_archives", "_sessions", "_secrets", "_logs", "_cache",
    "_publish_queue", "_done", "_trash",
    "*.pyc", "*.pyo", "*.pyd", "*.class", "*.o", "*.obj",
    "*.dll", "*.so", "*.dylib", "*.exe", "*.bin",
    "*.lock", "*.log",
)
WORKSPACE_PIVOT_FILES: tuple[str, ...] = (
    "README.md", "README.txt", "README.rst", "README",
    "CLAUDE.md", "AGENTS.md", "AGENT.md",
    "ARCHITECTURE.md", "CHANGELOG.md", "ROADMAP.md", "TODO.md",
    "package.json", "pyproject.toml", "setup.py", "requirements.txt",
    "Cargo.toml", "go.mod", "Gemfile",
    "*.csproj", "*.sln",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ".github/-instructions.md",
)
WORKSPACE_PIVOT_MAX_BYTES = 8_000
WORKSPACE_CODE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs",
    ".java", ".kt", ".scala", ".groovy",
    ".cs", ".fs", ".vb",
    ".cpp", ".cc", ".cxx", ".c", ".h", ".hpp",
    ".rs", ".go", ".rb", ".php", ".swift",
    ".sh", ".ps1", ".bat", ".cmd",
    ".html", ".css", ".scss", ".sass", ".vue", ".svelte",
    ".sql", ".lua", ".dart", ".r", ".jl",
})
WORKSPACE_DOC_EXTENSIONS: frozenset[str] = frozenset({
    ".md", ".markdown", ".rst", ".txt", ".pdf", ".docx", ".doc",
    ".odt", ".tex", ".rtf",
})
def slugify_workspace(path) -> str:
    from pathlib import Path as _P
    name = _P(str(path)).name or _P(str(path)).anchor.rstrip("\\/").rstrip(":")
    slug = slugify_topic(name or "workspace")
    return slug or "workspace"
def _is_excluded(name: str, excludes: tuple[str, ...]) -> bool:
    from fnmatch import fnmatch
    for pat in excludes:
        if fnmatch(name, pat):
            return True
    return False
def detect_workspace_type(
    workspace_root: Path,
    excludes: tuple[str, ...] = WORKSPACE_DEFAULT_EXCLUDES,
    max_files_scanned: int = 500,
) -> str:
    code_count = 0
    doc_count = 0
    other_count = 0
    scanned = 0
    for p in workspace_root.rglob("*"):
        if scanned >= max_files_scanned:
            break
        if not p.is_file():
            continue
        if any(_is_excluded(parent.name, excludes) for parent in p.parents
               if parent != workspace_root and workspace_root in parent.parents
               or parent == workspace_root):
            continue
        if _is_excluded(p.name, excludes):
            continue
        ext = p.suffix.lower()
        if ext in WORKSPACE_CODE_EXTENSIONS:
            code_count += 1
        elif ext in WORKSPACE_DOC_EXTENSIONS:
            doc_count += 1
        else:
            other_count += 1
        scanned += 1
    total_typed = code_count + doc_count
    if total_typed == 0:
        return "mixed"
    code_ratio = code_count / total_typed
    if code_ratio > 0.60:
        return "code"
    if code_ratio < 0.40:
        return "doc"
    return "mixed"
def _list_tree_lines(
    root: Path,
    excludes: tuple[str, ...],
    max_depth: int,
    focus_subdir: Optional[str] = None,
) -> list[str]:
    lines: list[str] = []
    start = root
    if focus_subdir:
        candidate = (root / focus_subdir).resolve()
        try:
            candidate.relative_to(root.resolve())
            if candidate.is_dir():
                start = candidate
                lines.append(f"(Focus : {focus_subdir}/)")
        except (ValueError, OSError):
            pass
    def _walk(current: Path, depth: int):
        if depth > max_depth:
            return
        try:
            entries = sorted(
                current.iterdir(),
                key=lambda p: (p.is_file(), p.name.lower()),
            )
        except (PermissionError, OSError):
            return
        for entry in entries:
            if _is_excluded(entry.name, excludes):
                continue
            indent = "  " * depth
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"{indent}{entry.name}{suffix}")
            if entry.is_dir():
                _walk(entry, depth + 1)
    _walk(start, 0)
    return lines
def _read_pivot_files(
    root: Path,
    excludes: tuple[str, ...],
    char_budget: int,
) -> list[tuple[str, str]]:
    from fnmatch import fnmatch
    found: list[tuple[Path, str]] = []
    for entry in root.iterdir() if root.is_dir() else []:
        if not entry.is_file():
            continue
        if _is_excluded(entry.name, excludes):
            continue
        for pivot_pattern in WORKSPACE_PIVOT_FILES:
            if fnmatch(entry.name, pivot_pattern):
                found.append((entry, entry.name))
                break
    for sub in (root / ".github",):
        if not sub.is_dir():
            continue
        for entry in sub.iterdir():
            if not entry.is_file():
                continue
            if _is_excluded(entry.name, excludes):
                continue
            for pivot_pattern in WORKSPACE_PIVOT_FILES:
                if fnmatch(entry.name, pivot_pattern) or fnmatch(
                    f"{sub.name}/{entry.name}", pivot_pattern,
                ):
                    found.append((entry, f"{sub.name}/{entry.name}"))
                    break
    out: list[tuple[str, str]] = []
    spent = 0
    for path, rel in found:
        if spent >= char_budget:
            break
        try:
            raw = path.read_bytes()
        except (OSError, PermissionError):
            continue
        if len(raw) > WORKSPACE_PIVOT_MAX_BYTES:
            raw = raw[:WORKSPACE_PIVOT_MAX_BYTES]
            truncated = True
        else:
            truncated = False
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception:
            continue
        if truncated:
            text += "\n\n…(tronqué)…\n"
        remaining = char_budget - spent
        if len(text) > remaining:
            text = text[:remaining] + "\n\n…(tronqué : budget global)…\n"
        out.append((rel, text))
        spent += len(text)
    return out
def build_workspace_summary(
    workspace_root: Path,
    excludes: Optional[tuple[str, ...]] = None,
    focus_subdir: Optional[str] = None,
    char_budget: int = WORKSPACE_SUMMARY_CHAR_CAP,
) -> str:
    excl = excludes or WORKSPACE_DEFAULT_EXCLUDES
    sections: list[str] = []
    sections.append(f"# Workspace : {workspace_root}")
    wtype = detect_workspace_type(workspace_root, excl)
    sections.append(f"Type détecté : **{wtype}**")
    sections.append("")
    tree_budget = char_budget // 5
    tree_lines = _list_tree_lines(
        workspace_root, excl, WORKSPACE_TREE_MAX_DEPTH, focus_subdir,
    )
    tree_text = "\n".join(tree_lines)
    if len(tree_text) > tree_budget:
        tree_text = tree_text[:tree_budget] + "\n…(arbre tronqué : workspace dépasse le budget)…"
    sections.append("## Arbre")
    sections.append("```")
    sections.append(tree_text)
    sections.append("```")
    sections.append("")
    used = sum(len(s) + 1 for s in sections)
    remaining = max(0, char_budget - used)
    pivots = _read_pivot_files(workspace_root, excl, remaining)
    if pivots:
        sections.append("## Fichiers-pivots (lus intégralement)")
        for rel, content in pivots:
            sections.append(f"### {rel}")
            sections.append(content.rstrip())
            sections.append("")
    else:
        sections.append("## Fichiers-pivots")
        sections.append("(Aucun README/CLAUDE.md/pyproject/package.json détecté.)")
    return "\n".join(sections)
def slugify_topic(text: str, max_len: int = 30) -> str:
    import unicodedata
    if not text or not text.strip():
        return "libre"
    nkfd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in nkfd if not unicodedata.combining(c))
    ascii_text = ascii_text.lower()
    cleaned = "".join(c if c.isalnum() else " " for c in ascii_text)
    tokens = cleaned.split()
    stop = {
        "je", "tu", "il", "elle", "on", "nous", "vous", "ils", "elles",
        "veux", "voudrais", "souhaite", "souhaiterais",
        "apprendre", "apprends", "etudier", "etudie", "decouvrir", "decouvre",
        "comprendre", "comprends",
        "want", "to", "learn", "study", "discover", "understand",
        "le", "la", "les", "un", "une", "des", "du", "de", "d",
        "sur", "en", "dans", "avec", "pour", "par",
        "et", "ou", "the", "a", "an", "and", "or", "of", "in", "on",
        "ce", "cette", "ces", "mon", "ma", "mes", "son", "sa", "ses",
    }
    significant = [t for t in tokens if t not in stop and len(t) > 1]
    if not significant:
        significant = tokens
    slug = "-".join(significant)[:max_len].strip("-")
    return slug or "libre"
@dataclass
class SessionContext:
    matiere: str
    type: str
    num: str
    exo: str
    enonce_path: Optional[Path] = None
    annee: Optional[str] = None
    cm_transcription_path: Optional[Path] = None
    cm_poly_path: Optional[Path] = None
    correction_paths: list[Path] = field(default_factory=list)
    tache_path: Optional[Path] = None
    script_oral_path: Optional[Path] = None
    slides_pdf_path: Optional[Path] = None
    sujet_libre: Optional[str] = None
    workspace_root: Optional[Path] = None
    workspace_excludes: tuple[str, ...] = ()
    workspace_focus_subdir: Optional[str] = None
    droit_source: Optional[str] = None
    droit_transcription_path: Optional[Path] = None
    droit_fiche_path: Optional[Path] = None
    droit_arrets_paths: list[Path] = field(default_factory=list)
    droit_methodo_paths: list[Path] = field(default_factory=list)
class PromptBuilder:
    SECTION_HEADER = "=== {title} ==="
    DEFAULT_DURATION_HINT = "45-60 minutes"
    def __init__(self, system_prompt_path: Path, cours_root: Path):
        self._system_prompt = system_prompt_path.read_text(encoding="utf-8")
        self._cours_root = Path(cours_root)
    @property
    def system_prompt(self) -> str:
        return self._system_prompt
    def build_initial_context_message(
        self,
        ctx: SessionContext,
        is_resume: bool = False,
        mode: str = "colle",
        colle_format: str = "mixte",
        corrige_anchor: str = "strict",
    ) -> str:
        parts: list[str] = []
        if is_resume:
            parts.append("[RESUME_SESSION]")
            parts.append("")
        anchor_normalized = self._normalize_corrige_anchor(corrige_anchor)
        parts.append(self._section("CONTEXTE DE LA SÉANCE"))
        parts.append(self._build_session_header(ctx))
        if ctx.workspace_root is not None:
            parts.append("[WORKSPACE]")
            wtype = detect_workspace_type(
                ctx.workspace_root,
                ctx.workspace_excludes or WORKSPACE_DEFAULT_EXCLUDES,
            )
            parts.append(f"[WORKSPACE_TYPE : {wtype}]")
            if ctx.workspace_focus_subdir:
                parts.append(f"[WORKSPACE_FOCUS : {ctx.workspace_focus_subdir}]")
            pedagogical_format = self._normalize_colle_format(colle_format)
            parts.append(f"[FORMAT PÉDAGOGIQUE : {pedagogical_format}]")
        if ctx.sujet_libre:
            parts.append(f"[SUJET LIBRE]")
        if ctx.droit_source is not None:
            parts.append(f"[SOURCE : droit]")
            parts.append(f"[MODE : {mode}]")
            parts.append(f"[FORMAT PÉDAGOGIQUE : {self._normalize_colle_format(colle_format)}]")
            parts.append(f"[ANCRAGE : fiche de révision (pas de corrigé officiel)]")
        elif mode == "colle":
            parts.append(f"[FORMAT COLLE : {self._normalize_colle_format(colle_format)}]")
            parts.append(f"[ANCRAGE CORRIGÉ : {anchor_normalized}]")
        elif mode == "découverte":
            parts.append(f"[MODE : découverte]")
            parts.append(f"[ANCRAGE CORRIGÉ : {anchor_normalized}]")
            pedagogical_format = self._normalize_colle_format(colle_format)
            parts.append(f"[FORMAT PÉDAGOGIQUE : {pedagogical_format}]")
            applied_material = self._describe_applied_material(ctx)
            if applied_material:
                parts.append(f"[MATÉRIEL APPLIQUÉ : {applied_material}]")
        parts.append("")
        if ctx.workspace_root is not None:
            parts.append(self._section("WORKSPACE (résumé auto)"))
            try:
                summary = build_workspace_summary(
                    ctx.workspace_root,
                    excludes=ctx.workspace_excludes or WORKSPACE_DEFAULT_EXCLUDES,
                    focus_subdir=ctx.workspace_focus_subdir,
                )
            except Exception as exc:
                logger.exception("build_workspace_summary a échoué")
                summary = f"(Résumé indisponible : {exc})"
            parts.append(summary)
            parts.append("")
            parts.append(
                "**Aucun matériel COURS n'est attaché à cette séance.** "
                "Tu enseignes sur ce workspace. Tu disposes des outils "
                "`Read`, `Grep`, `Glob` (CLI Claude Code, cwd = "
                f"{ctx.workspace_root}) pour explorer le dossier "
                "au-delà du résumé ci-dessus. Le résumé donne une vue "
                "d'ensemble : utilise les outils pour zoomer sur les "
                "fichiers que tu juges importants pour répondre à la "
                "question de l'étudiant."
            )
            parts.append("")
            parts.append(self._section("INSTRUCTIONS"))
            if is_resume:
                parts.append(
                    "Reprends la séance interrompue. Fais un récap court de "
                    "ce qu'on avait abordé (≤3 phrases) puis enchaîne avec "
                    "ta dernière question/proposition. Si le résumé "
                    "workspace ci-dessus ne suffit pas, utilise Read/Grep/Glob "
                    "pour retrouver le contexte."
                )
            else:
                parts.append(
                    "**1er tour, phase de cadrage** : ouvre par une "
                    "présentation brève (3-5 phrases) du workspace tel que "
                    "tu le comprends depuis le résumé : à quoi sert ce "
                    "dossier, sa structure principale, les fichiers-pivots "
                    "que tu as lus. Puis pose 2-3 questions courtes : que "
                    "veut faire l'étudiant (découvrir / être interrogé / "
                    "approfondir un point précis) ? Quel est son niveau "
                    "actuel sur ce sujet (jamais vu / vu mais flou / "
                    "j'ai écrit ça mais je veux comprendre ce que l'IA a "
                    "fait) ? Combien de temps a-t-il ? Attends sa réponse "
                    "avant d'enchaîner sur le cœur de la séance.\n\n"
                    "Cf. PROMPT_SYSTEME_WORKSPACE.md pour le détail des "
                    "postures (explain / quiz / deep-dive) et l'usage des "
                    "outils FS."
                )
            return "\n".join(parts).rstrip() + "\n"
        if ctx.droit_source is not None:
            if ctx.droit_transcription_path is not None:
                parts.append(self._section("TRANSCRIPTION DU COURS"))
                parts.append(self._read_text_file(
                    ctx.droit_transcription_path, CM_TRANSCRIPTION_WORD_CAP))
                parts.append("")
            if ctx.droit_fiche_path is not None:
                parts.append(self._section("FICHE DE RÉVISION"))
                parts.append(self._read_text_file(
                    ctx.droit_fiche_path, PERSO_MATERIAL_WORD_CAP))
                parts.append("")
            refs: list[str] = []
            for p in ctx.droit_methodo_paths:
                refs.append(f"- Méthodo : {p.name}")
            for p in ctx.droit_arrets_paths:
                refs.append(f"- Fiche d'arrêt : {p.name}")
            if refs:
                parts.append(self._section("RÉFÉRENCES DISPONIBLES (méthodo & arrêts)"))
                parts.append("\n".join(refs))
                parts.append("")
            parts.append(
                "**Contenu produit par Cartable.** Il n'y a PAS de corrigé "
                "officiel d'exercice : ta référence pédagogique est la FICHE DE "
                "RÉVISION ci-dessus (et la transcription du cours). Tu ancres "
                "tes attentes et tes corrections sur la fiche, pas sur un "
                "barème externe."
            )
            parts.append("")
            parts.append(self._section("INSTRUCTIONS"))
            if is_resume:
                parts.append(
                    "Reprends la séance interrompue. Récap court (≤3 phrases) "
                    "de ce qu'on avait abordé, puis enchaîne selon §2.2 du "
                    "prompt système."
                )
            elif mode == "découverte":
                parts.append(
                    "**Mode découverte (droit)** : l'étudiant démarre ou révise "
                    f"« {ctx.type} {ctx.num} » en {ctx.droit_source}. Ouvre par "
                    "1 phrase d'annonce + 1 question de calibrage (« qu'est-ce "
                    "que vous en savez déjà ? »). Puis cycle court : exposition "
                    "(2-5 phrases ancrées sur la fiche) → question simple → "
                    "validation. Max 2 concepts neufs/réplique."
                )
            elif mode == "guidé":
                parts.append(
                    "**Mode guidé (droit)** : accompagne une lecture active de "
                    "la fiche et de la transcription ci-dessus. Demande à "
                    "l'étudiant où commencer, puis déroule section par section "
                    "en l'interrogeant au fil de l'eau."
                )
            else:
                parts.append(
                    "**Mode colle (droit)** : interroge l'étudiant à l'oral sur "
                    f"« {ctx.type} {ctx.num} » ({ctx.droit_source}) en posture "
                    "colle exigeante (§2.2 du prompt COMPAGNON). Pioche tes "
                    "questions dans la fiche et la transcription. Pas de corrigé "
                    "officiel : tu ne valides « faux » que sur erreur manifeste "
                    "au regard de la fiche, sinon tu fais préciser/justifier."
                )
            return "\n".join(parts).rstrip() + "\n"
        if ctx.sujet_libre:
            parts.append(self._section("SUJET LIBRE (choisi par l'étudiant)"))
            sujet = ctx.sujet_libre.strip()
            if len(sujet) > SUJET_LIBRE_CHAR_CAP:
                sujet = sujet[:SUJET_LIBRE_CHAR_CAP] + " […tronqué]"
            parts.append(sujet)
            parts.append("")
            parts.append(
                "**Aucun matériel COURS n'est attaché à cette séance.** "
                "Tu t'appuies uniquement sur tes connaissances LLM propres "
                "pour enseigner ce sujet. Pas de CORRIGÉ OFFICIEL, pas de "
                "POLY DU PROF, pas de SCRIPT ORAL PERSO. Les sections "
                "habituelles du contexte sont vides."
            )
            parts.append("")
        if ctx.enonce_path is not None:
            section_title = "POLY DU COURS" if ctx.type.upper() == "CM" else "ÉNONCÉ DE L'EXERCICE"
            parts.append(self._section(section_title))
            parts.append(self._extract_pdf_text(ctx.enonce_path))
            parts.append("")
        skip_corrige = (mode == "colle" and anchor_normalized == "aucun")
        if ctx.correction_paths and not skip_corrige:
            parts.append(self._section("CORRIGÉ OFFICIEL"))
            parts.append(self._render_corrections_block(ctx))
            parts.append("")
        if ctx.tache_path is not None:
            parts.append(self._section("TACHE PERSO (préparation écrite de l'étudiant)"))
            parts.append(self._read_text_file(ctx.tache_path, PERSO_MATERIAL_WORD_CAP))
            parts.append("")
        if ctx.script_oral_path is not None:
            parts.append(self._section("SCRIPT ORAL PERSO (TTS-ready)"))
            parts.append(self._read_text_file(ctx.script_oral_path, PERSO_MATERIAL_WORD_CAP))
            parts.append("")
        if ctx.slides_pdf_path is not None:
            parts.append(self._section("SLIDES PERSO (mention)"))
            parts.append(
                f"Slides disponibles à : {ctx.slides_pdf_path}. "
                "Contenu non extrait ; référez-vous-y si l'étudiant cite un schéma."
            )
            parts.append("")
        if ctx.cm_transcription_path is not None:
            parts.append(self._section("TRANSCRIPTION CM PERTINENTE"))
            parts.append(self._read_cm_transcription(ctx.cm_transcription_path))
            parts.append("")
        if ctx.cm_poly_path is not None:
            parts.append(self._section("POLY DU PROF (extraits)"))
            parts.append(self._extract_pdf_text(ctx.cm_poly_path))
            parts.append("")
        parts.append(self._section("INSTRUCTIONS"))
        if mode == "colle" and ctx.sujet_libre:
            parts.append(
                "**Mode colle, SUJET LIBRE** : l'étudiant veut être "
                "interrogé sur un sujet **hors COURS/** (aucun matériel "
                "académique attaché). Le sujet est dans la section "
                "« SUJET LIBRE » ci-dessus. Tu t'appuies sur tes "
                "connaissances LLM propres pour calibrer tes questions.\n\n"
                "**1er tour, phase de cadrage rapide** : pose 1 ou 2 "
                "questions courtes pour cibler l'interrogation (niveau "
                "déclaré sur le sujet, points précis à tester). Puis "
                "enchaîne en posture colle (§2.2 du prompt COMPAGNON).\n\n"
                "**Ancrage corrigé** : automatiquement `aucun` (pas de "
                "corrigé officiel disponible). Tu ne valides « faux » "
                "que sur erreur factuelle manifeste, sinon tu discutes "
                "la cohérence du raisonnement étudiant. Cf. §1.4 mode "
                "`aucun` du prompt COMPAGNON.\n\n"
            )
        if mode == "découverte":
            applied = self._describe_applied_material(ctx)
            if ctx.sujet_libre:
                parts.append(
                    "**Mode découverte, SUJET LIBRE** : l'étudiant a choisi "
                    "d'apprendre un sujet **hors COURS/** (aucun matériel "
                    "académique attaché). Le sujet est dans la section "
                    "« SUJET LIBRE » ci-dessus. Tu t'appuies sur tes "
                    "connaissances LLM propres pour enseigner ce sujet.\n\n"
                    "**1er tour, phase de cadrage** : ne te lance pas tout "
                    "de suite dans l'enseignement. Pose 2 à 3 **questions "
                    "courtes** dans UNE seule réponse pour cibler la séance :\n"
                    "  - Niveau actuel (zéro / bases / déjà des notions).\n"
                    "  - Objectif concret visé.\n"
                    "  - Temps dispo + fréquence envisagée.\n"
                    "  - Pré-acquis utiles éventuels.\n\n"
                    "**À partir du 2ᵉ tour** : cycle court exposition (2-5 "
                    "phrases) → question simple → validation/recadrage → "
                    "exposition suivante. Max 2 concepts neufs/réplique. "
                    "Pas de barème d'indices.\n\n"
                    "**Fin de séance** : récap 3-5 takeaways + suggestion "
                    "de prochaine étape + `<<<END_SESSION>>>`.\n\n"
                )
            elif applied:
                parts.append(
                    "**Mode découverte (cas B, matériel d'application "
                    "existant)** : l'étudiant cible un TP/exercice précis "
                    f"qu'il n'a pas (ou peu) les bases pour aborder. Tu es son "
                    f"**tuteur explicateur** sur « {ctx.num} » "
                    f"({ctx.matiere}). Le contexte initial contient déjà "
                    f"le matériel d'application ([MATÉRIEL APPLIQUÉ : {applied}]). "
                    "Utilise le matériel existant comme support de séance.\n\n"
                    "**Posture bottom-up** : identifie les prérequis "
                    "manquants pour avancer dans le TP, fais des micro-leçons "
                    "ancrées sur chaque prérequis, et reconnecte IMMÉDIATEMENT "
                    "au TP cible (« et maintenant, en utilisant ce qu'on vient "
                    "de voir, écrivez la ligne X »). Pas de cours complet : "
                    "uniquement les briques utiles aux fonctions du TP.\n\n"
                    "**Ouverture (1ᵉʳ message)** : 1 phrase d'annonce + 1 "
                    "question de calibrage. Au tour suivant, identifie le "
                    "1ᵉʳ prérequis manquant et propose une micro-leçon ciblée.\n\n"
                    "**Reste** : cycle court exposition → question → validation "
                    "→ exposition suivante. Max 2 concepts neufs/réplique. Pas "
                    "de barème d'indices. Fin de séance : "
                    "récap 3-5 takeaways + `<<<END_SESSION>>>`.\n\n"
                )
            else:
                parts.append(
                    "**Mode découverte (cas A, pas de matériel "
                    "d'application)** : l'étudiant démarre un sujet qu'il "
                    "n'a pas (ou peu) suivi en CM, sans cibler de TP "
                    f"précis. Tu es son **tuteur explicateur** sur "
                    f"« {ctx.num} » ({ctx.matiere}).\n\n"
                    "**Ouverture (1ᵉʳ message)** : 1 phrase d'annonce du "
                    "sujet + 1 question de calibrage simple (« qu'est-ce "
                    "que vous en savez déjà ? »). Pas de plan détaillé, "
                    "pas de structuration verbeuse.\n\n"
                    "**Suite** : cycle court exposition (2-5 phrases) → "
                    "question simple inventée au fil de la conversation "
                    "(calibrée sur la dernière réponse de l'étudiant) → "
                    "validation/recadrage → exposition suivante. Max 2 "
                    "concepts neufs/réplique. Pas de barème d'indices.\n\n"
                    "**Fin de séance** : récap 3-5 takeaways + suggestion "
                    "de prochaine étape + `<<<END_SESSION>>>`.\n\n"
                )
        elif ctx.enonce_path is None:
            parts.append(
                "**Mode révision sans énoncé** : il n'y a pas d'énoncé "
                f"d'exercice précis pour cette séance (sujet : « {ctx.num} », "
                f"matière : {ctx.matiere}). L'étudiant veut réviser le "
                "contenu d'un thème, pas résoudre un exercice donné. "
                "À toi de prendre l'initiative :\n\n"
                "- En **mode colle** : annonce-toi à l'étudiant en 1 phrase, "
                "  préviens-le que tu vas créer ta propre série de questions "
                "  depuis les matériaux disponibles (CORRIGÉ OFFICIEL, POLY "
                "  DU PROF, SCRIPT ORAL PERSO, SLIDES). Demande-lui s'il "
                "  préfère un parcours dans l'ordre, ou s'il cible un point "
                "  précis. Puis enchaîne en posture colle (§2.2 du prompt).\n"
                "- En **mode guidé** : accompagne la lecture du script oral / "
                "  slides. Demande à l'étudiant où il veut commencer "
                "  (« on déroule depuis le début ? un point précis ? »).\n\n"
                "**Ressources disponibles** : matériaux dans les sections "
                "ci-dessus (CORRIGÉ, POLY, SCRIPT, SLIDES). Tu n'as PAS "
                "besoin d'énoncé externe : l'annale + le poly te donnent "
                "assez de matière pour 1 h+.\n\n"
            )
        if is_resume:
            parts.append(
                "Reprends la séance interrompue. Fais un récap court de "
                "où on en était puis enchaîne selon §2.2 du prompt système."
            )
        else:
            if mode == "découverte":
                parts.append(
                    "Démarre la séance. Annonce le sujet en 1 phrase puis "
                    "pose ta question de calibrage selon §2.2 du prompt "
                    "DECOUVERTE."
                )
            else:
                parts.append(
                    "Démarre la séance. Pose la première question selon §2.2 "
                    "du prompt système."
                )
        return "\n".join(parts).strip() + "\n"
    def _section(self, title: str) -> str:
        return self.SECTION_HEADER.format(title=title)
    def _build_session_header(self, ctx: SessionContext) -> str:
        now = datetime.now(TIMEZONE)
        if ctx.sujet_libre:
            lines = [
                f"Type de séance : sujet libre (hors COURS/)",
                f"Slug interne : {ctx.num}",
                f"Date : {now.strftime('%Y-%m-%d')}",
                f"Heure de début : {now.strftime('%H:%M')}",
                f"Durée prévue : {self.DEFAULT_DURATION_HINT}",
            ]
            return "\n".join(lines)
        lines = [
            f"Matière : {ctx.matiere}",
            f"Type : {ctx.type} {ctx.num}",
        ]
        if ctx.type.upper() == "CM":
            lines.append("Cours magistral entier (pas d'exercice ciblé)")
        elif ctx.exo and ctx.exo != "full":
            lines.append(f"Exercice ciblé : exercice {ctx.exo}")
        else:
            lines.append("Exercice ciblé : tout le TD/TP")
        lines.append(f"Date : {now.strftime('%Y-%m-%d')}")
        lines.append(f"Heure de début : {now.strftime('%H:%M')}")
        lines.append(f"Durée prévue : {self.DEFAULT_DURATION_HINT}")
        return "\n".join(lines)
    def _extract_pdf_text(self, pdf_path: Path) -> str:
        suffix = pdf_path.suffix.lower()
        if suffix in (".md", ".txt"):
            if not pdf_path.exists():
                return f"[Fichier introuvable : {pdf_path}]"
            try:
                return pdf_path.read_text(encoding="utf-8").strip()
            except OSError as e:
                logger.warning("Echec lecture %s : %s", pdf_path, e)
                return f"[Lecture échouée ({e}) : {pdf_path}]"
        try:
            from pypdf import PdfReader
        except ImportError:
            return (
                f"[pypdf indisponible : joindre le PDF en multimodal : {pdf_path}]"
            )
        if not pdf_path.exists():
            return f"[PDF introuvable : {pdf_path}]"
        try:
            reader = PdfReader(str(pdf_path))
            chunks: list[str] = []
            for page in reader.pages:
                txt = page.extract_text() or ""
                if txt.strip():
                    chunks.append(txt)
            text = "\n".join(chunks).strip()
            if not text:
                return f"[Extraction PDF vide : PDF probablement scanné : {pdf_path}]"
            return text
        except Exception as e:
            logger.warning("Echec extraction PDF %s : %s", pdf_path, e)
            return f"[Extraction PDF échouée ({e}) : {pdf_path}]"
    def _read_cm_transcription(self, txt_path: Path) -> str:
        try:
            text = txt_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Echec lecture transcription CM %s : %s", txt_path, e)
            return f"[Lecture transcription CM échouée : {e}]"
        return self._cap_words(text, CM_TRANSCRIPTION_WORD_CAP)
    def _read_text_file(self, txt_path: Path, word_cap: int) -> str:
        if not txt_path.exists():
            return f"[Fichier introuvable : {txt_path}]"
        try:
            text = txt_path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Echec lecture %s : %s", txt_path, e)
            return f"[Lecture échouée : {e}]"
        return self._cap_words(text, word_cap)
    def _render_corrections_block(self, ctx: "SessionContext") -> str:
        chunks: list[str] = []
        total = 0
        truncated = False
        for path in ctx.correction_paths:
            label = path.name
            extracted = self._extract_pdf_text(path)
            block = f"--- {label} ---\n{extracted}"
            remaining = CORRECTION_TOTAL_CHAR_CAP - total
            if remaining <= 0:
                truncated = True
                break
            if len(block) > remaining:
                block = block[:remaining] + "\n[...corrigé tronqué : cap atteint]"
                truncated = True
            chunks.append(block)
            total += len(block)
            if truncated:
                break
        if truncated and len(ctx.correction_paths) > len(chunks):
            remaining_files = [
                p.name for p in ctx.correction_paths[len(chunks):]
            ]
            chunks.append(
                "[...corrigés non inclus faute de place : "
                + ", ".join(remaining_files) + "]"
            )
        return "\n\n".join(chunks)
    COLLE_FORMATS_VALID = ("oral", "photos", "mixte")
    COLLE_FORMAT_DEFAULT = "mixte"
    CORRIGE_ANCHORS_VALID = ("strict", "consultatif", "aucun")
    CORRIGE_ANCHOR_DEFAULT = "strict"
    @staticmethod
    def _describe_applied_material(ctx: "SessionContext") -> str:
        parts: list[str] = []
        ident = f"{ctx.type}{ctx.num}" if ctx.type and ctx.num else ""
        if ident:
            parts.append(f"sujet {ident}")
        bits: list[str] = []
        if ctx.script_oral_path is not None:
            bits.append("script oral")
        if ctx.slides_pdf_path is not None:
            bits.append("slides")
        if ctx.enonce_path is not None:
            bits.insert(0, "énoncé")
        if not bits:
            return ""
        if parts:
            return f"{parts[0]} : matériaux disponibles : " + ", ".join(bits)
        return "matériaux disponibles : " + ", ".join(bits)
    @classmethod
    def _normalize_colle_format(cls, raw: str) -> str:
        v = (raw or "").strip().lower()
        return v if v in cls.COLLE_FORMATS_VALID else cls.COLLE_FORMAT_DEFAULT
    @classmethod
    def _normalize_corrige_anchor(cls, raw: str) -> str:
        v = (raw or "").strip().lower()
        if v in ("sans_corrigé", "sans_corrige", "sans corrigé", "sans corrige"):
            return "aucun"
        return v if v in cls.CORRIGE_ANCHORS_VALID else cls.CORRIGE_ANCHOR_DEFAULT
    @staticmethod
    def _cap_words(text: str, max_words: int) -> str:
        words = text.split()
        if len(words) <= max_words:
            return text
        kept = " ".join(words[:max_words])
        return (
            f"{kept}\n\n[...tronqué à {max_words} mots, "
            f"total {len(words)}]"
        )