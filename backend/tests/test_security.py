from dataclasses import asdict, replace
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import SQLAlchemyError

import app as app_module
from app.api import routes
from app.core.config import load_settings
from app.etl import pipeline as pipeline_module
from app.etl.pipeline import EtlAlreadyRunning, JobETLPipeline
from app.etl.sources.hh import HHSource
from app.etl.types import EtlResult


@pytest.fixture
def application(monkeypatch):
    settings = replace(load_settings(), etl_api_token="a" * 48, cors_origins=["http://localhost:8080"])
    monkeypatch.setattr(app_module, "load_settings", lambda: settings)
    monkeypatch.setattr(app_module, "init_engine", lambda _: None)
    monkeypatch.setattr(app_module, "create_all_tables", lambda: None)
    app = app_module.create_app()
    app.config["TESTING"] = True
    return app


def auth():
    return {"Authorization": "Bearer " + "a" * 48}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "Basic anything"}, {"Authorization": "Bearer \u043f\u0430\u0440\u043e\u043b\u044c"}])
def test_unauthorized_etl_never_starts(application, monkeypatch, headers):
    run = Mock()
    monkeypatch.setattr(routes.JobETLPipeline, "run", run)
    response = application.test_client().post("/api/v1/etl/run", json={"target_rows": 5000}, headers=headers)
    assert response.status_code == 401
    run.assert_not_called()


def test_etl_disabled_without_token(application, monkeypatch):
    application.extensions["settings"].etl_api_token = ""
    run = Mock()
    monkeypatch.setattr(routes.JobETLPipeline, "run", run)
    assert application.test_client().post("/api/v1/etl/run", json={}, headers=auth()).status_code == 503
    run.assert_not_called()


@pytest.mark.parametrize("body", [[], "string", None, {"target_rows": True}, {"target_rows": 0}, {"target_rows": -1}, {"target_rows": 10001}, {"target_rows": 2.5}, {"target_rows": "5000"}])
def test_invalid_etl_payload_rejected(application, monkeypatch, body):
    run = Mock()
    monkeypatch.setattr(routes.JobETLPipeline, "run", run)
    import json
    response = application.test_client().post("/api/v1/etl/run", data=json.dumps(body), content_type="application/json", headers=auth())
    assert response.status_code == 400
    run.assert_not_called()


def test_etl_authorized_and_bounded(application, monkeypatch):
    result = EtlResult(5000, 5000, 5000, 5000, 0, 0)
    run = Mock(return_value=result)
    monkeypatch.setattr(routes.JobETLPipeline, "run", run)
    response = application.test_client().post("/api/v1/etl/run", json={"target_rows": 5000}, headers=auth())
    assert response.status_code == 200
    assert response.json == asdict(result)
    run.assert_called_once_with(target_rows=5000)


def test_etl_conflict_returns_409(application, monkeypatch):
    monkeypatch.setattr(routes.JobETLPipeline, "run", Mock(side_effect=EtlAlreadyRunning))
    assert application.test_client().post("/api/v1/etl/run", json={}, headers=auth()).status_code == 409


def test_large_body_rejected(application, monkeypatch):
    run = Mock()
    monkeypatch.setattr(routes.JobETLPipeline, "run", run)
    response = application.test_client().post("/api/v1/etl/run", json={"padding": "x" * 20000}, headers=auth())
    assert response.status_code == 413
    run.assert_not_called()


@pytest.mark.parametrize("path", ["/jobs?page=abc", "/jobs?page=0", "/jobs?page_size=101", "/jobs?search=" + "a" * 201, "/metrics/skills?limit=abc", "/metrics/locations?limit=-1", "/metrics/employers?limit=31"])
def test_bad_queries_rejected_without_database(application, path):
    assert application.test_client().get("/api/v1" + path).status_code == 400


def test_errors_do_not_disclose_secrets(application, monkeypatch, caplog):
    secret = "simulated-database-credential"
    monkeypatch.setattr(routes, "session_scope", Mock(side_effect=SQLAlchemyError(secret)))
    response = application.test_client().get("/api/v1/metrics/overview")
    assert response.status_code == 500
    assert response.json == {"error": "Internal server error"}
    assert secret not in response.get_data(as_text=True)
    assert secret not in caplog.text


def test_cors_and_headers(application):
    client = application.test_client()
    assert "Access-Control-Allow-Origin" not in client.get("/api/v1/health", headers={"Origin": "https://attacker.invalid"}).headers
    response = client.options("/api/v1/etl/run", headers={"Origin": "http://localhost:8080", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Authorization"})
    assert response.status_code in (200, 204)
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:8080"
    assert "Authorization" in response.headers["Access-Control-Allow-Headers"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert not application.debug


def test_database_password_encoding_and_redaction():
    password = "p@ss:/?# word"
    settings = replace(load_settings(), database_url=None, postgres_password=password, etl_api_token="sensitive-token")
    assert settings.sqlalchemy_database_uri.password == password
    assert password not in str(settings.sqlalchemy_database_uri)
    assert password not in repr(settings)
    assert "sensitive-token" not in repr(settings)


def test_concurrent_ingestion_stops_before_scraping(monkeypatch):
    session = Mock()
    session.execute.return_value.scalar_one.return_value = False

    @contextmanager
    def scope():
        yield session

    monkeypatch.setattr(pipeline_module, "session_scope", scope)
    pipeline = JobETLPipeline(load_settings())
    pipeline._scrape = Mock()
    with pytest.raises(EtlAlreadyRunning):
        pipeline.run(5000)
    pipeline._scrape.assert_not_called()


def test_scraped_link_cannot_change_fetch_host():
    html = '''<div data-qa="vacancy-serp__vacancy">
      <a data-qa="serp-item__title" href="http://127.0.0.1:8000/vacancy/123">Developer</a>
      <span data-qa="vacancy-serp__vacancy-employer">Acme</span>
      <span data-qa="vacancy-serp__vacancy-address">Moscow</span>
    </div>'''
    jobs = HHSource._parse_html_cards(html)
    assert len(jobs) == 1
    assert jobs[0].url == "https://hh.ru/vacancy/123"
    jobs[0].external_id = "../internal"
    client = Mock()
    assert HHSource()._enrich_from_vacancy_page(client, jobs[0]) is None
    client.get.assert_not_called()
