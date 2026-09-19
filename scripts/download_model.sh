#!/bin/sh
# Scarica un modello ggml di Whisper (multilingua, supporta l'italiano).
# Uso: scripts/download_model.sh [nome]   (default: small-q5_1)
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
NAME="${1:-${STT_TTS_MODEL_NAME:-small-q5_1}}"
DEST="$ROOT/models/ggml-${NAME}.bin"
URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-${NAME}.bin"

mkdir -p "$ROOT/models"
if [ -f "$DEST" ]; then
    echo "Già presente: $DEST"
    exit 0
fi

echo "==> Download $URL"
if command -v wget >/dev/null 2>&1; then
    wget -O "$DEST" "$URL"
elif command -v curl >/dev/null 2>&1; then
    curl -L -o "$DEST" "$URL"
else
    echo "Serve wget o curl" >&2
    exit 1
fi

echo "==> Salvato: $DEST"
echo "Modelli utili: tiny, base, small-q5_1, medium-q5_0, large-v3"
