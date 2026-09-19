"""Gestione input audio: conversione a 16 kHz mono WAV per Whisper.

Whisper.cpp richiede PCM 16-bit, 16 kHz, mono. ffmpeg decodifica m4a/wav/mp3
(ed eventuali altri formati supportati) e riscrive nel formato atteso.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

AUDIO_EXTENSIONS = {".m4a", ".wav", ".mp3", ".ogg", ".oga", ".flac", ".aac", ".opus", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v"}
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS


class AudioError(RuntimeError):
    pass


def is_video(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def probe_duration(path: Path, ffmpeg: str = "ffmpeg") -> float:
    """Durata in secondi tramite ffprobe (fallback: ffmpeg -f null)."""
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    cp = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ]
    )
    if cp.returncode == 0 and cp.stdout.strip():
        try:
            return float(json.loads(cp.stdout)["format"]["duration"])
        except (KeyError, ValueError, json.JSONDecodeError):
            pass
    return 0.0


def to_wav16k(
    src: str | Path,
    dst: str | Path | None = None,
    ffmpeg: str = "ffmpeg",
) -> Path:
    """Converte un file audio in WAV 16 kHz mono PCM s16le.

    Restituisce il percorso del WAV generato.
    """
    src = Path(src)
    if not src.is_file():
        raise AudioError(f"File di input non trovato: {src}")
    if src.suffix.lower() not in MEDIA_EXTENSIONS:
        raise AudioError(
            f"Formato non supportato: {src.suffix}. Attesi: "
            f"{', '.join(sorted(MEDIA_EXTENSIONS))}"
        )

    if dst is None:
        dst = src.with_name(src.stem + ".16k.wav")
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    cp = _run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(dst),
        ]
    )
    if cp.returncode != 0 or not dst.is_file():
        raise AudioError(f"Conversione fallita per {src}:\n{cp.stderr.strip()}")
    return dst


def has_audio_stream(path: str | Path, ffmpeg: str = "ffmpeg") -> bool:
    """True se il file contiene almeno una traccia audio."""
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    cp = _run(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=index",
            "-of",
            "json",
            str(path),
        ]
    )
    if cp.returncode != 0:
        return False
    try:
        return bool(json.loads(cp.stdout).get("streams"))
    except json.JSONDecodeError:
        return False


def dub_video(
    video_path: str | Path,
    audio_path: str | Path,
    out_path: str | Path,
    ffmpeg: str = "ffmpeg",
    video_codec: str = "copy",
    audio_codec: str = "aac",
    audio_bitrate: str = "192k",
) -> Path:
    """Sostituisce la traccia audio di un video con `audio_path`.

    - Il video non viene ricodificato (`-c:v copy`) quando possibile.
    - Se l'audio è più corto del video viene riempito con silenzio (`apad`);
      se è più lungo viene tagliato alla durata del video (`-t`).
    """
    video_path = Path(video_path)
    audio_path = Path(audio_path)
    out_path = Path(out_path)
    if not video_path.is_file():
        raise AudioError(f"Video non trovato: {video_path}")
    if not audio_path.is_file():
        raise AudioError(f"Audio TTS non trovato: {audio_path}")
    if not has_audio_stream(video_path, ffmpeg):
        raise AudioError(f"Il file non contiene tracce audio: {video_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(video_path, ffmpeg)

    cmd = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        video_codec,
        "-c:a",
        audio_codec,
        "-b:a",
        audio_bitrate,
        "-af",
        "apad",
    ]
    if duration > 0:
        cmd += ["-t", f"{duration:.3f}"]
    else:
        cmd += ["-shortest"]
    if out_path.suffix.lower() in {".mp4", ".m4v", ".mov"}:
        cmd += ["-movflags", "+faststart"]
    cmd.append(str(out_path))

    cp = _run(cmd)
    if cp.returncode != 0 or not out_path.is_file():
        raise AudioError(f"Dubbing fallito per {video_path}:\n{cp.stderr.strip()}")
    return out_path
