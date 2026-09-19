# Istruzioni per l'utente — Installazione e build (Alpine / Debian)

Questa guida spiega come installare l'applicazione STT + TTS Italiano e come
creare l'eseguibile autocontenuto su **Alpine Linux** e **Debian/Ubuntu**.
Tutti i comandi vanno eseguiti dal root del repo (`/data`):

```sh
cd /data
```

---

## 1. Prerequisiti di sistema

### Su Alpine Linux (musl)

```sh
apk add python3 py3-pip ffmpeg espeak-ng git build-base cmake
```

### Su Debian / Ubuntu (glibc)

```sh
apt-get update
apt-get install -y python3 python3-venv python3-pip ffmpeg espeak-ng git build-essential cmake curl
```

### Voce neurale Piper (solo Debian/Ubuntu)

Piper è un TTS neurale che gira in locale (modelli ONNX), qualità molto
superiore a espeak-ng. Richiede **glibc** → su Alpine/musl non è utilizzabile
(onnxruntime richiede glibc) e si resta su espeak-ng.

```sh
sh scripts/setup_piper.sh      # scarica bin/piper/ + voci in models/piper/
```

Poi, per usare la voce neurale:

```sh
./.venv/bin/stt-tts-ita run audio.m4a -o output --tts-engine piper
./.venv/bin/stt-tts-ita run video.mp4 -o output --tts-engine piper   # + dubbing
```

Voci italiane: `it_IT-serena-medium` (default), `it_IT-serena-high`,
`it_IT-paola-medium`, `it_IT-riccardo-x_low` (via `--tts-voice`). Override
percorsi: `STT_TTS_PIPER_BIN` / `STT_TTS_PIPER_MODELS_DIR`.

---

## 2. Installazione completa (identica su entrambi)

Lo script installa le dipendenze, crea il virtualenv, compila `whisper.cpp` e
scarica il modello `small-q5_1` (~181 MB). È idempotente: puoi rilanciarlo.

```sh
sh scripts/setup.sh
```

Verifica che tutto sia pronto:

```sh
./.venv/bin/stt-tts-ita info
```

Esempio di utilizzo:

```sh
./.venv/bin/stt-tts-ita run audio.m4a -o output          # audio -> trascrizione + TTS
./.venv/bin/stt-tts-ita run video.mp4 -o output          # video -> + output/video.dubbed.mp4
./.venv/bin/stt-tts-ita transcribe audio.mp3 -o output   # solo trascrizione
```

---

## 3. Eseguibile autocontenuto

Ci sono due tipi di eseguibile, con differenze importanti.

### Opzione A — Zipapp (portabile: Alpine e Debian)

Un archivio eseguibile Python che **funziona su entrambi i sistemi**:
basta avere `python3 >= 3.10` installato.

```sh
sh scripts/build_zipapp.sh          # produce dist/stt-tts-ita.pyz (~111 KB)
```

Eseguire dal root del progetto (trova da solo modelli e binari):

```sh
./dist/stt-tts-ita.pyz info
./dist/stt-tts-ita.pyz run video.mp4 -o output
```

Se lo lanci da un'altra cartella, indicagli la posizione del progetto:

```sh
STT_TTS_ROOT=/data ./dist/stt-tts-ita.pyz info
```

### Opzione B — Binario nativo PyInstaller autocontenuto (~445 MB)

```sh
sh scripts/build_binary.sh          # produce dist/stt-tts-ita
```

**ATTENZIONE — il binario è legato al sistema in cui viene compilato:**

| Compilato su | Binario | Funziona su |
| --- | --- | --- |
| Debian/Ubuntu | glibc-linked | Debian/Ubuntu e altre distro glibc |
| Alpine | musl-linked | solo Alpine/musl |

Il binario **non è portabile tra i due**: se lo compili su Alpine non gira su
Debian e viceversa. Per un eseguibile che funzioni ovunque usa lo **zipapp**.

Il binario include **tutto**: `whisper-cli`, il modello
`models/ggml-small-q5_1.bin`, il motore Piper con le voci italiane
(`models/piper/`). È un single-file: funziona da qualsiasi cartella. A runtime
restano esterni solo `ffmpeg` e `espeak-ng` di sistema. Un modello custom può
essere usato con `STT_TTS_MODEL=/percorso/modello.bin`.

---

## 4. Build dell'eseguibile PyInstaller per Debian (da Debian)

Per ottenere un eseguibile per Debian/Ubuntu devi compilarlo **su una macchina
Debian/Ubuntu**:

```sh
# su una macchina Debian/Ubuntu
cd /data
sh scripts/setup.sh          # dipendenze apt + venv + whisper + modello
sh scripts/build_binary.sh   # produce dist/stt-tts-ita (glibc, per Debian)
./dist/stt-tts-ita info      # verifica
```

Se hai solo Alpine ma devi produrre il binario Debian, hai due strade:

**a) Con Docker** (semplice, serve il daemon Docker):

```sh
docker run --rm -v /data:/src -w /src debian:bookworm \
    bash -c "apt-get update && apt-get install -y python3 python3-venv python3-pip ffmpeg espeak-ng git build-essential cmake && sh scripts/setup.sh && sh scripts/build_binary.sh"
```

**b) Senza Docker: rootfs Debian + proot (dal container Alpine)**

PyInstaller non è un cross-compiler: il binario eredita la libc dell'ambiente di
build (glibc su Debian, musl su Alpine). si può comunque **compilare da Alpine
per Debian** usando una rootfs Debian in user-space:

```sh
# 1. Estrai la rootfs Debian (usa solo la stdlib Python; scrive in ./srv/debian-rootfs)
apk add --no-cache python3 proot procps        # su Alpine solo la prima volta
python3 scripts/debian_rootfs.py
#    -> /srv/debian-rootfs da poter usare via proot
# Per una libc più vecchia usa Debian 11 (archiviata): 
#   python3 scripts/debian_rootfs.py --tag bullseye-slim --dest /srv/debian-bullseye
#   -> binario compatibile con Debian >= 11 / Ubuntu >= 20.04 (glibc 2.31)

# 2. Bootstra dei toolchain nella rootfs (la prima esecuzione installa gpgv, poi ri-firma apt)
#    Su bullseye (EOL): apt punta ad archive.debian.org e l'immagine include già
#    pacchetti di sicurezza più nuovi dell'archivio -> serve un downgrade mirato:
proot -r srv/debian-bullseye -b /proc:/proc -b /dev:/dev -b /sys:/sys -0 \
    /usr/bin/sh -c "cd /root/build && sh scripts/setup.sh && apt-get install -y libpython3.9 && sh scripts/build_binary.sh"

# 3. Copia il binario glibc fuori dalla rootfs
cp srv/debian-rootfs/root/build/dist/stt-tts-ita ./dist/stt-tts-ita
```

Il binario è costruito dallo spec `scripts/stt-tts-ita.spec`, che **non
impacchetta le librerie runtime GCC** (`libstdc++.so.6`, `libgcc_s`, `libgomp`):
PyInstaller metterebbe la copia estratta in `LD_LIBRARY_PATH` per tutti i
subprocessi (ffmpeg, piper, whisper-cli), e su distro con librerie native più
nuove (es. ffmpeg RPM Fusion su Fedora, che chiede `GLIBCXX_3.4.29/32`) ffmpeg
fallirebbe con `version 'GLIBCXX_...' not found`. Queste librerie sono presenti
su qualunque sistema glibc, quindi vengono usate quelle del sistema.

Richiede `apk add proot` (l'esecuzione di binari glibc dentro la rootfs usa
proot, che in questo ambiente è necessario perché il container non consente
`mount`/`mknod`/`debootstrap`). NOTA: i comandi proot vanno eseguiti da una
directory che **esiste anche dentro la rootfs** (`cd` esplicito, perché proot
parte da `/`).

Il binario `dist/stt-tts-ita` prodotto così è glibc-linked e funziona su
Debian/Ubuntu. La versione minima di glibc richiesta dipende dalla distro di
build: con **bookworm** (glibc 2.36) richiede glibc 2.34 (Debian >= 12 /
Ubuntu >= 22.04); per girare anche su **Debian 11 / Ubuntu 20.04** compila su
**bullseye** (glibc 2.31) come sopra.

**Bundle pronto all'uso (Debian).** Dopo la build binaria si può assemblare una
cartella autocontenuta con Piper e modello inclusi:

```sh
# (copiato già pronto in dist/debian/ durante la build)
cd dist/debian && ./stt-tts-ita run audio.m4a -o out --tts-engine piper
```

Vedi `dist/debian/README.txt`.

---

## 5. Cosa serve a runtime

Qualunque eseguibile tu usi, sulla macchina finale servono (non impacchettati):

- `ffmpeg` (conversione audio / mux video)
- `espeak-ng` (TTS locale, fallback)
- un modello whisper in `models/*.bin` (es. `ggml-small-q5_1.bin`)

Per la voce neurale Piper (Debian/glibc), in più:

- `bin/piper/` (binario nativo + librerie)
- le voci in `models/piper/*.onnx`

Riferimenti: queste istruzioni sono un estratto guidato — per i dettagli
completi vedi `README.md`.