from __future__ import annotations
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
DIALOGUE_DIR = ROOT / "_scripts" / "dialogue"
for _p in (str(ROOT), str(DIALOGUE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import fs_tools
from fs_tools import (
    FS_TOOL_NAMES,
    TOOL_MARKER_CLOSE,
    TOOL_MARKER_OPEN,
    FsToolResult,
    anthropic_fs_tools,
    execute_fs_tool,
    gemini_fs_declarations,
    openai_fs_tools,
    tool_call_label,
    tool_call_marker,
)
class TestSchemas(unittest.TestCase):
    def test_three_tool_names(self):
        self.assertEqual(FS_TOOL_NAMES, ("Read", "Grep", "Glob"))
    def test_gemini_declarations_format(self):
        decls = gemini_fs_declarations()
        self.assertEqual({d["name"] for d in decls}, {"Read", "Grep", "Glob"})
        for d in decls:
            self.assertIn("description", d)
            self.assertIn("parameters", d)
    def test_gemini_types_are_uppercase(self):
        decls = gemini_fs_declarations()
        for d in decls:
            params = d["parameters"]
            self.assertEqual(params["type"], "OBJECT")
            for prop in params["properties"].values():
                self.assertTrue(prop["type"].isupper(), prop)
    def test_anthropic_tools_format(self):
        tools = anthropic_fs_tools()
        self.assertEqual(len(tools), 3)
        for t in tools:
            self.assertIn("name", t)
            self.assertIn("description", t)
            self.assertIn("input_schema", t)
            self.assertEqual(t["input_schema"]["type"], "object")
    def test_openai_tools_format(self):
        tools = openai_fs_tools()
        self.assertEqual(len(tools), 3)
        for t in tools:
            self.assertEqual(t["type"], "function")
            self.assertIn("parameters", t["function"])
class TestExecute(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "rapport.tex").write_text(
            "ligne un\nligne deux\nmot-cle ici\nligne quatre\n",
            encoding="utf-8",
        )
        (self.root / "src").mkdir()
        (self.root / "src" / "main.py").write_text(
            "def f():\n    return 42\n", encoding="utf-8",
        )
        (self.root / "_secrets").mkdir()
        (self.root / "_secrets" / "cle.txt").write_text("TOPSECRET", encoding="utf-8")
        (self.root / "config.env").write_text("API_KEY=xxx", encoding="utf-8")
    def tearDown(self):
        self._tmp.cleanup()
    def test_read_text_file_numbered(self):
        res = execute_fs_tool("Read", {"path": "rapport.tex"}, self.root)
        self.assertTrue(res.ok)
        self.assertIn("ligne un", res.text)
        self.assertIn("1\t", res.text)
        self.assertIsNone(res.document)
    def test_read_offset_limit(self):
        res = execute_fs_tool(
            "Read", {"path": "rapport.tex", "offset": 2, "limit": 1}, self.root,
        )
        self.assertTrue(res.ok)
        self.assertIn("ligne deux", res.text)
        self.assertNotIn("ligne quatre", res.text)
    def test_read_missing_file_soft_error(self):
        res = execute_fs_tool("Read", {"path": "absent.txt"}, self.root)
        self.assertFalse(res.ok)
        self.assertIn("introuvable", res.text.lower())
    def test_read_traversal_rejected(self):
        res = execute_fs_tool("Read", {"path": "../../etc/passwd"}, self.root)
        self.assertFalse(res.ok)
        self.assertIn("hors du dossier", res.text.lower())
    def test_read_secret_dir_refused(self):
        res = execute_fs_tool("Read", {"path": "_secrets/cle.txt"}, self.root)
        self.assertFalse(res.ok)
        self.assertIn("sensible", res.text.lower())
    def test_read_env_file_refused(self):
        res = execute_fs_tool("Read", {"path": "config.env"}, self.root)
        self.assertFalse(res.ok)
        self.assertIn("sensible", res.text.lower())
    def test_read_pdf_returns_document(self):
        (self.root / "sujet.pdf").write_bytes(b"%PDF-1.4\n%fake pdf bytes")
        res = execute_fs_tool("Read", {"path": "sujet.pdf"}, self.root)
        self.assertTrue(res.ok)
        self.assertIsNotNone(res.document)
        self.assertEqual(res.document["media_type"], "application/pdf")
        self.assertEqual(res.document["label"], "sujet.pdf")
        self.assertIn("joint", res.text.lower())
    def test_read_binary_file_soft_error(self):
        (self.root / "data.dat").write_bytes(b"\x00\x01\x02binary\x00")
        res = execute_fs_tool("Read", {"path": "data.dat"}, self.root)
        self.assertFalse(res.ok)
    def test_grep_finds_match(self):
        res = execute_fs_tool("Grep", {"pattern": "mot-cle"}, self.root)
        self.assertTrue(res.ok)
        self.assertIn("rapport.tex:3", res.text)
    def test_grep_no_match(self):
        res = execute_fs_tool("Grep", {"pattern": "introuvableXYZ"}, self.root)
        self.assertTrue(res.ok)
        self.assertIn("aucune correspondance", res.text.lower())
    def test_grep_invalid_regex_soft_error(self):
        res = execute_fs_tool("Grep", {"pattern": "[unclosed"}, self.root)
        self.assertFalse(res.ok)
        self.assertIn("régulière", res.text.lower())
    def test_grep_ignore_case(self):
        res = execute_fs_tool(
            "Grep", {"pattern": "MOT-CLE", "ignore_case": True}, self.root,
        )
        self.assertTrue(res.ok)
        self.assertIn("rapport.tex:3", res.text)
    def test_grep_skips_secrets(self):
        res = execute_fs_tool("Grep", {"pattern": "TOPSECRET"}, self.root)
        self.assertTrue(res.ok)
        self.assertIn("aucune correspondance", res.text.lower())
    def test_glob_finds_files(self):
        res = execute_fs_tool("Glob", {"pattern": "**/*.py"}, self.root)
        self.assertTrue(res.ok)
        self.assertIn("src/main.py", res.text)
    def test_glob_no_match(self):
        res = execute_fs_tool("Glob", {"pattern": "**/*.rs"}, self.root)
        self.assertTrue(res.ok)
        self.assertIn("aucun fichier", res.text.lower())
    def test_glob_skips_secret_dir(self):
        res = execute_fs_tool("Glob", {"pattern": "**/*.txt"}, self.root)
        self.assertTrue(res.ok)
        self.assertNotIn("_secrets", res.text)
    def test_unknown_tool_soft_error(self):
        res = execute_fs_tool("Bash", {"cmd": "rm -rf /"}, self.root)
        self.assertFalse(res.ok)
        self.assertIn("inconnu", res.text.lower())
    def test_missing_required_param_soft_error(self):
        res = execute_fs_tool("Read", {}, self.root)
        self.assertFalse(res.ok)
        self.assertIsInstance(res, FsToolResult)
    def test_execute_never_raises(self):
        for name in ("Read", "Grep", "Glob", "Nope"):
            try:
                execute_fs_tool(name, {"path": None, "pattern": None}, self.root)
            except Exception as e:
                self.fail(f"execute_fs_tool({name}) a levé : {e}")
class TestToolCallMarker(unittest.TestCase):
    def test_label_read(self):
        self.assertEqual(
            tool_call_label("Read", {"path": "rapport.tex"}), "rapport.tex")
    def test_label_grep_glob(self):
        self.assertEqual(tool_call_label("Grep", {"pattern": "def foo"}), "def foo")
        self.assertEqual(tool_call_label("Glob", {"pattern": "**/*.py"}), "**/*.py")
    def test_label_missing_arg(self):
        self.assertEqual(tool_call_label("Read", {}), "?")
        self.assertEqual(tool_call_label("Read", None), "?")
    def test_marker_roundtrip(self):
        import json as _json
        m = tool_call_marker("Read", "rapport.tex", True)
        self.assertTrue(m.startswith(TOOL_MARKER_OPEN))
        self.assertTrue(m.endswith(TOOL_MARKER_CLOSE))
        inner = m[len(TOOL_MARKER_OPEN):-len(TOOL_MARKER_CLOSE)]
        self.assertEqual(
            _json.loads(inner),
            {"tool": "Read", "label": "rapport.tex", "ok": True},
        )
    def test_marker_ok_false(self):
        import json as _json
        m = tool_call_marker("Grep", "xyz", False)
        d = _json.loads(m[len(TOOL_MARKER_OPEN):-len(TOOL_MARKER_CLOSE)])
        self.assertFalse(d["ok"])
    def test_marker_single_line(self):
        self.assertNotIn("\n", tool_call_marker("Read", "a/b/c.tex", True))
    def test_marker_delimiters_distinct_from_parser_close_tag(self):
        self.assertNotIn("<<<END>>>", TOOL_MARKER_OPEN)
        self.assertNotIn("<<<END>>>", TOOL_MARKER_CLOSE)
if __name__ == "__main__":
    unittest.main(verbosity=2)