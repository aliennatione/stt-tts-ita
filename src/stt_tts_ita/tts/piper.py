"""Motore TTS locale basato su Piper (voce neurale ONNX, offline).

Piper richiede glibc (onnxruntime): non è installabile su Alpine/musl → su
Debian/glibc si distribuisce il binario nativo in `bin/piper/` con le voci
italiane in `models/piper/` (vedi `scripts/setup_piper.sh`). Su Alpine il
motore non risulta disponibile e resta il fallback espeak.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..config import PROJECT_ROOT
from .base import TTSError, TTSEngine

DEFAULT_PIPER_VOICE = "it_IT-serena-medium"


class PiperEngine(TTSEngine):
    name = "piper"

    def __init__(
        self,
        *,
        binary: str | None = None,
        models_dir: str | None = None,
        voice: str = DEFAULT_PIPER_VOICE,
        speed: float = 1.0,
        length_scale: float | None = None,
    ):
        self.binary = binary
        self.models_dir = models_dir
        self.voice = voice
        self.speed = speed
        self.length_scale = length_scale

    def resolve_binary(self) -> str:
        if self.binary:
            if Path(self.binary).is_file():
                return self.binary
            found = shutil.which(self.binary)
            if found:
                return found
        env = os.environ.get("STT_TTS_PIPER_BIN")
        if env:
            if Path(env).is_file():
                return env
            found = shutil.which(env)
            if found:
                return found
        for cand in (
            PROJECT_ROOT / "bin" / "piper" / "piper",
            PROJECT_ROOT / "bin" / "piper",
        ):
            if cand.is_file():
                return str(cand)
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle and (Path(bundle) / "bin" / "piper" / "piper").is_file():
            return str(Path(bundle) / "bin" / "piper" / "piper")
        found = shutil.which("piper")
        return found or ""

    def models_path(self) -> Path:
        if self.models_dir:
            return Path(self.models_dir)
        env = os.environ.get("STT_TTS_PIPER_MODELS_DIR")
        if env:
            return Path(env)
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            bundled = Path(bundle) / "models" / "piper"
            if bundled.is_dir() and any(bundled.glob("*.onnx")):
                return bundled
        return PROJECT_ROOT / "models" / "piper"

    def resolve_model(self, voice: str | None = None) -> Path:
        name = (voice or self.voice).strip()
        if Path(name).is_file():
            return Path(name)
        stem = name[:-5] if name.lower().endswith(".onnx") else name
        base = self.models_path()
        cand = base / f"{stem}.onnx"
        if cand.is_file():
            return cand
        raise TTSError(
            f"Modello voce Piper non trovato: {cand}. Esegui "
            "scripts/setup_piper.sh oppure imposta STT_TTS_PIPER_MODELS_DIR."
        )

    def available(self) -> bool:
        if not self.resolve_binary():
            return False
        base = self.models_path()
        if not base.is_dir():
            return False
        try:
            self.resolve_model(self.voice)
            return True
        except TTSError:
            return any(base.glob("*.onnx"))

    def synthesize(self, text: str, out_path: str | Path, **kwargs) -> Path:
        binary = self.resolve_binary()
        if not binary:
            raise TTSError(
                "Binario piper non trovato. Esegui scripts/setup_piper.sh su "
                "Debian/glibc oppure imposta STT_TTS_PIPER_BIN."
            )
        model = self.resolve_model(kwargs.get("voice"))
        if not text.strip():
            raise TTSError("Nessun testo da sintetizzare.")
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        speed = kwargs.get("speed") or self.speed
        length_scale = kwargs.get("length_scale") or self.length_scale
        if length_scale is None:
            length_scale = 1.0 / speed

        cmd = [
            binary,
            "-m",
            str(model),
            "--output_file",
            str(out_path),
            "--length_scale",
            f"{length_scale:.3f}",
        ]

        env = os.environ.copy()
        bindir = str(Path(binary).resolve().parent)
        libdirs = [bindir, str(Path(bindir) / "lib")]
        existing = env.get("LD_LIBRARY_PATH", "")
        if existing:
            libdirs.append(existing)
        env["LD_LIBRARY_PATH"] = os.pathsep.join(libdirs)

        cp = subprocess.run(
            cmd, input=text, capture_output=True, text=True, env=env
        )
        if cp.returncode != 0 or not out_path.is_file():
            raise TTSError("piper è terminato con errore:\n" + cp.stderr.strip())
        return out_path