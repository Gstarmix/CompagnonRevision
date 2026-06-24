import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "_scripts"
DIALOGUE = SCRIPTS / "dialogue"
for _p in (str(ROOT), str(SCRIPTS), str(DIALOGUE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from droit_resolver import (
    find_fiche,
    find_transcription,
    list_arrets,
    list_matieres,
    list_methodo_matiere,
    list_methodo_transverse,
    list_nums_for_type,
    list_types_for_matiere,
)
def touch(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path
class TestDroitResolver(unittest.TestCase):
    def setUp(self):
        self._tmpobj = TemporaryDirectory()
        self.droit = Path(self._tmpobj.name)
        dp = self.droit / "droit-personnes"
        touch(dp / "CM" / "transcriptions" / "CM1_droit-personnes_2206.txt", b"cours")
        touch(dp / "CM" / "transcriptions" / "CM2_droit-personnes_2906.txt", b"cours")
        touch(dp / "CM" / "fiches" / "fiche_CM1_droit-personnes_2206.md", b"# Fiche")
        touch(dp / "CM" / "audio" / "CM1_droit-personnes_2206.m4a")
        touch(dp / "TD" / "TD1_droit-personnes_0310.txt", b"td")
        touch(dp / "TD" / "fiche_TD1_droit-personnes_0310.md", b"# Fiche TD")
        touch(dp / "arrets" / "arret_cassation_2026.md", b"# Arret")
        touch(dp / "arrets" / ".gitkeep")
        touch(dp / "methodo" / "note_methodo_dp.md", b"# Methodo matiere")
        idr = self.droit / "intro-droit"
        touch(idr / "CM" / "transcriptions" / "CM1_intro-droit_1509.txt", b"cours")
        touch(self.droit / "_methodo" / "methodo_dissertation.md", b"# Dissertation")
        touch(self.droit / "_methodo" / "methodo_cas-pratique.md", b"# Cas pratique")
    def tearDown(self):
        self._tmpobj.cleanup()
    def test_list_matieres_exclut_transverses(self):
        self.assertEqual(
            list_matieres(self.droit), ["droit-personnes", "intro-droit"]
        )
    def test_list_matieres_root_absente(self):
        self.assertEqual(list_matieres(self.droit / "nope"), [])
    def test_types_majeure_cm_et_td(self):
        self.assertEqual(
            list_types_for_matiere(self.droit, "droit-personnes"), ["CM", "TD"]
        )
    def test_types_mineure_cm_seul(self):
        self.assertEqual(
            list_types_for_matiere(self.droit, "intro-droit"), ["CM"]
        )
    def test_nums_cm_union_transcription_et_fiche(self):
        self.assertEqual(
            list_nums_for_type(self.droit, "droit-personnes", "CM"), ["1", "2"]
        )
    def test_nums_td(self):
        self.assertEqual(
            list_nums_for_type(self.droit, "droit-personnes", "TD"), ["1"]
        )
    def test_find_transcription_cm(self):
        hit = find_transcription(self.droit, "droit-personnes", "CM", "1")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.name, "CM1_droit-personnes_2206.txt")
    def test_find_transcription_td(self):
        hit = find_transcription(self.droit, "droit-personnes", "TD", "1")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.name, "TD1_droit-personnes_0310.txt")
    def test_find_fiche_cm(self):
        hit = find_fiche(self.droit, "droit-personnes", "CM", "1")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.name, "fiche_CM1_droit-personnes_2206.md")
    def test_find_fiche_absente_retourne_none(self):
        self.assertIsNone(find_fiche(self.droit, "droit-personnes", "CM", "2"))
    def test_find_transcription_mauvais_num(self):
        self.assertIsNone(find_transcription(self.droit, "droit-personnes", "CM", "9"))
    def test_list_arrets_ignore_gitkeep(self):
        arrets = list_arrets(self.droit, "droit-personnes")
        self.assertEqual([p.name for p in arrets], ["arret_cassation_2026.md"])
    def test_list_methodo_matiere(self):
        methodo = list_methodo_matiere(self.droit, "droit-personnes")
        self.assertEqual([p.name for p in methodo], ["note_methodo_dp.md"])
    def test_list_methodo_transverse(self):
        methodo = list_methodo_transverse(self.droit)
        self.assertEqual(
            [p.name for p in methodo],
            ["methodo_cas-pratique.md", "methodo_dissertation.md"],
        )
    def test_methodo_transverse_root_absente(self):
        self.assertEqual(list_methodo_transverse(self.droit / "nope"), [])
if __name__ == "__main__":
    unittest.main()