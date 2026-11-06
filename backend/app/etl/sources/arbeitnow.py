from __future__ import annotations

import re
from typing import Any

import requests

from app.etl.sources.base import parse_datetime
from app.etl.types import RawJob


_TAG_RE = re.compile(r"<[^>]+>")


class ArbeitnowSource:
    name = "arbeitnow"
    base_url = "https://www.arbeitnow.com/api/job-board-api"

    def __init__(self, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_jobs(self, target_rows: int, max_pages: int) -> list[RawJob]:
        headers = {"User-Agent": "job-analytics-dashboard/1.0"}
        results: list[RawJob] = []

        with requests.Session() as client:
            client.headers.update(headers)
            client.trust_env = False
            for page in range(1, max_pages + 1):
                if len(results) >= target_rows:
                    break

                params = {"page": page}
                try:
                    response = client.get(self.base_url, params=params, timeout=self.timeout_seconds, allow_redirects=False)
                    response.raise_for_status()
                    payload = response.json()
                except requests.RequestException:
                    break

                items = payload.get("data") or []
                if not items:
                    break

                for item in items:
                    parsed = self._parse_item(item)
                    if parsed is not None:
                        results.append(parsed)

        return results

    def _parse_item(self, item: dict[str, Any]) -> RawJob | None:
        external_id = item.get("slug") or item.get("title")
        title = item.get("title")
        company = item.get("company_name") or "Unknown"
        location = item.get("location") or "Remote"

        if not external_id or not title:
            return None

        tags = item.get("tags") or []
        description = self._strip_html(item.get("description") or "")
        tags_text = ", ".join(str(tag) for tag in tags)
        merged_description = f"{description} {tags_text}".strip()
        job_types = item.get("job_types") or []

        remote_type = "Remote" if "remote" in location.lower() else "On-site"

        return RawJob(
            source=self.name,
            external_id=str(external_id),
            title=str(title),
            company=str(company),
            location=str(location),
            country="Global",
            city=None,
            employment_type=job_types[0] if job_types else None,
            remote_type=remote_type,
            salary_from=None,
            salary_to=None,
            salary_currency=None,
            published_at=parse_datetime(item.get("created_at")),
            url=item.get("url") or "https://www.arbeitnow.com/",
            description=merged_description or None,
        )

    @staticmethod
    def _strip_html(value: str) -> str:
        cleaned = _TAG_RE.sub(" ", value)
        return re.sub(r"\s+", " ", cleaned).strip()
