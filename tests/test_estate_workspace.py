import time

from fastapi.testclient import TestClient

from forensic_auditor.api import app
from forensic_auditor.official.estate import cents
from tools.official_generate import generate_records, export_csv_zip


def test_zip_uses_shared_workspace_with_resolvable_sources_and_unchanged_exports(tmp_path):
    db, archive = tmp_path / 'estate.db', tmp_path / 'estate_csv.zip'
    generate_records(101, db)
    export_csv_zip(db, archive)
    with TestClient(app) as client:
        loaded = client.post('/api/datasets/upload?seed=101', files={'file': ('estate_csv.zip', archive.read_bytes())})
        assert loaded.status_code == 200, loaded.text
        sid = loaded.json()['session_id']
        base = f'/api/estates/{sid}/workspace'
        try:
            started = client.post(base + '/investigate', json={'mode': 'offline'})
            assert started.status_code == 200, started.text
            for _ in range(100):
                case = client.get(base + '/case').json()
                if case['status'] != 'running':
                    break
                time.sleep(.02)
            assert case['status'] == 'offline_complete'
            assert case['findings']
            original = client.get(f'/api/estates/{sid}/case?reveal=true').json()
            assert [f['amount_centavos'] for f in case['findings']] == [cents(f['peso_amount']) for f in original['findings']]
            assert len(case['leads']) == len(original['findings']) + len(original['leads_not_pursued'])
            refs = {r for f in case['findings'] for r in f['evidence']}
            for entry in case['timeline']:
                refs.update(entry['result']['evidence'])
                if entry['tool'] == 'trace_funds':
                    assert len(entry['result']['edges']) == len(entry['result']['evidence'])
            for ref in refs:
                source = client.get(base + '/evidence', params={'ref': ref})
                assert source.status_code == 200, source.text
                original_source = client.get(base + '/evidence', params={'ref': ref, 'reveal': True}).json()
                assert source.json()['original'] != original_source['original']
            for table, count in loaded.json()['coverage'].items():
                records = client.get(base + '/records/' + table).json()
                assert records['total'] == count
                for row in records['rows']:
                    assert client.get(base + '/evidence', params={'ref': row['evidence_id']}).status_code == 200
            answer = client.post(base + '/ask', json={'question': 'Explain the findings', 'mode': 'offline'}).json()
            assert answer['evidence'] and set(answer['evidence']) <= refs
            assert answer['case_status'] == case['status']
            assert client.get(base + '/export/json?full=true').json() == original
            assert client.get(base + '/export/replay?full=true').content.startswith(b'PK')
            assert client.get(base + '/evidence?ref=another-dataset').status_code == 404
        finally:
            client.delete(base)
