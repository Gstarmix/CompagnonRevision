from __future__ import annotations
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock
ROOT = Path(__file__).resolve().parent.parent
DIALOGUE_DIR = ROOT / "_scripts" / "dialogue"
for _p in (str(ROOT), str(DIALOGUE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
class TestDSPyImportable(unittest.TestCase):
    def test_dspy_imports(self):
        import dspy
        self.assertTrue(hasattr(dspy, "Signature"))
        self.assertTrue(hasattr(dspy, "Predict"))
        self.assertTrue(hasattr(dspy, "Example"))
class TestSignatures(unittest.TestCase):
    def test_respond_to_slide_meta_has_required_fields(self):
        from dspy_compiler import RespondToSlideMeta
        fields = set(RespondToSlideMeta.model_fields.keys())
        for f in ("slide_index", "slide_total", "slide_title", "response"):
            self.assertIn(f, fields, f"Field {f} manquant dans RespondToSlideMeta")
    def test_respond_to_student_reading_has_required_fields(self):
        from dspy_compiler import RespondToStudentReading
        fields = set(RespondToStudentReading.model_fields.keys())
        for f in (
            "slide_title", "slide_expected_content", "student_reading",
            "response", "should_advance",
        ):
            self.assertIn(f, fields, f"Field {f} manquant dans RespondToStudentReading")
class TestDataset(unittest.TestCase):
    def test_meta_arrival_examples_have_5_entries(self):
        from dspy_compiler import get_meta_arrival_examples
        examples = get_meta_arrival_examples()
        self.assertEqual(len(examples), 5)
    def test_meta_arrival_examples_responses_are_short(self):
        from dspy_compiler import get_meta_arrival_examples
        for ex in get_meta_arrival_examples():
            self.assertLessEqual(
                len(ex.response.split()), 10,
                "Réponses canoniques meta doivent être ≤ 10 mots (concision)",
            )
    def test_reading_examples_mixed_advance_decisions(self):
        from dspy_compiler import get_reading_examples
        examples = get_reading_examples()
        self.assertGreaterEqual(len(examples), 3)
        decisions = {ex.should_advance for ex in examples}
        self.assertEqual(decisions, {True, False})
class TestMetric(unittest.TestCase):
    def test_clean_response_scores_high(self):
        from dspy_compiler import tutor_response_metric, get_meta_arrival_examples
        ex = get_meta_arrival_examples()[0]
        prediction = MagicMock()
        prediction.response = "Allez-y, lisez."
        score = tutor_response_metric(ex, prediction)
        self.assertEqual(score, 1.0)
    def test_response_with_role_hijack_loses_points(self):
        from dspy_compiler import tutor_response_metric, get_meta_arrival_examples
        ex = get_meta_arrival_examples()[0]
        prediction = MagicMock()
        prediction.response = (
            "Allez-y, lisez.\nUSER: ok\nASSISTANT: ok"
        )
        score = tutor_response_metric(ex, prediction)
        self.assertLess(score, 1.0)
        self.assertGreaterEqual(score, 0.5)
    def test_response_with_recited_rule_loses_points(self):
        from dspy_compiler import tutor_response_metric, get_meta_arrival_examples
        ex = get_meta_arrival_examples()[0]
        prediction = MagicMock()
        prediction.response = (
            "Allez-y, lisez.\n\nRÈGLE INVIOLABLE: pas de bla."
        )
        score = tutor_response_metric(ex, prediction)
        self.assertLess(score, 1.0)
    def test_response_too_long_loses_points(self):
        from dspy_compiler import tutor_response_metric, get_meta_arrival_examples
        ex = get_meta_arrival_examples()[0]
        prediction = MagicMock()
        prediction.response = " ".join(["mot"] * 200)
        score = tutor_response_metric(ex, prediction)
        self.assertLess(score, 1.0)
    def test_score_bounded_0_to_1(self):
        from dspy_compiler import tutor_response_metric, get_meta_arrival_examples
        ex = get_meta_arrival_examples()[0]
        for response in [
            "",
            "Allez-y.",
            "USER: a\nASSISTANT: b\nRÈGLE INVIOLABLE\n" + "x" * 1000,
            "Allez-y. <<<NEXT_SLIDE>>> au milieu et fin.",
        ]:
            prediction = MagicMock()
            prediction.response = response
            score = tutor_response_metric(ex, prediction)
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)
class TestGuidedTutorModule(unittest.TestCase):
    def test_instantiable_without_lm(self):
        from dspy_compiler import GuidedTutor
        tutor = GuidedTutor()
        self.assertIsNotNone(tutor.respond_to_meta)
        self.assertIsNotNone(tutor.respond_to_reading)
    def test_compile_without_lm_raises(self):
        from dspy_compiler import compile_guided_tutor
        with self.assertRaises(RuntimeError):
            compile_guided_tutor(lm=None)
if __name__ == "__main__":
    unittest.main()