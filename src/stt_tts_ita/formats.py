"""Serializzazione della trascrizione: SRT, VTT, testo semplice, JSON."""

from __future__ import annotations

import json
from pathlib import Path

from .transcribe import Transcript


def _fmt_srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_vtt_time(seconds: float) -> str:
    return _fmt_srt_time(seconds).replace(",", ".")


def to_srt(transcript: Transcript) -> str:
    blocks = []
    for i, seg in enumerate(transcript.segments, start=1):
        blocks.append(
            f"{i}\n{_fmt_srt_time(seg.start)} --> {_fmt_srt_time(seg.end)}\n"
            f"{seg.text.strip()}\n"
        )
    return "\n".join(blocks)


def to_vtt(transcript: Transcript) -> str:
    lines = ["WEBVTT", ""]
    for seg in transcript.segments:
        lines.append(f"{_fmt_vtt_time(seg.start)} --> {_fmt_vtt_time(seg.end)}")
        lines.append(seg.text.strip())
        lines.append("")
    return "\n".join(lines)


def to_txt(transcript: Transcript, with_timestamps: bool = False) -> str:
    if not with_timestamps:
        return transcript.text + "\n"
    return "\n".join(
        f"[{_fmt_srt_time(s.start)} --> {_fmt_srt_time(s.end)}] {s.text.strip()}"
        for s in transcript.segments
    ) + "\n"


def write_outputs(
    transcript: Transcript,
    output_dir: str | Path,
    stem: str,
    formats: tuple[str, ...] = ("json", "srt", "vtt", "txt"),
) -> dict[str, Path]:
    """Scrive i formati richiesti e restituisce {formato: percorso}."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    writers = {
        "json": lambda: json.dumps(
            transcript.as_dict(), ensure_ascii=False, indent=2
        ),
        "srt": lambda: to_srt(transcript),
        "vtt": lambda: to_vtt(transcript),
        "txt": lambda: to_txt(transcript, with_timestamps=True),
    }
    written: dict[str, Path] = {}
    for fmt in formats:
        if fmt not in writers:
            raise ValueError(f"Formato di output sconosciuto: {fmt}")
        path = output_dir / f"{stem}.{fmt}"
        path.write_text(writers[fmt](), encoding="utf-8")
        written[fmt] = path
    return written
