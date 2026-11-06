from __future__ import annotations

import hashlib
import re
from typing import Iterable

from app.etl.types import CleanJob, RawJob


ROLE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "data_science": (
        "data scientist",
        "data science",
        "machine learning",
        "ml engineer",
        "ai engineer",
        "nlp",
        "computer vision",
        "data engineer",
        "bi analyst",
        "sql analyst",
        "data analyst",
        "data analytics",
        "дата",
        "машинн",
        "аналитик данных",
        "ml",
        "ai",
    ),
    "it": (
        "software",
        "backend",
        "frontend",
        "fullstack",
        "devops",
        "cloud",
        "sre",
        "qa",
        "tester",
        "mobile",
        "android",
        "ios",
        "developer",
        "programmer",
        "system analyst",
        "business analyst",
        "разработчик",
        "инженер",
        "тестировщик",
        "девопс",
        "системный аналитик",
        "бизнес аналитик",
    ),
}

SKILL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("python", re.compile(r"\bpython\b", flags=re.IGNORECASE)),
    ("sql", re.compile(r"\bsql\b", flags=re.IGNORECASE)),
    ("postgresql", re.compile(r"\bpostgres(?:ql)?\b", flags=re.IGNORECASE)),
    ("docker", re.compile(r"\bdocker\b", flags=re.IGNORECASE)),
    ("kubernetes", re.compile(r"\bkubernetes\b|\bk8s\b", flags=re.IGNORECASE)),
    ("aws", re.compile(r"\baws\b|\bamazon web services\b", flags=re.IGNORECASE)),
    ("gcp", re.compile(r"\bgcp\b|\bgoogle cloud\b", flags=re.IGNORECASE)),
    ("azure", re.compile(r"\bazure\b", flags=re.IGNORECASE)),
    ("flask", re.compile(r"\bflask\b", flags=re.IGNORECASE)),
    ("django", re.compile(r"\bdjango\b", flags=re.IGNORECASE)),
    ("fastapi", re.compile(r"\bfastapi\b", flags=re.IGNORECASE)),
    ("spark", re.compile(r"\bspark\b", flags=re.IGNORECASE)),
    ("hadoop", re.compile(r"\bhadoop\b", flags=re.IGNORECASE)),
    ("airflow", re.compile(r"\bairflow\b", flags=re.IGNORECASE)),
    ("tableau", re.compile(r"\btableau\b", flags=re.IGNORECASE)),
    ("power bi", re.compile(r"\bpower[\s-]?bi\b", flags=re.IGNORECASE)),
    ("tensorflow", re.compile(r"\btensorflow\b", flags=re.IGNORECASE)),
    ("pytorch", re.compile(r"\bpytorch\b", flags=re.IGNORECASE)),
    ("scikit-learn", re.compile(r"\bscikit[-\s]?learn\b|\bsklearn\b", flags=re.IGNORECASE)),
    ("pandas", re.compile(r"\bpandas\b", flags=re.IGNORECASE)),
    ("numpy", re.compile(r"\bnumpy\b", flags=re.IGNORECASE)),
    ("javascript", re.compile(r"\bjavascript\b", flags=re.IGNORECASE)),
    ("typescript", re.compile(r"\btypescript\b", flags=re.IGNORECASE)),
    ("react", re.compile(r"\breact\b", flags=re.IGNORECASE)),
    ("vue", re.compile(r"\bvue(?:\.js)?\b", flags=re.IGNORECASE)),
    ("node", re.compile(r"\bnode(?:\.js)?\b", flags=re.IGNORECASE)),
    ("java", re.compile(r"\bjava\b", flags=re.IGNORECASE)),
    ("golang", re.compile(r"\bgolang\b|\bgo\s+(?:developer|engineer)\b", flags=re.IGNORECASE)),
    ("c++", re.compile(r"c\+\+", flags=re.IGNORECASE)),
    ("redis", re.compile(r"\bredis\b", flags=re.IGNORECASE)),
    ("elasticsearch", re.compile(r"\belasticsearch\b", flags=re.IGNORECASE)),
    ("git", re.compile(r"\bgit\b", flags=re.IGNORECASE)),
    ("linux", re.compile(r"\blinux\b", flags=re.IGNORECASE)),
)

CURRENCY_TO_USD: dict[str, float] = {
    "USD": 1.0,
    "EUR": 1.09,
    "RUR": 0.011,
    "RUB": 0.011,
    "KZT": 0.0022,
    "BYR": 0.31,
    "BYN": 0.31,
    "UAH": 0.025,
    "GBP": 1.26,
}

_WHITESPACE_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9а-яё]+", flags=re.IGNORECASE)


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    compact = _WHITESPACE_RE.sub(" ", text)
    return compact.strip()


def classify_role(title: str, description: str) -> str:
    haystack = f"{title} {description}".lower()
    scores = {"data_science": 0, "it": 0}
    for role, keywords in ROLE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in haystack:
                scores[role] += 1

    if scores["data_science"] > 0 and scores["data_science"] >= scores["it"]:
        return "data_science"
    return "it"


def extract_skills(title: str, description: str) -> list[str]:
    haystack = f"{title} {description}".lower()
    found = [skill for skill, pattern in SKILL_PATTERNS if pattern.search(haystack)]
    return sorted(set(found))


def to_usd(value: float | None, currency: str | None) -> float | None:
    if value is None:
        return None
    if not currency:
        return None
    rate = CURRENCY_TO_USD.get(currency.upper())
    if rate is None:
        return None
    return round(value * rate, 2)


def build_fingerprint(source: str, title: str, company: str, location: str) -> str:
    normalized = "|".join(
        [
            source.lower(),
            _NON_ALNUM_RE.sub("", title.lower()),
            _NON_ALNUM_RE.sub("", company.lower()),
            _NON_ALNUM_RE.sub("", location.lower()),
        ]
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def clean_raw_job(raw: RawJob) -> CleanJob | None:
    title = normalize_text(raw.title)
    company = normalize_text(raw.company)
    location = normalize_text(raw.location)
    description = normalize_text(raw.description)

    if not title or not company or not location:
        return None

    role_family = classify_role(title, description)
    skills = extract_skills(title, description)
    salary_currency = raw.salary_currency.upper() if raw.salary_currency else None

    return CleanJob(
        source=raw.source,
        external_id=str(raw.external_id),
        title=title,
        role_family=role_family,
        company=company,
        location=location,
        country=normalize_text(raw.country or "unknown") or "unknown",
        city=normalize_text(raw.city) or None,
        employment_type=normalize_text(raw.employment_type) or None,
        remote_type=normalize_text(raw.remote_type) or None,
        salary_currency=salary_currency,
        salary_from=raw.salary_from,
        salary_to=raw.salary_to,
        salary_usd_from=to_usd(raw.salary_from, salary_currency),
        salary_usd_to=to_usd(raw.salary_to, salary_currency),
        published_at=raw.published_at,
        url=raw.url,
        description=description or None,
        fingerprint=build_fingerprint(raw.source, title, company, location),
        skills=skills,
    )


def deduplicate_jobs(jobs: Iterable[CleanJob]) -> list[CleanJob]:
    seen: set[str] = set()
    unique_jobs: list[CleanJob] = []
    for job in jobs:
        key = f"{job.source}:{job.external_id}"
        if key in seen:
            continue
        seen.add(key)
        unique_jobs.append(job)
    return unique_jobs
