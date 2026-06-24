from __future__ import annotations
from typing import Any
import dspy
import sys
from pathlib import Path
_DIALOGUE_DIR = Path(__file__).resolve().parent
if str(_DIALOGUE_DIR) not in sys.path:
    sys.path.insert(0, str(_DIALOGUE_DIR))
from output_filters import apply_all_filters
class RespondToSlideMeta(dspy.Signature):
    slide_index = dspy.InputField(
        desc="Numéro 1-based de la slide qui vient d'apparaître.",
    )
    slide_total = dspy.InputField(
        desc="Nombre total de slides dans la séance.",
    )
    slide_title = dspy.InputField(
        desc="Titre de la slide (peut être vide).",
    )
    response = dspy.OutputField(
        desc=(
            "Réponse du tuteur. Une seule phrase courte qui invite l'étudiant "
            "à lire (ex: « Allez-y, lisez. »). Pas de commentaire sur le "
            "contenu de la slide, pas d'annonce de la slide suivante, "
            "pas de balise <<<NEXT_SLIDE>>>."
        ),
    )
class RespondToStudentReading(dspy.Signature):
    slide_title = dspy.InputField(desc="Titre de la slide courante.")
    slide_expected_content = dspy.InputField(
        desc="Aperçu du texte oral attendu sur cette slide (depuis le SCRIPT).",
    )
    student_reading = dspy.InputField(
        desc="Ce que l'étudiant vient de dire en lisant/résumant la slide.",
    )
    response = dspy.OutputField(
        desc=(
            "Réponse du tuteur (1-3 phrases). Vouvoiement strict, pas de "
            "superlatif, pas de récitation des règles internes. Si une "
            "nuance est utile, l'apporter. Sinon, accusé bref."
        ),
    )
    should_advance = dspy.OutputField(
        desc=(
            "True si la slide est acquise et qu'on peut avancer à la slide "
            "suivante, False sinon. Critères True : étudiant a lu, a réagi "
            "correctement, point critique verrouillé. Critères False : "
            "blocage, formulation floue, point en suspens."
        ),
    )
class GuidedTutor(dspy.Module):
    def __init__(self):
        super().__init__()
        self.respond_to_meta = dspy.Predict(RespondToSlideMeta)
        self.respond_to_reading = dspy.Predict(RespondToStudentReading)
    def on_slide_arrival(self, slide_index, slide_total, slide_title=""):
        return self.respond_to_meta(
            slide_index=str(slide_index),
            slide_total=str(slide_total),
            slide_title=slide_title or "",
        )
    def on_student_reading(self, slide_title, slide_expected_content,
                           student_reading):
        return self.respond_to_reading(
            slide_title=slide_title or "",
            slide_expected_content=slide_expected_content or "",
            student_reading=student_reading,
        )
def get_meta_arrival_examples() -> list[dspy.Example]:
    return [
        dspy.Example(
            slide_index="2", slide_total="12",
            slide_title="Sortie a en somme de produits",
            response="Allez-y, lisez.",
        ).with_inputs("slide_index", "slide_total", "slide_title"),
        dspy.Example(
            slide_index="5", slide_total="12",
            slide_title="Karnaugh sortie a",
            response="Je vous écoute.",
        ).with_inputs("slide_index", "slide_total", "slide_title"),
        dspy.Example(
            slide_index="1", slide_total="12",
            slide_title="Accroche",
            response="Prenez le temps de lire.",
        ).with_inputs("slide_index", "slide_total", "slide_title"),
        dspy.Example(
            slide_index="7", slide_total="12",
            slide_title="Conversion NAND-NAND",
            response="Slide affichée, à vous.",
        ).with_inputs("slide_index", "slide_total", "slide_title"),
        dspy.Example(
            slide_index="3", slide_total="12",
            slide_title="De Morgan",
            response="Allez-y, lisez la slide.",
        ).with_inputs("slide_index", "slide_total", "slide_title"),
    ]
def get_reading_examples() -> list[dspy.Example]:
    return [
        dspy.Example(
            slide_title="Sortie a en SdP",
            slide_expected_content="12 mintermes pour la sortie a, réflexe a-bar 4 termes",
            student_reading=(
                "Ok, alors a c'est 12 mintermes mais on peut passer par a-bar "
                "qui n'a que 4 termes, c'est plus court."
            ),
            response=(
                "Bon résumé, vous avez le réflexe. Précision : la convention "
                "« passer par le complément quand l'autre est plus court » "
                "marche aussi pour les autres sorties."
            ),
            should_advance=True,
        ).with_inputs("slide_title", "slide_expected_content", "student_reading"),
        dspy.Example(
            slide_title="De Morgan",
            slide_expected_content="Complément d'une somme = produit des compléments",
            student_reading=(
                "Heu, je sais pas trop comment De Morgan s'applique ici."
            ),
            response=(
                "OK, on fixe la règle avant. Énoncez De Morgan dans sa forme "
                "« complément d'une somme = ? »."
            ),
            should_advance=False,
        ).with_inputs("slide_title", "slide_expected_content", "student_reading"),
        dspy.Example(
            slide_title="Karnaugh",
            slide_expected_content="Grille 4×4, code Gray, regroupements puissances de 2",
            student_reading=(
                "Le carnaut c'est en gros une table mais autrement."
            ),
            response=(
                "« En gros » et « autrement » ne sont pas des termes "
                "techniques. Reformulez : qu'est-ce qui change exactement "
                "entre la table de vérité et le Karnaugh ?"
            ),
            should_advance=False,
        ).with_inputs("slide_title", "slide_expected_content", "student_reading"),
    ]
def tutor_response_metric(example: dspy.Example, prediction: Any,
                          trace: Any = None) -> float:
    response = getattr(prediction, "response", "") or ""
    text, stats = apply_all_filters(response)
    score = 0.0
    if stats["role_hijacking_lines_removed"] == 0:
        score += 0.25
    if stats["recited_paragraphs_removed"] == 0:
        score += 0.25
    word_count = len(response.split())
    is_meta_arrival = "slide_index" in example.inputs().__dict__ \
        if hasattr(example, "inputs") else False
    max_words = 60 if is_meta_arrival else 100
    if word_count <= max_words:
        score += 0.25
    if stats["misplaced_next_slide_removed"] == 0:
        score += 0.25
    return score
def compile_guided_tutor(lm: Any, num_threads: int = 1) -> GuidedTutor:
    if lm is None:
        raise RuntimeError(
            "Aucun LM configuré. Faire dspy.configure(lm=...) avant compile.",
        )
    optimizer = dspy.BootstrapFewShot(
        metric=tutor_response_metric,
        max_bootstrapped_demos=3,
        max_labeled_demos=3,
    )
    student = GuidedTutor()
    trainset = get_meta_arrival_examples() + get_reading_examples()
    compiled = optimizer.compile(student, trainset=trainset)
    return compiled