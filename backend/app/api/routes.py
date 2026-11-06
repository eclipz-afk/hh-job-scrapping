from __future__ import annotations

from dataclasses import asdict
from secrets import compare_digest

from flask import Blueprint, abort, current_app, request

from app.db.base import session_scope
from app.db.repository import (
    get_employer_metrics,
    get_location_metrics,
    get_overview_metrics,
    get_salary_band_metrics,
    get_skill_metrics,
    get_timeline_metrics,
    list_jobs,
)
from app.etl.pipeline import EtlAlreadyRunning, JobETLPipeline


def _serialize_job(job) -> dict:
    return {
        "id": job.id,
        "source": job.source,
        "external_id": job.external_id,
        "title": job.title,
        "role_family": job.role_family,
        "company": job.company,
        "location": job.location,
        "country": job.country,
        "city": job.city,
        "employment_type": job.employment_type,
        "remote_type": job.remote_type,
        "salary_currency": job.salary_currency,
        "salary_from": job.salary_from,
        "salary_to": job.salary_to,
        "salary_usd_from": job.salary_usd_from,
        "salary_usd_to": job.salary_usd_to,
        "published_at": job.published_at.isoformat() if job.published_at else None,
        "url": job.url,
        "skills": [skill.name for skill in job.skills],
    }


def create_api_blueprint() -> Blueprint:
    bp = Blueprint("api", __name__)

    def integer_arg(name: str, default: int, maximum: int) -> int:
        try:
            value = int(request.args.get(name, default))
        except (TypeError, ValueError):
            abort(400)
        if not 1 <= value <= maximum:
            abort(400)
        return value

    def metric_filters() -> tuple[str | None, str | None]:
        role_family = request.args.get("role_family")
        source = request.args.get("source")
        return role_family, source

    @bp.get("/health")
    def health() -> tuple[dict, int]:
        return {"status": "ok"}, 200

    @bp.get("/jobs")
    def jobs() -> tuple[dict, int]:
        page = integer_arg("page", 1, 10000)
        page_size = integer_arg("page_size", 30, 100)
        role_family = request.args.get("role_family")
        source = request.args.get("source")
        search = request.args.get("search")
        if search and len(search) > 200:
            abort(400)

        with session_scope() as session:
            rows, total = list_jobs(
                session=session,
                page=page,
                page_size=page_size,
                role_family=role_family,
                source=source,
                search=search,
            )
            payload = [_serialize_job(job) for job in rows]

        return {
            "page": page,
            "page_size": page_size,
            "total": total,
            "items": payload,
        }, 200

    @bp.get("/metrics/overview")
    def metrics_overview() -> tuple[dict, int]:
        role_family, source = metric_filters()
        with session_scope() as session:
            payload = get_overview_metrics(session, role_family=role_family, source=source)
        return payload, 200

    @bp.get("/metrics/skills")
    def metrics_skills() -> tuple[list[dict], int]:
        limit = integer_arg("limit", 20, 50)
        role_family, source = metric_filters()
        with session_scope() as session:
            payload = get_skill_metrics(session, limit=limit, role_family=role_family, source=source)
        return payload, 200

    @bp.get("/metrics/salary-bands")
    def metrics_salary_bands() -> tuple[list[dict], int]:
        role_family, source = metric_filters()
        with session_scope() as session:
            payload = get_salary_band_metrics(session, role_family=role_family, source=source)
        return payload, 200

    @bp.get("/metrics/locations")
    def metrics_locations() -> tuple[list[dict], int]:
        limit = integer_arg("limit", 15, 50)
        role_family, source = metric_filters()
        with session_scope() as session:
            payload = get_location_metrics(session, limit=limit, role_family=role_family, source=source)
        return payload, 200

    @bp.get("/metrics/employers")
    def metrics_employers() -> tuple[list[dict], int]:
        limit = integer_arg("limit", 10, 30)
        role_family, source = metric_filters()
        with session_scope() as session:
            payload = get_employer_metrics(session, limit=limit, role_family=role_family, source=source)
        return payload, 200

    @bp.get("/metrics/timeline")
    def metrics_timeline() -> tuple[list[dict], int]:
        role_family, source = metric_filters()
        with session_scope() as session:
            payload = get_timeline_metrics(session, role_family=role_family, source=source)
        return payload, 200

    @bp.post("/etl/run")
    def etl_run() -> tuple[dict, int]:
        settings = current_app.extensions["settings"]
        if not settings.etl_api_token:
            return {"error": "ETL is disabled until ETL_API_TOKEN is configured"}, 503
        authorization = request.headers.get("Authorization", "").split()
        if (
            len(authorization) != 2
            or authorization[0].lower() != "bearer"
            or not compare_digest(authorization[1].encode(), settings.etl_api_token.encode())
        ):
            return {"error": "Unauthorized"}, 401

        request_payload = request.get_json()
        if not isinstance(request_payload, dict):
            return {"error": "JSON body must be an object"}, 400
        target_rows = request_payload.get("target_rows", settings.target_cleaned_rows)
        if type(target_rows) is not int or not 1 <= target_rows <= 10000:
            return {"error": "target_rows must be an integer between 1 and 10000"}, 400

        pipeline = JobETLPipeline(settings)
        try:
            result = pipeline.run(target_rows=target_rows)
        except EtlAlreadyRunning:
            return {"error": "ETL is already running"}, 409

        return asdict(result), 200

    return bp
