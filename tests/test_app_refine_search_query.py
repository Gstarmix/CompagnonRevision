"""
test_app_refine_search_query.py : couverture endpoint
POST /api/refine_search_query (Phases v15.7.14 + v15.7.15).

On mocke ``ClaudeClient`` pour ne pas appeler Gemini Flash en réseau.

Phase v15.7.15, workflow 2-étapes :
    Étape 1 : <<<CONCEPT>>>{concept, concept_alternatives, level, key_specs, domain}<<<END>>>
    Étape 2 : <<<REFINED>>>{query, alternatives}<<<END>>>

Le mock de ClaudeClient doit donc renvoyer 2 réponses successives
quand l'endpoint enchaîne les 2 calls.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "_scripts"
for _p in (
    str(ROOT),
    str(SCRIPTS),
    str(SCRIPTS / "dialogue"),
    str(SCRIPTS / "audio"),
    str(SCRIPTS / "quota"),
    str(SCRIPTS / "web"),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)


class TestApiRefineSearchQuery(unittest.TestCase):

    def setUp(self):
        import app
        self.app_module = app
        self.client = app.app.test_client()

    def _make_fake_client_pair(self, concept_response, refined_response):
        """Phase v15.7.15 : 2 ClaudeClients consécutifs (workflow 2-étapes).

        Renvoie une lambda qui produit un fake différent à chaque appel
        (1ᵉʳ = concept, 2ᵉ = refined). Utilisé via patch side_effect.
        """
        responses = [concept_response, refined_response]

        def make_one(*args, **kwargs):  # noqa: ARG001 (side_effect ignore les args)
            r = responses.pop(0) if responses else "<<<REFINED>>>{}<<<END>>>"
            fake = MagicMock()
            fake._history = []
            type(fake).history = property(lambda self_: list(self_._history))

            def _fake_append(text):
                fake._history.append({"role": "user", "content": text})

            def _fake_stream(on_event):  # noqa: ARG001
                fake._history.append({"role": "assistant", "content": r})

            fake.append_user_message.side_effect = _fake_append
            fake.stream_response.side_effect = _fake_stream
            return fake

        return make_one

    # Helper legacy 1-shot (pour les cas où l'endpoint stoppe à l'étape 1)
    def _make_fake_client(self, response_text):
        fake = MagicMock()
        fake._history = []
        type(fake).history = property(lambda self_: list(self_._history))

        def _fake_append(text):
            fake._history.append({"role": "user", "content": text})

        def _fake_stream(on_event):  # noqa: ARG001
            fake._history.append({"role": "assistant", "content": response_text})

        fake.append_user_message.side_effect = _fake_append
        fake.stream_response.side_effect = _fake_stream
        return fake

    def test_empty_description_returns_400(self):
        r = self.client.post("/api/refine_search_query", json={"description": ""})
        self.assertEqual(r.status_code, 400)
        self.assertIn("description", r.get_json()["error"].lower())

    def test_happy_path_returns_query_and_alternatives(self):
        # Phase v15.7.15 : 2 réponses consécutives (concept puis refined)
        concept = ('<<<CONCEPT>>>{"concept": "comparateur logique 3 bits",'
                   ' "concept_alternatives": ["codeur prioritaire 8 vers 3"],'
                   ' "level": "L1", "key_specs": "3 entrées 2 sorties",'
                   ' "domain": "logique combinatoire"}<<<END>>>')
        refined = ('<<<REFINED>>>{"query": "comparateur logique 3 bits cours table de vérité",'
                   ' "alternatives": ["circuit combinatoire 3 entrées 2 sorties exercice corrigé",'
                   ' "comparateur numérique table de vérité L1 électronique"]}<<<END>>>')
        with patch("app.ClaudeClient", side_effect=self._make_fake_client_pair(concept, refined)):
            r = self.client.post("/api/refine_search_query", json={
                "description": "Le tuteur vient de me dire : analysez le composant COMP...",
                "target": "web",
            })
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        body = r.get_json()
        self.assertEqual(body["query"], "comparateur logique 3 bits cours table de vérité")
        self.assertEqual(len(body["alternatives"]), 2)
        self.assertEqual(body["model"], "gemini-2.5-flash")
        self.assertEqual(body["target"], "web")
        # Phase v15.7.15 : concept et level exposés dans la réponse
        self.assertEqual(body["concept"], "comparateur logique 3 bits")
        self.assertEqual(body["level"], "L1")

    def test_youtube_target_passed_through(self):
        concept = ('<<<CONCEPT>>>{"concept": "multiplexeur 2 vers 1",'
                   ' "level": "L1", "key_specs": "2 entrées 1 sélecteur"}<<<END>>>')
        refined = '<<<REFINED>>>{"query": "MUX 2 vers 1 cours vidéo", "alternatives": []}<<<END>>>'
        with patch("app.ClaudeClient", side_effect=self._make_fake_client_pair(concept, refined)):
            r = self.client.post("/api/refine_search_query", json={
                "description": "Donnez l'équation logique du MUX21",
                "target": "youtube",
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["target"], "youtube")

    def test_invalid_target_falls_back_to_web(self):
        concept = '<<<CONCEPT>>>{"concept": "test concept", "level": "L1"}<<<END>>>'
        refined = '<<<REFINED>>>{"query": "test", "alternatives": []}<<<END>>>'
        with patch("app.ClaudeClient", side_effect=self._make_fake_client_pair(concept, refined)):
            r = self.client.post("/api/refine_search_query", json={
                "description": "test description",
                "target": "weird",
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["target"], "web")

    def test_forces_gemini_flash_regardless_of_engine_pref(self):
        """L'endpoint doit construire le ClaudeClient avec engine='gemini_api'
        et model='gemini-2.5-flash', peu importe la pref user.
        Phase v15.7.15 : vérifie sur les 2 calls (concept + refined)."""
        concept = '<<<CONCEPT>>>{"concept": "x", "level": "L1"}<<<END>>>'
        refined = '<<<REFINED>>>{"query": "test query", "alternatives": []}<<<END>>>'
        with patch("app.ClaudeClient", side_effect=self._make_fake_client_pair(concept, refined)) as MockClient, \
             patch("app._read_engine_pref", return_value="cli_subscription"):
            r = self.client.post("/api/refine_search_query", json={
                "description": "test description",
            })
        self.assertEqual(r.status_code, 200)
        # ClaudeClient doit avoir été appelé 2 fois (concept + refined)
        self.assertEqual(MockClient.call_count, 2)
        # Sur chaque call : engine=gemini_api, model=gemini-2.5-flash
        for call in MockClient.call_args_list:
            kwargs = call.kwargs
            self.assertEqual(kwargs.get("engine"), "gemini_api")
            self.assertEqual(kwargs.get("model"), "gemini-2.5-flash")

    def test_exclude_propagated_to_step2_sys_prompt(self):
        """Phase v15.7.15 : exclude est propagé au sys_prompt de l'étape 2
        (compose query), pas l'étape 1 (infer concept)."""
        concept = '<<<CONCEPT>>>{"concept": "x", "level": "L1"}<<<END>>>'
        refined = '<<<REFINED>>>{"query": "alt query", "alternatives": []}<<<END>>>'
        with patch("app.ClaudeClient", side_effect=self._make_fake_client_pair(concept, refined)) as MockClient:
            r = self.client.post("/api/refine_search_query", json={
                "description": "test",
                "exclude": ["query déjà tentée 1", "query déjà tentée 2"],
            })
        self.assertEqual(r.status_code, 200)
        # Le sys_prompt de la 2e call (refined) contient les exclude
        # (la 1ʳᵉ call = infer_concept ne les utilise pas)
        sys_prompt_step2 = MockClient.call_args_list[1].kwargs.get("system_prompt") or ""
        self.assertIn("query déjà tentée 1", sys_prompt_step2)
        self.assertIn("query déjà tentée 2", sys_prompt_step2)

    def test_empty_query_in_response_returns_502(self):
        """Si l'étape 2 renvoie {query: ""}, l'endpoint retourne 502."""
        concept = '<<<CONCEPT>>>{"concept": "x", "level": "L1"}<<<END>>>'
        refined = '<<<REFINED>>>{"query": "", "alternatives": []}<<<END>>>'
        with patch("app.ClaudeClient", side_effect=self._make_fake_client_pair(concept, refined)):
            r = self.client.post("/api/refine_search_query", json={
                "description": "test description",
            })
        self.assertEqual(r.status_code, 502)
        body = r.get_json()
        self.assertEqual(body["error"], "reponse_vide")
        self.assertEqual(body["step"], "compose_query")

    def test_empty_concept_in_step1_returns_502(self):
        """Phase v15.7.15 : si l'étape 1 (infer concept) renvoie un concept
        vide, l'endpoint stoppe net et retourne 502 step=infer_concept."""
        concept = '<<<CONCEPT>>>{"concept": "", "level": "L1"}<<<END>>>'
        refined = '<<<REFINED>>>{"query": "ne sera pas utilisé", "alternatives": []}<<<END>>>'
        with patch("app.ClaudeClient", side_effect=self._make_fake_client_pair(concept, refined)):
            r = self.client.post("/api/refine_search_query", json={
                "description": "test description",
            })
        self.assertEqual(r.status_code, 502)
        body = r.get_json()
        self.assertEqual(body["error"], "reponse_vide")
        self.assertEqual(body["step"], "infer_concept")

    def test_alternatives_capped_at_3(self):
        """Plus de 3 alternatives → tronqué à 3."""
        concept = '<<<CONCEPT>>>{"concept": "x", "level": "L1"}<<<END>>>'
        refined = ('<<<REFINED>>>{"query": "main", "alternatives": '
                   '["a1", "a2", "a3", "a4", "a5"]}<<<END>>>')
        with patch("app.ClaudeClient", side_effect=self._make_fake_client_pair(concept, refined)):
            r = self.client.post("/api/refine_search_query", json={
                "description": "test description",
            })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.get_json()["alternatives"]), 3)

    def test_concept_data_propagated_to_step2_prompt(self):
        """Phase v15.7.15 : le concept inféré à l'étape 1 (concept,
        level, key_specs, domain) est injecté dans le sys_prompt de
        l'étape 2 pour orienter la composition de la query."""
        concept = ('<<<CONCEPT>>>{"concept": "comparateur 3 bits",'
                   ' "concept_alternatives": ["codeur"],'
                   ' "level": "L2",'
                   ' "key_specs": "3 entrées 2 sorties",'
                   ' "domain": "logique combinatoire"}<<<END>>>')
        refined = '<<<REFINED>>>{"query": "result", "alternatives": []}<<<END>>>'
        with patch("app.ClaudeClient", side_effect=self._make_fake_client_pair(concept, refined)) as MockClient:
            r = self.client.post("/api/refine_search_query", json={
                "description": "x",
            })
        self.assertEqual(r.status_code, 200)
        # Le sys_prompt de l'étape 2 contient le concept inféré
        sys_prompt_step2 = MockClient.call_args_list[1].kwargs.get("system_prompt") or ""
        self.assertIn("comparateur 3 bits", sys_prompt_step2)
        self.assertIn("L2", sys_prompt_step2)
        self.assertIn("3 entrées 2 sorties", sys_prompt_step2)
        self.assertIn("logique combinatoire", sys_prompt_step2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
