import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from forensic_auditor import qa
from forensic_auditor.api import app, register, sessions
from forensic_auditor.investigation import Investigation
from openrouter_client import OpenRouterError


CONFIG = {'model': 'test-model', 'timeout': 5, 'max_tokens': 2048}


def test_context_history_privacy_and_citation_validation():
    case = {'status': 'incomplete', 'findings': [{'claim': 'Acme discrepancy', 'evidence': ['bank:1']}],
            'leads': [{'state': 'dismissed', 'reason': 'Refund checked'}],
            'totals': {'MXN': 12345}, 'timeline': [{'tool': 'reconcile', 'result': {'original': 'SECRET'}}],
            'source_evidence': {'bank:1': 'SECRET'}}
    def mask(value):
        return json.loads(json.dumps(value).replace('Acme', 'Entity-1').replace('bank:1', 'Ref-1'))
    with patch.object(qa, 'settings', return_value=CONFIG), patch.object(qa, 'chat', return_value=json.dumps(
        {'answer': 'The case remains incomplete.', 'evidence': ['Ref-1']})) as chat:
        result = qa.explain(case, 'Explain Acme user@example.com', ['bank:1', 'bank:other'], mask=mask,
                            history=[{'question': 'Earlier question', 'answer': 'Earlier explanation'}])
        sent = json.dumps(chat.call_args.args[0])
        assert 'SECRET' not in sent and 'Acme' not in sent and 'user@example.com' not in sent
        assert 'bank:other' not in sent
        assert 'Refund checked' in sent and '12345' in sent and 'Earlier question' in sent
        assert result['evidence'] == ['bank:1']
        assert chat.call_args.kwargs['synthetic'] is False


@pytest.mark.parametrize('response', ['not JSON', '{"answer":"Invented","evidence":["other-case:1"]}',
                                      '{"answer":3,"evidence":[]}'])
def test_bad_model_answers_fail_closed(response):
    with patch.object(qa, 'settings', return_value=CONFIG), patch.object(qa, 'chat', return_value=response):
        with pytest.raises(OpenRouterError, match='invalid answer'):
            qa.explain({'status': 'offline_complete'}, 'Explain', [], mask=lambda x: x)


def test_api_defaults_to_llm_and_keeps_history_local():
    # Existing generator returns public records and separate evaluator ground truth.
    from forensic_auditor.synthetic_records import records
    first = register(records(17, 'all', False), synthetic=True)['session_id']
    second = register(records(18, 'all', False), synthetic=True)['session_id']
    try:
        for sid in (first, second):
            sessions[sid]['job'] = Investigation(sessions[sid]['data'])
            sessions[sid]['job'].run()
        def respond(messages, **kwargs):
            context = json.loads(messages[1]['content'])
            assert context['case']['findings']
            return json.dumps({'answer': 'Supported discrepancy in the supplied records.',
                               'evidence': context['allowed_evidence'][:1]})
        with TestClient(app) as client, patch.object(qa, 'settings', return_value=CONFIG), patch.object(qa, 'chat', side_effect=respond):
            base = f'/api/datasets/{first}'
            result = client.post(base + '/ask', json={'question': 'Explain the findings'})
            assert result.status_code == 200, result.text
            assert result.json()['mode'] == 'ai'
            assert client.get(base + '/evidence', params={'ref': result.json()['evidence'][0]}).status_code == 200
            assert len(sessions[first]['qa_history']) == 1
            assert 'qa_history' not in sessions[second]
        with TestClient(app) as client, patch.object(qa, 'settings', return_value=CONFIG), patch.object(qa, 'chat', side_effect=OpenRouterError('Provider unavailable')):
            failure = client.post(base + '/ask', json={'question': 'Explain'})
            assert failure.status_code == 502
            assert len(sessions[first]['qa_history']) == 1
    finally:
        sessions.pop(first, None)
        sessions.pop(second, None)
