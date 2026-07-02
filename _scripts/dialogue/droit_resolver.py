"""
droit_resolver.py : résolution des chemins dans l'arbo DROIT/ (projet Cartable).

Pendant **simple** de ``cours_resolver.py`` pour le contenu produit par Cartable
(études de Droit). L'arbo COURS (L1 Info) est PDF/code-centrée (TD/TP/CC, énoncé +
corrigé officiel + exo numérotés) ; l'arbo DROIT est markdown-centrée et bien plus
plate : par matière, des transcriptions de CM/TD et des fiches de révision, plus
de la méthodo et des fiches d'arrêt. Pas de « corrigé officiel », pas de numéro
d'exercice, pas de millésime.

Arbo cible (cf. Cartable/_handoff/01_ARCHITECTURE.md) ::

    DROIT/
        <slug>/                       # ex: droit-personnes, constit1
            CM/audio/                 # .m4a/.mp3 (non lus ici)
            CM/transcriptions/        # CM{n}_<slug>_<JJMM>.txt
            CM/fiches/                # fiche_CM{n}_<slug>_<JJMM>.md
            TD/                        # TD{n}_<slug>_<JJMM>.txt + fiche_TD{n}_*.md
            methodo/                   # méthodo propre à la matière
            arrets/                    # fiches d'arrêt / jurisprudence
        _methodo/                      # supports de méthodo TRANSVERSES (methodo_<type>.md)

Conventions de nommage (mêmes que Cartable, slug à tirets, `_` sépare les champs) :
    transcription : ``<CM|TD><num>_<slug>_<JJMM>.txt``
    fiche         : ``fiche_<CM|TD><num>_<slug>_<JJMM>.md``

Ce module est **autonome** : il lit le disque (les slugs SONT les noms de dossiers),
sans dépendre du registre `matieres.py` de Cartable ni d'aucun import croisé.

Statut : module additif, prêt à être câblé. Voir le handoff d'intégration côté
Cartable (`_handoff/04_INTEGRATION_COMPAGNON.md`) pour les étapes restantes
(config CARTABLE_ROOT, sélecteur GUI, prompt_builder) à faire en session supervisée.
"""

import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================ Conventions

#: Dossiers de DROIT/ qui ne sont pas des matières (transverses / techniques).
_NON_MATIERE_DIRS = frozenset({"_methodo", "_inbox", "_archives"})

#: Types canoniques d'un cours de droit. Pas de TP/CC/exo comme en Info.
_KNOWN_TYPES = ("CM", "TD")

#: Transcription : CM3_droit-personnes_1509.txt → (type=CM, num=3)
_TRANSCRIPT_RE = re.compile(r"^(?P<type>CM|TD)(?P<num>\d+)_", re.IGNORECASE)

#: Fiche : fiche_CM3_droit-personnes_1509.md → (type=CM, num=3)
_FICHE_RE = re.compile(r"^fiche_(?P<type>CM|TD)(?P<num>\d+)_", re.IGNORECASE)


# ============================================================ Navigation matières

def list_matieres(droit_root: Path) -> list[str]:
    """Slugs des matières présentes dans ``DROIT/`` (noms de sous-dossiers).

    Exclut les dossiers transverses (`_methodo`, `_inbox`...) et tout dossier
    commençant par `_` ou `.`. Tri alphabétique.
    """
    if not droit_root.is_dir():
        return []
    out = []
    for p in droit_root.iterdir():
        if not p.is_dir():
            continue
        if p.name in _NON_MATIERE_DIRS or p.name.startswith((".", "_")):
            continue
        out.append(p.name)
    return sorted(out)


def list_types_for_matiere(droit_root: Path, slug: str) -> list[str]:
    """Types disponibles pour une matière : ``["CM"]`` ou ``["CM", "TD"]``.

    Un type n'est exposé que s'il contient effectivement du matériel
    (transcription ou fiche). Une matière a toujours au moins du CM si le
    dossier existe ; le TD n'apparaît que pour les majeures qui en ont.
    """
    base = droit_root / slug
    if not base.is_dir():
        return []
    out = []
    if _has_material(base / "CM"):
        out.append("CM")
    if _has_material(base / "TD"):
        out.append("TD")
    return out


def list_nums_for_type(droit_root: Path, slug: str, type_code: str) -> list[str]:
    """Numéros de séance disponibles pour un (matière, type), tri numérique.

    Les numéros sont extraits des noms de fichiers (transcriptions ET fiches),
    de sorte qu'une séance apparaisse même si seule la fiche ou seule la
    transcription existe.
    """
    type_code = type_code.upper()
    nums: set[str] = set()
    for folder, regex in _material_dirs(droit_root, slug, type_code):
        if not folder.is_dir():
            continue
        for f in folder.iterdir():
            if not f.is_file():
                continue
            m = regex.match(f.name)
            if m and m.group("type").upper() == type_code:
                nums.add(m.group("num"))
    return sorted(nums, key=lambda n: (int(n) if n.isdigit() else 10**6, n))


# ============================================================ Résolution fichiers

def find_transcription(
    droit_root: Path, slug: str, type_code: str, num: str,
) -> Optional[Path]:
    """Transcription ``.txt`` d'un CM/TD donné, None si introuvable.

    Pour CM : ``DROIT/<slug>/CM/transcriptions/<TYPE><num>_*.txt``.
    Pour TD : ``DROIT/<slug>/TD/<TYPE><num>_*.txt``.
    """
    type_code = type_code.upper()
    folder = _transcript_dir(droit_root, slug, type_code)
    return _match_num(folder, _TRANSCRIPT_RE, type_code, num, ".txt")


def find_fiche(
    droit_root: Path, slug: str, type_code: str, num: str,
) -> Optional[Path]:
    """Fiche de révision ``.md`` d'un CM/TD donné, None si introuvable.

    Pour CM : ``DROIT/<slug>/CM/fiches/fiche_<TYPE><num>_*.md``.
    Pour TD : ``DROIT/<slug>/TD/fiche_<TYPE><num>_*.md``.
    """
    type_code = type_code.upper()
    folder = _fiche_dir(droit_root, slug, type_code)
    return _match_num(folder, _FICHE_RE, type_code, num, ".md")


def list_arrets(droit_root: Path, slug: str) -> list[Path]:
    """Fiches d'arrêt / jurisprudence d'une matière (``arrets/``), triées."""
    return _list_files(droit_root / slug / "arrets", (".md", ".txt", ".pdf"))


def list_methodo_matiere(droit_root: Path, slug: str) -> list[Path]:
    """Supports de méthodo propres à une matière (``<slug>/methodo/``)."""
    return _list_files(droit_root / slug / "methodo", (".md", ".txt", ".pdf"))


def list_methodo_transverse(droit_root: Path) -> list[Path]:
    """Supports de méthodo transverses (``DROIT/_methodo/methodo_*.md``).

    Produits par `methodo.py` côté Cartable (dissertation, commentaire d'arrêt,
    fiche d'arrêt, cas pratique, consultation).
    """
    return _list_files(droit_root / "_methodo", (".md",))


# ============================================================ Internes

def _has_material(folder: Path) -> bool:
    """True si ``folder`` (CM/ ou TD/) contient au moins une transcription ou
    fiche, en cherchant aussi dans les sous-dossiers ``transcriptions``/``fiches``."""
    if not folder.is_dir():
        return False
    for sub in (folder, folder / "transcriptions", folder / "fiches"):
        if not sub.is_dir():
            continue
        for f in sub.iterdir():
            if f.is_file() and (
                _TRANSCRIPT_RE.match(f.name) or _FICHE_RE.match(f.name)
            ):
                return True
    return False


def _transcript_dir(droit_root: Path, slug: str, type_code: str) -> Path:
    """Dossier des transcriptions : CM/transcriptions/ ou TD/ (plat)."""
    if type_code == "CM":
        return droit_root / slug / "CM" / "transcriptions"
    return droit_root / slug / "TD"


def _fiche_dir(droit_root: Path, slug: str, type_code: str) -> Path:
    """Dossier des fiches : CM/fiches/ ou TD/ (plat)."""
    if type_code == "CM":
        return droit_root / slug / "CM" / "fiches"
    return droit_root / slug / "TD"


def _material_dirs(droit_root: Path, slug: str, type_code: str):
    """Yields (dossier, regex) où chercher des numéros pour ce (matière, type)."""
    yield _transcript_dir(droit_root, slug, type_code), _TRANSCRIPT_RE
    yield _fiche_dir(droit_root, slug, type_code), _FICHE_RE


def _match_num(
    folder: Path, regex: re.Pattern, type_code: str, num: str, ext: str,
) -> Optional[Path]:
    """1er fichier de ``folder`` dont le nom matche ``regex`` avec le bon type et
    num, et la bonne extension. Tri inverse → préfère le nom le plus récent."""
    if not folder.is_dir():
        return None
    try:
        names = sorted((p.name for p in folder.iterdir() if p.is_file()), reverse=True)
    except OSError:
        return None
    for name in names:
        if not name.lower().endswith(ext):
            continue
        m = regex.match(name)
        if m and m.group("type").upper() == type_code and m.group("num") == num:
            return folder / name
    return None


def _list_files(folder: Path, exts: tuple[str, ...]) -> list[Path]:
    """Fichiers de ``folder`` avec une des extensions, triés par nom (ignore
    les `.gitkeep`)."""
    if not folder.is_dir():
        return []
    exts_lower = tuple(e.lower() for e in exts)
    try:
        items = sorted(folder.iterdir())
    except OSError:
        return []
    return [
        p for p in items
        if p.is_file() and p.suffix.lower() in exts_lower and p.name != ".gitkeep"
    ]
