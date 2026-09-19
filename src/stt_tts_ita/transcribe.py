"""Trascrizione con timestamp tramite whisper.cpp (binario nativo whisper-cli).

Non usa librerie Python: invoca `whisper-cli` e legge l'output JSON/SRT.
Modello multilingua (small/base) con `-l it` per forzare l'italiano.
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .audio import to_wav16k
from .config import Config

_TS_RE = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d{1,3})")


@dataclass
class Segment:
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class Transcript:
    segments: list[Segment] = field(default_factory=list)
    language: str = "it"
    source: str = ""

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments).strip()

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "language": self.language,
            "text": self.text,
            "segments": [
                {
                    "start": round(s.start, 3),
                    "end": round(s.end, 3),
                    "text": s.text.strip(),
                }
                for s in self.segments
            ],
        }


def parse_timestamp(value: str) -> float:
    """Converte 'HH:MM:SS,mmm' (o con punto) in secondi float."""
    m = _TS_RE.search(value or "")
    if not m:
        return 0.0
    h, mm, ss, frac = m.groups()
    millis = int(frac.ljust(3, "0")[:3])
    return int(h) * 3600 + int(mm) * 60 + int(ss) + millis / 1000.0


def transcript_from_whisper_json(payload: dict, source: str = "") -> Transcript:
    language = str(payload.get("result", {}).get("language", "it"))
    segments: list[Segment] = []
    for item in payload.get("transcription", []):
        ts = item.get("timestamps", {})
        segments.append(
            Segment(
                start=parse_timestamp(ts.get("from", "")),
                end=parse_timestamp(ts.get("to", "")),
                text=item.get("text", "").strip(),
            )
        )
    return Transcript(segments=segments, language=language, source=source)


def transcribe(
    audio_path: str | Path,
    cfg: Config,
    output_prefix: str | Path | None = None,
    keep_wav: bool = False,
    extra_args: list[str] | None = None,
) -> Transcript:
    """Trascrive un file audio restituendo i segmenti con timestamp.

    Se `output_prefix` è indicato, whisper-cli scrive anche .json/.srt/.txt.
    """
    whisper_cli = cfg.resolve_whisper_cli()
    model = cfg.resolve_model()
    audio_path = Path(audio_path)

    tmpdir: tempfile.TemporaryDirectory | None = None
    if audio_path.suffix.lower() == ".wav" and _is_16k_mono(audio_path, cfg.ffmpeg):
        wav = audio_path
    else:
        tmpdir = tempfile.TemporaryDirectory(prefix="stt_tts_")
        wav = to_wav16k(audio_path, Path(tmpdir.name) / "input.wav", cfg.ffmpeg)

    try:
        if output_prefix is None:
            prefix = Path(tmpdir.name if tmpdir else wav.parent) / "transcript"
        else:
            prefix = Path(output_prefix)
        prefix.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            whisper_cli,
            "-m",
            model,
            "-l",
            "auto" if cfg.language.lower() in ("", "auto") else cfg.language,
            "-t",
            str(cfg.threads),
            "-oj",
            "-of",
            str(prefix),
            "--no-prints",
        ]
        if extra_args:
            cmd.extend(extra_args)
        cmd.append(str(wav))

        cp = subprocess.run(cmd, capture_output=True, text=True)
        json_path = prefix.with_suffix(".json")
        if cp.returncode != 0 or not json_path.is_file():
            raise RuntimeError(
                "whisper-cli è terminato con errore:\n" + (cp.stderr or cp.stdout)
            )

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        return transcript_from_whisper_json(payload, source=str(audio_path))
    finally:
        if tmpdir is not None:
            if keep_wav:
                target = Path(output_prefix or audio_path).with_suffix(".16k.wav")
                try:
                    target.write_bytes(wav.read_bytes())
                except OSError:
                    pass
            tmpdir.cleanup()


def _is_16k_mono(path: Path, ffmpeg: str) -> bool:
    """Verifica rapida che il WAV sia già 16 kHz mono (evita riconversione)."""
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    cp = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0:
        return False
    try:
        stream = json.loads(cp.stdout)["streams"][0]
        return int(stream["sample_rate"]) == 16000 and int(stream["channels"]) == 1
    except (KeyError, ValueError, IndexError, json.JSONDecodeError):
        return False
