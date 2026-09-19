import copy
import re

import pytest
from fastapi.testclient import TestClient

from factu.erp import ERPClient
from factu.web import create_app


def test_detail_has_only_decision_buttons_and_no_time_input(bundle):
    service, batch, *_ = bundle
    service.process(batch, ocr=False)
    doc = service.store.one('SELECT id FROM documents')['id']
    with TestClient(create_app(service.store.root)) as client:
        html = client.get('/documents/' + doc).text
        assert re.findall(r'data-human-choice="([^"]+)"', html) == ['PAGAR', 'NO_PAGAR']
        assert 'Pedir información' not in html
        assert 'Minutos dedicados' not in html and 'name="minutes"' not in html
        assert 'Comprobar mi decisión' in html and 'Confirmar decisión' in html


@pytest.mark.parametrize('result', ['PAGAR', 'NO_PAGAR'])
def test_human_decision_can_be_previewed_and_saved_without_minutes(bundle, result):
    service, batch, *_ = bundle
    service.process(batch, ocr=False)
    doc = service.store.one('SELECT id FROM documents')['id']
    app = create_app(service.store.root)
    body = {'result': result, 'actor': 'Marta', 'reason': 'He comprobado el original y la respuesta documentada.',
            'evidence': 'Confirmación del responsable, referencia 52', 'acknowledged': []}
    with TestClient(app) as client:
        headers = {'X-CSRF-Token': app.state.service.store.csrf_token}
        preview = client.post(f'/api/documents/{doc}/answer/preview', json=body, headers=headers)
        assert preview.status_code == 200, preview.text
        assert not service.store.all('SELECT * FROM human_decisions')
        saved = client.post(f'/api/documents/{doc}/answer/commit',
                            json={**body, 'preview_token': preview.json()['preview_token']}, headers=headers)
        assert saved.status_code == 200, saved.text
    assert service.export_rows(batch)[0]['result'] == result
    assert service.dashboard(batch)['metrics']['human_seconds'] == 0
    assert service.store.verify_audit()['valid']


def test_erp_selector_uses_existing_preview_without_file_or_automatic_commit(bundle, monkeypatch):
    service, batch, *_ = bundle
    service.process(batch, ocr=False)
    original_snapshot = service.batch(batch)['snapshot_id']
    snapshot = copy.deepcopy(service.store.source(original_snapshot))
    snapshot['rows'][0]['estado'] = 'PAGADA'
    monkeypatch.setattr(ERPClient, 'snapshot', lambda self: snapshot)
    app = create_app(service.store.root)
    with TestClient(app) as client:
        html = client.get('/sources', params={'batch': batch}).text
        assert '<option value="erp">Datos contables (ERP)</option>' in html
        assert 'class="erp-change-form"' not in html
        assert 'No necesitas subir un archivo.' in html
        headers = {'X-CSRF-Token': app.state.service.store.csrf_token}
        response = client.post(f'/api/batches/{batch}/changes/erp', json={'actor': '', 'reason': ''}, headers=headers)
        assert response.status_code == 200, response.text
        plan = response.json()
        assert plan['affected'][0]['after'] == 'NO_PAGAR'
        assert service.batch(batch)['snapshot_id'] == original_snapshot
        assert service.export_rows(batch)[0]['result'] == 'PAGAR'
        page = client.get('/sources', params={'batch': batch, 'change': plan['id']}).text
        assert 'TODAVÍA SIN APLICAR' in page and 'Aplicar actualización' in page
        assert client.post(f"/api/changes/{plan['id']}/commit", headers=headers).status_code == 200
        assert service.export_rows(batch)[0]['result'] == 'NO_PAGAR'
    assert service.store.verify_audit()['valid']
