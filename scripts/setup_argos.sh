#!/bin/sh
# Installa argos-translate (traduzione neurale OFFLINE) per il supporto
# multi-lingua: rileva la lingua in ingresso (--lang auto) e traduce la
# trascrizione verso la lingua scelta con --translate (es. --translate it).
#
# Richiede glibc (Debian/Ubuntu) e rete SOLO per l'installazione/scaricamento
# dei modelli di lingua; a runtime è completamente offline e locale.
# Su Alpine/musl non è installabile (ctranslate2 non ha wheel musl).
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v apt-get >/dev/null 2>&1; then
    echo "!! argos-translate richiede glibc: eseguilo su Debian/Ubuntu (o dentro la rootfs Debian)." >&2
    echo "   Su Alpine/musl la traduzione offline resta quella del motore 'whisper' (solo verso 'en')." >&2
    exit 1
fi
if [ ! -x .venv/bin/python ]; then
    echo "Esegui prima scripts/setup.sh" >&2
    exit 1
fi

echo "==> [1/2] Installo argostranslate nel venv (ctranslate2, richiede glibc)"
./.venv/bin/python -m pip install --upgrade argostranslate

echo "==> [2/2] Scarico il modello di lingua (default: it = coppia en<->it)."
TARGET="${ARGOS_LANG:-it}"
./.venv/bin/argos-translate-manage --install-from-index "$TARGET"

echo
echo "==> Verifica rapida (en -> ${TARGET})"
printf 'Good morning, how are you?\n' | \
    ./.venv/bin/argos-translate --from-lang en --to-lang "$TARGET" || true

echo
echo "Uso: ./.venv/bin/stt-tts-ita run file.m4a -o out --lang auto --translate ${TARGET} --translate-engine argos"
echo "Voci in uscita: --tts-voice (es. it_IT-serena-medium per l'italiano, 'en' per espeak EN)"