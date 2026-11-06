from __future__ import annotations

from sqlalchemy import text

from app.core.config import Settings
from app.db.base import session_scope
from app.db.repository import upsert_jobs
from app.etl.cleaning import clean_raw_job, deduplicate_jobs
from app.etl.sources.arbeitnow import ArbeitnowSource
from app.etl.sources.hh import HHSource
from app.etl.types import CleanJob, EtlResult, RawJob


class EtlAlreadyRunning(RuntimeError):
    pass


class JobETLPipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sources = [
            HHSource(timeout_seconds=settings.request_timeout_seconds),
            ArbeitnowSource(timeout_seconds=settings.request_timeout_seconds),
        ]

    def run(self, target_rows: int | None = None) -> EtlResult:
        requested = self.settings.target_cleaned_rows if target_rows is None else target_rows
        if type(requested) is not int or not 1 <= requested <= 10000:
            raise ValueError("target_rows must be between 1 and 10000")
        # A transaction lock prevents concurrent ingestion across workers/containers.
        with session_scope() as session:
            acquired = session.execute(text("SELECT pg_try_advisory_xact_lock(726194203)")).scalar_one()
            if not acquired:
                raise EtlAlreadyRunning()
            return self._run_locked(requested, session)

    def _run_locked(self, requested: int, session) -> EtlResult:
        fetch_target = max(requested * 2, 2000)

        raw_jobs, source_rows = self._scrape(fetch_target)
        cleaned_jobs = self._clean(raw_jobs)
        notes: list[str] = []

        if len(cleaned_jobs) > requested:
            cleaned_jobs = cleaned_jobs[:requested]
        if len(cleaned_jobs) < requested:
            notes.append(
                f"Cleaned rows ({len(cleaned_jobs)}) are below target ({requested}). "
                "Increase MAX_SOURCE_PAGES or add more sources."
            )

        inserted_rows, updated_rows = upsert_jobs(session, cleaned_jobs)

        return EtlResult(
            requested_target=requested,
            scraped_rows=len(raw_jobs),
            cleaned_rows=len(cleaned_jobs),
            inserted_rows=inserted_rows,
            updated_rows=updated_rows,
            skipped_rows=max(len(raw_jobs) - len(cleaned_jobs), 0),
            source_rows=source_rows,
            notes=notes,
        )

    def _scrape(self, target_rows: int) -> tuple[list[RawJob], dict[str, int]]:
        per_source_target = max(target_rows // max(len(self.sources), 1), 1000)
        rows: list[RawJob] = []
        source_rows: dict[str, int] = {}

        for source in self.sources:
            fetched = source.fetch_jobs(
                target_rows=per_source_target,
                max_pages=self.settings.max_source_pages,
            )
            rows.extend(fetched)
            source_rows[source.name] = len(fetched)

        return rows, source_rows

    def _clean(self, rows: list[RawJob]) -> list[CleanJob]:
        cleaned: list[CleanJob] = []
        for row in rows:
            parsed = clean_raw_job(row)
            if parsed is not None:
                cleaned.append(parsed)

        return deduplicate_jobs(cleaned)
