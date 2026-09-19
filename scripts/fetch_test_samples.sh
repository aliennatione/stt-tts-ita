#!/bin/sh
# Scarica campioni audio italiani di pubblico dominio (LibriVox/Archive.org)
# e ne ricava segmenti brevi 16 kHz mono per i test.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
DEST="$ROOT/assets/samples"
TMP="${TMPDIR:-/tmp}/stt_tts_samples"
mkdir -p "$DEST" "$TMP"

dl() { # url file
    if command -v wget >/dev/null 2>&1; then
        wget -q -O "$2" "$1"
    else
        curl -fsSL -o "$2" "$1"
    fi
}

echo "==> Download sorgenti (LibriVox, public domain)"
dl "https://archive.org/download/mandragola_2108_librivox/mandragola_1_machiavelli_64kb.mp3" "$TMP/mand1.mp3"
dl "https://archive.org/download/mandragola_2108_librivox/mandragola_2_machiavelli_64kb.mp3" "$TMP/mand2.mp3"
dl "https://archive.org/download/cuore_fg_librivox/cuore_00_deamicis_64kb.mp3" "$TMP/cuore00.mp3"

echo "==> Estrazione segmenti 16 kHz mono"
clip() { # ss input output
    ffmpeg -y -loglevel error -ss "$1" -t 22 -i "$2" -ar 16000 -ac 1 -c:a pcm_s16le "$3"
}
clip 75  "$TMP/mand1.mp3"  "$DEST/mandragola_atto1_a.wav"
clip 320 "$TMP/mand1.mp3"  "$DEST/mandragola_atto1_b.wav"
clip 40  "$TMP/mand2.mp3"  "$DEST/mandragola_atto2.wav"
clip 8   "$TMP/cuore00.mp3" "$DEST/cuore_intro.wav"

echo "==> Video di prova per il dubbing (360p, audio dal campione Cuore)"
ffmpeg -y -loglevel error -f lavfi -i "color=c=blue:s=320x240:d=22" \
    -i "$DEST/cuore_intro.wav" -map 0:v -map 1:a \
    -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$DEST/test_video.mp4"

echo "==> Pronti in $DEST"
ls -lh "$DEST"
