"""Generate a WAV with Xiaomi MiMo VoiceDesign for the AE workflow.

Uses the documented OpenAI-compatible chat completion endpoint. The API key
is read from MIMO_API_KEY and is never written to an AE job or source manifest.
"""

import base64
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_URL = "https://api.xiaomimimo.com/v1/chat/completions"
VOICE_DESIGN_MODEL = "mimo-v2.5-tts-voicedesign"
PRESET_MODEL = "mimo-v2.5-tts"
VOICE_CLONE_MODEL = "mimo-v2.5-tts-voiceclone"


def get_api_key() -> str | None:
    key = os.environ.get("MIMO_API_KEY")
    if key or os.name != "nt":
        return key
    # The desktop app may still have its old process environment immediately
    # after the user adds a Windows user variable.
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as entry:
            value, _ = winreg.QueryValueEx(entry, "MIMO_API_KEY")
            return value or None
    except (FileNotFoundError, OSError):
        return None


def _synthesize(text: str, output: str | Path, model: str,
                instruction: str, voice: str | None = None) -> None:
    key = get_api_key()
    if not key:
        raise RuntimeError("MIMO_API_KEY is required for MiMo TTS")
    if not text.strip():
        raise ValueError("MiMo narration text must be nonempty")
    if model == VOICE_DESIGN_MODEL and not instruction.strip():
        raise ValueError("MiMo VoiceDesign needs a voice description")

    audio = {"format": "wav"}
    if voice is not None:
        audio["voice"] = voice
    else:
        audio["optimize_text_preview"] = False

    messages = []
    if instruction.strip():
        messages.append({"role": "user", "content": instruction})
    messages.append({"role": "assistant", "content": text})

    payload = {
        "model": model,
        "messages": messages,
        "audio": audio,
    }
    request = Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(3):
        try:
            with urlopen(request, timeout=180) as response:
                result = json.load(response)
            break
        except HTTPError as exc:
            if exc.code in (429, 503) and attempt < 2:
                time.sleep(5 * (attempt + 1))
                continue
            raise RuntimeError(f"MiMo TTS request failed with HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(f"MiMo TTS network error: {exc.reason}") from exc

    try:
        audio_data = result["choices"][0]["message"]["audio"]["data"]
        audio_bytes = base64.b64decode(audio_data, validate=True)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise RuntimeError("MiMo TTS response did not contain base64 audio") from exc
    if not (audio_bytes.startswith(b"RIFF") and audio_bytes[8:12] == b"WAVE"):
        raise RuntimeError("MiMo TTS returned data that is not a WAV file")
    Path(output).write_bytes(audio_bytes)


def synthesize_voice_design(text: str, output: str | Path, description: str) -> None:
    _synthesize(text, output, VOICE_DESIGN_MODEL, description)


def synthesize_preset(text: str, output: str | Path,
                      voice: str = "茉莉", style: str = "") -> None:
    _synthesize(text, output, PRESET_MODEL, style, voice)


def synthesize_voice_clone(text: str, output: str | Path,
                           reference_audio: str | Path, style: str = "") -> None:
    reference = Path(reference_audio)
    mime = {".wav": "audio/wav", ".mp3": "audio/mpeg"}.get(reference.suffix.lower())
    if mime is None:
        raise ValueError("MiMo voice clone reference must be WAV or MP3")
    encoded = base64.b64encode(reference.read_bytes()).decode("ascii")
    if len(encoded) > 10 * 1024 * 1024:
        raise ValueError("MiMo voice clone reference exceeds the 10 MB Base64 limit")
    voice = f"data:{mime};base64,{encoded}"
    _synthesize(text, output, VOICE_CLONE_MODEL, style, voice)
