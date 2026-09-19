"""Motore TTS locale basato su espeak-ng (open source, offline, CPU).

Qualità sintetica/robotica ma sempre disponibile: usato come fallback garantito
quando Kokoro non è raggiungibile.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .base import TTSError, TTSEngine


class EspeakEngine(TTSEngine):
    name = "espeak"

    def __init__(
        self,
        binary: str = "espeak-ng",
        voice: str = "it",
        speed: int = 150,
        pitch: int = 50,
    ):
        self.binary = binary
        self.voice = voice
        self.speed = speed
        self.pitch = pitch

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def synthesize(self, text: str, out_path: str | Path, **kwargs) -> Path:
        if not self.available():
            raise TTSError(f"espeak-ng non trovato: {self.binary}")
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        voice = kwargs.get("voice") or self.voice
        speed = kwargs.get("speed") or self.speed
        pitch = kwargs.get("pitch") or self.pitch
        cp = subprocess.run(
            [
                self.binary,
                "-v",
                str(voice),
                "-s",
                str(speed),
                "-p",
                str(pitch),
                "-w",
                str(out_path),
            ],
            input=text,
            capture_output=True,
            text=True,
        )
        if cp.returncode != 0 or not out_path.is_file():
            raise TTSError("espeak-ng è terminato con errore:\n" + cp.stderr.strip())
        return out_path
