"""DSPy : compilation des prompts pédagogiques (Phase A.7.2 v15, Phase LT).

Long terme du programme « gommer le biais aléatoire des prompts ».

Au lieu d'écrire un prompt en prose et d'espérer que le modèle le suive,
on **décrit la signature** (input → output spec) et DSPy se charge de
trouver la formulation qui maximise un score sur un dataset d'évaluation.
La logique pédagogique passe alors de « prose flou » à « contrat
input/output testable ».

Pattern :

1. Définir la **Signature** : input fields + output fields + description
   du comportement attendu. C'est l'équivalent d'une docstring de fonction
   pour un LLM.
2. Définir le **module** qui consomme la signature (Predict, ChainOfThought,
   ReAct…) et l'enchaînement éventuel.
3. Définir un **dataset** d'exemples (input → output souhaité).
4. Définir une **metric** qui score les sorties.
5. **Compiler** : DSPy teste plusieurs formulations / few-shots et garde
   celle qui maximise la metric.
6. Le module compilé est sérialisable (.json) et rechargeable en runtime.

PoC : 2 signatures (réponse à un meta d'arrivée slide / réponse à une
lecture étudiante) + dataset 5 exemples + metric basée sur les filtres
output_filters. La compilation effective demande un LM configuré (Claude
CLI gratuit, Ollama local, ou clé API). Sans LM, on peut quand même :
- Vérifier que les signatures sont bien définies
- Évaluer manuellement des candidats avec la metric
- Sérialiser/rappeler la structure

Voir tests/test_dspy_compiler.py pour les tests sans LM réel.
"""
from __future__ import annotations

from typing import Any

import dspy

# Permet l'import des filtres depuis ce module (path setup côté caller)
import sys
from pathlib import Path
_DIALOGUE_DIR = Path(__file__).resolve().parent
if str(_DIALOGUE_DIR) not in sys.path:
    sys.path.insert(0, str(_DIALOGUE_DIR))

from output_filters import apply_all_filters


# ============================================================ Signatures

class RespondToSlideMeta(dspy.Signature):
    """Le tuteur reçoit un meta d'arrivée slide. L'étudiant vient juste
    d'arriver sur cette slide, il n'a pas encore lu le contenu.

    Le tuteur produit une réponse COURTE qui invite à lire (1 phrase
    max), sans commenter le contenu de la slide, sans annoncer la slide
    suivante, sans émettre de balise transition.
    """

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
    """Le tuteur reçoit la lecture/résumé de la slide courante par l'étudiant.

    Selon la qualité de la réponse, le tuteur :
    - ajoute une nuance utile (1-3 phrases),
    - décide d'avancer (`should_advance=True`) ou de rester sur la slide.

    Le caller (DSPy module) traduit `should_advance=True` en émission de
    la balise `<<<NEXT_SLIDE>>>` à la fin du message ou en tool call.
    """

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


# ============================================================ Module composé

class GuidedTutor(dspy.Module):
    """Module DSPy qui orchestre les 2 signatures du mode guidé.

    Au runtime, le caller appelle la méthode appropriée selon le type de
    message reçu (meta d'arrivée vs lecture de l'étudiant). DSPy se charge
    de la formulation effective via l'optimiseur compilé (ou via la
    formulation par défaut si pas compilé).
    """

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


# ============================================================ Dataset PoC

# Exemples tirés de tests/eval_prompt.md (S1, S2, S3, S6, S15). Format
# DSPy : objets dspy.Example avec les champs input et output spécifiés.
def get_meta_arrival_examples() -> list[dspy.Example]:
    """5 exemples de réponse à un meta d'arrivée slide. Réponses
    canoniques courtes que la metric devrait scorer haut."""
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
    """3 exemples de réponse à une lecture étudiante (positifs/négatifs)."""
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


# ============================================================ Métrique

def tutor_response_metric(example: dspy.Example, prediction: Any,
                          trace: Any = None) -> float:
    """Score 0-1 d'une réponse du tuteur selon les rails déterministes.

    Critères :
    - Pas de role hijacking (USER:/ASSISTANT:) → 0.25
    - Pas de récitation des règles du prompt → 0.25
    - Longueur raisonnable (≤ 60 mots pour meta, ≤ 100 pour reading) → 0.25
    - Pas de balise <<<NEXT_SLIDE>>> dans le texte si le contexte est un
      meta d'arrivée → 0.25

    DSPy optimiseur cherche la formulation qui maximise ce score sur le
    dataset.
    """
    response = getattr(prediction, "response", "") or ""
    text, stats = apply_all_filters(response)

    score = 0.0

    # 1. Pas de role hijacking
    if stats["role_hijacking_lines_removed"] == 0:
        score += 0.25

    # 2. Pas de récitation du prompt
    if stats["recited_paragraphs_removed"] == 0:
        score += 0.25

    # 3. Longueur raisonnable
    word_count = len(response.split())
    is_meta_arrival = "slide_index" in example.inputs().__dict__ \
        if hasattr(example, "inputs") else False
    max_words = 60 if is_meta_arrival else 100
    if word_count <= max_words:
        score += 0.25

    # 4. Pas de balise NEXT_SLIDE en plein texte (sauf en queue)
    if stats["misplaced_next_slide_removed"] == 0:
        score += 0.25

    return score


# ============================================================ Helper compile

def compile_guided_tutor(lm: Any, num_threads: int = 1) -> GuidedTutor:
    """Compile le module GuidedTutor avec DSPy BootstrapFewShot.

    Demande un LM configuré (dspy.LM ou compatible). Sans LM, lève
    RuntimeError. Le caller doit avoir fait dspy.configure(lm=lm) avant.

    Le résultat est un GuidedTutor optimisé qu'on peut sérialiser via
    .save() puis recharger en runtime avec .load(), sans payer la
    compilation à chaque démarrage.

    PoC simple : optimiseur BootstrapFewShot qui choisit les meilleurs
    few-shots parmi le dataset. Pour un compile plus poussé, voir
    MIPROv2 ou COPRO dans la doc DSPy.
    """
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
