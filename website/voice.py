import os
from typing import Tuple

import requests


class VoiceServiceError(Exception):
    """Raised when the voice service cannot fulfill a request."""


def _get_api_key() -> str:
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        raise VoiceServiceError(
            'OPENAI_API_KEY is not configured on the server. '
            'Add it to enable ChatGPT voice features.'
        )
    return api_key


def synthesize_speech(text: str, voice: str = 'alloy') -> Tuple[bytes, str]:
    """Generate speech audio from text using OpenAI's TTS endpoint."""
    api_key = _get_api_key()
    model = os.getenv('OPENAI_TTS_MODEL', 'gpt-4o-mini-tts')
    response = requests.post(
        'https://api.openai.com/v1/audio/speech',
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        json={
            'model': model,
            'voice': voice or 'alloy',
            'input': text,
            'format': 'mp3',
        },
        timeout=90,
    )
    if response.status_code >= 400:
        raise VoiceServiceError(
            f"TTS request failed ({response.status_code}): {response.text[:200]}"
        )
    return response.content, response.headers.get('Content-Type', 'audio/mpeg')


def transcribe_audio(file_storage) -> str:
    """Transcribe audio using OpenAI's Whisper/ChatGPT transcription endpoint."""
    api_key = _get_api_key()
    model = os.getenv('OPENAI_STT_MODEL', 'gpt-4o-mini-transcribe')
    filename = getattr(file_storage, 'filename', 'voice-input.webm') or 'voice-input.webm'
    content_type = file_storage.content_type or 'audio/webm'

    response = requests.post(
        'https://api.openai.com/v1/audio/transcriptions',
        headers={'Authorization': f'Bearer {api_key}'},
        data={'model': model, 'response_format': 'json'},
        files={'file': (filename, file_storage.stream, content_type)},
        timeout=90,
    )

    if response.status_code >= 400:
        raise VoiceServiceError(
            f"Transcription failed ({response.status_code}): {response.text[:200]}"
        )

    payload = response.json()
    return (payload.get('text') or '').strip()

