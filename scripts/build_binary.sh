#!/bin/sh
# Costruisce un eseguibile autocontenuto con PyInstaller.
# Impacchetta l'orchestratore Python e bin/whisper-cli.
# Restano esterni (documentati): ffmpeg, espeak-ng e il modello in models/.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -x .venv/bin/python ]; then
    echo "Esegui prima scripts/setup.sh" >&2
    exit 1
fi
if [ ! -x bin/whisper-cli ]; then
    echo "bin/whisper-cli mancante: esegui scripts/build_whisper_cpp.sh" >&2
    exit 1
fi

echo "==> Installo PyInstaller nel venv"
./.venv/bin/python -m pip install --upgrade pyinstaller

echo "==> Build eseguibile"
./.venv/bin/pyinstaller \
    --noconfirm \
    --clean \
    scripts/stt-tts-ita.spec

echo "==> Pronto: dist/stt-tts-ita"
echo "    ffmpeg, espeak-ng e models/*.bin devono essere disponibili a runtime."
echo "    Suggerimento: distribuisci dist/stt-tts-ita + bin/whisper-cli + models/."
