from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class RawJob:
    source: str
    external_id: str
    title: str
    company: str
    location: str
    country: str
    city: str | None
    employment_type: str | None
    remote_type: str | None
    salary_from: float | None
    salary_to: float | None
    salary_currency: str | None
    published_at: datetime | None
    url: str
    description: str | None


@dataclass(slots=True)
class CleanJob:
    source: str
    external_id: str
    title: str
    role_family: str
    company: str
    location: str
    country: str
    city: str | None
    employment_type: str | None
    remote_type: str | None
    salary_currency: str | None
    salary_from: float | None
    salary_to: float | None
    salary_usd_from: float | None
    salary_usd_to: float | None
    published_at: datetime | None
    url: str
    description: str | None
    fingerprint: str
    skills: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EtlResult:
    requested_target: int
    scraped_rows: int
    cleaned_rows: int
    inserted_rows: int
    updated_rows: int
    skipped_rows: int
    source_rows: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
