"""Registro dei motori TTS disponibili."""

from __future__ import annotations

from .base import TTSError, TTSEngine
from .espeak import EspeakEngine
from .http_tts import HttpTTSEngine
from .piper import PiperEngine

ENGINES = ("espeak", "kokoro", "piper")


def build_engine(
    name: str,
    *,
    espeak_binary: str = "espeak-ng",
    url: str = "http://localhost:7860",
    mode: str = "openai",
    voice: str | None = None,
    speed: float = 1.0,
    piper_binary: str | None = None,
    piper_models_dir: str | None = None,
) -> TTSEngine:
    """Crea un motore TTS per nome. `auto` sceglie: Kokoro se raggiungibile,
    altrimenti Piper (se disponibile, es. nel binario autocontenuto),
    altrimenti espeak."""
    name = (name or "auto").lower()
    if name == "auto":
        kokoro = HttpTTSEngine(base_url=url, mode=mode, **({"voice": voice} if voice else {}))
        if kokoro.available():
            return kokoro
        piper = PiperEngine(**({"voice": voice} if voice else {}))
        if piper.available():
            return piper
        return EspeakEngine(binary=espeak_binary, **({"voice": voice} if voice else {}))
    if name == "kokoro":
        kwargs = {"base_url": url, "mode": mode, "speed": speed}
        if voice:
            kwargs["voice"] = voice
        return HttpTTSEngine(**kwargs)
    if name == "espeak":
        kwargs = {"binary": espeak_binary, "speed": int(speed * 150) or 150}
        if voice:
            kwargs["voice"] = voice
        return EspeakEngine(**kwargs)
    if name == "piper":
        kwargs = {"speed": speed}
        if piper_binary:
            kwargs["binary"] = piper_binary
        if piper_models_dir:
            kwargs["models_dir"] = piper_models_dir
        if voice:
            kwargs["voice"] = voice
        return PiperEngine(**kwargs)
    raise TTSError(f"Motore TTS sconosciuto: {name}. Disponibili: {', '.join(ENGINES)}")


__all__ = [
    "TTSEngine",
    "TTSError",
    "EspeakEngine",
    "HttpTTSEngine",
    "PiperEngine",
    "build_engine",
    "ENGINES",
]
