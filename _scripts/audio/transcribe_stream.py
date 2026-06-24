import logging
import os
import sys
from pathlib import Path
logger = logging.getLogger(__name__)
def _setup_nvidia_dlls() -> list[str]:
    site_packages = None
    for p in sys.path:
        if "site-packages" in p and os.path.isdir(p):
            site_packages = p
            break
    if not site_packages:
        return []
    nvidia_dir = os.path.join(site_packages, "nvidia")
    if not os.path.isdir(nvidia_dir):
        return []
    dll_dirs: list[str] = []
    for root, _, _ in os.walk(nvidia_dir):
        if os.path.basename(root) in ("bin", "lib"):
            dll_dirs.append(root)
    if not dll_dirs:
        return []
    current = os.environ.get("PATH", "")
    new_dirs = [d for d in dll_dirs if d not in current]
    if new_dirs:
        os.environ["PATH"] = ";".join(new_dirs) + ";" + current
    if hasattr(os, "add_dll_directory"):
        for d in dll_dirs:
            try:
                os.add_dll_directory(d)
            except OSError:
                pass
    return dll_dirs
_setup_nvidia_dlls()
from faster_whisper import WhisperModel
class WhisperTranscriber:
    DEFAULT_MODEL_SIZE = "large-v3"
    DEFAULT_DEVICE = "auto"
    DEFAULT_COMPUTE_TYPE = "auto"
    DEFAULT_LANGUAGE = "fr"
    DEFAULT_VAD_MIN_SILENCE_MS = 500
    def __init__(
        self,
        model_size: str = DEFAULT_MODEL_SIZE,
        device: str = DEFAULT_DEVICE,
        compute_type: str = DEFAULT_COMPUTE_TYPE,
    ):
        if device == "auto" or compute_type == "auto":
            d, c = self._detect_device_compute()
            if device == "auto":
                device = d
            if compute_type == "auto":
                compute_type = c
        logger.info(
            "Chargement Whisper %s (device=%s, compute=%s)...",
            model_size, device, compute_type,
        )
        try:
            self._model = WhisperModel(
                model_size, device=device, compute_type=compute_type
            )
        except (RuntimeError, OSError) as e:
            if device != "cpu":
                logger.warning(
                    "Init CUDA Whisper a echoue (%s) : fallback CPU.",
                    e.__class__.__name__,
                )
                self._model = WhisperModel(
                    model_size, device="cpu", compute_type="int8"
                )
            else:
                raise
        logger.info("Whisper pret.")
    @staticmethod
    def _detect_device_compute() -> tuple[str, str]:
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                return "cuda", "int8_float16"
        except Exception:
            pass
        return "cpu", "int8"
    def transcribe(
        self,
        wav_path: Path,
        language: str = DEFAULT_LANGUAGE,
    ) -> tuple[str, float]:
        segments, info = self._model.transcribe(
            str(wav_path),
            language=language,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": self.DEFAULT_VAD_MIN_SILENCE_MS,
            },
        )
        text = " ".join(seg.text.strip() for seg in segments)
        return text, info.duration