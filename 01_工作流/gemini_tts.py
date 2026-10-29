"""Gemini text-to-speech (Interactions API) for History Studio.

The API key comes from the GEMINI_API environment variable (falls back to the Windows user environment,
so a Studio started before the variable was set still finds it). The key is never printed or written.
"""
import base64
import json
import os
import urllib.error
import urllib.request
import wave
from pathlib import Path

API_URL = 'https://generativelanguage.googleapis.com/v1beta/interactions'
DEFAULT_MODEL = 'gemini-3.8-flash-tts'


def _key() -> str:
    k = os.environ.get('GEMINI_API', '').strip()
    if not k and os.name == 'nt':
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as h:
                k = str(winreg.QueryValueEx(h, 'GEMINI_API')[0]).strip()
        except OSError:
            k = ''
    if not k:
        raise RuntimeError('GEMINI_API is not set (Windows user environment variable)')
    return k


def _find_audio(o):
    """First base64 audio payload anywhere in the response."""
    if isinstance(o, dict):
        for k in ('data', 'audio'):
            v = o.get(k)
            if isinstance(v, str) and len(v) > 1000:
                return v
        for v in o.values():
            r = _find_audio(v)
            if r:
                return r
    elif isinstance(o, list):
        for v in o:
            r = _find_audio(v)
            if r:
                return r
    return None


def synthesize(text: str, out: Path, voice: str, style: str = '', model: str = DEFAULT_MODEL, timeout: int = 300) -> None:
    """Speak `text` verbatim with a prebuilt voice; `style` is a natural-language reading direction."""
    content = {'type': 'text', 'text': text}
    if style:
        content['annotations'] = [{'type': 'speech_metadata', 'style': style}]
    body = {'model': model, 'input': [{'type': 'user_input', 'content': [content]}],
            'response_format': {'type': 'audio'}, 'generation_config': {'speech_config': [{'voice': voice}]}}
    req = urllib.request.Request(API_URL, data=json.dumps(body).encode(), method='POST',
                                 headers={'Content-Type': 'application/json', 'x-goog-api-key': _key()})
    try:
        raw = urllib.request.urlopen(req, timeout=timeout).read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Gemini TTS HTTP {e.code}: {e.read()[:300]!r}') from None
    audio = _find_audio(json.loads(raw))
    if not audio:
        raise RuntimeError('Gemini TTS returned no audio')
    b = base64.b64decode(audio)
    out.parent.mkdir(parents=True, exist_ok=True)
    if b[:4] == b'RIFF':
        out.write_bytes(b)
    else:   # headerless 24 kHz mono s16le
        with wave.open(str(out), 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(b)
