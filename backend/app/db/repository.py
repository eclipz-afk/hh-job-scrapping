from collections.abc import Sequence
from typing import Any

from sqlalchemy import case, delete, desc, func, literal, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.db.models import Job, Skill, job_skills
from app.etl.cleaning import CURRENCY_RATE_DATE, CURRENCY_RATE_SOURCE
from app.etl.roles import role_category
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


def _salary_midpoint():
    """Use the known salary bound when the other bound is absent."""
    lower_salary = func.coalesce(Job.salary_usd_from, Job.salary_usd_to)
    upper_salary = func.coalesce(Job.salary_usd_to, Job.salary_usd_from)
    return (lower_salary + upper_salary) / 2


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
        select(Job.id, Job.source, Job.external_id).where(
            tuple_(Job.source, Job.external_id).in_(keys)
        )
    ).all()
    id_map = {(row.source, row.external_id): row.id for row in id_rows}

    _replace_job_skills(session, jobs, id_map)

    return inserted_rows, updated_rows


def _replace_job_skills(
    session: Session, jobs: Sequence[CleanJob], id_map: dict[tuple[str, str], int]
) -> None:
    skill_names = sorted({skill for job in jobs for skill in job.skills})
    if not skill_names:
        return

    existing = (
        session.execute(select(Skill.name).where(Skill.name.in_(skill_names))).scalars().all()
    )
    existing_set = set(existing)
    missing = [name for name in skill_names if name not in existing_set]

    if missing:
        stmt = insert(Skill).values([{"name": name} for name in missing])
        session.execute(stmt.on_conflict_do_nothing(index_elements=[Skill.name]))

    skill_rows = session.execute(
        select(Skill.id, Skill.name).where(Skill.name.in_(skill_names))
    ).all()
    skill_map = {row.name: row.id for row in skill_rows}

    job_ids = []
    for job in jobs:
        job_id = id_map.get((job.source, job.external_id))
        if job_id is not None:
            job_ids.append(job_id)
    if not job_ids:
        return

    session.execute(delete(job_skills).where(job_skills.c.job_id.in_(job_ids)))

    associations = []
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
        session.execute(
            stmt.on_conflict_do_nothing(index_elements=[job_skills.c.job_id, job_skills.c.skill_id])
        )


def list_jobs(
    session: Session,
    page: int,
    page_size: int,
    role_family: str | None = None,
    source: str | None = None,
    search: str | None = None,
    skill: str | None = None,
    company: str | None = None,
    location: str | None = None,
    country: str | None = None,
    category: str | None = None,
) -> tuple[list[Job], int]:
    conditions = _metric_conditions(role_family, source)
    if search:
        pattern = f"%{search.lower()}%"
        conditions.append(
            func.lower(Job.title).like(pattern) | func.lower(Job.company).like(pattern)
        )
    if skill:
        conditions.append(Job.skills.any(Skill.name == skill))
    if company:
        conditions.append(Job.company == company)
    if location:
        location_label = func.coalesce(func.nullif(Job.city, ""), Job.location)
        conditions.append(location_label == location)
    if country:
        conditions.append(Job.country == country)
    if category:
        category_query = select(Job.title, Job.role_family).where(*conditions).distinct()
        category_keys = []
        for title, family in session.execute(category_query):
            if role_category(title, family) == category:
                category_keys.append((title, family))
        conditions.append(tuple_(Job.title, Job.role_family).in_(category_keys))

    stmt = select(Job).options(selectinload(Job.skills))
    count_stmt = select(func.count()).select_from(Job)

    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = session.execute(count_stmt).scalar_one()

    jobs = (
        session.execute(
            stmt.order_by(desc(Job.published_at).nullslast(), desc(Job.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    return jobs, int(total)


def get_overview_metrics(
    session: Session,
    role_family: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    salary_mid = _salary_midpoint()
    conditions = _metric_conditions(role_family, source)

    totals_stmt = select(
        func.count(Job.id).label("total_jobs"),
        func.count(func.distinct(Job.company)).label("total_companies"),
        func.count(func.distinct(Job.title)).label("unique_titles"),
        func.count(func.distinct(Job.location)).label("total_locations"),
        func.avg(salary_mid).label("avg_salary_usd"),
        func.percentile_cont(literal(0.5)).within_group(salary_mid).label("median_salary_usd"),
        func.count(salary_mid).label("salary_jobs"),
        func.max(Job.created_at).label("last_collected_at"),
    )
    for condition in conditions:
        totals_stmt = totals_stmt.where(condition)

    totals = session.execute(totals_stmt).one()

    average_salary = None
    if totals.avg_salary_usd is not None:
        average_salary = round(float(totals.avg_salary_usd), 2)
    median_salary = None
    if totals.median_salary_usd is not None:
        median_salary = round(float(totals.median_salary_usd), 2)

    last_collected_at = None
    if totals.last_collected_at:
        last_collected_at = totals.last_collected_at.isoformat()

    return {
        "total_jobs": int(totals.total_jobs or 0),
        "total_companies": int(totals.total_companies or 0),
        "unique_titles": int(totals.unique_titles or 0),
        "total_locations": int(totals.total_locations or 0),
        "avg_salary_usd": average_salary,
        "median_salary_usd": median_salary,
        "salary_jobs": int(totals.salary_jobs or 0),
        "salary_rate_date": CURRENCY_RATE_DATE,
        "salary_rate_source": CURRENCY_RATE_SOURCE,
        "last_collected_at": last_collected_at,
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
        .order_by(desc("jobs_count"), Skill.name)
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
    salary_mid = _salary_midpoint()
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


def get_role_metrics(
    session: Session, role_family: str | None = None, source: str | None = None
) -> list[dict[str, Any]]:
    stmt = select(Job.title, Job.role_family, func.count(Job.id).label("jobs_count")).group_by(
        Job.title, Job.role_family
    )
    for condition in _metric_conditions(role_family, source):
        stmt = stmt.where(condition)
    category_counts = {}
    for row in session.execute(stmt):
        category = role_category(row.title, row.role_family)
        category_key = (category, row.role_family)
        category_counts[category_key] = category_counts.get(category_key, 0) + int(row.jobs_count)

    sorted_categories = sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))
    metrics = []
    for (category, role_family), job_count in sorted_categories:
        metrics.append({"category": category, "role_family": role_family, "count": job_count})
    return metrics
