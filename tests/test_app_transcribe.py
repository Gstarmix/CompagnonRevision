import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
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
class _FakeTranscriber:
    def transcribe(self, wav_path):
        return ("Bonjour, ceci est un test.", 1.42)
class TestApiTranscribe(unittest.TestCase):
    def setUp(self):
        import app
        app._transcriber = None
        self.client = app.app.test_client()
    def tearDown(self):
        import app
        app._transcriber = None
    def test_missing_audio_field_returns_400(self):
        r = self.client.post("/api/transcribe", data={})
        self.assertEqual(r.status_code, 400)
        body = r.get_json()
        self.assertIn("audio", body.get("error", "").lower())
    def test_empty_filename_returns_400(self):
        r = self.client.post(
            "/api/transcribe",
            data={"audio": (io.BytesIO(b""), "")},
            content_type="multipart/form-data",
        )
        self.assertEqual(r.status_code, 400)
    def test_successful_transcription_returns_text(self):
        with patch("app._get_transcriber", return_value=_FakeTranscriber()):
            r = self.client.post(
                "/api/transcribe",
                data={"audio": (io.BytesIO(b"fake-webm-bytes"), "rec.webm")},
                content_type="multipart/form-data",
            )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        body = r.get_json()
        self.assertEqual(body["text"], "Bonjour, ceci est un test.")
        self.assertAlmostEqual(body["duration_seconds"], 1.42, places=2)
    def test_whisper_load_failure_returns_500(self):
        def _raise():
            raise RuntimeError("CUDA OOM")
        with patch("app._get_transcriber", side_effect=_raise):
            r = self.client.post(
                "/api/transcribe",
                data={"audio": (io.BytesIO(b"x"), "rec.webm")},
                content_type="multipart/form-data",
            )
        self.assertEqual(r.status_code, 500)
        body = r.get_json()
        self.assertEqual(body["error"], "whisper_load_failed")
        self.assertIn("CUDA OOM", body["detail"])
    def test_transcribe_failure_returns_500(self):
        class FailTranscriber:
            def transcribe(self, p):
                raise ValueError("decode error")
        with patch("app._get_transcriber", return_value=FailTranscriber()):
            r = self.client.post(
                "/api/transcribe",
                data={"audio": (io.BytesIO(b"x"), "rec.webm")},
                content_type="multipart/form-data",
            )
        self.assertEqual(r.status_code, 500)
        body = r.get_json()
        self.assertEqual(body["error"], "transcribe_failed")
        self.assertIn("decode error", body["detail"])
    def test_text_is_stripped(self):
        class WhitespaceTranscriber:
            def transcribe(self, p):
                return ("   bonjour   ", 0.5)
        with patch("app._get_transcriber", return_value=WhitespaceTranscriber()):
            r = self.client.post(
                "/api/transcribe",
                data={"audio": (io.BytesIO(b"x"), "rec.webm")},
                content_type="multipart/form-data",
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["text"], "bonjour")
if __name__ == "__main__":
    unittest.main(verbosity=2)