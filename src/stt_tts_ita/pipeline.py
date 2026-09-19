"""Pipeline end-to-end: audio italiano -> trascrizione con timestamp -> TTS."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .audio import dub_video, is_video, to_wav16k
from .config import Config
from .formats import write_outputs
from .transcribe import Segment, Transcript, transcribe
from .translate import translate_transcript
from .tts import TTSEngine, build_engine


def default_voice_for(engine_name: str, lang: str | None) -> str | None:
    """Voce coerente con la lingua di uscita quando non è stata scelta."""

    if not lang:
        return None
    lang = lang.lower()
    if engine_name == "piper":
        return {
            "it": "it_IT-serena-medium",
            "en": "en_US-lessac-medium",
            "en_us": "en_US-lessac-medium",
        }.get(lang)
    if engine_name == "espeak":
        return lang
    return None


@dataclass
class PipelineResult:
    transcript: Transcript
    output_dir: Path
    transcript_files: dict[str, Path]
    tts_audio: Path | None
    aligned_audio: Path | None
    manifest: Path
    dubbed_video: Path | None = None

    def as_dict(self) -> dict:
        return {
            "output_dir": str(self.output_dir),
            "transcript_files": {k: str(v) for k, v in self.transcript_files.items()},
            "tts_audio": str(self.tts_audio) if self.tts_audio else None,
            "aligned_audio": str(self.aligned_audio) if self.aligned_audio else None,
            "dubbed_video": str(self.dubbed_video) if self.dubbed_video else None,
            "manifest": str(self.manifest),
            "segments": len(self.transcript.segments),
            "language": self.transcript.language,
        }


def run_pipeline(
    audio_path: str | Path,
    output_dir: str | Path,
    cfg: Config | None = None,
    tts_engine: str = "auto",
    tts_voice: str | None = None,
    tts_url: str | None = None,
    tts_mode: str = "openai",
    tts_speed: float = 1.0,
    do_tts: bool = True,
    align: bool = False,
    dub: bool | None = None,
    formats: tuple[str, ...] = ("json", "srt", "vtt", "txt"),
    translate: str | None = None,
    translate_engine: str = "auto",
) -> PipelineResult:
    """Esegue l'intera pipeline e restituisce i percorsi generati.

    `dub`:
      - None (default): attiva il dubbing automaticamente per input video;
      - True: forza il dubbing (solo per input video);
      - False: disattiva il dubbing.
    """
    cfg = cfg or Config()
    audio_path = Path(audio_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = audio_path.stem

    video_input = is_video(audio_path)
    want_dub = dub is True or (dub is None and video_input)
    if want_dub and not video_input:
        raise ValueError("Il dubbing (--dub) richiede un input video (es. .mp4)")
    if want_dub and not do_tts:
        raise ValueError("Il dubbing richiede il TTS: non usare --no-tts con --dub")

    transcript = transcribe(audio_path, cfg, output_prefix=output_dir / stem)
    if translate:
        transcript = translate_transcript(
            transcript,
            translate,
            engine=translate_engine,
            audio_path=audio_path,
            cfg=cfg,
        )
    written = write_outputs(transcript, output_dir, stem, formats=formats)

    tts_audio: Path | None = None
    aligned_audio: Path | None = None
    dubbed_video: Path | None = None
    engine: TTSEngine | None = None

    if do_tts:
        if not tts_voice and translate:
            tts_voice = default_voice_for(tts_engine, translate)
        engine = build_engine(
            tts_engine,
            espeak_binary=cfg.espeak,
            url=tts_url or cfg.kokoro_url,
            mode=tts_mode,
            voice=tts_voice,
            speed=tts_speed,
        )
        if not tts_voice and translate:
            tts_voice = default_voice_for(engine.name, translate)
            if tts_voice:
                engine = build_engine(
                    engine.name,
                    espeak_binary=cfg.espeak,
                    url=tts_url or cfg.kokoro_url,
                    mode=tts_mode,
                    voice=tts_voice,
                    speed=tts_speed,
                )
        tts_audio = engine.synthesize_segments(
            transcript.segments, output_dir, stem=f"{stem}.tts", voice=tts_voice
        )
        if align or want_dub:
            aligned_audio = synthesize_aligned(
                engine, transcript.segments, output_dir, stem=f"{stem}.aligned", cfg=cfg
            )
        if want_dub:
            dubbed_video = dub_video(
                audio_path,
                aligned_audio,
                output_dir / f"{stem}.dubbed.mp4",
                cfg.ffmpeg,
            )

    manifest = output_dir / f"{stem}.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source": str(audio_path),
                "language": transcript.language,
                "segments": len(transcript.segments),
                "tts_engine": engine.name if engine else None,
                "tts_voice": tts_voice,
                "transcript_files": {k: str(v) for k, v in written.items()},
                "tts_audio": str(tts_audio) if tts_audio else None,
                "aligned_audio": str(aligned_audio) if aligned_audio else None,
                "dubbed_video": str(dubbed_video) if dubbed_video else None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return PipelineResult(
        transcript=transcript,
        output_dir=output_dir,
        transcript_files=written,
        tts_audio=tts_audio,
        aligned_audio=aligned_audio,
        manifest=manifest,
        dubbed_video=dubbed_video,
    )


def synthesize_aligned(
    engine: TTSEngine,
    segments: list[Segment],
    output_dir: Path,
    stem: str = "aligned",
    cfg: Config | None = None,
    tmp_dir: Path | None = None,
) -> Path:
    """Genera un WAV che replica i tempi originali: TTS per segmento + silenzi.

    Utile per "ridoppiare" l'audio mantenendo la sincronizzazione dei timestamp.
    """
    cfg = cfg or Config()
    output_dir = Path(output_dir)
    parts_dir = (tmp_dir or output_dir / f"{stem}_parts")
    parts_dir.mkdir(parents=True, exist_ok=True)

    normalized: list[Path] = []
    cursor = 0.0
    gap_index = 0

    for i, seg in enumerate(segments):
        gap = seg.start - cursor
        if gap > 0.05:
            silence = parts_dir / f"gap_{gap_index:04d}.wav"
            _make_silence(gap, silence, cfg.ffmpeg)
            normalized.append(silence)
            gap_index += 1
        raw = engine.synthesize(seg.text, parts_dir / f"seg_{i:04d}.wav")
        norm = parts_dir / f"seg_{i:04d}_16k.wav"
        to_wav16k(raw, norm, cfg.ffmpeg)
        normalized.append(norm)
        cursor = seg.start + _duration(norm, cfg.ffmpeg)

    out = output_dir / f"{stem}.wav"
    _concat(normalized, out, parts_dir, cfg.ffmpeg)
    return out


def _duration(path: Path, ffmpeg: str) -> float:
    from .audio import probe_duration

    return probe_duration(path, ffmpeg)


def _make_silence(seconds: float, out_path: Path, ffmpeg: str) -> None:
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=16000:cl=mono",
            "-t",
            f"{seconds:.3f}",
            "-c:a",
            "pcm_s16le",
            str(out_path),
        ],
        check=True,
        capture_output=True,
    )


def _concat(parts: list[Path], out_path: Path, work_dir: Path, ffmpeg: str) -> None:
    list_file = work_dir / "concat.txt"
    list_file.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in parts), encoding="utf-8"
    )
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:a",
            "pcm_s16le",
            str(out_path),
        ],
        check=True,
        capture_output=True,
    )
