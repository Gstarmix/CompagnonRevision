import os
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "_scripts"))
sys.path.insert(0, str(ROOT / "_scripts" / "dialogue"))
sys.path.insert(0, str(ROOT / "_scripts" / "quota"))
sys.path.insert(0, str(ROOT / "_scripts" / "web"))
from prompt_builder import (
    SessionContext,
    build_workspace_summary,
    detect_workspace_type,
    slugify_workspace,
)
class TestSlugifyWorkspace(unittest.TestCase):
    def test_basename_kebab(self):
        self.assertEqual(
            slugify_workspace("/home/user/code/Compagnon_Revision"),
            "compagnon-revision",
        )
    def test_windows_path(self):
        self.assertEqual(
            slugify_workspace(r"C:\Users\Gstar\Documents\RoleplayOverlay"),
            "roleplayoverlay",
        )
    def test_short_name(self):
        self.assertEqual(slugify_workspace("/tmp/CV"), "cv")
    def test_empty_fallback(self):
        slug = slugify_workspace("")
        self.assertIn(slug, ("workspace", ""))
class TestDetectWorkspaceType(unittest.TestCase):
    def _mkfile(self, root: Path, rel: str, content: str = "x") -> None:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    def test_code_heavy(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            for i in range(10):
                self._mkfile(r, f"src/mod_{i}.py")
            self._mkfile(r, "README.md")
            self.assertEqual(detect_workspace_type(r), "code")
    def test_doc_heavy(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            for i in range(8):
                self._mkfile(r, f"notes/chap_{i}.md")
            self._mkfile(r, "main.py")
            self.assertEqual(detect_workspace_type(r), "doc")
    def test_mixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            for i in range(5):
                self._mkfile(r, f"src/{i}.py")
            for i in range(5):
                self._mkfile(r, f"docs/{i}.md")
            self.assertEqual(detect_workspace_type(r), "mixed")
    def test_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(detect_workspace_type(Path(tmp)), "mixed")
class TestBuildWorkspaceSummary(unittest.TestCase):
    def test_basic_summary_includes_tree_and_pivots(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            (r / "README.md").write_text(
                "# My Project\n\nThis project does X.\n", encoding="utf-8",
            )
            (r / "src").mkdir()
            (r / "src" / "main.py").write_text("print('hi')\n", encoding="utf-8")
            (r / ".git").mkdir()
            (r / ".git" / "config").write_text("[core]", encoding="utf-8")
            summary = build_workspace_summary(r)
            self.assertIn("My Project", summary)
            self.assertIn("main.py", summary)
            self.assertNotIn(".git", summary.split("## Fichiers-pivots")[0])
    def test_focus_subdir(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = Path(tmp)
            (r / "src" / "deep").mkdir(parents=True)
            (r / "src" / "deep" / "focused.py").write_text("x", encoding="utf-8")
            (r / "other" / "other.py").parent.mkdir(parents=True, exist_ok=True)
            (r / "other" / "other.py").write_text("y", encoding="utf-8")
            summary = build_workspace_summary(r, focus_subdir="src/deep")
            self.assertIn("focused.py", summary)
            self.assertIn("Focus", summary)
class TestSessionContextWorkspace(unittest.TestCase):
    def test_workspace_root_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = SessionContext(
                matiere="WORKSPACE",
                type="DIR",
                num="test-ws",
                exo="full",
                workspace_root=Path(tmp),
            )
            self.assertIsNotNone(ctx.workspace_root)
            self.assertEqual(ctx.matiere, "WORKSPACE")
class TestBuildSessionIdWorkspace(unittest.TestCase):
    def test_workspace_id_format(self):
        from app import _build_session_id
        ctx = SessionContext(
            matiere="WORKSPACE",
            type="DIR",
            num="compagnon-revision",
            exo="full",
            workspace_root=Path.cwd(),
        )
        sid = _build_session_id(
            ctx, mode="workspace",
            colle_format="mixte", corrige_anchor="aucun",
        )
        self.assertIn("WORKSPACE_compagnon-revision_full", sid)
        self.assertTrue(sid.endswith("_workspace_mixte_aucun"))
class TestResolveSessionId(unittest.TestCase):
    def test_default_appends_1(self):
        from app import _resolve_session_id
        with tempfile.TemporaryDirectory() as tmp:
            sid = _resolve_session_id("base", sessions_dir=Path(tmp))
            self.assertEqual(sid, "base_1")
    def test_force_new_finds_next_available(self):
        from app import _resolve_session_id
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "base_1.json").write_text("{}", encoding="utf-8")
            sid = _resolve_session_id(
                "base", force_new_session=True, sessions_dir=root,
            )
            self.assertEqual(sid, "base_2")
    def test_force_new_skips_existing_chain(self):
        from app import _resolve_session_id
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for n in (1, 2, 3, 5):
                (root / f"base_{n}.json").write_text("{}", encoding="utf-8")
            sid = _resolve_session_id(
                "base", force_new_session=True, sessions_dir=root,
            )
            self.assertEqual(sid, "base_4")
    def test_no_force_returns_1_even_if_exists(self):
        from app import _resolve_session_id
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "base_1.json").write_text("{}", encoding="utf-8")
            sid = _resolve_session_id("base", sessions_dir=root)
            self.assertEqual(sid, "base_1")
class TestRuntimeSettingsWorkspace(unittest.TestCase):
    def test_default_workspace_presets_empty(self):
        from runtime_settings import _default_settings
        d = _default_settings()
        self.assertEqual(d["workspace_presets"], [])
        self.assertEqual(d["workspace_excludes"], [])
        self.assertEqual(d["last_selection"]["workspace_root"], "")
        self.assertEqual(d["last_selection"]["workspace_focus_subdir"], "")
    def test_merge_workspace_lists(self):
        from runtime_settings import _merge_with_defaults
        raw = {
            "workspace_presets": ["C:\\foo", "C:\\bar", "C:\\foo"],
            "workspace_excludes": ["_archives", "*.log"],
        }
        out = _merge_with_defaults(raw)
        self.assertEqual(out["workspace_presets"], ["C:\\foo", "C:\\bar"])
        self.assertEqual(out["workspace_excludes"], ["_archives", "*.log"])
class TestStartSessionWorkspaceIntegration(unittest.TestCase):
    def test_start_session_workspace_returns_200_json(self):
        from app import app, _state, _state_lock, SESSIONS_DIR
        with _state_lock:
            globals()["_state"] = None
        client = app.test_client()
        created_session_id = None
        with tempfile.TemporaryDirectory() as tmp:
            r = client.post("/api/start_session", json={
                "matiere": "WORKSPACE",
                "type": "DIR",
                "num": "_",
                "exo": "full",
                "workspace_root": tmp,
                "generate_invented_pdf": True,
            })
            try:
                self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
                self.assertIn("application/json", r.content_type)
                data = r.get_json()
                self.assertEqual(data["mode"], "workspace")
                self.assertIn("WORKSPACE", data["session_id"])
                self.assertTrue(
                    data["session_id"].endswith("_workspace_mixte_aucun_1"),
                    data["session_id"],
                )
                self.assertEqual(data["corrige_anchor"], "aucun")
                created_session_id = data["session_id"]
            finally:
                if created_session_id:
                    artifact = SESSIONS_DIR / f"{created_session_id}.json"
                    if artifact.exists():
                        artifact.unlink()
                with _state_lock:
                    globals()["_state"] = None
if __name__ == "__main__":
    unittest.main()