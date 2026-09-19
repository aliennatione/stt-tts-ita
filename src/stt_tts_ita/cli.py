"""Interfaccia a riga di comando."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Config
from .formats import write_outputs
from .pipeline import run_pipeline, synthesize_aligned
from .transcribe import Segment, Transcript, transcribe
from .translate import TRANSLATION_ENGINES, translate_transcript
from .tts import ENGINES, build_engine

_EXAMPLES = """\
esempi:

  # 1) Dubbing in italiano di un video in inglese (EN -> IT, voce maschile Piper)
  stt-tts-ita --lang auto run film_en.mp4 -o out \\
      --translate it --translate-engine argos \\
      --tts-engine piper --tts-voice it_IT-riccardo-x_low

  # (senza argos-translate installato si può tradurre solo verso l'inglese:
  #  il dubbing EN usa la voce inglese Piper, non serve espeak installato)
  stt-tts-ita --lang auto run film_it.mp4 -o out --translate en \\
      --translate-engine whisper --tts-engine piper --tts-voice en_US-ryan-medium

  # 1b) Dubbing EN con voce inglese predefinita (basta scrivere):
  stt-tts-ita --lang auto run film_it.mp4 -o out --dub \\
      --translate en --translate-engine whisper

  # 2) Semplice sostituzione voce (stessa lingua, niente traduzione)
  stt-tts-ita run film_it.mp4 -o out \\
      --tts-engine piper --tts-voice it_IT-riccardo-x_low

  # 3) Solo trascrizione (sottotitoli, nessun TTS / nessun dubbing)
  stt-tts-ita run film.mp4 -o out --no-dub --no-tts

  # 4) Trascrizione + sottotitoli da solo
  stt-tts-ita transcribe intervista.m4a -o out

  # 5) TTS (voce) ripartendo da un transcript JSON esistente
  stt-tts-ita tts out/film.json -o out --tts-engine piper --tts-voice it_IT-paola-medium

  # 6) Dubbing con WAV allineato ai timestamp originali + velocità voce
  stt-tts-ita run lezione.mp4 -o out --tts-engine piper \\
      --tts-voice it_IT-serena-medium --align --tts-speed 1.1

  voci Piper incluse: it_IT-serena-medium (italiano, donna, default),
  it_IT-serena-high, it_IT-paola-medium, it_IT-riccardo-x_low (italiano, uomo),
  en_US-lessac-medium (inglese, donna), en_US-ryan-medium (inglese, uomo).
  Con --tts-engine espeak la voce è il codice lingua (es. it, en).
"""


def _add_translation_options(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--translate",
        metavar="LANG",
        default=None,
        help="Traduci la trascrizione verso questa lingua (es. it, en) — sempre offline/locale",
    )
    p.add_argument(
        "--translate-engine",
        choices=TRANSLATION_ENGINES,
        default="auto",
        help="Motore di traduzione offline (auto: whisper->en se target en, altrimenti argos)",
    )


def _add_tts_options(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--tts-engine",
        choices=["auto", *ENGINES],
        default="auto",
        help="Motore TTS (default: auto = Kokoro se raggiungibile, altrimenti Piper, infine espeak)",
    )
    p.add_argument("--tts-url", default=None, help="URL base del servizio Kokoro")
    p.add_argument(
        "--tts-mode",
        choices=["openai", "gradio"],
        default="openai",
        help="Protocollo HTTP del servizio TTS",
    )
    p.add_argument("--tts-voice", default=None, help="Voce (es. it_IT-serena-medium o it_IT-riccardo-x_low per piper; en_US-lessac-medium/en_US-ryan-medium per l'inglese; it per espeak)")
    p.add_argument("--tts-speed", type=float, default=1.0,
                   help="Velocità di lettura (1.0 = normale; es. 1.2 più veloce)")
    p.add_argument("--no-tts", action="store_true", help="Solo trascrizione (nessun TTS/dubbing)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stt-tts-ita",
        description="Audio parlato italiano -> trascrizione con timestamp -> TTS (open source). "
        "Con input video attiva anche il dubbing (sostituzione traccia audio).",
        epilog=_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--model", help="Percorso modello ggml Whisper (default: models/ggml-small-q5_1.bin)")
    parser.add_argument("--lang", default=None, help="Lingua input per whisper (default: auto = rilevata)")
    parser.add_argument("--threads", type=int, default=None, help="Thread di inferenza whisper (default: 4)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser(
        "run", help="Trascrivi e rigenera in TTS (audio o video, con dubbing)",
        description="Pipeline completa: conversione -> trascrizione (+ opz. traduzione) -> TTS -> dubbing.",
    )
    p_run.add_argument("input", help="File audio (m4a/wav/mp3) o video (mp4/mkv/...)")
    p_run.add_argument(
        "-o", "--output", default="output",
        help="Cartella di output (creata se manca; default: ./output)",
    )
    p_run.add_argument(
        "--format",
        nargs="+",
        default=["json", "srt", "vtt", "txt"],
        help="Formati di trascrizione da scrivere (json srt vtt txt; default: tutti)",
    )
    p_run.add_argument(
        "--align",
        action="store_true",
        help="Genera anche un WAV allineato ai timestamp originali",
    )
    dub_group = p_run.add_mutually_exclusive_group()
    dub_group.add_argument(
        "--dub",
        dest="dub",
        action="store_true",
        default=None,
        help="Sostituisci la traccia audio del video con il TTS (auto per input video)",
    )
    dub_group.add_argument(
        "--no-dub",
        dest="dub",
        action="store_false",
        default=None,
        help="Non sostituire la traccia audio anche per input video",
    )
    _add_translation_options(p_run)
    _add_tts_options(p_run)

    p_tr = sub.add_parser(
        "transcribe", help="Solo trascrizione con timestamp",
        description="Converte il media in WAV 16 kHz e produce trascrizione + sottotitoli.",
    )
    p_tr.add_argument("input", help="File audio o video")
    p_tr.add_argument("-o", "--output", default="output",
                      help="Cartella di output (default: ./output)")
    p_tr.add_argument(
        "--format",
        nargs="+",
        default=["json", "srt", "vtt", "txt"],
        help="Formati di trascrizione da scrivere (json srt vtt txt; default: tutti)",
    )

    p_tts = sub.add_parser(
        "tts", help="Rigenera audio da un transcript JSON",
        description="Sintetizza la voce a partire dal JSON di trascrizione (con timestamp).",
    )
    p_tts.add_argument("input", help="File JSON con 'segments'")
    p_tts.add_argument("-o", "--output", default="output",
                       help="Cartella di output (default: ./output)")
    p_tts.add_argument(
        "--align", action="store_true",
        help="Genera anche un WAV allineato ai timestamp originali",
    )
    _add_translation_options(p_tts)
    _add_tts_options(p_tts)

    sub.add_parser(
        "info", help="Mostra binari/modelli risolti e motori disponibili",
        description="Stampa percorsi risolti di whisper-cli/modello e quali motori TTS sono disponibili.",
    )
    return parser


def _cfg_from_args(args) -> Config:
    cfg = Config()
    if getattr(args, "model", None):
        cfg.model = args.model
    if getattr(args, "lang", None):
        cfg.language = args.lang
    if getattr(args, "threads", None):
        cfg.threads = args.threads
    return cfg


def _load_transcript(path: Path) -> Transcript:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    segments = [
        Segment(start=float(s["start"]), end=float(s["end"]), text=str(s["text"]))
        for s in payload.get("segments", [])
    ]
    return Transcript(
        segments=segments,
        language=payload.get("language", "it"),
        source=payload.get("source", ""),
    )


def cmd_run(args) -> int:
    cfg = _cfg_from_args(args)
    result = run_pipeline(
        args.input,
        args.output,
        cfg=cfg,
        tts_engine=args.tts_engine,
        tts_voice=args.tts_voice,
        tts_url=args.tts_url,
        tts_mode=args.tts_mode,
        tts_speed=args.tts_speed,
        do_tts=not args.no_tts,
        align=args.align,
        dub=args.dub,
        formats=tuple(args.format),
        translate=args.translate,
        translate_engine=args.translate_engine,
    )
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_transcribe(args) -> int:
    cfg = _cfg_from_args(args)
    audio = Path(args.input)
    output_dir = Path(args.output)
    tr = transcribe(audio, cfg, output_prefix=output_dir / audio.stem)
    written = write_outputs(tr, output_dir, audio.stem, formats=tuple(args.format))
    print(
        json.dumps(
            {"files": {k: str(v) for k, v in written.items()}},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_tts(args) -> int:
    cfg = _cfg_from_args(args)
    tr = _load_transcript(args.input)
    if args.translate:
        tr = translate_transcript(
            tr,
            args.translate,
            engine=args.translate_engine,
            cfg=cfg,
        )
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    engine = build_engine(
        args.tts_engine,
        espeak_binary=cfg.espeak,
        url=args.tts_url or cfg.kokoro_url,
        mode=args.tts_mode,
        speed=args.tts_speed,
    )
    tts_voice = args.tts_voice
    if not tts_voice and args.translate:
        tts_voice = default_voice_for(engine.name, args.translate)
        if tts_voice:
            engine = build_engine(
                engine.name,
                espeak_binary=cfg.espeak,
                url=args.tts_url or cfg.kokoro_url,
                mode=args.tts_mode,
                voice=tts_voice,
                speed=args.tts_speed,
            )
    stem = Path(args.input).stem
    out = engine.synthesize_segments(
        tr.segments, output_dir, stem=f"{stem}.tts", voice=tts_voice
    )
    result = {"tts_engine": engine.name, "tts_audio": str(out)}
    if args.align:
        aligned = synthesize_aligned(
            engine, tr.segments, output_dir, stem=f"{stem}.aligned", cfg=cfg
        )
        result["aligned_audio"] = str(aligned)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_info(args) -> int:
    cfg = Config()
    info: dict = {"root": str(cfg.root), "language": cfg.language, "threads": cfg.threads}
    try:
        info["whisper_cli"] = cfg.resolve_whisper_cli()
    except FileNotFoundError as exc:
        info["whisper_cli"] = f"NON TROVATO: {exc}"
    try:
        info["model"] = cfg.resolve_model()
    except FileNotFoundError as exc:
        info["model"] = f"NON TROVATO: {exc}"
    engines = {}
    for name in ENGINES:
        engine = build_engine(
            name,
            espeak_binary=cfg.espeak,
            url=cfg.kokoro_url,
            mode="openai",
        )
        engines[name] = engine.available()
    info["engines"] = engines
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "run": cmd_run,
        "transcribe": cmd_transcribe,
        "tts": cmd_tts,
        "info": cmd_info,
    }
    try:
        return handlers[args.command](args)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"errore: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
