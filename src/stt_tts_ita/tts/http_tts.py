"""Motore TTS remoto via HTTP (Kokoro e server compatibili OpenAI).

Supporta due protocolli, così l'app resta senza dipendenze Python e può usare
il container Kokoro (`efxtv/kokoro-tts`, Gradio su :7860) oppure un server
OpenAI-compatibile (es. Kokoro-FastAPI su /v1/audio/speech).

L'endpoint viene configurato con KOKORO_URL / --tts-url.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from .base import TTSError, TTSEngine


class HttpTTSEngine(TTSEngine):
    name = "kokoro"

    def __init__(
        self,
        base_url: str = "http://localhost:7860",
        mode: str = "openai",
        voice: str = "af_heart",
        model: str = "kokoro",
        speed: float = 1.0,
        timeout: float = 120.0,
        fn_index: int = 0,
    ):
        self.base_url = base_url.rstrip("/")
        self.mode = mode
        self.voice = voice
        self.model = model
        self.speed = speed
        self.timeout = timeout
        self.fn_index = fn_index

    def available(self) -> bool:
        """Verifica raggiungibilità del servizio (endpoint di health/config)."""
        for path in self._probe_paths():
            try:
                with urllib.request.urlopen(
                    f"{self.base_url}{path}", timeout=5
                ) as resp:
                    if resp.status < 500:
                        return True
            except (urllib.error.URLError, OSError, ValueError):
                continue
        return False

    def _probe_paths(self) -> tuple[str, ...]:
        if self.mode == "gradio":
            return ("/config", "/")
        return ("/health", "/v1/models", "/")

    def synthesize(self, text: str, out_path: str | Path, **kwargs) -> Path:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        voice = kwargs.get("voice") or self.voice
        speed = kwargs.get("speed") or self.speed
        if self.mode == "gradio":
            audio = self._gradio_predict(text, voice, speed)
        else:
            audio = self._openai_speech(text, voice, speed)
        out_path.write_bytes(audio)
        return out_path

    def _post(self, url: str, payload: dict, headers: dict | None = None) -> bytes:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            raise TTSError(f"HTTP {exc.code} da {url}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TTSError(f"Servizio TTS non raggiungibile ({url}): {exc.reason}") from exc

    def _openai_speech(self, text: str, voice: str, speed: float) -> bytes:
        payload = {
            "model": self.model,
            "input": text,
            "voice": voice,
            "response_format": "wav",
            "speed": speed,
        }
        return self._post(f"{self.base_url}/v1/audio/speech", payload)

    def _gradio_predict(self, text: str, voice: str, speed: float) -> bytes:
        """Chiama l'endpoint /api/predict di Gradio e scarica l'audio risultante."""
        payload = {"data": [text, voice, speed], "fn_index": self.fn_index}
        raw = self._post(f"{self.base_url}/api/predict", payload)
        result = json.loads(raw)
        data = result.get("data", [])
        url = _find_audio_url(data)
        if not url:
            raise TTSError(
                "Risposta Gradio senza URL audio. Verifica fn_index/parametri: "
                + json.dumps(data)[:300]
            )
        if url.startswith("/"):
            url = self.base_url + url
        elif not url.startswith("http"):
            url = f"{self.base_url}/{url.lstrip('/')}"
        with urllib.request.urlopen(url, timeout=self.timeout) as resp:
            return resp.read()


def _find_audio_url(data) -> str | None:
    if isinstance(data, str):
        if data.startswith("http") and _looks_like_audio(data):
            return data
        return None
    if isinstance(data, dict):
        for key in ("url", "path", "name"):
            val = data.get(key)
            if isinstance(val, str) and (val.startswith("http") or _looks_like_audio(val)):
                return val
        for val in data.values():
            found = _find_audio_url(val)
            if found:
                return found
    if isinstance(data, list):
        for item in data:
            found = _find_audio_url(item)
            if found:
                return found
    return None


def _looks_like_audio(value: str) -> bool:
    return value.lower().endswith((".wav", ".mp3", ".ogg", ".flac"))
