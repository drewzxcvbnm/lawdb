"""Unit tests run offline. LAWDB_INTEGRATION=1 also exercises the existing read-only DB."""
import os
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from app.main import app, decision, pdf_path, search_sql


def test_filters_bind_values_and_keep_source_dates():
    sql, params = search_sql("' OR 1=1 --", 'text', 'Court', '', '', date(2020,1,1), None, 'newest', 2)
    assert "' OR 1=1 --" not in sql
    assert params['q'] == "' OR 1=1 --"
    assert params['offset'] == 20
    assert 'd.registration_date >= %(date_from)s' in sql
    assert 'd.court = %(court)s' in sql
    assert 'candidates AS MATERIALIZED' in sql


def test_identifier_does_not_use_full_text_match():
    sql, params = search_sql('A123', 'identifier', '', '', '', None, None, 'relevance', 1)
    assert 'doc.tsv @@' not in sql
    assert 'd.case_number = %(q)s' in sql
    assert 'd.ecli = %(q)s' in sql


def test_page_boundaries_preserve_blank_interior_page():
    row = {'id': '3c66549d-1430-44c2-b4ce-3c3173bc4c3a', 'body': 'one\f\fthree\f'}
    db = Mock()
    db.execute.return_value.fetchone.return_value = row
    @contextmanager
    def connection():
        yield db
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(pool=SimpleNamespace(connection=connection))))
    result = decision(request, row['id'], 2)
    assert result['text'] == ''
    assert result['page_count'] == 3
    assert 'body' not in result


def test_validation_and_security_without_database():
    client = TestClient(app)
    for query in ['page=0', 'page=501', 'sort=sql', 'mode=unknown', 'date_from=nope', 'q=' + 'x'*301]:
        assert client.get('/api/search?' + query).status_code == 422
    assert client.get('/api/decisions/not-a-uuid/pdf').status_code == 422
    response = client.get('/')
    assert response.status_code == 200
    assert "script-src 'self'" in response.headers['content-security-policy']
    assert client.get('/', headers={'host':'evil.example'}).status_code == 400
    assert client.get('/api/decisions/00000000-0000-0000-0000-000000000000/pdf').status_code == 404


@pytest.mark.skipif(os.getenv('LAWDB_INTEGRATION') != '1', reason='Requires local corpus')
def test_real_collection_search_filters_reader_pdf():
    with TestClient(app) as client:
        catalog = client.get('/api/catalog')
        assert catalog.status_code == 200, catalog.text
        assert catalog.json()['searchable'] > 0
        recent = client.get('/api/search?sort=newest')
        assert recent.status_code == 200, recent.text
        item = recent.json()['items'][0]
        exact = client.get('/api/search', params={'q':item['case_number'],'mode':'identifier'})
        assert exact.status_code == 200, exact.text
        assert any(r['id'] == item['id'] for r in exact.json()['items'])
        filtered = client.get('/api/search', params={'court':item['court'],'date_from':item['registration_date'],'date_to':item['registration_date']})
        assert filtered.status_code == 200, filtered.text
        assert all(r['court']==item['court'] and r['registration_date']==item['registration_date'] for r in filtered.json()['items'])
        keyword = client.get('/api/search', params={'q':'darba līgums'})
        assert keyword.status_code == 200, keyword.text
        assert keyword.json()['items']
        match = keyword.json()['items'][0]
        assert '⟦' in match['snippet']
        reader = client.get(f"/api/decisions/{match['id']}", params={'page':match['match_page']})
        assert reader.status_code == 200, reader.text
        assert reader.json()['page_count'] >= match['match_page']
        pdf = client.get(f"/api/decisions/{match['id']}/pdf", headers={'Range':'bytes=0-99'})
        assert pdf.status_code == 206
        assert pdf.content.startswith(b'%PDF')
        assert client.get('/api/search?q=-darba').status_code == 422
        assert client.get('/api/search?date_from=2025-01-01&date_to=2020-01-01').status_code == 422
        assert client.get('/api/search?q=zzzxxyyimpossibleword').json()['items'] == []
        second = client.get('/api/search?page=2&sort=newest')
        assert second.status_code == 200
        assert not {r['id'] for r in recent.json()['items']} & {r['id'] for r in second.json()['items']}
