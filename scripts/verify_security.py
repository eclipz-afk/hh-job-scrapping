"""Check local services without starting ingestion or exposing credentials."""

from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import dotenv_values
import requests
from sqlalchemy import create_engine, text

from app.core.config import load_settings


def main() -> None:
    values = dotenv_values(ROOT / ".env")
    settings = load_settings()
    api_base = "http://127.0.0.1:" + str(settings.flask_port) + settings.api_prefix
    headers = {"Authorization": "Bearer " + settings.etl_api_token}
    checks = {}
    with requests.Session() as client:
        client.trust_env = False
        health = client.get(api_base + "/health", timeout=10)
        checks["api_health"] = health.status_code == 200
        checks["api_headers"] = health.headers.get("X-Content-Type-Options") == "nosniff"
        checks["unauthorized_etl"] = client.post(api_base + "/etl/run", json={}, timeout=10).status_code == 401
        checks["oversized_etl"] = client.post(api_base + "/etl/run", json={"target_rows": 10001}, headers=headers, timeout=10).status_code == 400
        checks["invalid_json_type"] = client.post(api_base + "/etl/run", json=[], headers=headers, timeout=10).status_code == 400
        checks["bad_pagination"] = client.get(api_base + "/jobs", params={"page": "invalid"}, timeout=10).status_code == 400
        checks["untrusted_origin"] = "Access-Control-Allow-Origin" not in client.get(api_base + "/health", headers={"Origin": "https://attacker.invalid"}, timeout=10).headers
        frontend = client.get("http://127.0.0.1:8080", timeout=10)
        checks["frontend_health"] = frontend.status_code == 200
        checks["frontend_headers"] = frontend.headers.get("X-Frame-Options") == "DENY" and "frame-ancestors" in frontend.headers.get("Content-Security-Policy", "")
        checks["env_not_served"] = client.get("http://127.0.0.1:8080/.env", timeout=10).status_code in (403, 404)
        checks["script_integrity"] = frontend.text.count('integrity="sha384-') == 2
        config = client.get("http://127.0.0.1:8080/js/config.js", timeout=10)
        checks["token_not_in_frontend"] = bool(settings.etl_api_token) and settings.etl_api_token not in frontend.text + config.text
        overview = client.get(api_base + "/metrics/overview", timeout=10)
        overview.raise_for_status()
        jobs = overview.json()["total_jobs"]
        checks["database_rows_present"] = jobs > 0
        print("jobs_after", jobs)

        docker_settings = replace(settings, database_url=None, postgres_host="127.0.0.1", postgres_port=int(values.get("POSTGRES_HOST_PORT", "5433")))
        engine = create_engine(docker_settings.sqlalchemy_database_uri, hide_parameters=True, connect_args={"connect_timeout": 5})
        try:
            with engine.connect() as connection:
                checks["database_matches_api"] = connection.execute(text("SELECT count(*) FROM jobs")).scalar_one() == jobs
                acquired = connection.execute(text("SELECT pg_try_advisory_xact_lock(726194203)")).scalar_one()
                checks["etl_lock_acquired"] = bool(acquired)
                if acquired:
                    response = client.post(api_base + "/etl/run", json={"target_rows": 1}, headers=headers, timeout=10)
                    checks["concurrent_etl_rejected"] = response.status_code == 409
        finally:
            engine.dispose()

    for check, passed in checks.items():
        print(check, "PASS" if passed else "FAIL")
    raise SystemExit(0 if all(checks.values()) else 1)


if __name__ == "__main__":
    main()
