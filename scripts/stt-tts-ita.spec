# -*- mode: python ; coding: utf-8 -*-
# Spec PyInstaller per stt-tts-ita (onefile).
#
# Bundled tutto il necessario per STT + TTS:
#   - bin/whisper-cli        (whisper.cpp)
#   - models/ggml-small-q5_1.bin  (modello whisper, embedded)
#   - bin/piper/             (piper + libs onnxruntime, espeak-ng)
#   - models/piper/          (voci italiane Piper)
# Restano esterni (documentati): ffmpeg, espeak-ng di sistema.
#
# IMPORTANTE: le librerie runtime GCC (libstdc++, libgcc_s, libgomp) vengono
# ESCLUSE dal bundle: il bootloader le metterebbe in LD_LIBRARY_PATH per tutti
# i subprocess (es. ffmpeg/piper/whisper-cli) causando conflitti di versione
# quando il sistema la più recente (es. ffmpeg RPM Fusion su Fedora chiede
# GLIBCXX_3.4.32). Sono comunque presenti su qualunque sistema glibc.
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(ROOT, "src/stt_tts_ita/__main__.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=[(os.path.join(ROOT, "bin/whisper-cli"), "bin")],
    datas=[
        (os.path.join(ROOT, "models/ggml-small-q5_1.bin"), "models"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

_GCC_RUNTIME = ("libstdc++.so", "libgcc_s.so", "libgomp.so")


def _keep(binary) -> bool:
    # binary = (dest_name, src_path, typecode)
    base = os.path.basename(binary[1])
    for prefix in _GCC_RUNTIME:
        if base.startswith(prefix):
            print(f"  exclude: {base}")
            return False
    return True


a.binaries = [b for b in a.binaries if _keep(b)]

# Piper: binario + librerie native + voci neurali.
from PyInstaller.building.datastruct import Tree

a.datas += Tree(os.path.join(ROOT, "bin/piper"), prefix="bin/piper")
a.datas += Tree(os.path.join(ROOT, "models/piper"), prefix="models/piper")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="stt-tts-ita",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)