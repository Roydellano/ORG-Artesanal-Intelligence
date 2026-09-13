from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from forensic_auditor.api import app, sessions
from forensic_auditor import voice
from tools.setup_voice import agent_config, TOOL, main as setup_voice_main


def test_signing_keeps_key_server_side_and_validates_token():
    config = {'ELEVENLABS_API_KEY': 'secret', 'ELEVENLABS_AGENT_ID': 'agent_demo'}
    response = httpx.Response(200, json={'token': 'ephemeral-conversation-token'},
                              request=httpx.Request('GET', 'https://api.elevenlabs.io'))
    with patch.object(voice, 'settings', return_value=config), patch.object(voice.httpx, 'request', return_value=response) as call:
        result = voice.signed_session()
        assert 'secret' not in str(result)
        assert result == {'conversation_token': 'ephemeral-conversation-token', 'max_seconds': 180}
        assert call.call_args.args[:2] == ('GET', voice.BASE + '/convai/conversation/token')
        assert call.call_args.kwargs['headers'] == {'xi-api-key': 'secret'}
        assert call.call_args.kwargs['params'] == {'agent_id': 'agent_demo'}
        assert call.call_args.kwargs['json'] is None
    for invalid in ({}, {'token': ''}, {'token': ' '}, {'token': 42}, {'token': 'x' * 16385}):
        with patch.object(voice, 'settings', return_value=config), patch.object(voice, 'request', return_value=invalid):
            with pytest.raises(voice.VoiceError):
                voice.signed_session()


def test_voice_rejects_uploaded_records_before_provider_call():
    sessions['voice-upload'] = {'synthetic': False, 'job': object()}
    try:
        with TestClient(app) as client, patch('forensic_auditor.api.signed_session') as provider:
            for path, body in [('/voice/session', {}), ('/voice/ask', {'question': 'Explain'})]:
                assert client.post('/api/datasets/voice-upload' + path, json=body).status_code == 409
            provider.assert_not_called()
    finally:
        sessions.pop('voice-upload', None)


def test_voice_requires_case_and_uses_existing_ai_answer_route():
    sessions['voice-demo'] = {'synthetic': True, 'job': None}
    try:
        with TestClient(app) as client:
            assert client.post('/api/datasets/voice-demo/voice/session').status_code == 409
            sessions['voice-demo']['job'] = object()
            with patch('forensic_auditor.api.ask', return_value={'answer': 'Supported', 'evidence': ['R-1']}) as ask:
                response = client.post('/api/datasets/voice-demo/voice/ask', json={'question': 'Explain', 'mode': 'offline'})
                assert response.status_code == 200
                assert ask.call_args.args[1].mode == 'ai'
    finally:
        sessions.pop('voice-demo', None)


def test_voice_falls_back_to_offline_when_ai_provider_fails():
    from fastapi import HTTPException
    sessions['voice-demo'] = {'synthetic': True, 'job': object()}
    try:
        with TestClient(app) as client:
            def ask_mock(sid, req):
                if req.mode == 'ai':
                    raise HTTPException(502, 'OpenRouter HTTP 429: Rate-limited')
                return {'answer': 'Offline extraction fallback', 'evidence': ['R-1']}
            with patch('forensic_auditor.api.ask', side_effect=ask_mock):
                response = client.post('/api/datasets/voice-demo/voice/ask', json={'question': 'Explain'})
                assert response.status_code == 200
                assert response.json()['answer'] == 'Offline extraction fallback'
    finally:
        sessions.pop('voice-demo', None)


def test_provider_errors_are_sanitized():
    response = httpx.Response(401, text='private provider body secret', request=httpx.Request('GET', voice.BASE))
    with patch.object(voice, 'settings', return_value={'ELEVENLABS_API_KEY': 'secret'}), patch.object(voice.httpx, 'request', return_value=response):
        with pytest.raises(voice.VoiceError, match='HTTP 401') as error:
            voice.request('GET', '/test')
        assert 'secret' not in str(error.value)


def test_agent_config_requires_tool_wait_and_auth_and_bounds_duration():
    config = agent_config('tool_demo')
    assert config['conversation_config']['tts']['model_id'] == 'eleven_flash_v2'
    assert agent_config('tool_demo', 'custom_voice')['conversation_config']['tts'] == {
        'model_id': 'eleven_flash_v2', 'voice_id': 'custom_voice'}
    assert config['platform_settings']['auth']['enable_auth']
    assert not config['platform_settings']['privacy']['record_voice']
    assert config['conversation_config']['conversation']['max_duration_seconds'] == 180
    assert config['conversation_config']['agent']['prompt']['tool_ids'] == ['tool_demo']
    assert config['conversation_config']['agent']['language'] == 'en'
    assert 'Hello' in config['conversation_config']['agent']['first_message']
    assert 'English' in config['conversation_config']['agent']['prompt']['prompt']
    assert TOOL['expects_response']
    assert TOOL['response_timeout_secs'] > 60


def test_setup_voice_main_updates_configured_agent():
    config = {'ELEVENLABS_API_KEY': 'secret', 'ELEVENLABS_TOOL_ID': 'tool_123',
              'ELEVENLABS_AGENT_ID': 'agent_123', 'ELEVENLABS_VOICE_ID': ''}
    with patch('tools.setup_voice.settings', return_value=config), \
         patch('tools.setup_voice.request', return_value={'status': 'ok'}) as req:
        setup_voice_main()
        assert req.call_args.args[:2] == ('PATCH', '/convai/agents/agent_123')
        payload = req.call_args.kwargs['payload']
        assert payload['conversation_config']['agent']['language'] == 'en'
        assert 'Hello' in payload['conversation_config']['agent']['first_message']
