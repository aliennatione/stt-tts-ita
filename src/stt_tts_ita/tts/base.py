"""Interfaccia comune per i motori TTS."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class TTSError(RuntimeError):
    pass


class TTSEngine(ABC):
    """Motore di sintesi vocale. Restituisce il percorso del WAV generato."""

    name: str = "base"

    @abstractmethod
    def synthesize(self, text: str, out_path: str | Path, **kwargs) -> Path:
        raise NotImplementedError

    @abstractmethod
    def available(self) -> bool:
        raise NotImplementedError

    def synthesize_segments(
        self,
        segments,
        output_dir: str | Path,
        stem: str = "tts",
        **kwargs,
    ) -> Path:
        """Sintetizza l'intero testo come singolo file (default)."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        text = " ".join(s.text.strip() for s in segments).strip()
        if not text:
            raise TTSError("Nessun testo da sintetizzare.")
        return self.synthesize(text, output_dir / f"{stem}.wav", **kwargs)
