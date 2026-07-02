"""
transcribe_stream.py : wrapper léger autour de faster-whisper.

Phase A : transcription **non-streaming**, le WAV complet est passé au
modèle qui retourne le texte intégral. Le streaming Whisper viendra en
Phase B si la latence du non-streaming s'avère gênante en pratique
(à mesurer d'abord).

Modèle par défaut : ``large-v3`` sur CUDA en ``int8_float16``. Tient dans
les 6 Go VRAM de la RTX 2060 et donne une qualité FR excellente. Si
CUDA n'est pas dispo (DLL cuBLAS introuvable, drivers absents, etc.),
fallback automatique sur CPU en ``int8``.
Cf. pattern d'Arsenal_Arguments/whisper_engine.ps1 et
``COURS/_scripts/transcribe.py``.

Cf. ARCHITECTURE.md §7.2.
"""

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _setup_nvidia_dlls() -> list[str]:
    """Ajoute les DLL des paquets ``nvidia-cublas-cu12`` et
    ``nvidia-cudnn-cu12`` (installés via pip dans ``site-packages/nvidia/``)
    au PATH et à la liste des DLL dirs Python. Sans ça, faster-whisper
    sur CUDA échoue avec ``Library cublas64_12.dll is not found or cannot
    be loaded``. À appeler **avant** l'import de ``faster_whisper``.
    """
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


# CRITIQUE : setup nvidia DLLs AVANT d'importer faster_whisper, sinon
# l'init du modèle CUDA crash sur cublas64_12.dll missing.
_setup_nvidia_dlls()

from faster_whisper import WhisperModel  # noqa: E402


class WhisperTranscriber:
    """Wrapper non-streaming autour de ``faster_whisper.WhisperModel``.

    Le modèle est chargé en VRAM dans le constructeur : coût ~3 Go + quelques
    secondes au premier appel (ou plus selon la taille). Une instance est
    censée vivre toute la session : NE PAS réinstancier par WAV.
    """

    DEFAULT_MODEL_SIZE = "large-v3"
    DEFAULT_DEVICE = "auto"      # auto = cuda si dispo, sinon cpu
    DEFAULT_COMPUTE_TYPE = "auto"  # auto = int8_float16 (cuda) / int8 (cpu)
    DEFAULT_LANGUAGE = "fr"
    DEFAULT_VAD_MIN_SILENCE_MS = 500

    def __init__(
        self,
        model_size: str = DEFAULT_MODEL_SIZE,
        device: str = DEFAULT_DEVICE,
        compute_type: str = DEFAULT_COMPUTE_TYPE,
    ):
        # Auto-détection device/compute si demandé.
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
            # CUDA peut échouer même quand `get_cuda_device_count() > 0` :
            # cuBLAS/cuDNN bibliothèques absentes du runtime, drivers
            # mismatch, etc. Fallback explicite sur CPU plutôt que de
            # remonter une erreur opaque côté UI.
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
        """Auto-détection GPU/CPU + compute_type optimal."""
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
        """Transcrit ``wav_path`` et retourne ``(texte, duree_audio_secondes)``.

        VAD activé avec un seuil de silence de 500 ms : coupe les blancs trop
        longs en début/fin/inter-mots, améliore la qualité du joining. Le
        texte retourné est la concaténation des segments séparés par un
        espace, après ``strip()`` de chacun.
        """
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
