"""
cours_resolver.py : résolution des chemins canoniques dans l'arbo COURS.

Trouve l'énoncé, les corrigés officiels, la TACHE perso et le script oral
perso pour un (matière, type, num, exo, annee) donné. Logique calquée sur
``BotGSTAR/extensions/cours_pipeline.py`` (``resolve_correction_pdf``,
``find_enonce_pdf``, ``list_perso_material``) mais standalone, sans
dépendance au Cog Discord.

Le `PromptBuilder` consomme ces helpers pour injecter le **CORRIGÉ
OFFICIEL** dans le contexte initial de la séance, sinon Claude infère
depuis le seul énoncé et dérive du corrigé prof.
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================ Conventions

#: Pour les TD/TP, exo='full' privilégie le concat global s'il existe, sinon
#: agrège tous les correction_*_ex*_*.pdf trouvés.
_CONCAT_FILE_PATTERN = "concat_{type}{num}_{matiere}.pdf"

#: Phase v15.7.32 : types **libres** (browse générique). Quand la matière
#: a des dossiers qui ne suivent pas la convention canonique TD/TP/CC/CM,
#: on les expose quand même dans le combobox Type. Le resolver scan
#: heuristiquement le dossier pour trouver énoncé/corrigé/scripts.
#:
#: Conçu pour PSI ``_revision_CC1/`` ``_revision_CC2/`` ``TP_recherche_docu/``
#: mais s'applique à toute matière qui crée des dossiers ad hoc.
#: Heuristique de nommage des PDFs dans un dossier libre :
#:   énoncé    : nom contient ``enonce`` OU ``aide_memoire`` OU ``sujet``
#:               OU ``poly`` OU ``pitch_oral`` OU commence par ``cm_``
#:   corrigé   : nom contient ``correction`` OU ``annale_synthese``
#:               OU ``corrige`` (alternative orthographe)
#:   imprimable: nom contient ``script_imprimable`` OU ``recopie``
#:               (variante PSI `*_a4_recopie.pdf`)
#:   slides    : nom contient ``slides`` ou ``pitch``
#: Scripts oraux : sous-dossiers ``scripts/`` (PSI) ou ``scripts_oraux/``
#: (convention canonique).

#: Dossiers techniques à exclure du combobox Type (jamais des sessions).
_EXCLUDED_TOP_DIRS = frozenset({
    "_moodle", "_archives", "_inbox_dl", "_contextes_reprise",
    "_A_TRIER", "_a_trier", "_audit", "_publish_queue",
    "_prompts_claude_ai", "_prompts_claude_code", "_perso",
    "_scripts", "_INBOX", "_A_VALIDER", "_temp_latex", "_archived",
    "_lectures",  # PSI : sous-dossier de lectures complémentaires
    "scripts_oraux",  # toujours sous {MAT}/CM/scripts_oraux/, jamais session
})

#: Heuristiques de classification des fichiers dans un dossier libre.
#: Phase v15.7.33 : `aide_memoire` retiré des énoncés (c'est un poly de
#: révision, mappé vers cm_poly_path). `pitch_oral` retiré des slides
#: (c'est un pitch, pas un slide deck). `annale_synthese` reste l'énoncé
#: par défaut pour les dossiers de révision (PDF Q&A qui sert à la fois
#: d'examen blanc et de corrigé).
_FREE_ENONCE_HINTS = ("annale_synthese", "enonce", "exos", "sujet")
_FREE_CORRIGE_HINTS = ("correction", "annale_synthese", "corrige", "corrigé")
_FREE_POLY_HINTS = ("aide_memoire", "poly", "cheat_sheet", "synthese")
_FREE_IMPRIMABLE_HINTS = ("script_imprimable", "_recopie", "a4_recopie")
_FREE_SLIDES_HINTS = ("slides",)


_FREE_MATERIAL_EXTS = (".pdf", ".md", ".txt")


def _has_material_recursive(folder: Path, max_depth: int = 2) -> bool:
    """True si ``folder`` (ou sous-dossiers jusqu'à ``max_depth``) contient
    au moins un fichier pédagogique (PDF, MD ou TXT). Pour décider si un
    dossier libre vaut la peine d'être exposé dans le combobox Type
    (sinon dossier vide ou que des sources techniques).

    Phase v15.7.32 : étendu à .md/.txt pour détecter PSI ``_revision_CC1/``
    qui n'a que des markdown (pas encore compilés en PDF).
    """
    if not folder.is_dir():
        return False
    try:
        for p in folder.iterdir():
            if p.is_file() and p.suffix.lower() in _FREE_MATERIAL_EXTS:
                return True
            if p.is_dir() and max_depth > 0:
                if _has_material_recursive(p, max_depth - 1):
                    return True
    except OSError:
        return False
    return False


# Alias rétrocompat (anciens tests éventuels)
_has_pdf_recursive = _has_material_recursive


def _is_canonical_type(type_code: str) -> bool:
    """True si le type est canonique TD/TP/CC/CM/Quiz/Examen.

    Sinon : type libre, traité par scan heuristique.
    """
    return type_code.upper() in ("TD", "TP", "CC", "CM", "QUIZ", "EXAMEN")


def _get_free_type_dir(cours_root: Path, matiere: str, type_code: str) -> Optional[Path]:
    """``{cours_root}/{MAT}/{type_code}/`` si existe ET non-canonique.

    Type libre = le nom du dossier EST le « type » du combobox.
    Casse insensible pour matcher `_revision_CC2` même si l'utilisateur
    tape `_REVISION_CC2`.
    """
    if _is_canonical_type(type_code):
        return None
    base = cours_root / matiere.upper()
    if not base.is_dir():
        return None
    candidate = base / type_code
    if candidate.is_dir():
        return candidate
    # Scan tolérant casse
    target_lower = type_code.lower()
    for p in base.iterdir():
        if p.is_dir() and p.name.lower() == target_lower:
            return p
    return None


def _match_free_pdf(
    folder: Path,
    hints: tuple[str, ...],
    exts: tuple[str, ...] = (".pdf",),
) -> Optional[Path]:
    """1er fichier de ``folder`` qui matche un hint, **par ordre de priorité**.

    Les hints sont testés un par un (du plus prioritaire au plus
    générique). Le 1ᵉʳ hint qui trouve un match l'emporte. Évite que
    ``pitch_oral_30s.pdf`` soit retourné comme énoncé quand
    ``aide_memoire_CC2.pdf`` existe à côté : `aide_memoire` doit être
    listé en premier dans ``_FREE_ENONCE_HINTS``.

    Pour les fichiers qui matchent le même hint, tri par nom inverse
    (préfère les versions plus récentes type `_v2`, date suffixée).

    Phase v15.7.32 : extensions élargies. Par défaut ``.pdf``, mais on
    peut passer ``(".pdf", ".md")`` pour les dossiers `_revision_CC1/`
    qui n'ont pas encore de versions compilées en PDF. Préfère **toujours
    le .pdf si présent** parmi les matches d'un même hint (tri stable
    via priorité d'ext dans la clé de sort).
    """
    if not folder.is_dir():
        return None
    exts_lower = tuple(e.lower() for e in exts)
    try:
        files = [
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in exts_lower
        ]
    except OSError:
        return None
    if not files:
        return None
    # Tri principal : nom inverse. Pour stabilité, on préfère .pdf > .md > .txt
    # (l'ordre dans `exts` définit la priorité : plus prioritaire = plus tôt).
    ext_priority = {e: i for i, e in enumerate(exts_lower)}
    files_sorted = sorted(
        files,
        key=lambda p: (ext_priority.get(p.suffix.lower(), 99), -ord(p.name[0]) if p.name else 0, p.name),
    )
    # Reverse alpha sur le nom pour préférer les versions plus récentes
    files_sorted.sort(key=lambda p: (ext_priority.get(p.suffix.lower(), 99), p.name), reverse=False)
    # Final : applique l'ordre des hints
    for hint in hints:
        for p in files_sorted:
            if hint in p.name.lower():
                return p
    return None


def _scan_free_corrections(folder: Path) -> list[Path]:
    """Tous les fichiers de ``folder`` qui matchent ``_FREE_CORRIGE_HINTS``,
    triés par nom croissant (pour stabilité du picker UI).

    Phase v15.7.32 : accepte ``.pdf`` ET ``.md`` (cas `_revision_CC1/`
    qui n'a que des markdown). Préfère le PDF si les deux versions
    existent (tri stable par extension).
    """
    if not folder.is_dir():
        return []
    try:
        items = sorted(folder.iterdir())
    except OSError:
        return []
    out: list[Path] = []
    seen_stems: set[str] = set()
    # 1ère passe : PDFs (prioritaires)
    for p in items:
        if not p.is_file() or p.suffix.lower() != ".pdf":
            continue
        low = p.name.lower()
        if any(h in low for h in _FREE_CORRIGE_HINTS):
            out.append(p)
            seen_stems.add(p.stem.lower())
    # 2ème passe : .md (uniquement si pas déjà capturés en PDF)
    for p in items:
        if not p.is_file() or p.suffix.lower() != ".md":
            continue
        low = p.name.lower()
        if not any(h in low for h in _FREE_CORRIGE_HINTS):
            continue
        if p.stem.lower() in seen_stems:
            continue
        out.append(p)
    return out


def _find_free_script(
    folder: Path,
    exts: tuple[str, ...],
    theme: Optional[str] = None,
) -> Optional[Path]:
    """Cherche un script dans ``folder/scripts/`` puis ``folder/scripts_oraux/``.

    Préférence : fichier qui contient ``script_oral`` dans le nom, sinon
    n'importe quel fichier avec l'extension cible.

    Phase v15.7.33 : param ``theme`` optionnel pour filtrer par sujet.
    Quand un dossier libre agrège plusieurs thèmes (PSI ``_revision_CC2/``
    a 4 scripts : `Bit_information`, `RAID`, `TP_Shannon`, `USB`), passer
    le thème en ``num`` (ex : ``"TP_Shannon"``) filtre sur le fichier
    correspondant. Si ``theme`` est ``None`` ou ``"full"``, comportement
    historique (1ᵉʳ trouvé).
    """
    is_themed = theme and theme.lower() != "full"
    theme_lower = (theme or "").lower()
    for sub_name in ("scripts", "scripts_oraux"):
        sub = folder / sub_name
        if not sub.is_dir():
            continue
        try:
            names = sorted((p.name for p in sub.iterdir() if p.is_file()))
        except OSError:
            continue
        # Pref 1 : script_oral_{theme}.{ext} si thème ciblé, sinon
        # script_oral_*.{ext} générique.
        for name in names:
            low = name.lower()
            if not any(low.endswith(e) for e in exts):
                continue
            if "script_oral" not in low:
                continue
            if is_themed:
                # Le nom doit contenir `_{theme}.` ou `_{theme}_`
                if (f"_{theme_lower}." not in low) and (f"_{theme_lower}_" not in low):
                    continue
            return sub / name
        # Pref 2 : tout fichier de l'ext (rarement utile, fallback)
        if not is_themed:
            for name in names:
                low = name.lower()
                if any(low.endswith(e) for e in exts):
                    return sub / name
    return None


def _detect_themes_in_free_dir(folder: Path) -> list[str]:
    """Détecte les **thèmes** d'un dossier libre en analysant les patterns
    de nommage ``{prefix}_{theme}.{ext}`` dans ``folder/scripts/`` (ou
    ``folder/scripts_oraux/``).

    Pattern reconnu : fichiers ``script_oral_{theme}.{txt,md}`` ou
    ``slides_{theme}.pdf`` ou ``script_imprimable_{theme}.pdf``. La partie
    après le préfixe et avant l'extension est extraite comme thème.

    Retourne la liste triée alphabétiquement des thèmes uniques. Vide si
    aucun pattern reconnu (le dossier est traité comme ``full`` uniquement).

    Exemple PSI ``_revision_CC2/scripts/`` :
        script_oral_Bit_information.txt → "Bit_information"
        script_oral_RAID.txt → "RAID"
        script_oral_TP_Shannon.txt → "TP_Shannon"
        script_oral_USB.txt → "USB"
        → ["Bit_information", "RAID", "TP_Shannon", "USB"]
    """
    if not folder.is_dir():
        return []
    themes: set[str] = set()
    # Patterns de préfixe → extensions cibles. Ordre = priorité de détection.
    patterns = (
        ("script_oral_", (".txt", ".md")),
        ("slides_", (".pdf",)),
        ("script_imprimable_", (".pdf",)),
    )
    for sub_name in ("scripts", "scripts_oraux"):
        sub = folder / sub_name
        if not sub.is_dir():
            continue
        try:
            names = list(p.name for p in sub.iterdir() if p.is_file())
        except OSError:
            continue
        for name in names:
            for prefix, exts in patterns:
                low = name.lower()
                if not low.startswith(prefix):
                    continue
                for ext in exts:
                    if low.endswith(ext):
                        # Extrait le thème : nom sans le préfixe et sans l'ext
                        theme = name[len(prefix):-len(ext)]
                        # Cas dégénéré : si le thème est juste vide ou
                        # purement numérique (style script_oral_1.txt), on
                        # n'a probablement pas affaire à un dossier multi-
                        # thématique. On l'ajoute quand même par défaut, le
                        # filtre côté list_nums décide.
                        if theme:
                            themes.add(theme)
                        break
    return sorted(themes)


def _match_free_pdf_themed(
    folder: Path,
    hints: tuple[str, ...],
    theme: Optional[str] = None,
    exts: tuple[str, ...] = (".pdf",),
) -> Optional[Path]:
    """Variante de ``_match_free_pdf`` qui filtre par thème.

    Phase v15.7.33 : pour les types libres avec thèmes (cas PSI
    ``_revision_CC2/`` qui a ``exos_TP_Shannon.pdf`` au top). Si
    ``theme`` est fourni et non-``full``, retourne le 1ᵉʳ fichier dont le
    nom contient à la fois un hint **et** le thème. Sinon, comportement
    historique (``_match_free_pdf`` standard).
    """
    is_themed = theme and theme.lower() != "full"
    if not is_themed:
        return _match_free_pdf(folder, hints, exts)
    theme_lower = theme.lower()
    if not folder.is_dir():
        return None
    exts_lower = tuple(e.lower() for e in exts)
    try:
        files = [
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in exts_lower
        ]
    except OSError:
        return None
    if not files:
        return None
    for hint in hints:
        for p in sorted(files, key=lambda p: p.name):
            low = p.name.lower()
            if hint in low and theme_lower in low:
                return p
    return None


def find_free_poly(
    cours_root: Path,
    matiere: str,
    type_code: str,
) -> Optional[Path]:
    """Phase v15.7.33 : auto-résolution du **poly CM** pour les types libres.

    Cas réel : PSI ``_revision_CC2/aide_memoire_CC2.pdf`` est un poly de
    révision (cheat sheet), pas un énoncé d'exercice. Il sert de
    matériau de référence au tuteur, mappé vers ``cm_poly_path`` du
    SessionContext (section « POLY DU PROF » du prompt initial).

    Retourne None pour les types canoniques (la convention TD/TP/CC/CM
    classique a déjà ses propres mécanismes).
    """
    free_dir = _get_free_type_dir(cours_root, matiere, type_code)
    if free_dir is None:
        return None
    return _match_free_pdf(free_dir, _FREE_POLY_HINTS, exts=(".pdf", ".md"))


# ============================================================ Énoncé

def find_enonce_pdf(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    annee: Optional[str] = None,
) -> Optional[Path]:
    """Énoncé PDF d'un TD/TP/CC, None si introuvable.

    Conventions supportées :

    - TD/TP : ``COURS/{MAT}/{TYPE}/{TYPE}{num}/enonce_{TYPE}{num}_{MAT}.pdf``
    - CC flat : ``COURS/{MAT}/CC/enonce_CC{num}_{annee}_{MAT}.pdf``
    - CC nesté (style AN1) : ``COURS/{MAT}/CC/{annee}/CC{num}/enonce_CC{num}_{MAT}.pdf``
    - Ancienne convention minimaliste : ``enonce.pdf``
    """
    # Phase v15.7.32 : type libre, scan heuristique du dossier directement.
    # Phase v15.7.33 : quand num est un thème (ex `TP_Shannon`), priorise
    # `exos_{theme}.{pdf,md}` au top du dossier.
    # Phase v15.7.36.3 : fallback `annale_synthese` global **retiré** pour
    # types libres : l'annale est un Q&A (questions + corrections) mappé
    # vers `correction_paths`, **pas** un énoncé d'exercice séparé. Pour
    # un dossier de révision globale (PSI `_revision_CC2/`), il n'existe
    # généralement pas de fichier d'énoncé strict. Le tuteur s'appuie sur
    # `cm_poly_path = aide_memoire` (référence) + `correction_paths =
    # annale_synthese` (Q&A). `_build_session_context` côté app.py tolère
    # `enonce=None` pour les types libres (sans raise FileNotFoundError).
    free_dir = _get_free_type_dir(cours_root, matiere, type_code)
    if free_dir is not None:
        is_themed = num and num.lower() != "full"
        if is_themed:
            # exos_{theme}.{pdf,md} spécifique au thème, seulement si
            # un fichier de ce type existe vraiment (cas PSI exos_TP_Shannon).
            themed = _match_free_pdf_themed(
                free_dir, ("exos",),  # hint réduit à exos uniquement
                theme=num, exts=(".pdf", ".md"),
            )
            if themed is not None:
                return themed
        # Pas d'énoncé strict pour ce type libre : le caller doit tolérer.
        return None
    type_code = type_code.upper()
    matiere = matiere.upper()
    for folder in _candidate_exercise_folders(cours_root, matiere, type_code, num, annee):
        hit = _find_enonce_in_folder(folder, type_code, num, matiere, annee)
        if hit is not None:
            return hit
    return None


def _find_enonce_in_folder(
    folder: Path,
    type_code: str,
    num: str,
    matiere: str,
    annee: Optional[str],
) -> Optional[Path]:
    if not folder.is_dir():
        return None
    # CM : pas d'`enonce_*.pdf` mais on peut tenter le poly `cm_{mat}_{N}.pdf`
    # comme document de référence (le contenu du cours).
    if type_code.upper() == "CM":
        poly = folder / f"cm_{matiere.lower()}_{num}.pdf"
        if poly.is_file():
            return poly
        # Variantes éventuelles (cm_an1_7.pdf, cm_prg2_3.pdf, etc.)
        try:
            names = sorted((p.name for p in folder.iterdir() if p.is_file()))
        except OSError:
            names = []
        for name in names:
            low = name.lower()
            if not (low.startswith(f"cm_{matiere.lower()}_") and low.endswith(".pdf")):
                continue
            # Match strict du numéro pour éviter qu'un `cm_prg2_70.pdf` ne sorte
            # pour `num=7`.
            m = re.match(rf"^cm_{matiere.lower()}_({re.escape(num)})\.pdf$",
                         name, re.IGNORECASE)
            if m:
                return folder / name
        # Pas de poly → pas d'énoncé pour ce CM (acceptable, le script suffit).
        return None
    # 1. Nouvelle convention exacte avec annee
    if annee:
        exact = folder / f"enonce_{type_code}{num}_{annee}_{matiere}.pdf"
        if exact.is_file():
            return exact
    # 2. Nouvelle convention sans annee
    exact_no_annee = folder / f"enonce_{type_code}{num}_{matiere}.pdf"
    if exact_no_annee.is_file():
        return exact_no_annee
    # 3. Scan tolérant (CC flat, plusieurs millésimes côte à côte)
    try:
        names = sorted((p.name for p in folder.iterdir() if p.is_file()), reverse=True)
    except OSError:
        names = []
    for name in names:
        low = name.lower()
        if not (low.startswith("enonce_") and low.endswith(".pdf")):
            continue
        if f"{type_code.lower()}{num}" not in low:
            continue
        if matiere.lower() not in low:
            continue
        if annee and f"_{annee}_" not in name:
            continue
        return folder / name
    # 4. Ancienne convention minimaliste
    legacy = folder / "enonce.pdf"
    if legacy.is_file():
        return legacy
    return None


# ============================================================ Corrections

def resolve_corrections(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    exo: str,
    annee: Optional[str] = None,
    prefer_concat: bool = True,
) -> list[Path]:
    """Liste des corrigés officiels.

    - ``exo`` numérique (ex: ``"3"``) : retourne ``[correction_ex3]`` si trouvé.
    - ``exo == "full"`` :
        * TD/TP : retourne ``[concat_*.pdf]`` s'il existe, sinon **tous** les
          ``correction_*_ex*_*.pdf`` du dossier corrections.
        * CC : retourne ``[correction_CC{num}_{annee}_{MAT}.pdf]`` (global).
    - Liste vide si rien trouvé (le PromptBuilder skip alors la section).

    ``prefer_concat`` (défaut True) : pour ``exo='full'``, privilégie le concat
    global comme avant. Passer ``False`` pour forcer la liste des fichiers
    individuels (utile côté UI panneau Docs où on veut un item par exercice
    dans le picker (« Exercice 1 », « Exercice 2 », etc.) plutôt qu'un seul
    « Toutes les corrections » qui peut prêter à confusion vis-à-vis des
    entrées Énoncé / Script déjà présentes dans le picker.
    """
    # Phase v15.7.32 : type libre, scan heuristique des corrigés.
    # Phase v15.7.33 : pour un thème ciblé, on retourne TOUS les corrigés
    # du dossier (l'annale_synthese couvre tous les thèmes, mais on garde
    # le pattern d'éventuels `correction_{theme}.pdf` futurs en bonus).
    free_dir = _get_free_type_dir(cours_root, matiere, type_code)
    if free_dir is not None:
        return _scan_free_corrections(free_dir)
    type_code = type_code.upper()
    matiere = matiere.upper()
    folders = list(_candidate_exercise_folders(cours_root, matiere, type_code, num, annee))

    if exo == "full":
        return _collect_full_corrections(
            folders, type_code, num, matiere, annee, prefer_concat=prefer_concat
        )
    return _collect_single_correction(folders, type_code, num, exo, matiere, annee)


def _collect_single_correction(
    folders: list[Path],
    type_code: str,
    num: str,
    exo: str,
    matiere: str,
    annee: Optional[str],
) -> list[Path]:
    for folder in folders:
        for corr_dir in (folder / "corrections", folder):
            if not corr_dir.is_dir():
                continue
            hit = _match_correction_file(
                corr_dir, type_code, num, matiere, annee, exo=exo
            )
            if hit is not None:
                return [hit]
    return []


def _collect_full_corrections(
    folders: list[Path],
    type_code: str,
    num: str,
    matiere: str,
    annee: Optional[str],
    prefer_concat: bool = True,
) -> list[Path]:
    if prefer_concat:
        # Préférence : concat global. Cherché dans corrections/ d'abord (cas
        # AN1 réel), puis au niveau du dossier de l'exo (fallback).
        # Pour CC, le concat inclut l'année (`concat_CC{num}_{annee}_{MAT}.pdf`)
        # car plusieurs millésimes coexistent dans le même dossier corrections/.
        # On essaie d'abord la variante annee si fournie, puis fallback générique.
        concat_names: list[str] = []
        if type_code.upper() == "CC" and annee:
            concat_names.append(
                f"concat_{type_code}{num}_{annee}_{matiere}.pdf"
            )
        concat_names.append(_CONCAT_FILE_PATTERN.format(
            type=type_code, num=num, matiere=matiere
        ))
        for concat_name in concat_names:
            for folder in folders:
                for parent in (folder / "corrections", folder):
                    concat = parent / concat_name
                    if concat.is_file():
                        return [concat]
    # Sinon : tous les correction_*_ex*_*.pdf agrégés (TD/TP) ou le global CC
    results: list[Path] = []
    seen: set[Path] = set()
    for folder in folders:
        for corr_dir in (folder / "corrections", folder):
            if not corr_dir.is_dir():
                continue
            try:
                files = sorted(corr_dir.iterdir(), reverse=True)
            except OSError:
                continue
            for cand in files:
                if cand.suffix.lower() != ".pdf":
                    continue
                name = cand.name
                low = name.lower()
                if not low.startswith("correction_"):
                    continue
                if f"{type_code}{num}".lower() not in low:
                    continue
                if matiere.lower() not in low:
                    continue
                if annee and f"_{annee}_" not in name:
                    continue
                if cand in seen:
                    continue
                seen.add(cand)
                results.append(cand)
    if not prefer_concat:
        # Tri ASC par numéro d'exercice (Ex 1, 2, 3…) pour le picker UI.
        # Le scan interne utilise reverse=True donc les résultats arrivent
        # en ordre inverse, on remet à plat. Ex non détecté → fin de liste.
        def _exo_sort_key(p: Path) -> tuple[int, str]:
            m = re.search(r"_ex([\d-]+)", p.stem, re.IGNORECASE)
            if not m:
                return (10**6, p.stem)
            head = m.group(1).split("-")[0]
            try:
                return (int(head), p.stem)
            except ValueError:
                return (10**6, p.stem)
        results.sort(key=_exo_sort_key)
    return results


def _match_correction_file(
    corr_dir: Path,
    type_code: str,
    num: str,
    matiere: str,
    annee: Optional[str],
    exo: str,
) -> Optional[Path]:
    try:
        files = sorted(corr_dir.iterdir(), reverse=True)
    except OSError:
        return None
    target_ex = re.compile(rf"_ex{re.escape(exo)}(?:_|\.pdf$)", re.IGNORECASE)
    for cand in files:
        if cand.suffix.lower() != ".pdf":
            continue
        name = cand.name
        low = name.lower()
        if not low.startswith("correction_"):
            continue
        if f"{type_code}{num}".lower() not in low:
            continue
        if matiere.lower() not in low:
            continue
        if annee and f"_{annee}_" not in name:
            continue
        if not target_ex.search(name):
            continue
        return cand
    return None


# ============================================================ Matériel perso

def find_perso_tache(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    exo: str,
    annee: Optional[str] = None,
) -> Optional[Path]:
    """TACHE_*.md : préparation perso de l'exercice (raisonnement écrit).

    Conventions :
      - TD/TP : ``{MAT}/{TYPE}/{TYPE}{num}/TACHE_{MAT}_{TYPE}{num}_ex{exo}.md``
      - TD/TP exo='full' : ``concat_TACHE_{TYPE}{num}_{MAT}.md``
      - CC : ``{MAT}/CC/TACHE_{MAT}_CC{num}_{annee}.md``
    """
    type_code = type_code.upper()
    matiere = matiere.upper()
    for folder in _candidate_exercise_folders(cours_root, matiere, type_code, num, annee):
        if exo == "full":
            concat = folder / f"concat_TACHE_{type_code}{num}_{matiere}.md"
            if concat.is_file():
                return concat
        if type_code == "CC":
            # Niveau matiere/CC/, pas matiere/CC/{annee}/
            cc_root = cours_root / matiere / "CC"
            if annee:
                cand = cc_root / f"TACHE_{matiere}_CC{num}_{annee}.md"
                if cand.is_file():
                    return cand
            # Sans annee : prend la plus récente
            try:
                matches = sorted(
                    (p for p in cc_root.iterdir()
                     if p.name.startswith(f"TACHE_{matiere}_CC{num}_")
                     and p.suffix == ".md"),
                    reverse=True,
                )
            except OSError:
                matches = []
            if matches:
                return matches[0]
        else:
            cand = folder / f"TACHE_{matiere}_{type_code}{num}_ex{exo}.md"
            if cand.is_file():
                return cand
    return None


def find_perso_script_oral(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    annee: Optional[str] = None,
) -> Optional[Path]:
    """script_oral_*.txt : version TTS-ready, validée à la main.

    Pas de granularité par exo : un seul script global par TD/TP,
    par millésime pour les CC. On préfère l'extension ``.txt`` si elle
    existe (clean), sinon le ``SCRIPT_*.md`` source.
    """
    # Phase v15.7.32 : type libre, scan _find_free_script.
    # Phase v15.7.33 : filtrage par thème via `num` (`TP_Shannon` →
    # `script_oral_TP_Shannon.txt`). Si num=`full` ou None, comportement
    # historique (1ᵉʳ trouvé).
    free_dir = _get_free_type_dir(cours_root, matiere, type_code)
    if free_dir is not None:
        return _find_free_script(free_dir, (".txt", ".md"), theme=num)
    type_code = type_code.upper()
    matiere = matiere.upper()
    for folder in _candidate_exercise_folders(cours_root, matiere, type_code, num, annee):
        scripts = folder / "scripts_oraux"
        if not scripts.is_dir():
            continue
        # Priorité : script_oral_*.txt (préférer "transcription" sur "inference")
        prefer = ("transcription", "")
        for variant in prefer:
            for ext in (".txt", ".md"):
                hit = _scan_script_dir(scripts, matiere, type_code, num, annee, variant, ext)
                if hit is not None:
                    return hit
    return None


def _scan_script_dir(
    scripts_dir: Path,
    matiere: str,
    type_code: str,
    num: str,
    annee: Optional[str],
    variant: str,
    ext: str,
) -> Optional[Path]:
    try:
        names = sorted(p.name for p in scripts_dir.iterdir() if p.is_file())
    except OSError:
        return None
    target = f"{type_code.lower()}{num}"
    for name in names:
        low = name.lower()
        if not low.endswith(ext):
            continue
        if not (low.startswith("script_oral_") or low.startswith("script_")):
            continue
        if matiere.lower() not in low:
            continue
        if target not in low:
            continue
        if annee and f"_{annee}" not in name:
            continue
        if variant and variant not in low:
            continue
        return scripts_dir / name
    return None


def find_perso_script_md(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    annee: Optional[str] = None,
) -> Optional[Path]:
    """SCRIPT_*.md : source Feynman avec headers `## [SLIDE N]`.

    Spécifique au mode `guidé` qui parse les sections slide-par-slide
    (cf. ``script_parser.parse_script``). Ne renvoie PAS le ``.txt``
    extrait (qui n'a pas les headers SLIDE).

    Phase v15.7.36.7 : pour les **types libres** (`_revision_CC*`,
    `TP_recherche_docu`, etc.), scanne aussi `{free_dir}/scripts/` avec
    le pattern `SCRIPT_{theme}.md` où `theme = num`. Cas PSI
    `_revision_CC2/scripts/SCRIPT_Bit_information.md` régénéré
    2026-05-12 : sans ce scan, le mode guidé continuait à tomber en
    « lite » même après la régen propre.
    """
    # Phase v15.7.36.7 : types libres, scan direct du sous-dossier scripts/
    free_dir = _get_free_type_dir(cours_root, matiere, type_code)
    if free_dir is not None:
        for sub_name in ("scripts", "scripts_oraux"):
            sub = free_dir / sub_name
            if not sub.is_dir():
                continue
            # Cherche `SCRIPT_{num}.md` (matching exact par thème, casse
            # insensible). `num` est le thème pour les types libres.
            theme_lower = (num or "").lower()
            try:
                names = sorted(p.name for p in sub.iterdir() if p.is_file())
            except OSError:
                continue
            for name in names:
                low = name.lower()
                if not (low.startswith("script_") and low.endswith(".md")):
                    continue
                if not name.startswith("SCRIPT_"):  # uppercase strict §3
                    continue
                # Extract middle : `script_{theme}.md` → middle=theme
                middle = low[len("script_"):-len(".md")]
                if middle == theme_lower or theme_lower in middle:
                    return sub / name
        # Si on est dans un type libre, on ne tombe PAS dans la branche
        # canonique ci-dessous (qui matche par TYPE_CODE + num) : c'est
        # incompatible avec le naming `SCRIPT_{theme}.md` des types libres.
        return None

    # Branche canonique TD/TP/CC/CM : scan dans scripts_oraux/
    type_code = type_code.upper()
    matiere = matiere.upper()
    for folder in _candidate_exercise_folders(cours_root, matiere, type_code, num, annee):
        scripts = folder / "scripts_oraux"
        if not scripts.is_dir():
            continue
        prefer = ("transcription", "")
        for variant in prefer:
            hit = _scan_script_dir(scripts, matiere, type_code, num, annee, variant, ".md")
            if hit is not None:
                return hit
    return None


def find_perso_script_imprimable(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    annee: Optional[str] = None,
) -> Optional[Path]:
    """``script_imprimable_{MAT}_{TYPE}{N}.pdf`` : version PDF lisible du
    script oral, à afficher dans le panneau de lecture si pas de version
    imprimée à côté de soi.
    """
    # Phase v15.7.32 : type libre, heuristique nom imprimable / recopie.
    # Phase v15.7.33 : filtrage par thème (`script_imprimable_{theme}.pdf`).
    free_dir = _get_free_type_dir(cours_root, matiere, type_code)
    if free_dir is not None:
        is_themed = num and num.lower() != "full"
        # 1. Sous-dossier scripts/ (priorité, cas PSI _revision_CC2/)
        for sub_name in ("scripts", "scripts_oraux"):
            sub = free_dir / sub_name
            if is_themed:
                hit = _match_free_pdf_themed(
                    sub, _FREE_IMPRIMABLE_HINTS, theme=num,
                )
            else:
                hit = _match_free_pdf(sub, _FREE_IMPRIMABLE_HINTS)
            if hit is not None:
                return hit
        # 2. Fallback : PDF dans le dossier libre directement
        # (cas `aide_memoire_CC2_a4_recopie.pdf` au top de _revision_CC2/)
        if is_themed:
            hit = _match_free_pdf_themed(
                free_dir, _FREE_IMPRIMABLE_HINTS, theme=num,
            )
            if hit is not None:
                return hit
        return _match_free_pdf(free_dir, _FREE_IMPRIMABLE_HINTS)
    type_code = type_code.upper()
    matiere = matiere.upper()
    for folder in _candidate_exercise_folders(cours_root, matiere, type_code, num, annee):
        scripts = folder / "scripts_oraux"
        if not scripts.is_dir():
            continue
        try:
            names = sorted((p.name for p in scripts.iterdir() if p.is_file()), reverse=True)
        except OSError:
            continue
        target = f"{type_code.lower()}{num}"
        for name in names:
            low = name.lower()
            if not (low.startswith("script_imprimable_") and low.endswith(".pdf")):
                continue
            if matiere.lower() not in low:
                continue
            if target not in low:
                continue
            if annee and f"_{annee}" not in name:
                continue
            return scripts / name
    return None


def find_perso_slides_pdf(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    annee: Optional[str] = None,
) -> Optional[Path]:
    """slides_*.pdf : slides RoleplayOverlay. Mention seulement (pas extrait)."""
    # Phase v15.7.32 : type libre, heuristique slides.
    # Phase v15.7.33 : filtrage par thème (`slides_{theme}.pdf`). Priorité
    # sous-dossier scripts/. `pitch_oral_30s.pdf` n'est plus pris en
    # compte comme slides (c'est un pitch, hint retiré de _FREE_SLIDES_HINTS).
    free_dir = _get_free_type_dir(cours_root, matiere, type_code)
    if free_dir is not None:
        is_themed = num and num.lower() != "full"
        for sub_name in ("scripts", "scripts_oraux"):
            sub = free_dir / sub_name
            if is_themed:
                hit = _match_free_pdf_themed(
                    sub, _FREE_SLIDES_HINTS, theme=num,
                )
            else:
                hit = _match_free_pdf(sub, _FREE_SLIDES_HINTS)
            if hit is not None:
                return hit
        # Pas de slides au top du dossier libre par convention.
        return None
    type_code = type_code.upper()
    matiere = matiere.upper()
    for folder in _candidate_exercise_folders(cours_root, matiere, type_code, num, annee):
        scripts = folder / "scripts_oraux"
        if not scripts.is_dir():
            continue
        try:
            names = sorted((p.name for p in scripts.iterdir() if p.is_file()), reverse=True)
        except OSError:
            continue
        target = f"{type_code.lower()}{num}"
        for name in names:
            low = name.lower()
            if not (low.startswith("slides_") and low.endswith(".pdf")):
                continue
            if matiere.lower() not in low:
                continue
            if target not in low:
                continue
            if annee and f"_{annee}" not in name:
                continue
            return scripts / name
    return None


# ============================================================ Browser arbo (alimente la GUI)

#: Types canoniques scannés par les helpers list_*. PSI a parfois des numéros
#: textuels (SHANNON, SGF) : c'est géré naturellement par le tri _natural_key.
_BROWSER_KNOWN_TYPES = ("TD", "TP", "CC", "CM", "Quiz", "Examen")


def list_matieres(cours_root: Path) -> list[str]:
    """Sous-dossiers de COURS/ qui ressemblent à des codes matière (2-6
    caractères alphanumériques uppercase, ex AN1, EN1, PRG2, PSI, ISE).
    """
    if not cours_root.is_dir():
        return []
    out = []
    for p in cours_root.iterdir():
        if not p.is_dir():
            continue
        if re.match(r"^[A-Z][A-Z0-9]{1,5}$", p.name):
            out.append(p.name)
    return sorted(out)


def list_types_for_matiere(cours_root: Path, matiere: str) -> list[str]:
    """Types présents pour cette matière.

    Phase v15.7.32 : expose les **types libres** en plus des canoniques :
    tout sous-dossier de la matière qui contient au moins 1 PDF (récursif
    sur 2 niveaux) et qui n'est pas dans ``_EXCLUDED_TOP_DIRS``. Permet
    aux dossiers ad-hoc (PSI ``_revision_CC2/`` ``TP_recherche_docu/``)
    d'apparaître dans le combobox sans devoir hardcoder leur convention.

    L'ordre du retour : canoniques d'abord (TD/TP/CC/CM/Quiz/Examen),
    puis libres triés alphabétiquement.
    """
    base = cours_root / matiere
    if not base.is_dir():
        return []
    canon: list[str] = []
    free: list[str] = []
    for p in base.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if name in _EXCLUDED_TOP_DIRS:
            continue
        if name in _BROWSER_KNOWN_TYPES:
            canon.append(name)
        elif _has_pdf_recursive(p, max_depth=2):
            free.append(name)
    return sorted(canon) + sorted(free)


def list_nums_for_type(
    cours_root: Path,
    matiere: str,
    type_code: str,
) -> list[str]:
    """Numéros disponibles pour un (matière, type).

    - TD/TP/Quiz/Examen : sous-dossiers ``{TYPE}{num}/``.
    - CC flat (style EN1) : noms de fichiers ``enonce_CC{num}_{annee}_*.pdf``.
    - CC nesté (style AN1) : ``CC/{annee}/CC{num}/``.

    Tri naturel : ``"2"`` avant ``"10"``, et les codes textuels
    (``SHANNON``) après les numériques.
    """
    # Phase v15.7.32 : type libre, pas de notion canonique de num, le
    # dossier EST l'unité (`["full"]`).
    # Phase v15.7.33 : détection des **thèmes** dans les sous-dossiers
    # `scripts/` ou `scripts_oraux/`. Si le dossier libre agrège plusieurs
    # thèmes via `script_oral_{theme}.{txt,md}` (PSI `_revision_CC2/` a
    # 4 thèmes : Bit_information, RAID, TP_Shannon, USB), on les expose
    # comme nums. `full` reste premier de la liste (révision globale).
    if not _is_canonical_type(type_code):
        free_dir = _get_free_type_dir(cours_root, matiere, type_code)
        if free_dir is None:
            return []
        themes = _detect_themes_in_free_dir(free_dir)
        # 2 thèmes minimum pour les exposer (sinon c'est un dossier mono-
        # thématique, `full` suffit). 1 seul thème est exposé aussi pour
        # cohérence (l'user peut quand même cibler explicitement).
        if themes:
            return ["full"] + themes
        return ["full"]
    type_code = type_code.upper()
    base = cours_root / matiere / type_code
    if not base.is_dir():
        return []
    nums: set[str] = set()
    if type_code == "CC":
        for p in base.iterdir():
            if p.is_file():
                m = re.match(
                    r"^enonce_CC([A-Z0-9]+)_", p.name, re.IGNORECASE
                )
                if m:
                    nums.add(m.group(1).upper())
            elif p.is_dir() and re.match(r"^\d{4}-\d{2,4}$", p.name):
                for sub in p.iterdir():
                    if sub.is_dir():
                        m = re.match(
                            r"^CC([A-Z0-9]+)$", sub.name, re.IGNORECASE
                        )
                        if m:
                            nums.add(m.group(1).upper())
    elif type_code == "CM":
        # Les CMs sont à plat dans `{MAT}/CM/` : pas de dossier `CM{N}/`.
        # Les numéros disponibles s'extraient des fichiers eux-mêmes :
        #   - `scripts_oraux/SCRIPT_{MAT}_CM{N}.md` (script Feynman)
        #   - `scripts_oraux/slides_{MAT}_CM{N}.pdf` (slides Beamer)
        #   - `CM{N}_{MAT}_*.txt` (transcription)
        #   - `cm_{matiere_lower}_{N}.pdf` (poly)
        scripts_dir = base / "scripts_oraux"
        if scripts_dir.is_dir():
            for p in scripts_dir.iterdir():
                if not p.is_file():
                    continue
                m = re.match(
                    rf"^(?:SCRIPT|script_oral|script_imprimable|slides)_{matiere}_CM([A-Z0-9]+)",
                    p.name, re.IGNORECASE,
                )
                if m:
                    nums.add(m.group(1).upper())
        for p in base.iterdir():
            if not p.is_file():
                continue
            # Transcription : `CM{N}_{MAT}_DATE.txt`
            m = re.match(
                rf"^CM([A-Z0-9]+)_{matiere}_", p.name, re.IGNORECASE,
            )
            if m:
                nums.add(m.group(1).upper())
                continue
            # Poly : `cm_{matiere_lower}_{N}.pdf`
            m = re.match(
                rf"^cm_{matiere.lower()}_(\d+)\.pdf$", p.name, re.IGNORECASE,
            )
            if m:
                nums.add(m.group(1).upper())
    else:
        for p in base.iterdir():
            if not p.is_dir():
                continue
            m = re.match(
                rf"^{type_code}([A-Z0-9]+)$", p.name, re.IGNORECASE
            )
            if m:
                nums.add(m.group(1).upper())
    return sorted(nums, key=_natural_num_key)


def list_annees_for_cc(
    cours_root: Path,
    matiere: str,
    num: str,
    type_code: Optional[str] = None,
) -> list[str]:
    """Millésimes disponibles pour un CC (vide pour TD/TP).

    Phase v15.7.32 : accepte ``type_code`` optionnel pour gérer les types
    libres (`_revision_CC*`, etc.) qui n'ont pas de millésime. Si fourni
    et non-canonique, retourne ``[]`` sans erreur.
    """
    if type_code is not None and not _is_canonical_type(type_code):
        return []
    base = cours_root / matiere / "CC"
    if not base.is_dir():
        return []
    annees: set[str] = set()
    annee_re = re.compile(
        rf"^enonce_CC{re.escape(num)}_(\d{{4}}-\d{{2,4}})_", re.IGNORECASE
    )
    for p in base.iterdir():
        if p.is_file():
            m = annee_re.match(p.name)
            if m:
                annees.add(m.group(1))
        elif p.is_dir() and re.match(r"^\d{4}-\d{2,4}$", p.name):
            sub = p / f"CC{num}"
            if sub.is_dir():
                annees.add(p.name)
    return sorted(annees, reverse=True)


def list_exos_for_num(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    annee: Optional[str] = None,
) -> list[str]:
    """Exos disponibles. Toujours préfixé de ``"full"``.

    - CC : généralement ``["full"]`` seul (pas de découpage par exo).
    - TD/TP : scan ``corrections/correction_*_ex*_*.pdf`` + ``TACHE_*_ex*.md``
      pour récupérer les numéros qui ont **soit** un corrigé **soit** une
      TACHE perso. Tri numérique croissant.
    """
    # Phase v15.7.32 : type libre, un seul "exo" (full). Le dossier EST
    # l'unité pédagogique.
    if not _is_canonical_type(type_code):
        return ["full"]
    type_code = type_code.upper()
    out: list[str] = ["full"]
    if type_code in ("CC", "CM"):
        # CC : pas de découpage par exo (le sujet est unique).
        # CM : pas de notion d'exo (cours magistral global).
        return out

    folder = cours_root / matiere / type_code / f"{type_code}{num}"
    if not folder.is_dir():
        return out
    exos: set[str] = set()

    corr_dir = folder / "corrections"
    if corr_dir.is_dir():
        corr_re = re.compile(
            rf"^correction_{type_code}{re.escape(num)}_ex(\d+)_",
            re.IGNORECASE,
        )
        for p in corr_dir.iterdir():
            if p.is_file():
                m = corr_re.match(p.name)
                if m:
                    exos.add(m.group(1))

    tache_re = re.compile(
        rf"^TACHE_{matiere}_{type_code}{re.escape(num)}_ex(\d+)\.md$",
        re.IGNORECASE,
    )
    for p in folder.iterdir():
        if p.is_file():
            m = tache_re.match(p.name)
            if m:
                exos.add(m.group(1))

    out.extend(sorted(exos, key=lambda e: int(e)))
    return out


def _natural_num_key(s: str):
    """Tri : numériques avant textuels, dans l'ordre naturel."""
    if s.isdigit():
        return (0, int(s), s)
    return (1, 0, s)


# ============================================================ Internes : dossiers candidats

def _candidate_exercise_folders(
    cours_root: Path,
    matiere: str,
    type_code: str,
    num: str,
    annee: Optional[str],
):
    """Yields les dossiers où chercher l'énoncé / corrections / perso pour cet exo.

    Couvre les 2 conventions CC (flat à la EN1, nesté par millésime à la AN1).
    """
    if type_code in ("TD", "TP"):
        yield cours_root / matiere / type_code / f"{type_code}{num}"
        return
    if type_code == "CM":
        # CM : pas de sous-dossier `CM{N}/`, tout est à plat dans `{MAT}/CM/`.
        # Le numéro `num` n'est utilisé que dans les noms de fichiers
        # (`SCRIPT_{MAT}_CM{N}.md`, `slides_{MAT}_CM{N}.pdf`, `cm_*_{N}.pdf`).
        yield cours_root / matiere / "CM"
        return
    if type_code == "CC":
        # Style nesté
        if annee:
            yield cours_root / matiere / "CC" / annee / f"CC{num}"
        else:
            cc_root = cours_root / matiere / "CC"
            if cc_root.is_dir():
                try:
                    for entry in sorted(cc_root.iterdir(), reverse=True):
                        if entry.is_dir() and re.match(r"^\d{4}-\d{2,4}$", entry.name):
                            sub = entry / f"CC{num}"
                            if sub.is_dir():
                                yield sub
                except OSError:
                    pass
        # Style flat
        yield cours_root / matiere / "CC"
        return
    # Quiz / Examen / autre : fallback générique
    yield cours_root / matiere / type_code / f"{type_code}{num}"
