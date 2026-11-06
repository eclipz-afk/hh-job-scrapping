from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import case, delete, desc, func, literal, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Job, Skill, job_skills
from app.etl.types import CleanJob


def _chunked[T](items: Sequence[T], size: int) -> list[Sequence[T]]:
    if size <= 0:
        raise ValueError("size must be positive")
    return [items[idx : idx + size] for idx in range(0, len(items), size)]


def _metric_conditions(role_family: str | None, source: str | None) -> list:
    conditions = []
    if role_family:
        conditions.append(Job.role_family == role_family)
    if source:
        conditions.append(Job.source == source)
    return conditions


def upsert_jobs(session: Session, jobs: Sequence[CleanJob]) -> tuple[int, int]:
    if not jobs:
        return 0, 0

    inserted_total = 0
    updated_total = 0

    for batch in _chunked(jobs, size=1000):
        inserted_rows, updated_rows = _upsert_jobs_batch(session, batch)
        inserted_total += inserted_rows
        updated_total += updated_rows

    return inserted_total, updated_total


def _upsert_jobs_batch(session: Session, jobs: Sequence[CleanJob]) -> tuple[int, int]:
    keys = [(job.source, job.external_id) for job in jobs]
    existing_key_rows = session.execute(
        select(Job.source, Job.external_id).where(tuple_(Job.source, Job.external_id).in_(keys))
    ).all()
    existing_keys = {(row.source, row.external_id) for row in existing_key_rows}

    inserted_rows = sum(1 for key in keys if key not in existing_keys)
    updated_rows = len(keys) - inserted_rows

    payload = [
        {
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
            "published_at": job.published_at,
            "url": job.url,
            "description": job.description,
            "fingerprint": job.fingerprint,
        }
        for job in jobs
    ]

    stmt = insert(Job).values(payload)
    excluded = stmt.excluded
    update_map = {
        "title": excluded.title,
        "role_family": excluded.role_family,
        "company": excluded.company,
        "location": excluded.location,
        "country": excluded.country,
        "city": excluded.city,
        "employment_type": excluded.employment_type,
        "remote_type": excluded.remote_type,
        "salary_currency": excluded.salary_currency,
        "salary_from": excluded.salary_from,
        "salary_to": excluded.salary_to,
        "salary_usd_from": excluded.salary_usd_from,
        "salary_usd_to": excluded.salary_usd_to,
        "published_at": excluded.published_at,
        "url": excluded.url,
        "description": excluded.description,
        "fingerprint": excluded.fingerprint,
        "updated_at": func.now(),
    }

    upsert_stmt = stmt.on_conflict_do_update(
        index_elements=[Job.source, Job.external_id],
        set_=update_map,
    )
    session.execute(upsert_stmt)

    id_rows = session.execute(
        select(Job.id, Job.source, Job.external_id).where(tuple_(Job.source, Job.external_id).in_(keys))
    ).all()
    id_map = {(row.source, row.external_id): row.id for row in id_rows}

    _replace_job_skills(session, jobs, id_map)

    return inserted_rows, updated_rows


def _replace_job_skills(session: Session, jobs: Sequence[CleanJob], id_map: dict[tuple[str, str], int]) -> None:
    skill_names = sorted({skill for job in jobs for skill in job.skills})
    if not skill_names:
        return

    existing = session.execute(select(Skill.name).where(Skill.name.in_(skill_names))).scalars().all()
    existing_set = set(existing)
    missing = [name for name in skill_names if name not in existing_set]

    if missing:
        stmt = insert(Skill).values([{"name": name} for name in missing])
        session.execute(stmt.on_conflict_do_nothing(index_elements=[Skill.name]))

    skill_rows = session.execute(select(Skill.id, Skill.name).where(Skill.name.in_(skill_names))).all()
    skill_map = {row.name: row.id for row in skill_rows}

    job_ids = [id_map[(job.source, job.external_id)] for job in jobs if (job.source, job.external_id) in id_map]
    if not job_ids:
        return

    session.execute(delete(job_skills).where(job_skills.c.job_id.in_(job_ids)))

    associations: list[dict[str, int]] = []
    for job in jobs:
        job_id = id_map.get((job.source, job.external_id))
        if job_id is None:
            continue
        for skill in job.skills:
            skill_id = skill_map.get(skill)
            if skill_id is not None:
                associations.append({"job_id": job_id, "skill_id": skill_id})

    for associations_batch in _chunked(associations, size=5000):
        if not associations_batch:
            continue
        stmt = insert(job_skills).values(associations_batch)
        session.execute(stmt.on_conflict_do_nothing(index_elements=[job_skills.c.job_id, job_skills.c.skill_id]))


def list_jobs(
    session: Session,
    page: int,
    page_size: int,
    role_family: str | None = None,
    source: str | None = None,
    search: str | None = None,
) -> tuple[list[Job], int]:
    conditions = []
    if role_family:
        conditions.append(Job.role_family == role_family)
    if source:
        conditions.append(Job.source == source)
    if search:
        pattern = f"%{search.lower()}%"
        conditions.append(func.lower(Job.title).like(pattern))

    stmt = select(Job)
    count_stmt = select(func.count()).select_from(Job)

    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = session.execute(count_stmt).scalar_one()

    jobs = session.execute(
        stmt.order_by(desc(Job.published_at).nullslast(), desc(Job.id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).scalars().all()

    return jobs, int(total)


def get_overview_metrics(
    session: Session,
    role_family: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    salary_mid = (func.coalesce(Job.salary_usd_from, Job.salary_usd_to) + func.coalesce(Job.salary_usd_to, Job.salary_usd_from)) / 2
    conditions = _metric_conditions(role_family, source)

    totals_stmt = select(
        func.count(Job.id),
        func.count(func.distinct(Job.company)),
        func.count(func.distinct(Job.title)),
        func.count(func.distinct(Job.location)),
        func.avg(salary_mid),
        func.percentile_cont(literal(0.5)).within_group(salary_mid),
    )
    for condition in conditions:
        totals_stmt = totals_stmt.where(condition)

    totals = session.execute(totals_stmt).one()

    role_stmt = select(Job.role_family, func.count(Job.id).label("jobs_count")).group_by(Job.role_family)
    for condition in conditions:
        role_stmt = role_stmt.where(condition)

    role_counts_rows = session.execute(role_stmt).all()
    top_employer_stmt = select(Job.company, func.count(Job.id).label("jobs_count")).group_by(Job.company).order_by(desc("jobs_count")).limit(1)
    for condition in conditions:
        top_employer_stmt = top_employer_stmt.where(condition)

    top_employer_row = session.execute(top_employer_stmt).first()

    role_counts = {row.role_family: int(row.jobs_count) for row in role_counts_rows}

    return {
        "total_jobs": int(totals[0] or 0),
        "total_companies": int(totals[1] or 0),
        "unique_titles": int(totals[2] or 0),
        "total_locations": int(totals[3] or 0),
        "avg_salary_usd": round(float(totals[4]), 2) if totals[4] is not None else None,
        "median_salary_usd": round(float(totals[5]), 2) if totals[5] is not None else None,
        "top_employer": top_employer_row.company if top_employer_row is not None else None,
        "top_employer_jobs": int(top_employer_row.jobs_count) if top_employer_row is not None else 0,
        "role_counts": role_counts,
    }


def get_skill_metrics(
    session: Session,
    limit: int = 20,
    role_family: str | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    conditions = _metric_conditions(role_family, source)
    stmt = (
        select(Skill.name, func.count(job_skills.c.job_id).label("jobs_count"))
        .join(job_skills, job_skills.c.skill_id == Skill.id)
        .join(Job, Job.id == job_skills.c.job_id)
        .group_by(Skill.id)
        .order_by(desc("jobs_count"))
        .limit(limit)
    )
    for condition in conditions:
        stmt = stmt.where(condition)

    rows = session.execute(stmt).all()

    return [{"skill": row.name, "count": int(row.jobs_count)} for row in rows]


def get_salary_band_metrics(
    session: Session,
    role_family: str | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    salary_mid = (func.coalesce(Job.salary_usd_from, Job.salary_usd_to) + func.coalesce(Job.salary_usd_to, Job.salary_usd_from)) / 2
    conditions = _metric_conditions(role_family, source)
    band = case(
        (salary_mid < 1000, "under_1k"),
        (salary_mid < 2000, "1k_to_2k"),
        (salary_mid < 4000, "2k_to_4k"),
        else_="4k_plus",
    )

    stmt = (
        select(band.label("band"), func.count(Job.id).label("jobs_count"))
        .where(salary_mid.is_not(None))
        .group_by(band)
        .order_by(desc("jobs_count"))
    )
    for condition in conditions:
        stmt = stmt.where(condition)

    rows = session.execute(stmt).all()

    return [{"band": row.band, "count": int(row.jobs_count)} for row in rows]


def get_location_metrics(
    session: Session,
    limit: int = 15,
    role_family: str | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    conditions = _metric_conditions(role_family, source)
    location_label = func.coalesce(func.nullif(Job.city, ""), Job.location).label("location_label")
    stmt = (
        select(location_label, Job.country, func.count(Job.id).label("jobs_count"))
        .group_by(location_label, Job.country)
        .order_by(desc("jobs_count"))
        .limit(limit)
    )
    for condition in conditions:
        stmt = stmt.where(condition)

    rows = session.execute(stmt).all()

    return [
        {
            "location": row.location_label,
            "country": row.country,
            "count": int(row.jobs_count),
        }
        for row in rows
    ]


def get_employer_metrics(
    session: Session,
    limit: int = 12,
    role_family: str | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    conditions = _metric_conditions(role_family, source)
    stmt = (
        select(Job.company, func.count(Job.id).label("jobs_count"))
        .group_by(Job.company)
        .order_by(desc("jobs_count"))
        .limit(limit)
    )
    for condition in conditions:
        stmt = stmt.where(condition)

    rows = session.execute(stmt).all()
    return [{"company": row.company, "count": int(row.jobs_count)} for row in rows if row.company]


def get_timeline_metrics(
    session: Session,
    role_family: str | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    conditions = _metric_conditions(role_family, source)
    stmt = (
        select(func.date_trunc("week", Job.published_at).label("bucket"), func.count(Job.id).label("jobs_count"))
        .where(Job.published_at.is_not(None))
        .group_by("bucket")
        .order_by("bucket")
    )
    for condition in conditions:
        stmt = stmt.where(condition)

    rows = session.execute(stmt).all()

    return [{"week": row.bucket.isoformat(), "count": int(row.jobs_count)} for row in rows if row.bucket is not None]
