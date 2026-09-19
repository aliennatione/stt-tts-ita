# AGENTS.md — STT + TTS Italiano

App open source: audio/video italiano → trascrizione con timestamp → TTS, con
dubbing dei video. **Root del repo: `/data`** (questo workspace). Vedi
`README.md` per l'uso e `ISTRUZIONI.md` per la guida utente (setup + build eseguibile).

## Comandi principali

```sh
cd /data
sh scripts/setup.sh                                    # setup idempotente (Alpine/Debian)
./.venv/bin/stt-tts-ita info                           # verifica ambiente
./.venv/bin/stt-tts-ita run audio.m4a -o output        # trascrivi + TTS
./.venv/bin/stt-tts-ita run video.mp4 -o output        # + output/video.dubbed.mp4
./.venv/bin/stt-tts-ita transcribe audio.mp3 -o output # solo trascrizione
./.venv/bin/stt-tts-ita tts output/audio.json -o output# TTS da transcript JSON
./.venv/bin/python -m unittest discover -s tests -v    # test (12, veloci)
```

Il pacchetto è in `.venv` con `pip install -e .`; senza installazione:
`PYTHONPATH=src ./.venv/bin/python -m stt_tts_ita info`.

## Vincolo d'ambiente che cambia tutto (Alpine/musl)

Il container è **Alpine Linux (musl)**, senza Docker e senza GPU. Le wheel
`manylinux` **non** funzionano e non esistono wheel `musllinux` per
`ctranslate2`, `onnxruntime`, `torch` → **faster-whisper, Piper e Kokoro pip non
sono installabili qui**. Non riprovare `pip install faster-whisper`: fallisce su
build di `av`/`ctranslate2`.

Stack reale:
- **STT**: `whisper.cpp` compilato nativamente (`bin/whisper-cli`, git-ignored).
- **TTS**: `espeak-ng` locale (sempre disponibile); Kokoro solo via **HTTP**
  (`--tts-engine kokoro --tts-mode gradio|openai`); **Piper** neurale offline
  su Debian/glibc (`--tts-engine piper`, binario in `bin/piper/`, voci in
  `models/piper/`, vedi `scripts/setup_piper.sh`). Piper NON gira su Alpine/musl
  (onnxruntime richiede glibc) → lì resta espeak.
- **Video**: ffmpeg per conversione WAV 16 kHz mono e mux dubbing.

## Architettura

- `src/stt_tts_ita/audio.py` — conversione media→WAV 16 kHz mono, `probe_duration`,
  `has_audio_stream`, `dub_video` (mux: `-c:v copy`, audio `apad`+`-t` per durata invariata).
- `src/stt_tts_ita/transcribe.py` — wrapper `whisper-cli` (`-oj`) + parsing segmenti.
- `src/stt_tts_ita/formats.py` — SRT/VTT/TXT/JSON.
- `src/stt_tts_ita/pipeline.py` — orchestrazione; `synthesize_aligned` genera TTS
  per-segmento + silenzi nei gap e concat ffmpeg.
- `src/stt_tts_ita/tts/` — `espeak.py`, `http_tts.py` (Kokoro: `openai` o `gradio`), `piper.py` (CLI nativa: `-m <voce>.onnx --output_file --length_scale=1/speed`, `LD_LIBRARY_PATH` = dir binario + `lib/`), `build_engine`.
- `src/stt_tts_ita/cli.py` — comandi `run|transcribe|tts|info`.

Zero dipendenze Python obbligatorie: tutto via `subprocess`/`urllib` (stdlib).

## Eseguibile autocontenuto (sintesi)

- **Zipapp** (`scripts/build_zipapp.sh`): `.pyz` portabile Alpine **e** Debian
  (`python3 >= 3.10`). Da eseguire dal root del progetto (usa CWD), oppure con
  `STT_TTS_ROOT`/`STT_TTS_MODEL`/`STT_TTS_WHISPER_CLI`.
- **PyInstaller** (`scripts/build_binary.sh`): binario nativo ELF **linked con la
  libc del build environment** → non cross-platform tra Alpine (musl) e Debian
  (glibc). MA è possibile **compilare da Alpine per Debian** senza una macchina
  Debian: vedi `scripts/debian_rootfs.py` + proot in `ISTRUZIONI.md` §4b. Il
  metodo (verificato): `python3 scripts/debian_rootfs.py` estrae gli strati di
  `debian:bookworm-slim` dal Registry Docker in `srv/debian-rootfs` (solo
  stdlib); poi dentro la rootfs via `proot -r srv/debian-rootfs -b /proc:/proc
  -b /dev:/dev -b /sys:/sys -0` si fa `setup.sh` + `build_binary.sh`; il binario
  glibc va copiato fuori in `dist/stt-tts-ita`.
  - Lo spec (`scripts/stt-tts-ita.spec`) embedda **tutto**: `bin/whisper-cli`,
    `models/ggml-small-q5_1.bin`, `bin/piper/` e `models/piper/` → il risultato
    è un **singolo file onefile ~445 MB** totalmente autocontenuto (restano solo
    ffmpeg/espeak-ng di sistema).
  - Il container qui non permette `mount`/`mknod`/`debootstrap` (no
    CAP_SYS_ADMIN/CAP_MKNOD) → proot serve anche per esporre `/dev` reale.
  - First-time nella rootfs: `apt-get update` fallisce senza `gpgv` (slim) →
    bootstrap con `apt-get update -o Acquire::AllowInsecureRepositories=true`
    poi `apt-get install -y --allow-unauthenticated gpgv debian-archive-keyring`
    e ri-`apt-get update` firmato.
- Dettagli per l'utente finale in `ISTRUZIONI.md`.

## Regole specifiche del progetto

- I video con input `.mp4/.mkv/...` attivano il dubbing di default; `--no-dub` lo disattiva.
  `--dub` su input non video solleva `ValueError` (gestito in `cli.main`).
- La durata del video dubbato deve restare identica: usa `apad` + `-t <durata video>`.
- `build_engine("auto")` preferisce Kokoro se raggiungibile, altrimenti espeak.
- **Non aggiungere dipendenze pip pesanti** (torch, ctranslate2, etc.): rompono il
  target musl e l'eseguibile PyInstaller.
- **Piper = glibc**: installabile solo su Debian/glibc (`scripts/setup_piper.sh`),
  incluso dentro la rootfs Debian. Non riprovare su Alpine.
- `bin/`, `models/`, `output/`, `assets/samples/`, `.venv/`, `dist/`, `build/` sono
  git-ignored: rigenerabili con `scripts/`. NOTA: `/data/models` è un mount
  **read-only** in questo ambiente → i modelli si aggiornano nella rootfs/proot
  (`srv/debian-rootfs/root/build/models/`) e vanno nel bundle `dist/debian/`.

## Verifica

```sh
./.venv/bin/python -m unittest discover -s tests -v   # 18 test, <1s
sh scripts/fetch_test_samples.sh                       # campioni LibriVox (public domain)
```

Campioni italiani: *La mandragola* (Machiavelli, multi-voce) e *Cuore* (De Amicis,
voce singola) da archive.org. Verifica dubbing: crea un mp4 con ffmpeg e controlla
che video=h264 (copy), audio=aac e durata invariata.

## Gotchas note

- **`sh` vs `bash`**: brace expansion `{a,b,c}` non funziona in `sh`. Usa liste
  separate o un loop (successo nel primo setup: `{bin,models,...}` è stato preso
  come nome literal).
- **espeak voice=None**: quando `--tts-engine espeak` senza `--tts-voice`, il
  kwargs `voice=None` sovrascriveva il default `"it"`. Corretto con
  `kwargs.get("voice") or self.voice` in `tts/espeak.py` e `tts/http_tts.py`.
- **`__main__.py` PyInstaller**: l'importo relativo `from .cli import main` fallisce
  con PyInstaller (script top-level). Usa importo assoluto.
- **proot**: parte in `/` (il CWD host `/data` non esiste nella rootfs guest) →
  mettere sempre `cd /root/build &&` prima dei comandi; preferire `-r` esplicito
  (con `-R` il guest-`/root` risultava una vista diversa/incoerente).
- **Sync del codice nella rootfs**: `/root/build` è una **copia** (non un bind) di
  `/data`. `cp -r /data/src /srv/.../root/build/src` con destino già esistente
  crea un NIDO `src/src/` e la build usa lo `src` vecchio! Usare sempre
  `rm -rf <dest> && cp -r <src> <dest>` (o `rsync --delete`).
- **proot cwd**: quando si lancia un binario con `cd /data …` dentro proot, il cwd
  che vede l'app può collassare (es. su `/tmp`): le verifiche "da cartella pulita"
  vanno fatte controllando i path effettivi nel JSON di `info`, non assumendo il cwd.
- **rootfs Debian**: within the rootfs apt è unsigned alla prima `apt-get update`
  (manca `gpgv` nella slim) → bootstrap come da AGENTS.md sopra. La rootfs va
  creata con `python3 scripts/debian_rootfs.py` (servono `python3` e rete; niente
  Docker). Per compat con Debian 11/Ubuntu 20.04 (glibc 2.31): build su rootfs
  **bullseye-slim** (`--tag bullseye-slim --dest …`, apt → `archive.debian.org`).
- **Bullseye EOL gotcha**: l'immagine docker di bullseye-slim include già gli
  update di sicurezza (es. libc6/perl u14/u5) più nuovi dell'archivio EOL (u11/u3)
  → apt fallisce con "held broken packages". Fix verificato: downgrade mirato
  `apt-get install -y --allow-downgrades libc6=<u11> perl-base=<u3>` prima del
  resto. PyInstaller su bullseye richiede in più `apt-get install libpython3.9`
  (libpython3.9.so.1.0) prima di `build_binary.sh`.
- **Requisiti glibc dei deliverable**: whisper-cli compilato su bullseye richiede
  max GLIBC_2.29 (verificato con `strings | sort -uV | tail`); il bundle
  `dist/debian/` è ricompilato su bullseye e gira su Debian >= 11 / Ubuntu >= 20.04.
- **PyInstaller e libstdc++ bundled**: il bootloader mette `/tmp/_MEI...` in cima a
  `LD_LIBRARY_PATH` per TUTTI i subprocessi. Se PyInstaller impacchetta la
  `libstdc++.so.6` (e `libgcc_s`/`libgomp`) dell'ambiente di build, su distro con
  librerie native più nuove (es. ffmpeg RPM Fusion su Fedora chiede
  `GLIBCXX_3.4.29/32`, `CXXABI_1.3.15`) ffmpeg/spawn fallisce. Fix: `scripts/stt-tts-ita.spec`
  filtra fuori dal `binaries` le librerie runtime GCC (presenti ovunque su glibc);
  `build_binary.sh` ora costruisce da spec, quindi il bundle NON contiene quelle
  librerie (verifica: `pyi-archive_viewer -l dist/stt-tts-ita | grep libstdc` vuoto).
  Nota: in uno .spec i path sono relativi alla dir dello spec (PyInstaller cambia
  CWD) → usare `SPECPATH` + `os.path.join` con `ROOT` assoluto; niente `__file__`.
- **Whisper==traduzione con bundling**: excluded le lib gcc runtime, whisper-cli e
  piper usano quelle di sistema: verificato su bullseye (glibc 2.31) e Fedora ha
  versioni più nuove compatibili in avanti.
- **`resolve_whisper_cli` vs CWD**: nel binario PyInstaller la copia embedded
  (`sys._MEIPASS/bin/whisper-cli`) vince sul percorso `PROJECT_ROOT/bin/whisper-cli`
  (derivato dal CWD): se quell'ultimo esiste rotto/vuoto (es. clone senza `bin/`)
  si userebbe comunque quello e ffmpeg/whisper fallirebbe con Errno 2. Ordine:
  `STT_TTS_WHISPER_CLI` esplicito (se file reale) → `_MEIPASS/bin` → `PROJECT_ROOT/bin`
  → `PATH`. Stessa logica per `resolve_model` (`STT_TTS_MODEL` → `_MEIPASS/models` →
  `PROJECT_ROOT/models`) e per le voci Piper (`models_path` con fallback `_MEIPASS`).
  Test: `tests/test_translate.py::ResolveWhisperCliTest` / `ResolveModelTest`.