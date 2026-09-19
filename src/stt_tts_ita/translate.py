"""Traduzione offline della trascrizione verso la lingua di uscita.

Due motori, entrambi 100% locali (nessuna API):
- `whisper`: usa l'opzione `--translate` di whisper.cpp → solo verso **en**
  (limite del modello, ma zero dipendenze aggiuntive).
- `argos`: usa il traduttore neurale **argos-translate** (offline) via CLI
  esterna. Supporta coppie arbitrarie (es. it<->en, es->it, ...). Non incluso
  nel bundle: installabile su Debian/glibc con `scripts/setup_argos.sh`.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .audio import to_wav16k
from .config import Config
from .transcribe import Transcript, _is_16k_mono, transcript_from_whisper_json

TRANSLATION_ENGINES = ("auto", "whisper", "argos")


class TranslationError(RuntimeError):
    pass


def _whisper_translate_to_json(
    wav: Path,
    cfg: Config,
    prefix: Path,
) -> dict:
    whisper_cli = cfg.resolve_whisper_cli()
    model = cfg.resolve_model()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        whisper_cli,
        "-m",
        model,
        "-l",
        "auto",
        "-tr",
        "-t",
        str(cfg.threads),
        "-oj",
        "-of",
        str(prefix),
        "--no-prints",
        str(wav),
    ]
    cp = subprocess.run(cmd, capture_output=True, text=True)
    json_path = prefix.with_suffix(".json")
    if cp.returncode != 0 or not json_path.is_file():
        raise TranslationError(
            "whisper (-tr) è terminato con errore:\n" + (cp.stderr or cp.stdout)
        )
    return json.loads(json_path.read_text(encoding="utf-8"))


def translate_with_whisper(
    audio_path: str | Path,
    target: str,
    cfg: Config | None = None,
) -> Transcript:
    """Ritrascrive con whisper `--translate` (solo verso 'en')."""
    if target.lower() != "en":
        raise TranslationError(
            "Il motore 'whisper' traduce solo verso 'en'. Per altre lingue "
            "usa '--translate-engine argos' (scripts/setup_argos.sh)."
        )
    cfg = cfg or Config()
    audio_path = Path(audio_path)
    tmpdir = tempfile.TemporaryDirectory(prefix="stt_tts_tr_")
    try:
        if audio_path.suffix.lower() == ".wav" and _is_16k_mono(audio_path, cfg.ffmpeg):
            wav = audio_path
        else:
            wav = to_wav16k(audio_path, Path(tmpdir.name) / "input.wav", cfg.ffmpeg)
        payload = _whisper_translate_to_json(wav, cfg, Path(tmpdir.name) / "tr")
        tr = transcript_from_whisper_json(payload, source=str(audio_path))
        tr.language = "en"
        return tr
    finally:
        tmpdir.cleanup()


def translate_with_argos(
    transcript: Transcript,
    target: str,
    *,
    src_lang: str | None = None,
    argos_cmd: str = "argos-translate",
) -> Transcript:
    """Traduce ogni segmento con argos-translate (offline, localmente)."""
    src = (src_lang or transcript.language or "auto").lower()
    tgt = target.lower()
    if src == "auto":
        raise TranslationError(
            "Lingua di origine non rilevabile: servi un transcript con "
            "'language' valorizzata (es. generato con --lang auto)."
        )
    if src == tgt:
        return Transcript(
            segments=list(transcript.segments),
            language=tgt,
            source=transcript.source,
        )

    def _translate(text: str) -> str:
        if not text.strip():
            return ""
        try:
            cp = subprocess.run(
                [argos_cmd, "--from-lang", src, "--to-lang", tgt, text],
                capture_output=True,
                text=True,
            )
            if cp.returncode != 0:
                cp = subprocess.run(
                    [argos_cmd, "-q", "-f", src, "-t", tgt, text],
                    capture_output=True,
                    text=True,
                )
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"argos-translate non trovato ({argos_cmd}). "
                "Esegui scripts/setup_argos.sh su Debian/glibc."
            ) from exc
        if cp.returncode != 0:
            raise TranslationError(
                f"argos-translate ({src}->{tgt}) è terminato con errore:\n"
                + (cp.stderr or cp.stdout).strip()
            )
        return cp.stdout.strip()

    segments = []
    for seg in transcript.segments:
        try:
            text = _translate(seg.text)
        except TranslationError:
            raise
        segments.append(type(seg)(start=seg.start, end=seg.end, text=text))
    return Transcript(segments=segments, language=tgt, source=transcript.source)


def translate_transcript(
    transcript: Transcript,
    target: str,
    *,
    engine: str = "auto",
    audio_path: str | Path | None = None,
    cfg: Config | None = None,
) -> Transcript:
    """Applica la traduzione scegliendo il motore.

    `auto`:
      - target == "en": motore whisper (nessuna dipendenza extra);
      - altre lingue: motore argos (se installato).
    """
    target = target.lower()
    if target == (transcript.language or "").lower():
        return transcript
    eng = (engine or "auto").lower()
    if eng == "whisper" or (eng == "auto" and target == "en"):
        if eng == "auto" and target != "en":
            raise TranslationError(
                "Serve argos-translate per tradurre offline verso lingue "
                "diverse da 'en'. Esegui scripts/setup_argos.sh."
            )
        if not audio_path:
            raise TranslationError(
                "Il motore 'whisper' richiede il file audio di origine "
                "(usalo dal comando 'run', non da 'tts')."
            )
        if cfg is None:
            cfg = Config()
        return translate_with_whisper(audio_path, target, cfg)
    return translate_with_argos(
        transcript,
        target,
        argos_cmd=(cfg.argos_cmd if cfg else "argos-translate"),
    )