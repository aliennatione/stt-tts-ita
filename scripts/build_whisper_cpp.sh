#!/bin/sh
# Compila whisper.cpp e copia whisper-cli in bin/.
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
SRC="${WHISPER_CPP_SRC:-$ROOT/build/whisper.cpp}"
JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"

mkdir -p "$ROOT/bin" "$ROOT/build"

if [ ! -d "$SRC/.git" ]; then
    echo "==> Clone whisper.cpp"
    git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git "$SRC"
fi

echo "==> Configure (Release, statico)"
cmake -S "$SRC" -B "$SRC/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=OFF \
    -DWHISPER_BUILD_TESTS=OFF \
    -DWHISPER_BUILD_EXAMPLES=ON \
    -DWHISPER_BUILD_SERVER=OFF

echo "==> Build"
cmake --build "$SRC/build" --config Release -j "$JOBS"

cp "$SRC/build/bin/whisper-cli" "$ROOT/bin/whisper-cli"
echo "==> Pronto: $ROOT/bin/whisper-cli"
