#!/bin/sh
# Setup completo dell'ambiente isolato (Alpine/musl o Debian/glibc).
# Idempotente: può essere rieseguito senza problemi.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

MODEL="${STT_TTS_MODEL_NAME:-small-q5_1}"
MODEL_FILE="models/ggml-${MODEL}.bin"
THREADS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"

echo "==> Progetto: $ROOT"

echo "==> [1/5] Dipendenze di sistema"
if command -v apk >/dev/null 2>&1; then
    apk add --no-cache python3 py3-pip ffmpeg espeak-ng git build-base cmake
elif command -v apt-get >/dev/null 2>&1; then
    apt-get update && apt-get install -y python3 python3-venv python3-pip ffmpeg espeak-ng git build-essential cmake
else
    echo "!! Gestore pacchetti non riconosciuto: installa manualmente python3, ffmpeg, espeak-ng, git, cmake, gcc" >&2
fi

echo "==> [2/5] Virtualenv isolato in .venv"
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
./.venv/bin/python -m pip install --upgrade pip >/dev/null
# Nessuna dipendenza Python obbligatoria (orchestratore stdlib). Solo dev:
./.venv/bin/python -m pip install -e . >/dev/null 2>&1 || true

echo "==> [3/5] Build di whisper.cpp in bin/"
if [ ! -x bin/whisper-cli ]; then
    ./scripts/build_whisper_cpp.sh
else
    echo "    bin/whisper-cli già presente"
fi

echo "==> [4/5] Download modello Whisper italiano ($MODEL)"
if [ ! -f "$MODEL_FILE" ]; then
    ./scripts/download_model.sh "$MODEL"
else
    echo "    $MODEL_FILE già presente"
fi

echo "==> [5/5] Verifica"
./.venv/bin/python -m stt_tts_ita info || true
echo
echo "Setup completato. Esempi:"
echo "  ./.venv/bin/stt-tts-ita run tuo_audio.m4a -o output"
echo "  ./.venv/bin/stt-tts-ita run tuo_audio.mp3 -o output --align"
