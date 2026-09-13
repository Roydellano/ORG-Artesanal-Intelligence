"""Server-side ElevenLabs credentials and short-lived voice connections."""
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values

ENV_PATH = Path(__file__).resolve().parents[1] / '.env'
BASE = 'https://api.elevenlabs.io/v1'


class VoiceError(RuntimeError):
    pass


def settings():
    values = {**dotenv_values(ENV_PATH), **os.environ}
    return {name: str(values.get(name) or '').strip() for name in
            ('ELEVENLABS_API_KEY', 'ELEVENLABS_AGENT_ID', 'ELEVENLABS_VOICE_ID', 'ELEVENLABS_TOOL_ID')}


def request(method, path, *, payload=None, params=None):
    key = settings()['ELEVENLABS_API_KEY']
    if not key:
        raise VoiceError('Add ELEVENLABS_API_KEY to the server .env, then run the voice setup command in README.')
    try:
        response = httpx.request(method, BASE + path, headers={'xi-api-key': key},
                                 json=payload, params=params, timeout=15)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as error:
        raise VoiceError(f'ElevenLabs HTTP {error.response.status_code}. Check API permissions, agent configuration and available credits.') from None
    except (httpx.HTTPError, ValueError):
        raise VoiceError('ElevenLabs connection failed or returned an invalid response. Try again later.') from None


def signed_session():
    agent = settings()['ELEVENLABS_AGENT_ID']
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', agent):
        raise VoiceError('Create the voice agent with: python -m tools.setup_voice')
    result = request('GET', '/convai/conversation/get-signed-url', params={'agent_id': agent})
    url = result.get('signed_url', '') if isinstance(result, dict) else ''
    try:
        parsed = urlsplit(url)
        valid = parsed.scheme == 'wss' and parsed.hostname == 'api.elevenlabs.io' and not parsed.username
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise VoiceError('ElevenLabs returned an invalid voice connection URL.')
    return {'signed_url': url, 'max_seconds': 180}
