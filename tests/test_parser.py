import json
import logging
import sys
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DIALOGUE_DIR = ROOT / "_scripts" / "dialogue"
for _p in (str(ROOT), str(DIALOGUE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
from parser import (
    ParserEvent,
    ParserEventType,
    ParserState,
    StreamParser,
)
class TestStreamParser(unittest.TestCase):
    def setUp(self):
        self.events: list[ParserEvent] = []
        self.parser = StreamParser(self.events.append)
    def _types(self) -> list[ParserEventType]:
        return [e.type for e in self.events]
    def _texts(self) -> str:
        return "".join(
            e.payload for e in self.events if e.type == ParserEventType.TEXT_CHUNK
        )
    def _suggested_edits(self) -> list[dict]:
        return [
            e.payload for e in self.events
            if e.type == ParserEventType.SUGGESTED_EDIT
        ]
    def test_01_simple_text(self):
        self.parser.feed("Bonjour le monde")
        self.parser.flush()
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0].type, ParserEventType.TEXT_CHUNK)
        self.assertEqual(self.events[0].payload, "Bonjour le monde")
    def test_02_tts_single_chunk(self):
        self.parser.feed("<<<TTS>>>Bonjour<<<END>>>")
        self.parser.flush()
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0].type, ParserEventType.TTS)
        self.assertEqual(self.events[0].payload, "Bonjour")
    def test_03_tts_split_in_5_chunks(self):
        chunks = ["<<<", "TTS>>>B", "onjou", "r<<<E", "ND>>>"]
        for c in chunks:
            self.parser.feed(c)
        self.parser.flush()
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0].type, ParserEventType.TTS)
        self.assertEqual(self.events[0].payload, "Bonjour")
    def test_04_tts_surrounded_by_text(self):
        self.parser.feed("Salut <<<TTS>>>OK<<<END>>> suite")
        self.parser.flush()
        self.assertEqual(self._types(), [
            ParserEventType.TEXT_CHUNK,
            ParserEventType.TTS,
            ParserEventType.TEXT_CHUNK,
        ])
        self.assertEqual(self.events[0].payload, "Salut ")
        self.assertEqual(self.events[1].payload, "OK")
        self.assertEqual(self.events[2].payload, " suite")
    def test_07_end_session(self):
        self.parser.feed("<<<END_SESSION>>>")
        self.parser.flush()
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0].type, ParserEventType.END_SESSION)
    def test_08_false_positive_tag(self):
        self.parser.feed("<<<X>>>")
        self.parser.flush()
        for e in self.events:
            self.assertEqual(
                e.type, ParserEventType.TEXT_CHUNK,
                f"Event inattendu: {e.type}",
            )
        self.assertEqual(self._texts(), "<<<X>>>")
    def test_09_truncated_during_probe(self):
        with self.assertLogs(level=logging.WARNING) as cm:
            self.parser.feed("<<<TT")
            self.parser.flush()
        for e in self.events:
            self.assertEqual(
                e.type, ParserEventType.TEXT_CHUNK,
                f"Event inattendu: {e.type}",
            )
        self.assertEqual(self.parser._state, ParserState.OUTSIDE)
        self.assertTrue(
            any("tronque" in line.lower() for line in cm.output),
            f"Warning de troncation introuvable. Logs: {cm.output}",
        )
    def test_se_01_valid(self):
        payload = json.dumps({
            "file": "AN1/TD/TD5/scripts_oraux/SCRIPT_AN1_TD5.md",
            "before": "f continue donc Rolle",
            "after": "f continue ET dérivable donc Rolle",
            "reason": "Il manque la dérivabilité.",
        })
        self.parser.feed(f"Voici une suggestion : <<<SUGGESTED_EDIT>>>{payload}<<<END>>>")
        self.parser.flush()
        suggs = self._suggested_edits()
        self.assertEqual(len(suggs), 1)
        self.assertEqual(suggs[0]["file"], "AN1/TD/TD5/scripts_oraux/SCRIPT_AN1_TD5.md")
        self.assertIn("dérivable", suggs[0]["after"])
        self.assertIn("Voici une suggestion :", self._texts())
    def test_se_02_split_in_chunks(self):
        payload = json.dumps({"file": "f.md", "before": "X", "after": "Y"})
        full = f"<<<SUGGESTED_EDIT>>>{payload}<<<END>>>"
        for i in range(0, len(full), 7):
            self.parser.feed(full[i:i + 7])
        self.parser.flush()
        suggs = self._suggested_edits()
        self.assertEqual(len(suggs), 1)
        self.assertEqual(suggs[0]["file"], "f.md")
    def test_se_03_invalid_json(self):
        with self.assertLogs(level=logging.WARNING):
            self.parser.feed("<<<SUGGESTED_EDIT>>>{not json<<<END>>>")
            self.parser.flush()
        self.assertEqual(self._suggested_edits(), [])
    def test_se_04_missing_required_field(self):
        with self.assertLogs(level=logging.WARNING):
            self.parser.feed(
                '<<<SUGGESTED_EDIT>>>{"file":"f.md","before":"X"}<<<END>>>'
            )
            self.parser.flush()
        self.assertEqual(self._suggested_edits(), [])
    def test_se_05_noop_before_equals_after(self):
        with self.assertLogs(level=logging.WARNING):
            self.parser.feed(
                '<<<SUGGESTED_EDIT>>>{"file":"f.md","before":"X","after":"X"}<<<END>>>'
            )
            self.parser.flush()
        self.assertEqual(self._suggested_edits(), [])
    def test_se_06_empty_before(self):
        with self.assertLogs(level=logging.WARNING):
            self.parser.feed(
                '<<<SUGGESTED_EDIT>>>{"file":"f.md","before":"","after":"Y"}<<<END>>>'
            )
            self.parser.flush()
        self.assertEqual(self._suggested_edits(), [])
    def test_se_07_optional_reason_missing(self):
        self.parser.feed(
            '<<<SUGGESTED_EDIT>>>{"file":"f.md","before":"X","after":"Y"}<<<END>>>'
        )
        self.parser.flush()
        suggs = self._suggested_edits()
        self.assertEqual(len(suggs), 1)
    def _remembers(self) -> list[dict]:
        return [
            e.payload for e in self.events if e.type == ParserEventType.REMEMBER
        ]
    def test_rm_01_valid(self):
        raw = '<<<REMEMBER>>>{"text": "Pense aux signatures"}<<<END>>>'
        self.parser.feed(raw)
        self.parser.flush()
        rms = self._remembers()
        self.assertEqual(len(rms), 1)
        self.assertEqual(rms[0]["text"], "Pense aux signatures")
        self.assertEqual(self._texts(), "")
    def test_rm_02_with_surrounding_text(self):
        self.parser.feed(
            'Noté. <<<REMEMBER>>>{"text":"X"}<<<END>>> Reprise.'
        )
        self.parser.flush()
        self.assertEqual(self._types(), [
            ParserEventType.TEXT_CHUNK,
            ParserEventType.REMEMBER,
            ParserEventType.TEXT_CHUNK,
        ])
        self.assertEqual(self._remembers()[0]["text"], "X")
    def test_rm_03_split_chunks(self):
        chunks = ['<<<REM', 'EMBER>>>{"', 'text":"abc"', '}<<<E', 'ND>>>']
        for c in chunks:
            self.parser.feed(c)
        self.parser.flush()
        rms = self._remembers()
        self.assertEqual(len(rms), 1)
        self.assertEqual(rms[0]["text"], "abc")
    def test_rm_04_invalid_json(self):
        with self.assertLogs(level=logging.WARNING):
            self.parser.feed('<<<REMEMBER>>>{not json<<<END>>>')
            self.parser.flush()
        self.assertEqual(self._remembers(), [])
    def test_rm_05_missing_text_field(self):
        with self.assertLogs(level=logging.WARNING):
            self.parser.feed('<<<REMEMBER>>>{"foo":"bar"}<<<END>>>')
            self.parser.flush()
        self.assertEqual(self._remembers(), [])
    def test_rm_06_empty_text(self):
        with self.assertLogs(level=logging.WARNING):
            self.parser.feed('<<<REMEMBER>>>{"text":"   "}<<<END>>>')
            self.parser.flush()
        self.assertEqual(self._remembers(), [])
    def test_rm_07_text_truncated_at_200(self):
        long_text = "x" * 250
        raw = '<<<REMEMBER>>>' + json.dumps({"text": long_text}) + '<<<END>>>'
        with self.assertLogs(level=logging.WARNING):
            self.parser.feed(raw)
            self.parser.flush()
        rms = self._remembers()
        self.assertEqual(len(rms), 1)
        self.assertEqual(len(rms[0]["text"]), 198)
        self.assertTrue(rms[0]["text"].endswith("…"))
    def test_rm_08_whitespace_normalized(self):
        raw = '<<<REMEMBER>>>{"text": "foo  bar\\nbaz"}<<<END>>>'
        self.parser.feed(raw)
        self.parser.flush()
        rms = self._remembers()
        self.assertEqual(len(rms), 1)
        self.assertEqual(rms[0]["text"], "foo bar baz")
if __name__ == "__main__":
    unittest.main(verbosity=2)