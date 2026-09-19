#!/bin/sh
# Crea un archivio eseguibile Python autocontenuto (zipapp) senza dipendenze extra.
# Il .pyz richiede un interprete Python 3 (>=3.10) a runtime.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p dist
./.venv/bin/python -m zipapp src -o dist/stt-tts-ita.pyz -p "/usr/bin/env python3"

echo "==> Pronto: dist/stt-tts-ita.pyz"
echo "    Uso: python3 dist/stt-tts-ita.pyz info"
echo "    Per modelli/binari esterni imposta STT_TTS_ROOT, STT_TTS_MODEL, STT_TTS_WHISPER_CLI."
