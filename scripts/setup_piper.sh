#!/bin/sh
# Installa il motore vocale Piper (neurale, ONNX) per um ambiente Debian/glibc.
# Su Alpine/musl piper non è utilizzabile (onnxruntime richiede glibc): qui
# resta espeak-ng. Idempotente.
#
#   bin/piper/       binario nativo + librerie condivise
#   models/piper/    voci italiane (.onnx + .onnx.json)
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

PI_VER="2023.11.14-2"
PI_URL="https://github.com/rhasspy/piper/releases/download/${PI_VER}/piper_linux_x86_64.tar.gz"
VOICES_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/it/it_IT"
# elenco: cartellaVoce/qualita nomeModello
PI_VOICES="serena/medium it_IT-serena-medium
serena/high it_IT-serena-high
paola/medium it_IT-paola-medium
riccardo/x_low it_IT-riccardo-x_low"

if [ "$(uname -m)" != "x86_64" ]; then
    echo "!! Piper prebuilt disponibile solo per x86_64" >&2
    exit 1
fi
if ! command -v apt-get >/dev/null 2>&1; then
    echo "!! Piper richiede glibc: eseguilo su Debian/Ubuntu (o dentro la rootfs Debian)." >&2
    echo "   Su Alpine/musl resta espeak-ng." >&2
    exit 1
fi
if ! command -v curl >/dev/null 2>&1 && ! command -v wget >/dev/null 2>&1; then
    echo "!! Serve curl o wget" >&2
    exit 1
fi

dl() {
    if command -v curl >/dev/null 2>&1; then curl -fsSL -o "$2" "$1"
    else wget -qO "$2" "$1"; fi
}

echo "==> [1/2] Binario piper (glibc, $PI_VER)"
mkdir -p bin models/piper
if [ ! -x bin/piper/piper ]; then
    TMPD="$(mktemp -d)"
    dl "$PI_URL" "$TMPD/piper.tar.gz"
    tar -xzf "$TMPD/piper.tar.gz" -C bin/
    rm -rf "$TMPD"
    echo "    salvato: bin/piper/piper"
else
    echo "    bin/piper/piper già presente"
fi

echo "==> [2/2] Voci italiane in models/piper/"
missing=0
echo "$PI_VOICES" | while read -r dir name; do
    [ -z "$dir" ] && continue
    if [ ! -f "models/piper/${name}.onnx" ]; then
        dl "$VOICES_BASE/${dir}/${name}.onnx" "models/piper/${name}.onnx"
        dl "$VOICES_BASE/${dir}/${name}.onnx.json" "models/piper/${name}.onnx.json"
        echo "    + ${name}"
    else
        echo "    = ${name} (già presente)"
    fi
done
[ "$missing" -gt 0 ] && exit 1

echo "==> Verifica"
if [ -x bin/piper/piper ]; then
    echo "Ciao." | LD_LIBRARY_PATH="$(pwd)/bin/piper" \
        bin/piper/piper -m models/piper/it_IT-serena-medium.onnx \
        --output_file /tmp/piper-test.wav >/dev/null 2>&1 \
        && echo "    sintesi OK: /tmp/piper-test.wav (22050 Hz)"
fi
echo
echo "Uso: ./.venv/bin/stt-tts-ita run audio.m4a -o output --tts-engine piper"
echo "Voci italiane: --tts-voice it_IT-serena-medium|it_IT-serena-high|it_IT-paola-medium|it_IT-riccardo-x_low"