"""Test per il motore TTS Piper (nessun binario reale richiesto)."""

import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from stt_tts_ita.tts import build_engine
from stt_tts_ita.tts.base import TTSError
from stt_tts_ita.tts.piper import PiperEngine


class TestPiperEngine(unittest.TestCase):
    def _engine(self, binary: Path, models_dir: Path, **kwargs) -> PiperEngine:
        return PiperEngine(binary=str(binary), models_dir=str(models_dir), **kwargs)

    def test_available_false_senza_binario(self):
        self.assertFalse(PiperEngine(binary="/nonexistent/piper").available())

    def test_available_true_con_binario_e_modello(self):
        with self._TmpFixture() as fx:
            engine = self._engine(fx.bin, fx.models)
            self.assertTrue(engine.available())

    def test_resolve_model_accetta_extension(self):
        with self._TmpFixture() as fx:
            engine = self._engine(fx.bin, fx.models)
            self.assertEqual(engine.resolve_model("oga"), fx.models / "oga.onnx")
            self.assertEqual(
                engine.resolve_model("it_IT-serena-medium.onnx"),
                fx.models / "it_IT-serena-medium.onnx",
            )

    def test_resolve_model_mancante(self):
        with self._TmpFixture() as fx:
            engine = self._engine(fx.bin, fx.models)
            with self.assertRaises(TTSError):
                engine.resolve_model("voce-assente")

    def test_auto_preferisce_piper_se_disponibile(self):
        """Con Kokoro irraggiungibile, 'auto' deve scegliere Piper (non espeak)."""
        with self._TmpFixture() as fx, \
                mock.patch("stt_tts_ita.tts.HttpTTSEngine.available", return_value=False), \
                mock.patch.dict(
                    os.environ,
                    {
                        "STT_TTS_PIPER_BIN": str(fx.bin),
                        "STT_TTS_PIPER_MODELS_DIR": str(fx.models),
                    },
                ):
            engine = build_engine("auto")
            self.assertIsInstance(engine, PiperEngine)

    def test_auto_espeak_senza_piper(self):
        with mock.patch("stt_tts_ita.tts.HttpTTSEngine.available", return_value=False):
            engine = build_engine("auto")
            self.assertFalse(isinstance(engine, PiperEngine))

    def test_synthesize_invoca_piper_con_flags(self):
        with self._TmpFixture() as fx:
            captured = {}

            def fake_run(cmd, **kwargs):
                captured["cmd"] = cmd
                captured["env"] = kwargs.get("env", {})
                captured["input"] = kwargs.get("input")
                fx.out.write_bytes(b"RIFF")
                cp = subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
                return cp

            old_run = subprocess.run
            subprocess.run = fake_run
            try:
                engine = self._engine(fx.bin, fx.models, speed=1.5)
                result = engine.synthesize("Ciao mondo", fx.out)
            finally:
                subprocess.run = old_run

            self.assertEqual(str(result), str(fx.out))
            cmd = captured["cmd"]
            self.assertIn("-m", cmd)
            self.assertIn(str(fx.models / "it_IT-serena-medium.onnx"), cmd)
            self.assertEqual(cmd[cmd.index("--length_scale") + 1], "0.667")
            self.assertEqual(captured["input"], "Ciao mondo")
            libdir = cmd[0].rsplit("/", 1)[0]
            self.assertIn(libdir, captured["env"].get("LD_LIBRARY_PATH", ""))
            self.assertIn(libdir + "/lib",
                          captured["env"].get("LD_LIBRARY_PATH", ""))

    def test_synthesize_errore(self):
        with self._TmpFixture() as fx:
            engine = self._engine(fx.bin, fx.models, voice="mancante")
            with self.assertRaises(TTSError):
                engine.synthesize("testo", fx.out)

    class _TmpFixture:
        def __enter__(self):
            import tempfile

            self._d = tempfile.TemporaryDirectory()
            self.tmp = Path(self._d.name)
            self.bin_dir = self.tmp / "bin"
            self.bin = self.bin_dir / "piper"
            self.models = self.tmp / "models"
            self.out = self.tmp / "out.wav"
            self.bin_dir.mkdir()
            self.models.mkdir()
            self.bin.write_text("#!/bin/sh\nexit 0\n")
            self.bin.chmod(0o755)
            (self.models / "it_IT-serena-medium.onnx").write_bytes(b"x" * 4)
            (self.models / "it_IT-serena-medium.onnx.json").write_text("{}")
            (self.models / "oga.onnx").write_bytes(b"y" * 4)
            return self

        def __exit__(self, *exc):
            self._d.cleanup()


if __name__ == "__main__":
    unittest.main()