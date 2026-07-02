"""
test_cours_resolver.py : couverture des helpers d'arbo COURS.

Lance avec :
    python -m unittest tests.test_cours_resolver
"""

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

# Path setup
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "_scripts"
DIALOGUE = SCRIPTS / "dialogue"
for _p in (str(ROOT), str(SCRIPTS), str(DIALOGUE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from cours_resolver import (  # noqa: E402
    find_enonce_pdf,
    find_perso_script_oral,
    find_perso_slides_pdf,
    find_perso_tache,
    list_annees_for_cc,
    list_exos_for_num,
    list_matieres,
    list_nums_for_type,
    list_types_for_matiere,
    resolve_corrections,
)


def touch(path: Path, content: bytes = b"") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class TestCoursResolverTD(unittest.TestCase):
    """Cas TD : un dossier par TD, corrections par exo, TACHE par exo."""

    def setUp(self):
        self._tmpobj = TemporaryDirectory()
        self.cours = Path(self._tmpobj.name)
        td5 = self.cours / "AN1" / "TD" / "TD5"
        # Énoncé + corrections par exo + TACHE + scripts_oraux
        touch(td5 / "enonce_TD5_AN1.pdf")
        touch(td5 / "corrections" / "correction_TD5_ex3_AN1.pdf")
        touch(td5 / "corrections" / "correction_TD5_ex4_AN1.pdf")
        touch(td5 / "TACHE_AN1_TD5_ex3.md", b"# Ma TACHE ex3")
        touch(td5 / "TACHE_AN1_TD5_ex4.md")
        touch(td5 / "scripts_oraux" / "script_oral_AN1_TD5_global_transcription.txt", b"script")
        touch(td5 / "scripts_oraux" / "slides_AN1_TD5_global_transcription.pdf")
        # Concat global pour le mode 'full'
        touch(td5 / "concat_TD5_AN1.pdf")
        touch(td5 / "concat_TACHE_TD5_AN1.md", b"# Concat TACHE")

    def tearDown(self):
        self._tmpobj.cleanup()

    def test_enonce_td(self):
        hit = find_enonce_pdf(self.cours, "AN1", "TD", "5")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.name, "enonce_TD5_AN1.pdf")

    def test_correction_single_exo(self):
        paths = resolve_corrections(self.cours, "AN1", "TD", "5", "3")
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].name, "correction_TD5_ex3_AN1.pdf")

    def test_correction_unknown_exo_returns_empty(self):
        paths = resolve_corrections(self.cours, "AN1", "TD", "5", "99")
        self.assertEqual(paths, [])

    def test_correction_full_prefers_concat(self):
        paths = resolve_corrections(self.cours, "AN1", "TD", "5", "full")
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].name, "concat_TD5_AN1.pdf")

    def test_correction_full_falls_back_to_individuals(self):
        (self.cours / "AN1" / "TD" / "TD5" / "concat_TD5_AN1.pdf").unlink()
        paths = resolve_corrections(self.cours, "AN1", "TD", "5", "full")
        self.assertEqual(len(paths), 2)
        names = {p.name for p in paths}
        self.assertEqual(
            names,
            {"correction_TD5_ex3_AN1.pdf", "correction_TD5_ex4_AN1.pdf"},
        )

    def test_tache_per_exo(self):
        hit = find_perso_tache(self.cours, "AN1", "TD", "5", "3")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.name, "TACHE_AN1_TD5_ex3.md")

    def test_tache_full_concat(self):
        hit = find_perso_tache(self.cours, "AN1", "TD", "5", "full")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.name, "concat_TACHE_TD5_AN1.md")

    def test_script_oral_picks_transcription_variant(self):
        # Ajout d'un variant inference plus récent ; le resolver doit garder
        # le transcription (validé à la main).
        td5 = self.cours / "AN1" / "TD" / "TD5"
        touch(td5 / "scripts_oraux" / "script_oral_AN1_TD5_global_inference.txt")
        hit = find_perso_script_oral(self.cours, "AN1", "TD", "5")
        self.assertIsNotNone(hit)
        self.assertIn("transcription", hit.name)

    def test_slides_pdf(self):
        hit = find_perso_slides_pdf(self.cours, "AN1", "TD", "5")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.suffix, ".pdf")
        self.assertTrue(hit.name.startswith("slides_AN1_TD5"))


class TestCoursResolverCC(unittest.TestCase):
    """Cas CC flat (style EN1) : tous les millésimes côte à côte."""

    def setUp(self):
        self._tmpobj = TemporaryDirectory()
        self.cours = Path(self._tmpobj.name)
        cc = self.cours / "EN1" / "CC"
        # 3 millésimes pour CC1 + 1 pour CC2
        for annee in ("2023-24", "2024-25", "2025-26"):
            touch(cc / f"enonce_CC1_{annee}_EN1.pdf")
            touch(cc / "corrections" / f"correction_CC1_{annee}_EN1.pdf")
            touch(cc / f"TACHE_EN1_CC1_{annee}.md", f"# TACHE {annee}".encode())
        touch(cc / "enonce_CC2_2023-24_EN1.pdf")
        touch(cc / "corrections" / "correction_CC2_2023-24_EN1.pdf")
        touch(cc / "scripts_oraux" / "script_oral_EN1_CC1_2025-26.txt")

    def tearDown(self):
        self._tmpobj.cleanup()

    def test_enonce_cc_with_annee(self):
        hit = find_enonce_pdf(self.cours, "EN1", "CC", "1", "2024-25")
        self.assertIsNotNone(hit)
        self.assertIn("2024-25", hit.name)

    def test_correction_cc_with_annee(self):
        paths = resolve_corrections(self.cours, "EN1", "CC", "1", "full", "2024-25")
        self.assertEqual(len(paths), 1)
        self.assertIn("2024-25", paths[0].name)

    def test_correction_cc_wrong_annee_empty(self):
        paths = resolve_corrections(self.cours, "EN1", "CC", "1", "full", "9999-99")
        self.assertEqual(paths, [])

    def test_tache_cc_per_annee(self):
        hit = find_perso_tache(self.cours, "EN1", "CC", "1", "full", "2025-26")
        self.assertIsNotNone(hit)
        self.assertIn("2025-26", hit.name)

    def test_script_oral_cc_with_annee(self):
        hit = find_perso_script_oral(self.cours, "EN1", "CC", "1", "2025-26")
        self.assertIsNotNone(hit)
        self.assertIn("2025-26", hit.name)


class TestCoursResolverEdgeCases(unittest.TestCase):

    def setUp(self):
        self._tmpobj = TemporaryDirectory()
        self.cours = Path(self._tmpobj.name)

    def tearDown(self):
        self._tmpobj.cleanup()

    def test_no_arbo_returns_none_or_empty(self):
        # Aucun fichier : tous les helpers doivent retourner None ou [].
        self.assertIsNone(find_enonce_pdf(self.cours, "AN1", "TD", "5"))
        self.assertEqual(resolve_corrections(self.cours, "AN1", "TD", "5", "3"), [])
        self.assertIsNone(find_perso_tache(self.cours, "AN1", "TD", "5", "3"))
        self.assertIsNone(find_perso_script_oral(self.cours, "AN1", "TD", "5"))
        self.assertIsNone(find_perso_slides_pdf(self.cours, "AN1", "TD", "5"))

    def test_legacy_enonce_pdf(self):
        td = self.cours / "AN1" / "TD" / "TD9"
        touch(td / "enonce.pdf")
        hit = find_enonce_pdf(self.cours, "AN1", "TD", "9")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.name, "enonce.pdf")


class TestCoursResolverBrowser(unittest.TestCase):
    """Helpers list_* qui alimentent la GUI."""

    def setUp(self):
        self._tmpobj = TemporaryDirectory()
        self.cours = Path(self._tmpobj.name)
        # AN1 avec TD1, TD5, TP2 + CC1 nesté
        for td in ("TD1", "TD5"):
            touch(self.cours / "AN1" / "TD" / td / f"enonce_{td}_AN1.pdf")
        touch(self.cours / "AN1" / "TD" / "TD5" / "corrections" / "correction_TD5_ex3_AN1.pdf")
        touch(self.cours / "AN1" / "TD" / "TD5" / "corrections" / "correction_TD5_ex5_AN1.pdf")
        touch(self.cours / "AN1" / "TD" / "TD5" / "corrections" / "correction_TD5_ex10_AN1.pdf")
        touch(self.cours / "AN1" / "TD" / "TD5" / "TACHE_AN1_TD5_ex7.md")
        touch(self.cours / "AN1" / "TP" / "TP2" / "enonce_TP2_AN1.pdf")
        touch(self.cours / "AN1" / "CC" / "2024-25" / "CC1" / "enonce_CC1_AN1.pdf")
        touch(self.cours / "AN1" / "CC" / "2025-26" / "CC1" / "enonce_CC1_AN1.pdf")
        # EN1 avec CC flat (3 millésimes pour CC1, 1 pour CC2)
        for annee in ("2023-24", "2024-25", "2025-26"):
            touch(self.cours / "EN1" / "CC" / f"enonce_CC1_{annee}_EN1.pdf")
        touch(self.cours / "EN1" / "CC" / "enonce_CC2_2023-24_EN1.pdf")
        # PSI avec un num textuel
        touch(self.cours / "PSI" / "TD" / "TDSHANNON" / "enonce_TDSHANNON_PSI.pdf")
        # Bruit qui ne doit pas être pris pour une matière
        (self.cours / "z_archive").mkdir()
        (self.cours / "_INBOX").mkdir()

    def tearDown(self):
        self._tmpobj.cleanup()

    def test_list_matieres(self):
        out = list_matieres(self.cours)
        self.assertEqual(out, ["AN1", "EN1", "PSI"])

    def test_list_matieres_missing_root(self):
        self.assertEqual(list_matieres(self.cours / "ghost"), [])

    def test_list_types_for_matiere_an1(self):
        out = list_types_for_matiere(self.cours, "AN1")
        self.assertEqual(out, ["CC", "TD", "TP"])

    def test_list_types_for_matiere_en1(self):
        out = list_types_for_matiere(self.cours, "EN1")
        self.assertEqual(out, ["CC"])

    def test_list_nums_for_type_td_natural_sort(self):
        # AN1 TD : TD1, TD5 (numériques croissants), tri naturel pas lexical
        out = list_nums_for_type(self.cours, "AN1", "TD")
        self.assertEqual(out, ["1", "5"])

    def test_list_nums_for_type_cc_flat(self):
        # EN1 CC : CC1 et CC2 via filenames
        out = list_nums_for_type(self.cours, "EN1", "CC")
        self.assertEqual(out, ["1", "2"])

    def test_list_nums_for_type_cc_nested(self):
        # AN1 CC : CC1 via sous-dossiers de millésime
        out = list_nums_for_type(self.cours, "AN1", "CC")
        self.assertEqual(out, ["1"])

    def test_list_nums_for_type_psi_textual(self):
        out = list_nums_for_type(self.cours, "PSI", "TD")
        self.assertEqual(out, ["SHANNON"])

    def test_list_nums_for_type_unknown(self):
        self.assertEqual(list_nums_for_type(self.cours, "AN1", "Quiz"), [])

    def test_list_annees_for_cc_flat(self):
        # EN1 CC1 : 3 millésimes, ordre desc
        out = list_annees_for_cc(self.cours, "EN1", "1")
        self.assertEqual(out, ["2025-26", "2024-25", "2023-24"])

    def test_list_annees_for_cc_nested(self):
        out = list_annees_for_cc(self.cours, "AN1", "1")
        self.assertEqual(out, ["2025-26", "2024-25"])

    def test_list_annees_for_cc_other_num(self):
        # CC2 EN1 n'a qu'un millésime
        out = list_annees_for_cc(self.cours, "EN1", "2")
        self.assertEqual(out, ["2023-24"])

    def test_list_exos_for_num_td(self):
        # AN1 TD5 : ex3, ex5, ex10 via correction + ex7 via TACHE
        out = list_exos_for_num(self.cours, "AN1", "TD", "5")
        self.assertEqual(out[0], "full")
        self.assertEqual(out[1:], ["3", "5", "7", "10"])

    def test_list_exos_for_num_cc_always_full(self):
        # CC : pas de découpage par exo, juste full
        out = list_exos_for_num(self.cours, "EN1", "CC", "1", "2024-25")
        self.assertEqual(out, ["full"])

    def test_list_exos_for_num_no_corrections(self):
        # TP2 AN1 sans corrections ni TACHE → juste 'full'
        out = list_exos_for_num(self.cours, "AN1", "TP", "2")
        self.assertEqual(out, ["full"])


class TestFreeTypeBrowse(unittest.TestCase):
    """Phase v15.7.32 : types libres (scan générique).

    Cas réels PSI : ``_revision_CC1/`` (que .md), ``_revision_CC2/``
    (.pdf prioritaires), ``TP_recherche_docu/``. Le scanner doit exposer
    ces dossiers dans list_types_for_matiere et le resolver doit y
    trouver énoncé/corrigé/script heuristiquement.
    """

    def setUp(self):
        self._tmpobj = TemporaryDirectory()
        self.cours = Path(self._tmpobj.name)
        # Setup PSI-like structure
        psi = self.cours / "PSI"
        # Canonical type avec sous-dossier (sera détecté)
        touch(psi / "TD" / "TD1" / "enonce_TD1_PSI.pdf")
        # Type libre `_revision_CC2` avec PDFs
        touch(psi / "_revision_CC2" / "aide_memoire_CC2.pdf")
        touch(psi / "_revision_CC2" / "aide_memoire_CC2_a4_recopie.pdf")
        touch(psi / "_revision_CC2" / "annale_synthese_CC2.pdf")
        touch(psi / "_revision_CC2" / "pitch_oral_30s.pdf")
        touch(psi / "_revision_CC2" / "scripts" / "script_oral_Bit.txt")
        # Type libre `_revision_CC1` avec QUE des .md (pas encore compilés)
        touch(psi / "_revision_CC1" / "aide_memoire_CC1.md", "# Aide-memoire CC1\nContenu...".encode("utf-8"))
        touch(psi / "_revision_CC1" / "annale_synthese_CC1.md", "# Annale CC1".encode("utf-8"))
        # Type libre `TP_recherche_docu` avec PDF
        touch(psi / "TP_recherche_docu" / "sujet_recherche.pdf")
        # Dossier technique exclu
        touch(psi / "_moodle" / "stuff.pdf")
        # Dossier vide sans PDF (sera exclu de types)
        (psi / "_archives").mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self._tmpobj.cleanup()

    def test_list_types_includes_free_dirs_with_material(self):
        types = list_types_for_matiere(self.cours, "PSI")
        self.assertIn("TD", types)
        self.assertIn("_revision_CC1", types)  # que .md → matche aussi
        self.assertIn("_revision_CC2", types)
        self.assertIn("TP_recherche_docu", types)

    def test_list_types_excludes_technical_dirs(self):
        types = list_types_for_matiere(self.cours, "PSI")
        self.assertNotIn("_moodle", types)  # exclu via _EXCLUDED_TOP_DIRS
        self.assertNotIn("_archives", types)  # vide

    def test_list_types_canonical_first(self):
        types = list_types_for_matiere(self.cours, "PSI")
        # Canonical (TD) doit venir avant les libres
        td_idx = types.index("TD")
        rev1_idx = types.index("_revision_CC1")
        self.assertLess(td_idx, rev1_idx)

    def test_list_nums_for_free_type_includes_themes(self):
        """Phase v15.7.33 : list_nums retourne full + thèmes détectés.

        Le setUp crée `scripts/script_oral_Bit.txt` (1 thème), donc
        nums = ['full', 'Bit'].
        """
        nums = list_nums_for_type(self.cours, "PSI", "_revision_CC2")
        self.assertEqual(nums, ["full", "Bit"])

    def test_list_nums_for_unknown_free_type_returns_empty(self):
        # Type libre qui n'existe pas → []
        nums = list_nums_for_type(self.cours, "PSI", "_fake_dir")
        self.assertEqual(nums, [])

    def test_list_exos_for_free_type_returns_full(self):
        out = list_exos_for_num(self.cours, "PSI", "_revision_CC2", "full", None)
        self.assertEqual(out, ["full"])

    def test_list_annees_for_free_type_returns_empty(self):
        out = list_annees_for_cc(self.cours, "PSI", "full", type_code="_revision_CC2")
        self.assertEqual(out, [])

    def test_find_enonce_returns_none_for_free_type_full(self):
        """Phase v15.7.36.3 : pour un type libre en mode `full`, pas
        d'énoncé strict (l'annale_synthese est mappée vers correction_paths,
        pas vers enonce_path). Évite le doublon Énoncé/Corrigé dans le
        picker Docs et le faux énoncé dans le prompt initial.
        """
        enonce = find_enonce_pdf(self.cours, "PSI", "_revision_CC2", "full", None)
        self.assertIsNone(enonce)

    def test_find_enonce_none_for_free_type_md_only(self):
        """`_revision_CC1/` n'a que des .md, et même comme ça pas d'énoncé
        strict : l'annale_synthese.md va dans corrections, pas dans
        enonce_path.
        """
        enonce = find_enonce_pdf(self.cours, "PSI", "_revision_CC1", "full", None)
        self.assertIsNone(enonce)

    def test_find_free_poly_returns_aide_memoire(self):
        """Phase v15.7.33 : find_free_poly retourne aide_memoire (cheat sheet)
        comme poly CM, séparé de l'énoncé.
        """
        from cours_resolver import find_free_poly
        poly = find_free_poly(self.cours, "PSI", "_revision_CC2")
        self.assertIsNotNone(poly)
        self.assertIn("aide_memoire", poly.name.lower())

    def test_resolve_corrections_finds_annale_synthese(self):
        corrs = resolve_corrections(
            self.cours, "PSI", "_revision_CC2", "full", "full", None,
        )
        self.assertEqual(len(corrs), 1)
        self.assertIn("annale_synthese", corrs[0].name.lower())

    def test_resolve_corrections_md_fallback(self):
        """`_revision_CC1/` que des .md → annale_synthese.md retournée."""
        corrs = resolve_corrections(
            self.cours, "PSI", "_revision_CC1", "full", "full", None,
        )
        self.assertEqual(len(corrs), 1)
        self.assertTrue(corrs[0].name.endswith(".md"))

    def test_find_script_oral_in_scripts_subdir(self):
        script = find_perso_script_oral(
            self.cours, "PSI", "_revision_CC2", "full", None,
        )
        self.assertIsNotNone(script)
        self.assertIn("script_oral", script.name.lower())

    def test_find_script_oral_filters_by_theme(self):
        """Phase v15.7.33 : num=`Bit` ramène `script_oral_Bit.txt` seulement.

        Le setUp crée `script_oral_Bit.txt`. Si on en avait plusieurs
        (Bit + RAID), num='RAID' ramènerait `script_oral_RAID.txt`.
        """
        # Ajoute un 2e thème pour démontrer le filtrage
        touch(self.cours / "PSI" / "_revision_CC2" / "scripts" / "script_oral_RAID.txt")
        script = find_perso_script_oral(
            self.cours, "PSI", "_revision_CC2", "Bit", None,
        )
        self.assertIsNotNone(script)
        self.assertIn("script_oral_bit", script.name.lower())
        script_raid = find_perso_script_oral(
            self.cours, "PSI", "_revision_CC2", "RAID", None,
        )
        self.assertIsNotNone(script_raid)
        self.assertIn("script_oral_raid", script_raid.name.lower())

    def test_find_enonce_themed_returns_exos_when_available(self):
        """Phase v15.7.33 + v15.7.36.3 : num=thème + fichier
        `exos_{theme}.{pdf,md}` au top → retourné comme énoncé. C'est le
        SEUL cas où un type libre a un énoncé strict (vrai exo). Sinon
        find_enonce retourne None et le tuteur s'appuie sur annale + poly.
        """
        # Ajoute exos_TP_Shannon.pdf au top
        touch(self.cours / "PSI" / "_revision_CC2" / "exos_TP_Shannon.pdf")
        # Et déclare le thème via script_oral
        touch(self.cours / "PSI" / "_revision_CC2" / "scripts" / "script_oral_TP_Shannon.txt")
        enonce = find_enonce_pdf(
            self.cours, "PSI", "_revision_CC2", "TP_Shannon", None,
        )
        self.assertIsNotNone(enonce)
        self.assertIn("exos_tp_shannon", enonce.name.lower())

    def test_find_enonce_themed_returns_none_when_no_exos(self):
        """Phase v15.7.36.3 : si num=thème mais PAS de fichier
        `exos_{theme}.{pdf,md}` correspondant, retourne None (pas de
        fallback annale, qui va dans corrections).
        """
        # Pas d'exos_Bit.pdf : le thème Bit n'a que script+slides
        enonce = find_enonce_pdf(
            self.cours, "PSI", "_revision_CC2", "Bit", None,
        )
        self.assertIsNone(enonce)

    def test_case_insensitive_match(self):
        """Le _get_free_type_dir tolère la casse (`_REVISION_CC2`).
        Phase v15.7.36.3 : pour un type libre en mode full, find_enonce
        retourne None (pas de doublon avec corrigé). On vérifie ici juste
        que la casse insensible matche bien le dossier (resolve_corrections
        ramène annale_synthese, c'est cohérent avec test_resolve_corrections).
        """
        # Le case-insensitive est validé via resolve_corrections (qui
        # accède au même _get_free_type_dir).
        corrs = resolve_corrections(
            self.cours, "PSI", "_REVISION_CC2", "full", "full", None,
        )
        self.assertEqual(len(corrs), 1)
        self.assertIn("annale_synthese", corrs[0].name.lower())

    def test_canonical_type_unaffected_by_free_type_logic(self):
        """Régression : un TD normal doit toujours résoudre via la
        convention canonique, pas via le scan libre.
        """
        enonce = find_enonce_pdf(self.cours, "PSI", "TD", "1", None)
        self.assertIsNotNone(enonce)
        self.assertEqual(enonce.name, "enonce_TD1_PSI.pdf")

    def test_detect_themes_extracts_themes_from_scripts(self):
        """Phase v15.7.33 : _detect_themes_in_free_dir extrait correctement
        les thèmes des fichiers script_oral_*.{txt,md} et slides_*.pdf.
        """
        from cours_resolver import _detect_themes_in_free_dir
        # Crée plusieurs thèmes pour test
        base = self.cours / "PSI" / "_revision_CC2" / "scripts"
        touch(base / "script_oral_RAID.txt")
        touch(base / "script_oral_USB.txt")
        touch(base / "slides_TP_Shannon.pdf")
        themes = _detect_themes_in_free_dir(self.cours / "PSI" / "_revision_CC2")
        # Bit (déjà setUp) + RAID + USB + TP_Shannon
        self.assertIn("Bit", themes)
        self.assertIn("RAID", themes)
        self.assertIn("USB", themes)
        self.assertIn("TP_Shannon", themes)


if __name__ == "__main__":
    unittest.main(verbosity=2)
