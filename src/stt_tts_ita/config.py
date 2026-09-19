"""Configurazione centrale del progetto STT+TTS Italiano.

Tutte le dipendenze esterne (binari nativi) sono risolte da qui, con override
via variabili d'ambiente. Nessuna dipendenza Python obbligatoria: l'orchestratore
richiama binari/test esterni via subprocess.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

def _discover_root() -> Path:
    """Individua la root del progetto, con fallback per esecuzione da zipapp.

    Ordine: STT_TTS_ROOT → cartella del sorgente → CWD. La CWD è necessaria
    quando il codice gira da un archivio .pyz, dove `__file__` è interno allo zip.
    """
    env = os.environ.get("STT_TTS_ROOT")
    if env:
        return Path(env).resolve()
    candidates: list[Path] = []
    try:
        candidates.append(Path(__file__).resolve().parents[2])
    except IndexError:
        pass
    candidates.append(Path.cwd().resolve())
    for candidate in candidates:
        if (candidate / "scripts").is_dir() or (candidate / "models").is_dir():
            return candidate
    return candidates[0]


PROJECT_ROOT = _discover_root()

DEFAULT_MODEL = os.environ.get(
    "STT_TTS_MODEL",
    str(PROJECT_ROOT / "models" / "ggml-small-q5_1.bin"),
)


@dataclass
class Config:
    """Parametri di esecuzione risolti a runtime."""

    root: Path = field(default_factory=lambda: PROJECT_ROOT)
    model: str = field(default_factory=lambda: DEFAULT_MODEL)
    language: str = field(default_factory=lambda: os.environ.get("STT_TTS_LANG", "auto"))
    threads: int = field(
        default_factory=lambda: int(os.environ.get("STT_TTS_THREADS", "4"))
    )
    ffmpeg: str = field(default_factory=lambda: os.environ.get("STT_TTS_FFMPEG", "ffmpeg"))
    argos_cmd: str = field(
        default_factory=lambda: os.environ.get("STT_TTS_ARGOS_CMD", "argos-translate")
    )
    whisper_cli: str = field(
        default_factory=lambda: os.environ.get(
            "STT_TTS_WHISPER_CLI", str(PROJECT_ROOT / "bin" / "whisper-cli")
        )
    )
    espeak: str = field(
        default_factory=lambda: os.environ.get("STT_TTS_ESPEAK", "espeak-ng")
    )
    kokoro_url: str = field(
        default_factory=lambda: os.environ.get("KOKORO_URL", "http://localhost:7860")
    )

    def resolve_whisper_cli(self) -> str:
        """Restituisce il percorso di whisper-cli (bundle PyInstaller, progetto, PATH).

        Nel binario autocontenuto (sys._MEIPASS) la copia estratta fa sempre
        fede: evita che un `bin/whisper-cli` vuoto/rotto nel CWD faccia fallire
        l'esecuzione. Un override esplicito via STT_TTS_WHISPER_CLI ha la
        precedenza, ma solo se il file esiste davvero.
        """
        explicit = os.environ.get("STT_TTS_WHISPER_CLI")
        if explicit and Path(explicit).is_file():
            return explicit
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            bundled = Path(bundle) / "bin" / "whisper-cli"
            if bundled.is_file():
                return str(bundled)
        if Path(self.whisper_cli).is_file():
            return self.whisper_cli
        found = shutil.which("whisper-cli")
        if found:
            return found
        raise FileNotFoundError(
            "whisper-cli non trovato. Esegui scripts/setup.sh o imposta "
            "STT_TTS_WHISPER_CLI."
        )

    def resolve_model(self) -> str:
        """Restituisce il percorso del modello (env esplicito → bundle → progetto)."""
        explicit = os.environ.get("STT_TTS_MODEL")
        if explicit and Path(explicit).is_file():
            return explicit
        bundle = getattr(sys, "_MEIPASS", None)
        if bundle:
            bundled = Path(bundle) / "models" / Path(self.model).name
            if bundled.is_file():
                return str(bundled)
        if Path(self.model).is_file():
            return self.model
        raise FileNotFoundError(
            f"Modello Whisper non trovato: {self.model}. "
            f"Esegui scripts/download_model.sh."
        )

    def require(self, binary: str) -> str:
        found = shutil.which(binary)
        if not found:
            raise FileNotFoundError(
                f"Binario richiesto non trovato nel PATH: {binary}"
            )
        return found
