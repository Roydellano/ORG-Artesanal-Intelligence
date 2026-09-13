import io
from pathlib import Path
import zipfile

from fastapi.testclient import TestClient

from forensic_auditor.api import app
from tools.legacy.demo import generate


def test_main_upload_recognizes_nested_student_materials_with_readme():
    example = Path(__file__).resolve().parents[1] / 'specs/student-materials/forensic-auditor/estate_csv_example'
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for source in example.iterdir():
            if source.is_file():
                archive.writestr(f'estate_csv_example/{source.name}', source.read_bytes())
    with TestClient(app) as client:
        response = client.post('/api/datasets/upload?seed=42',
                               files={'file': ('estate_csv_example.zip', stream.getvalue(), 'application/zip')})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['kind'] == 'official'
        assert len(result['coverage']) == 8
        assert set(result['coverage'].values()) == {1}
        sid = result['session_id']
        try:
            assert client.get(f'/api/estates/{sid}/case').json()['status'] == 'ready'
        finally:
            client.delete(f'/api/estates/{sid}')


def test_main_upload_keeps_original_csv_format():
    content, _ = generate(2026)
    with TestClient(app) as client:
        response = client.post('/api/datasets/upload', files={'file': ('records.zip', content, 'application/zip')})
        assert response.status_code == 200, response.text
        result = response.json()
        assert 'kind' not in result
        assert 'suppliers' in result['coverage']
        client.delete(f'/api/datasets/{result["session_id"]}')
