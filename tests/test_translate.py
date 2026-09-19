"""Test del modulo di traduzione offline (whisper/argos) e auto-detect lingua."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from stt_tts_ita.config import Config
from stt_tts_ita.transcribe import Segment, Transcript, transcribe
from stt_tts_ita.translate import (
    TranslationError,
    translate_transcript,
    translate_with_argos,
    translate_with_whisper,
)


def _tr(segments=("Ciao mondo.", "Come stai?"), lang="it"):
    return Transcript(
        segments=[Segment(start=i, end=i + 1.5, text=t) for i, t in enumerate(segments)],
        language=lang,
    )


def _whisper_payload(text="Hello world", lang="en"):
    return {
        "result": {"language": lang},
        "transcription": [
            {
                "timestamps": {"from": "00:00:01,000", "to": "00:00:03,500"},
                "text": text,
            }
        ],
    }


def _patch_wav16k():
    return (
        mock.patch("stt_tts_ita.translate._is_16k_mono", return_value=False),
        mock.patch("stt_tts_ita.translate.to_wav16k", return_value=Path("/tmp/t.wav")),
    )


class ArgosTranslateTest(unittest.TestCase):
    @mock.patch("stt_tts_ita.translate.subprocess.run")
    def test_argos_per_segment(self, run):
        run.return_value = mock.Mock(returncode=0, stdout="Hello world.")
        out = translate_with_argos(_tr(), "en", argos_cmd="argos-translate")
        self.assertEqual(out.language, "en")
        self.assertEqual([s.text for s in out.segments], ["Hello world.", "Hello world."])
        self.assertEqual([s.start for s in out.segments], [0.0, 1.0])
        run.assert_any_call(
            ["argos-translate", "--from-lang", "it", "--to-lang", "en", "Ciao mondo."],
            capture_output=True,
            text=True,
        )

    @mock.patch("stt_tts_ita.translate.subprocess.run")
    def test_argos_noop_same_lang(self, run):
        out = translate_with_argos(_tr(), "it", argos_cmd="argos-translate")
        self.assertEqual(out.text, "Ciao mondo. Come stai?")
        run.assert_not_called()

    def test_argos_missing_binary(self):
        with mock.patch("stt_tts_ita.translate.subprocess.run", side_effect=FileNotFoundError):
            with self.assertRaises(FileNotFoundError):
                translate_with_argos(_tr(), "en")

    @mock.patch("stt_tts_ita.translate.subprocess.run")
    def test_argos_failure(self, run):
        run.return_value = mock.Mock(returncode=1, stdout="", stderr="boom")
        with self.assertRaises(TranslationError):
            translate_with_argos(_tr(), "en")

    @mock.patch("stt_tts_ita.translate.subprocess.run")
    def test_argos_falls_back_to_modern_cli(self, run):
        run.side_effect = [
            mock.Mock(returncode=2, stdout="", stderr="old cli missing"),
            mock.Mock(returncode=0, stdout="Hello world."),
            mock.Mock(returncode=2, stdout="", stderr="old cli missing"),
            mock.Mock(returncode=0, stdout="Hello world."),
        ]
        out = translate_with_argos(_tr(), "en", argos_cmd="argos")
        self.assertEqual(out.text, "Hello world. Hello world.")
        run.assert_any_call(
            ["argos", "-q", "-f", "it", "-t", "en", "Ciao mondo."],
            capture_output=True,
            text=True,
        )

    def test_argos_needs_src_language(self):
        with self.assertRaises(TranslationError):
            translate_with_argos(_tr(lang="auto"), "en")


class DispatchTest(unittest.TestCase):
    def test_noop_when_target_equals_source(self):
        out = translate_transcript(_tr(), "it", engine="argos")
        self.assertEqual(out, _tr())

    def test_whisper_requires_audio(self):
        with self.assertRaises(TranslationError):
            translate_transcript(_tr(), "en", engine="whisper")

    def test_auto_target_en_dispatch_whisper(self):
        with mock.patch("stt_tts_ita.translate.translate_with_whisper") as m:
            translate_transcript(_tr(), "en", audio_path="/tmp/x.wav", cfg=Config())
            m.assert_called_once()

    def test_auto_non_en_falls_to_argos(self):
        with mock.patch("stt_tts_ita.translate.translate_with_argos") as m:
            translate_transcript(_tr(), "de", engine="auto", cfg=Config())
            m.assert_called_once()

    def test_auto_non_en_without_argos_raises(self):
        with mock.patch(
            "stt_tts_ita.translate.subprocess.run", side_effect=FileNotFoundError
        ):
            with self.assertRaises(FileNotFoundError):
                translate_transcript(_tr(), "de", engine="auto", cfg=Config())

    @mock.patch("stt_tts_ita.translate.subprocess.run")
    def test_whisper_non_en_engine_rejected(self, run):
        with self.assertRaises(TranslationError):
            translate_transcript(_tr(), "de", engine="whisper", audio_path="/tmp/x.wav")
        run.assert_not_called()


class WhisperTranslateTest(unittest.TestCase):
    @mock.patch("stt_tts_ita.translate.json.loads")
    @mock.patch("stt_tts_ita.translate.Path.read_text", return_value="{}")
    @mock.patch("stt_tts_ita.translate.Path.is_file", return_value=True)
    def test_whisper_translate_uses_tr(self, _isf, _read, jloads):
        jloads.return_value = _whisper_payload()
        p1, p2 = _patch_wav16k()
        with p1, p2, mock.patch("stt_tts_ita.translate.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            out = translate_with_whisper("/tmp/in.m4a", "en")
        cmd = run.call_args.args[0]
        self.assertIn("-tr", cmd)
        self.assertEqual(cmd[cmd.index("-l") + 1], "auto")
        self.assertEqual(out.language, "en")
        self.assertEqual(out.text, "Hello world")

    @mock.patch("stt_tts_ita.translate.subprocess.run")
    def test_whisper_engine_only_english(self, run):
        with self.assertRaises(TranslationError):
            translate_with_whisper("/tmp/in.m4a", "it")
        run.assert_not_called()


class AutoDetectLangTest(unittest.TestCase):
    @mock.patch("stt_tts_ita.transcribe.json.loads")
    @mock.patch("stt_tts_ita.transcribe.Path.read_text", return_value="{}")
    @mock.patch("stt_tts_ita.transcribe.Path.is_file", return_value=True)
    def test_explicit_lang_passed(self, _isf, _read, jloads):
        jloads.return_value = _whisper_payload("ciao", "it")
        p1, p2 = mock.patch("stt_tts_ita.transcribe._is_16k_mono", return_value=False), \
                 mock.patch("stt_tts_ita.transcribe.to_wav16k", return_value=Path("/tmp/t.wav"))
        cfg = Config(language="it")
        with p1, p2, mock.patch("stt_tts_ita.transcribe.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            tr = transcribe("/tmp/in.wav", cfg, output_prefix=Path("/tmp/o"))
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[cmd.index("-l") + 1], "it")
        self.assertEqual(tr.language, "it")

    @mock.patch("stt_tts_ita.transcribe.json.loads")
    @mock.patch("stt_tts_ita.transcribe.Path.read_text", return_value="{}")
    @mock.patch("stt_tts_ita.transcribe.Path.is_file", return_value=True)
    def test_auto_lang_detected(self, _isf, _read, jloads):
        jloads.return_value = _whisper_payload("bonjour", "fr")
        p1, p2 = mock.patch("stt_tts_ita.transcribe._is_16k_mono", return_value=False), \
                 mock.patch("stt_tts_ita.transcribe.to_wav16k", return_value=Path("/tmp/t.wav"))
        cfg = Config(language="auto")
        with p1, p2, mock.patch("stt_tts_ita.transcribe.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0, stdout="", stderr="")
            tr = transcribe("/tmp/in.wav", cfg, output_prefix=Path("/tmp/o"))
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[cmd.index("-l") + 1], "auto")
        self.assertEqual(tr.language, "fr")


class ResolveWhisperCliTest(unittest.TestCase):
    """Priorità di resolve_whisper_cli: env esplicito > bundle _MEIPASS > progetto > PATH."""

    def _make_bundle(self, tmp: Path) -> Path:
        b = tmp / "bundle" / "bin"
        b.mkdir(parents=True)
        (b / "whisper-cli").write_bytes(b"binary")
        return tmp / "bundle"

    def test_bundle_vince_su_file_cwd_rotto(self):
        with (tempfile.TemporaryDirectory() as d,):
            tmp = Path(d)
            bundle = self._make_bundle(tmp)
            stale = tmp / "bin" / "whisper-cli"  # esiste ma il bundle resta in cima
            stale.parent.mkdir(parents=True)
            stale.write_bytes(b"broken")
            cfg = Config(whisper_cli=str(stale))
            with mock.patch.object(sys, "_MEIPASS", str(bundle), create=True):
                self.assertEqual(
                    cfg.resolve_whisper_cli(),
                    str(bundle / "bin" / "whisper-cli"),
                )

    def test_fallback_progetto_senza_bundle(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            proj = tmp / "bin" / "whisper-cli"
            proj.parent.mkdir(parents=True)
            proj.write_bytes(b"binary")
            cfg = Config(whisper_cli=str(proj))
            self.assertEqual(cfg.resolve_whisper_cli(), str(proj))

    def test_env_override_vince_su_bundle(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            bundle = self._make_bundle(tmp)
            envcli = tmp / "env-cli"
            envcli.write_bytes(b"binary")
            cfg = Config()
            env = dict(os.environ)
            env["STT_TTS_WHISPER_CLI"] = str(envcli)
            with mock.patch.dict("stt_tts_ita.config.os.environ", env), \
                    mock.patch.object(sys, "_MEIPASS", str(bundle), create=True):
                self.assertEqual(cfg.resolve_whisper_cli(), str(envcli))

    def test_bundle_assente_fallisce_con_messaggio(self):
        with mock.patch.object(sys, "_MEIPASS", "/nonexistent-mei", create=True), \
                mock.patch("stt_tts_ita.config.shutil.which", return_value=None):
            cfg = Config(whisper_cli="/nonexistent/bin/whisper-cli")
            with self.assertRaises(FileNotFoundError) as ctx:
                cfg.resolve_whisper_cli()
            self.assertIn("STT_TTS_WHISPER_CLI", str(ctx.exception))


class ResolveModelTest(unittest.TestCase):
    def test_bundle_vince_su_modello_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            bundle = tmp / "bundle" / "models"
            bundle.mkdir(parents=True)
            (bundle / "ggml-small-q5_1.bin").write_bytes(b"model")
            cfg = Config(model=str(tmp / "models" / "ggml-small-q5_1.bin"))
            with mock.patch.object(sys, "_MEIPASS", str(tmp / "bundle"), create=True):
                self.assertEqual(
                    cfg.resolve_model(), str(bundle / "ggml-small-q5_1.bin")
                )

    def test_env_override_vince_su_bundle(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            bundle = tmp / "bundle" / "models"
            bundle.mkdir(parents=True)
            (bundle / "ggml-small-q5_1.bin").write_bytes(b"model")
            mine = tmp / "mio.bin"
            mine.write_bytes(b"mine")
            cfg = Config()
            env = dict(os.environ)
            env["STT_TTS_MODEL"] = str(mine)
            with mock.patch.dict("stt_tts_ita.config.os.environ", env), \
                    mock.patch.object(sys, "_MEIPASS", str(tmp / "bundle"), create=True):
                self.assertEqual(cfg.resolve_model(), str(mine))

    def test_fallback_progetto(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            proj = tmp / "models"
            proj.mkdir()
            model = proj / "ggml-small-q5_1.bin"
            model.write_bytes(b"model")
            cfg = Config(model=str(model))
            self.assertEqual(cfg.resolve_model(), str(model))


if __name__ == "__main__":
    unittest.main()