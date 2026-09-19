# STT + TTS Italiano

Applicazione **100% open source** che:

1. prende un file audio di parlato italiano (`m4a`, `wav`, `mp3`, e altri) **o un video** (`mp4`, `mkv`, `webm`, …);
2. ne fa la **trascrizione con timestamp** (segmenti con inizio/fine);
3. la **rigenera in voce (TTS)**;
4. per i video, **sostituisce la traccia audio** con il TTS (dubbing), mantenendo il video intatto.

Nessuna API proprietaria, nessuna GPU richiesta, nessuna dipendenza Python
obbligatoria: l'orchestratore usa solo la standard library e richiama binari
nativi open source.

## Architettura

```
audio (m4a/wav/mp3) o video (mp4/mkv) --ffmpeg--> WAV 16kHz mono
                                     |
                                     v
                        whisper.cpp (whisper-cli)  -->  segmenti + timestamp
                                     |
                                     v
                    json / srt / vtt / txt (+ manifest)
                                     |
                                     v
             TTS:  Kokoro (HTTP)  |  Piper (locale, Debian)  |  espeak-ng (fallback)
                                     |
                     +---------------+----------------+
                     v                                v
              audio rigenerato (.wav)        video con audio sostituito (.mp4)
```

| Componente | Tecnologia | Licenza | Ruolo |
| --- | --- | --- | --- |
| STT | [whisper.cpp](https://github.com/ggml-org/whisper.cpp) | MIT | trascrizione con timestamp, CPU |
| Modello | Whisper multilingua `small-q5_1` (GGML) | MIT | riconosce l'italiano |
| TTS (qualità) | [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) via Docker/HTTP | Apache-2.0 | voce neurale |
| TTS (locale) | [Piper](https://github.com/rhasspy/piper) (ONNX) su Debian/glibc | MIT | voce neurale offline |
| TTS (fallback) | [espeak-ng](https://github.com/espeak-ng/espeak-ng) | GPL-3.0 | offline, sempre disponibile |
| Conversione audio | ffmpeg | LGPL/GPL | decodifica input e montaggio |

> Il TTS Kokoro è opzionale: se non raggiungibile, l'app usa automaticamente
> `espeak-ng`. Si può anche orchestrare Kokoro come container esterno
> (`docker run -p 7860:7860 efxtv/kokoro-tts`) e puntarci `--tts-url`.
> Su Debian/Ubuntu si può usare **Piper** in locale (voce neurale, senza server):
> vedi `scripts/setup_piper.sh` e la sezione "Piper". Su Alpine/musl Piper non
> gira (onnxruntime richiede glibc) e resta espeak-ng.

## Installazione (ambiente isolato)

Lo script crea un **virtualenv** in `.venv/`, installa le dipendenze di sistema
(python, ffmpeg, espeak-ng, git, cmake, compilatore), compila `whisper.cpp` e
scarica il modello. È idempotente.

```sh
git clone <questo-repo> stt-tts-ita
cd stt-tts-ita
sh scripts/setup.sh
```

Su Alpine (musl) e Debian/Ubuntu (glibc) lo script sceglie automaticamente il
gestore pacchetti (`apk` o `apt`).

### Passi separati

```sh
sh scripts/build_whisper_cpp.sh          # compila bin/whisper-cli
sh scripts/download_model.sh small-q5_1  # scarica models/ggml-small-q5_1.bin
```

### Da usare dal venv

```sh
./.venv/bin/stt-tts-ita info             # verifica binari/modelli/motori
```

In alternativa, senza installare il pacchetto:

```sh
PYTHONPATH=src ./.venv/bin/python -m stt_tts_ita info
```

## Uso

```sh
# Pipeline completa: trascrizione + TTS
./.venv/bin/stt-tts-ita run audio.m4a -o output

# Solo trascrizione (JSON/SRT/VTT/TXT con timestamp)
./.venv/bin/stt-tts-ita transcribe audio.mp3 -o output

# TTS da un transcript JSON già prodotto
./.venv/bin/stt-tts-ita tts output/audio.json -o output

# Ridoppiaggio allineato ai timestamp originali (silenzi nei gap)
./.venv/bin/stt-tts-ita run audio.wav -o output --align

# TTS remoto Kokoro (Gradio del container efxtv/kokoro-tts)
./.venv/bin/stt-tts-ita run audio.wav -o output \
    --tts-engine kokoro --tts-url http://localhost:7860 --tts-mode gradio

# TTS remoto compatibile OpenAI (es. Kokoro-FastAPI)
./.venv/bin/stt-tts-ita run audio.wav -o output \
    --tts-engine kokoro --tts-url http://localhost:8880 --tts-mode openai

# TTS locale neurale Piper (su Debian/Ubuntu, dopo scripts/setup_piper.sh)
./.venv/bin/stt-tts-ita run audio.wav -o output --tts-engine piper

# Cambiare voce Piper (serena-high, paola-medium, riccardo-x_low)
./.venv/bin/stt-tts-ita run audio.wav -o output \
    --tts-engine piper --tts-voice it_IT-serena-high

# Lingua auto-rilevata + traduzione offline della trascrizione verso l'inglese
./.venv/bin/stt-tts-ita --lang auto run video.en.mkv -o output \
    --no-dub --no-tts --translate en --translate-engine whisper

# Film in inglese -> sottotitoli + voce italiana (richiede scripts/setup_argos.sh)
./.venv/bin/stt-tts-ita --lang auto run film.en.mkv -o output \
    --translate it --translate-engine argos --tts-engine piper --tts-voice it_IT-riccardo-x_low
```

### Esempi pronti all'uso

| Obiettivo | Comando |
| --- | --- |
| **Dubbing in italiano di un video EN** (traduzione + voce) | `stt-tts-ita --lang auto run film_en.mp4 -o out --translate it --translate-engine argos --tts-engine piper --tts-voice it_IT-riccardo-x_low` |
| **Sostituzione voce** (stessa lingua, niente traduzione) | `stt-tts-ita run film_it.mp4 -o out --tts-engine piper --tts-voice it_IT-riccardo-x_low` |
| Video IT → dubbing EN (con whisper, senza argos) | `stt-tts-ita --lang auto run film_it.mp4 -o out --translate en --translate-engine whisper --tts-engine piper --tts-voice en_US-lessac-medium` |
| Sostituzione voce con **espeak** (senza Piper) | `stt-tts-ita run clip.mp4 -o out --tts-engine espeak --tts-voice it` |
| Solo **trascrizione + sottotitoli** (niente TTS/dubbing) | `stt-tts-ita run film.mp4 -o out --no-dub --no-tts` |
| Solo trascrizione da audio | `stt-tts-ita transcribe intervista.m4a -o out` |
| Rigenerare la **voce da un JSON** esistente | `stt-tts-ita tts out/film.json -o out --tts-engine piper --tts-voice it_IT-paola-medium` |
| Dubbing + **WAV allineato** ai timestamp + velocità | `stt-tts-ita run lezione.mp4 -o out --tts-engine piper --tts-voice it_IT-serena-medium --align --tts-speed 1.1` |

Voci incluse nel binario (con `--tts-engine piper`):
italiano: `it_IT-serena-medium` (**donna**, default) · `it_IT-serena-high` ·
`it_IT-paola-medium` (donna) · `it_IT-riccardo-x_low` (**uomo**).
inglese: `en_US-lessac-medium` (donna) · `en_US-ryan-medium` (**uomo**).

### Lingua in ingresso e traduzione offline

Con il modello multilingua la lingua dell'audio viene **rilevata**
(`--lang auto`, default) e riportata nei file di trascrizione. La traduzione
di uscita è **sempre locale** (nessuna API):

- `--translate en --translate-engine whisper` → ritrascrive con
  `whisper-cli -tr` (nessuna dipendenza aggiuntiva; solo verso inglese);
- `--translate LINGUA --translate-engine argos` → traduttore neurale offline
  **argos-translate** per coppie arbitrarie (es. `en → it`). Richiede glibc:
  gli installa `sh scripts/setup_argos.sh` (param. `ARGOS_LANG`). A runtime è
  completamente offline.

Quando `--translate` è attivo la **voce** viene scelta sulla lingua di uscita
se non ne specifichi una: piper `it → it_IT-serena-medium`, espeak `lang`.

### Video e dubbing

Per un input video il dubbing è **automatico**: l'app estrae l'audio, lo
trascrive, genera il TTS **allineato ai timestamp originali** (con silenzi nei
gap) e sostituisce la traccia audio del video senza ricodificare il video.

```sh
# Dubbing automatico di un mp4
./.venv/bin/stt-tts-ita run video.mp4 -o output
# -> output/video.dubbed.mp4  (video: copy, audio: TTS allineato)

# Disattivare il dubbing (solo trascrizione + TTS wav)
./.venv/bin/stt-tts-ita run video.mp4 -o output --no-dub

# Forzare il dubbing (errore se l'input non è un video)
./.venv/bin/stt-tts-ita run clip.mkv -o output --dub
```

Comportamento del mux audio: il video è copiato (`-c:v copy`); l'audio TTS viene
riempito con silenzio se più corto (`apad`) o tagliato se più lungo (`-t`), così
la durata resta identica all'originale.

### Opzioni principali

| Opzione | Descrizione |
| --- | --- |
| `--tts-engine {auto,kokoro,piper,espeak}` | `auto` (default) usa Kokoro se raggiungibile, altrimenti espeak |
| `--tts-url` | URL base del servizio Kokoro |
| `--tts-mode {openai,gradio}` | protocollo HTTP del servizio TTS |
| `--tts-voice` | voce (es. `it` per espeak, `it_IT-serena-medium` per piper) |
| `--tts-speed` | velocità |
| `--align` | genera anche il WAV allineato ai timestamp |
| `--dub` / `--no-dub` | forza/disattiva la sostituzione della traccia audio del video (auto per i video) |
| `--format json srt vtt txt` | formati di trascrizione |
| `--model`, `--lang`, `--threads` | parametri Whisper (`--lang auto` = rilevata, default) |
| `--translate LANG` | traduce la trascrizione verso la lingua scelta (offline) |
| `--translate-engine {auto,whisper,argos}` | `auto`: whisper→`en`, argos→altre; `whisper`: solo `en` |

### Output

Per ogni input `nome.m4a` (o `nome.mp4`) vengono prodotti in `output/`:

- `nome.json` — segmenti con `start`/`end` in secondi
- `nome.srt`, `nome.vtt` — sottotitoli
- `nome.txt` — testo con timestamp
- `nome.tts.wav` — audio rigenerato
- `nome.aligned.wav` — (solo con `--align` o per video) audio sincronizzato
- `nome.dubbed.mp4` — (input video) video con la traccia audio sostituita
- `nome.manifest.json` — riepilogo dell'esecuzione

## Piper (voce neurale locale, Debian)

Piper è un TTS neurale (modelli ONNX) che gira **interamente in locale** senza
server. Richiede **glibc**: funziona su Debian/Ubuntu (e nel binario compilato
per Debian), non su Alpine/musl.

```sh
# su Debian/Ubuntu (rootfs inclusa via proot): scarica binario + voci italiane
sh scripts/setup_piper.sh

# usa la voce neurale
./.venv/bin/stt-tts-ita run audio.m4a -o output --tts-engine piper
./.venv/bin/stt-tts-ita run video.mp4 -o output --tts-engine piper  # + dubbing
```

Voci italiane disponibili: `it_IT-serena-medium` (default) e `it_IT-serena-high`
(femminili), `it_IT-paola-medium` (femminile) e `it_IT-riccardo-x_low`
(**maschile**). Il binario glibc finisce in `bin/piper/`, le voci in
`models/piper/`. Percorsi override: `STT_TTS_PIPER_BIN` /
`STT_TTS_PIPER_MODELS_DIR`.

## Eseguibile autocontenuto

Per distribuire senza Python/virtualenv e senza cartelle accessorie (restano
esterni solo ffmpeg e espeak-ng di sistema):

```sh
sh scripts/build_binary.sh
# prodotto: dist/stt-tts-ita  (~445 MB, single-file)
./dist/stt-tts-ita run audio.m4a -o output
```

Il binario PyInstaller impacchetta **tutto**: orchestratore, `whisper-cli`, il
modello `ggml-small-q5_1.bin`, Piper e le voci italiane (`models/piper/`).
Funziona da qualsiasi cartella. In alternativa, senza PyInstaller, si può
creare un archivio eseguibile Python (zipapp, che invece usa modello/binari
esterni):

```sh
sh scripts/build_zipapp.sh        # produce dist/stt-tts-ita.pyz
./.venv/bin/python dist/stt-tts-ita.pyz info
```

Voci italiane disponibili nel binario: `it_IT-serena-medium` (default, donna),
`it_IT-serena-high`, `it_IT-paola-medium`, `it_IT-riccardo-x_low` (**uomo**).
L'eseguibile Debian è pronto da copiare: vedi `dist/debian/README.txt`.

## Test

```sh
./.venv/bin/python -m unittest discover -s tests -v
```

### Verifica su audio reali (fonti libere)

La trascrizione è stata verificata su campioni italiani di pubblico dominio:

- *La mandragola* (Machiavelli), LibriVox — lettura corale, più voci:
  <https://archive.org/details/mandragola_2108_librivox>
- *Cuore* (De Amicis), LibriVox — lettore singolo:
  <https://archive.org/details/cuore_fg_librivox>

Rigenerazione dei campioni usati nei test:

```sh
sh scripts/fetch_test_samples.sh
```

## Note e limiti

- Whisper richiede WAV **16 kHz mono**: l'app converte automaticamente con ffmpeg.
- I modelli `small`/`medium` sono ~180–500 MB e vengono scaricati in `models/`.
- Su CPU espeak-ng è immediato; Kokoro è molto più lento senza GPU.
- Errori tipici sui testi poetici/arcaici sono normali con modelli piccoli;
  usa `--model medium-q5_0` o `large-v3` per maggiore accuratezza.

## Struttura

```
stt-tts-ita/
├── src/stt_tts_ita/
│   ├── audio.py         # conversione a WAV 16 kHz mono (ffmpeg)
│   ├── transcribe.py    # wrapper whisper-cli + parsing segmenti
│   ├── formats.py       # SRT/VTT/TXT/JSON
│   ├── pipeline.py      # pipeline end-to-end (+ allineamento)
│   ├── cli.py           # interfaccia a riga di comando
│   └── tts/             # motori TTS: espeak-ng, HTTP (Kokoro), Piper
├── scripts/             # setup, build whisper.cpp, modello, eseguibile, piper
├── tests/               # test stdlib unittest
├── bin/                 # whisper-cli, piper (git-ignored)
├── models/              # modelli GGML + voci piper (git-ignored)
└── output/              # risultati (git-ignored)
```

## Licenza

Codice dell'applicazione: MIT. Le dipendenze esterne mantengono le proprie
licenze (vedi tabella sopra).
